from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import re
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets
from PIL import Image

from app.config import Settings
from app.schemas.models import (
    CancelResponse,
    GenerateRequest,
    GenerationDetails,
    IdentityUsage,
    JobListResponse,
    JobStatus,
    JobView,
    ReferenceUsage,
    ResultInfo,
)
from app.services.comfy_client import ComfyClient
from app.services.comfy_launcher import ComfyLauncher
from app.services.errors import (
    ComfyExecutionError,
    JobConflictError,
    JobNotFoundError,
    ModelMissingError,
    PixelForgeError,
    QueueFullError,
    ReferenceCompatibilityError,
    VramError,
)
from app.services.model_catalog import is_sdxl_compatible
from app.services.model_downloads import lora_trigger
from app.services.outputs import (
    build_generation_details,
    image_result_info,
    load_metadata,
    reference_result_info,
    result_info,
    save_candidate_original,
    save_image_result,
    save_metadata,
    save_original,
    save_pixel_result,
)
from app.services.postprocess import PostProcessResult, postprocess_image
from app.services.prompt_engine import build_prompt_plan_async
from app.services.references import (
    get_identity_capabilities,
    get_reference_capabilities,
    resolve_reference_assets,
    usage_from_asset,
)
from app.services.translator import Translator

logger = logging.getLogger("pixelforge.jobs")

_TERMINAL_STATUSES = {JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.CANCELLED}


@dataclass
class Job:
    id: str
    request: GenerateRequest
    status: JobStatus = JobStatus.QUEUED
    stage_message: str = "대기 중..."
    progress: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    seed_used: int | None = None
    base_seed: int | None = None
    prompt_original: str | None = None
    prompt_used: str | None = None
    prompt_translated: bool = False
    negative_used: str | None = None
    prompt_plan: dict[str, Any] | None = None
    comfy_prompt_id: str | None = None
    step: int = 0
    total_steps: int = 0
    candidate_count: int = 1
    candidate_index: int = 0
    candidate_scores: list[float] = field(default_factory=list)
    candidate_summaries: list[dict[str, Any]] = field(default_factory=list)
    candidate_prompt_ids: list[str] = field(default_factory=list)
    result: ResultInfo | None = None
    error: str | None = None
    error_code: str | None = None
    cancel_requested: bool = False
    warnings: list[str] = field(default_factory=list)
    background_removed_ratio: float = 0.0
    palette_used: int = 0
    postprocess_mode: str = "quantize"
    # Resolved once per job so a settings change cannot swap models mid-job.
    checkpoint: str = ""
    lora: str | None = None
    # Reference page: ComfyUI input filenames and the metadata shown in results.
    reference_files: list[str] = field(default_factory=list)
    reference_usage: list[ReferenceUsage] = field(default_factory=list)
    reference_face_available: bool = False
    # Face identity (InstantID / PuLID): resolved model files and the uploaded
    # identity image name inside ComfyUI's input folder.
    identity_image_file: str = ""
    identity_model_file: str = ""
    identity_controlnet_file: str = ""
    identity_pulid_file: str = ""


class JobManager:
    """Single-GPU job queue. Only one ComfyUI prompt runs at a time."""

    def __init__(
        self,
        settings: Settings,
        comfy: ComfyClient,
        launcher: ComfyLauncher,
        translator: Translator | None = None,
    ):
        self.settings = settings
        self.comfy = comfy
        self.launcher = launcher
        self.translator = translator
        self.jobs: dict[str, Job] = {}
        self._pending: deque[str] = deque()
        self._active_id: str | None = None
        self._condition = asyncio.Condition()
        self._worker_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._load_persisted_jobs()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop(), name="pixelforge-job-worker")

    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        if self._active_id:
            await self.comfy.interrupt()

    async def submit(self, request: GenerateRequest) -> JobView:
        async with self._condition:
            if len(self._pending) >= self.settings.jobs.max_pending:
                raise QueueFullError(
                    f"대기 중인 작업이 너무 많습니다. 현재 작업이 끝난 뒤 다시 시도해 주세요. (최대 대기 {self.settings.jobs.max_pending}개)"
                )
            job_id = uuid.uuid4().hex[:12]
            while job_id in self.jobs:
                job_id = uuid.uuid4().hex[:12]
            seed = request.seed if request.seed is not None else random.randint(0, 4_294_967_295)
            job = Job(
                id=job_id,
                request=request,
                seed_used=seed,
                postprocess_mode=request.postprocess,
                total_steps=request.steps,
            )
            self.jobs[job_id] = job
            self._pending.append(job_id)
            self._condition.notify()
            position = self._queue_position(job_id)
            self._persist(job)
            logger.info("Job %s queued (position=%s, seed=%s)", job_id, position, seed)
            return self._view(job)

    def get(self, job_id: str) -> JobView:
        job = self.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError("작업을 찾을 수 없습니다. 서버가 재시작되었거나 잘못된 작업 ID입니다.")
        return self._view(job)

    async def cancel(self, job_id: str) -> CancelResponse:
        job = self.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError("작업을 찾을 수 없습니다.")
        if job.status in {JobStatus.COMPLETED, JobStatus.ERROR, JobStatus.CANCELLED}:
            raise JobConflictError("이미 종료된 작업은 취소할 수 없습니다.")

        job.cancel_requested = True
        if job.status == JobStatus.QUEUED:
            async with self._condition:
                with contextlib.suppress(ValueError):
                    self._pending.remove(job_id)
                self._condition.notify_all()
            job.status = JobStatus.CANCELLED
            job.stage_message = "취소됨"
            job.completed_at = datetime.now(timezone.utc)
            self._persist(job)
            logger.info("Job %s cancelled while queued", job_id)
            return CancelResponse(job_id=job_id, status=job.status, message="대기 중인 작업을 취소했습니다.")

        job.stage_message = "취소 요청 중..."
        await self.comfy.interrupt()
        if job.comfy_prompt_id:
            await self.comfy.delete_queue_items([job.comfy_prompt_id])
        logger.info("Job %s cancel requested while running", job_id)
        return CancelResponse(
            job_id=job_id,
            status=job.status,
            message="생성 취소를 요청했습니다. GPU 작업이 중단되는 즉시 취소됩니다.",
        )

    def queue_counts(self) -> tuple[int, int]:
        return (1 if self._active_id else 0, len(self._pending))

    def is_busy(self, job_id: str) -> bool:
        """True while the job is running or waiting in the queue."""
        return self._active_id == job_id or job_id in self._pending

    def active_job(self) -> JobView | None:
        if not self._active_id:
            return None
        job = self.jobs.get(self._active_id)
        return self._view(job) if job else None

    def list_recent(self, limit: int = 20, kind: str | None = None) -> JobListResponse:
        jobs = [
            job
            for job in self.jobs.values()
            if kind is None or job.request.kind == kind
        ]
        jobs.sort(
            key=lambda job: (
                job.status not in _TERMINAL_STATUSES,
                job.created_at,
            ),
            reverse=True,
        )
        active, pending = self.queue_counts()
        return JobListResponse(
            items=[self._view(job) for job in jobs[: max(1, limit)]],
            active=active,
            pending=pending,
        )

    def forget(self, job_id: str) -> None:
        """Drop a finished job from history after its output is deleted."""
        job = self.jobs.get(job_id)
        if job is not None and job.status not in _TERMINAL_STATUSES:
            return
        self.jobs.pop(job_id, None)
        try:
            (self.settings.jobs_dir / f"{job_id}.json").unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove job history for %s", job_id, exc_info=True)

    def _persist(self, job: Job) -> None:
        try:
            directory = self.settings.jobs_dir
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{job.id}.json"
            temporary = path.with_suffix(".json.tmp")
            payload = self._view(job).model_dump(mode="json")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        except Exception:
            logger.warning("Could not persist job %s", job.id, exc_info=True)

    def _load_persisted_jobs(self) -> None:
        directory = self.settings.jobs_dir
        if not directory.exists():
            return
        limit = max(1, int(self.settings.jobs.history_limit))
        files = sorted(
            directory.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                view = JobView.model_validate(data)
            except Exception:
                logger.debug("Skipping unreadable job history %s", path, exc_info=True)
                continue
            if view.job_id in self.jobs:
                continue
            job = Job(
                id=view.job_id,
                request=view.request,
                status=view.status,
                stage_message=view.stage_message,
                progress=view.progress,
                created_at=view.created_at,
                started_at=view.started_at,
                completed_at=view.completed_at,
                seed_used=view.seed_used,
                base_seed=view.base_seed,
                prompt_original=view.prompt_original,
                prompt_used=view.prompt_used,
                prompt_translated=view.prompt_translated,
                negative_used=view.negative_used,
                prompt_plan=view.prompt_plan.model_dump() if view.prompt_plan else None,
                comfy_prompt_id=view.comfy_prompt_id,
                step=view.step,
                total_steps=view.total_steps,
                result=view.result,
                error=view.error,
                error_code=view.error_code,
                postprocess_mode=view.request.postprocess,
            )
            if job.result is not None and job.result.details is None:
                # Older job snapshots were stored before the inspector existed;
                # rebuild the details from the metadata file so the history
                # entries can show their settings too.
                self._attach_details(job)
            if job.status not in _TERMINAL_STATUSES:
                job.status = JobStatus.CANCELLED
                job.stage_message = "서버 재시작으로 중단됨"
                job.completed_at = datetime.now(timezone.utc)
                job.error_code = "SERVER_RESTART"
                job.progress = min(job.progress, 99)
                self.jobs[job.id] = job
                self._persist(job)
            else:
                self.jobs[job.id] = job
        for path in files[limit:]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not prune job history %s", path, exc_info=True)
        if self.jobs:
            logger.info("Restored %s job history entries", len(self.jobs))

    def _queue_position(self, job_id: str) -> int:
        try:
            return self._pending.index(job_id) + 1
        except ValueError:
            return 0

    def _view(self, job: Job) -> JobView:
        return JobView(
            job_id=job.id,
            status=job.status,
            stage_message=job.stage_message,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            request=job.request,
            seed_used=job.seed_used,
            base_seed=job.base_seed,
            prompt_original=job.prompt_original,
            prompt_used=job.prompt_used,
            prompt_translated=job.prompt_translated,
            negative_used=job.negative_used,
            comfy_prompt_id=job.comfy_prompt_id,
            step=job.step,
            total_steps=job.total_steps,
            queue_position=self._queue_position(job.id) if job.status == JobStatus.QUEUED else 0,
            prompt_plan=job.prompt_plan,  # type: ignore[arg-type]
            result=job.result,
            error=job.error,
            error_code=job.error_code,
        )

    async def _worker_loop(self) -> None:
        while True:
            async with self._condition:
                await self._condition.wait_for(lambda: bool(self._pending))
                job_id = self._pending.popleft()
            job = self.jobs.get(job_id)
            if job is None or job.cancel_requested:
                if job is not None:
                    self._mark_cancelled(job)
                continue
            self._active_id = job_id
            try:
                await self._run_job(job)
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                job.stage_message = "서버 종료로 취소됨"
                job.completed_at = datetime.now(timezone.utc)
                self._persist(job)
                raise
            except Exception:
                logger.exception("Unhandled error while running job %s", job_id)
                if job.status not in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
                    job.status = JobStatus.ERROR
                    job.stage_message = "오류 발생"
                    job.error = "예상하지 못한 서버 오류가 발생했습니다. 로그를 확인해 주세요."
                    job.error_code = "INTERNAL_ERROR"
                    job.completed_at = datetime.now(timezone.utc)
                    self._persist(job)
            finally:
                self._active_id = None

    async def _run_job(self, job: Job) -> None:
        started = time.monotonic()
        ws_task: asyncio.Task | None = None
        is_native = job.request.kind in {"image", "reference"}
        is_reference = job.request.kind == "reference"
        try:
            if job.cancel_requested:
                self._mark_cancelled(job)
                return
            job.started_at = datetime.now(timezone.utc)
            job.status = JobStatus.PREPARING
            job.progress = 3
            job.stage_message = "프롬프트를 처리하는 중..."
            self._persist(job)
            await self._set_prompt(job)

            job.stage_message = "ComfyUI 연결을 확인하는 중..."
            await self.launcher.ensure_running(self.comfy)

            job.stage_message = "모델을 확인하는 중..."
            await self._check_models(job)

            if is_reference:
                job.stage_message = "참고 이미지를 준비하는 중..."
                await self._prepare_references(job)

            job.stage_message = "워크플로를 준비하는 중..."
            requested_candidates = int(
                job.request.candidates or self.settings.generation.default_candidates
            )
            job.candidate_count = (
                1
                if is_native
                else 1
                if job.request.mode == "tile"
                else max(
                    1,
                    min(int(self.settings.generation.max_candidates), requested_candidates),
                )
            )
            job.base_seed = job.seed_used

            job.status = JobStatus.GENERATING
            job.progress = 6
            job.stage_message = "ComfyUI에 생성을 요청하는 중..."
            self._persist(job)
            client_id = uuid.uuid4().hex
            ws_task = asyncio.create_task(self._listen_progress(job, client_id), name=f"comfy-ws-{job.id}")

            candidates: list[dict[str, Any]] = []
            for candidate_index in range(job.candidate_count):
                if job.cancel_requested:
                    self._mark_cancelled(job)
                    return
                job.candidate_index = candidate_index
                candidate_seed = (int(job.base_seed or 0) + candidate_index) & 0xFFFFFFFF
                workflow = self._build_workflow(
                    job, seed=candidate_seed, candidate_index=candidate_index
                )
                job.stage_message = (
                    "이미지를 생성하는 중..."
                    if is_native
                    else f"후보 {candidate_index + 1}/{job.candidate_count} 생성 중..."
                )
                prompt_id = await self.comfy.queue_prompt(workflow, client_id)
                job.comfy_prompt_id = prompt_id
                job.candidate_prompt_ids.append(prompt_id)
                job.progress = 8 + int(78 * candidate_index / job.candidate_count)

                entry = await self._wait_for_completion(job, prompt_id)
                if job.cancel_requested:
                    self._mark_cancelled(job)
                    return

                image_info = self._extract_image(entry)
                if image_info is None:
                    raise ComfyExecutionError(
                        "ComfyUI가 생성 이미지를 반환하지 않았습니다. 워크플로의 SaveImage 노드를 확인해 주세요."
                    )
                filename, subfolder, image_type = image_info
                job.stage_message = (
                    f"후보 {candidate_index + 1}/{job.candidate_count} 이미지를 가져오는 중..."
                )
                image_bytes = await self.comfy.view_image(filename, subfolder, image_type)
                candidate_path = save_candidate_original(
                    self.settings, job.id, candidate_index, image_bytes
                )

                try:
                    with Image.open(candidate_path) as image:
                        image.load()
                        original_image = image.convert("RGB")
                except Exception as exc:
                    raise ComfyExecutionError(
                        "생성된 원본 이미지를 읽을 수 없습니다.",
                        detail=str(exc),
                    ) from exc

                if is_native:
                    candidates.append(
                        {
                            "index": candidate_index,
                            "seed": candidate_seed,
                            "prompt_id": prompt_id,
                            "bytes": image_bytes,
                            "file": candidate_path.name,
                            "result": None,
                        }
                    )
                    job.candidate_scores.append(0.0)
                    job.candidate_summaries.append(
                        {
                            "index": candidate_index,
                            "seed": candidate_seed,
                            "file": candidate_path.name,
                            "status": "ok",
                            "kind": job.request.kind,
                            "size": job.request.image_size,
                            "warnings": [],
                        }
                    )
                    job.progress = 8 + int(78 * (candidate_index + 1) / job.candidate_count)
                    continue

                job.status = JobStatus.POSTPROCESSING
                job.progress = 8 + int(78 * (candidate_index + 0.8) / job.candidate_count)
                job.stage_message = (
                    f"후보 {candidate_index + 1}/{job.candidate_count} 픽셀아트로 변환하는 중..."
                )
                try:
                    result: PostProcessResult = await asyncio.to_thread(
                        postprocess_image,
                        original_image,
                        job.request.output_size,
                        job.request.postprocess,
                        job.request.palette_colors,
                        job.request.transparent,
                        self.settings.generation,
                        job.request.mode,
                        job.request.resize_filter,
                    )
                except Exception as exc:
                    logger.exception(
                        "Job %s candidate %s postprocess failed", job.id, candidate_index
                    )
                    job.candidate_scores.append(-1_000_000.0)
                    job.candidate_summaries.append(
                        {
                            "index": candidate_index,
                            "seed": candidate_seed,
                            "status": "postprocess_error",
                            "error": str(exc),
                        }
                    )
                    job.status = JobStatus.GENERATING
                    continue

                candidates.append(
                    {
                        "index": candidate_index,
                        "seed": candidate_seed,
                        "prompt_id": prompt_id,
                        "bytes": image_bytes,
                        "file": candidate_path.name,
                        "result": result,
                    }
                )
                job.candidate_scores.append(result.candidate_score)
                job.candidate_summaries.append(
                    {
                        "index": candidate_index,
                        "seed": candidate_seed,
                        "file": candidate_path.name,
                        "status": "ok",
                        "score": result.candidate_score,
                        "panel_suspected": result.panel_suspected,
                        "panel_score": round(result.panel_score, 4),
                        "fill": round(result.subject_fill, 4),
                        "components": result.subject_components,
                        "quality_passed": sum(1 for check in result.quality if check.passed),
                        "quality_total": len(result.quality),
                        "warnings": result.warnings,
                    }
                )
                job.progress = 8 + int(78 * (candidate_index + 1) / job.candidate_count)
                job.status = JobStatus.GENERATING

            if not candidates:
                raise ComfyExecutionError(
                    "모든 후보의 후처리에 실패했습니다. 원본 후보 이미지는 outputs/candidates에 보존되어 있습니다."
                )

            if is_native:
                selected = candidates[0]
                job.candidate_index = 0
                job.seed_used = int(selected["seed"])
                job.comfy_prompt_id = str(selected["prompt_id"])
                job.status = JobStatus.POSTPROCESSING
                job.progress = 88
                job.stage_message = "이미지를 저장하는 중..."
                original_path = save_original(self.settings, job.id, selected["bytes"])
                try:
                    with Image.open(original_path) as image:
                        image.load()
                        image_result = image.convert("RGB")
                except Exception as exc:
                    raise ComfyExecutionError(
                        "생성된 이미지를 읽을 수 없습니다.",
                        detail=str(exc),
                    ) from exc
                image_path, preview_path = save_image_result(
                    self.settings, job.id, image_result, job.request.image_size
                )
                details = self._generation_details(
                    job,
                    width=job.request.image_size,
                    height=job.request.image_size,
                    transparent=False,
                    postprocess=None,
                    elapsed_seconds=round(time.monotonic() - started, 2),
                )
                if is_reference:
                    job.result = reference_result_info(
                        self.settings,
                        job.id,
                        job.request.image_size,
                        references=job.reference_usage,
                        identity=self._identity_usage(job),
                        details=details,
                        mode=job.request.mode,
                        candidates_generated=len(candidates),
                        candidate_index=0,
                        warnings=job.warnings,
                    )
                else:
                    job.result = image_result_info(
                        self.settings,
                        job.id,
                        job.request.image_size,
                        job.request.mode,
                        candidates_generated=len(candidates),
                        candidate_index=0,
                        warnings=job.warnings,
                        details=details,
                    )
                job.completed_at = datetime.now(timezone.utc)
                self._save_native_metadata(
                    job, original_path, image_path, preview_path, started
                )
                job.progress = 100
                job.status = JobStatus.COMPLETED
                job.stage_message = "완료"
                self._persist(job)
                logger.info(
                    "%s job %s completed in %.2fs (%sx%s)",
                    job.request.kind.title(),
                    job.id,
                    time.monotonic() - started,
                    job.request.image_size,
                    job.request.image_size,
                )
                return

            selected = max(
                candidates,
                key=lambda item: (
                    item["result"].candidate_score,
                    -item["result"].panel_score,
                    -item["result"].subject_components,
                    -int(item["index"]),
                ),
            )
            result = selected["result"]
            image_bytes = selected["bytes"]
            job.candidate_index = int(selected["index"])
            job.seed_used = int(selected["seed"])
            job.comfy_prompt_id = str(selected["prompt_id"])
            if job.candidate_count > 1:
                result.warnings.insert(
                    0,
                    f"{job.candidate_count}개 후보 중 최선(#{job.candidate_index + 1})을 선택했습니다. "
                    "모든 후보 원본은 outputs/candidates에 보존되어 있습니다.",
                )

            job.status = JobStatus.POSTPROCESSING
            job.progress = 88
            job.stage_message = "선택한 후보를 저장하는 중..."
            original_path = save_original(self.settings, job.id, image_bytes)
            pixel_path, preview_path = save_pixel_result(
                self.settings, job.id, result, job.request.output_size
            )

            cutout_path = self.settings.cutouts_dir / f"{job.id}_cutout.png"
            crop_path = self.settings.crops_dir / f"{job.id}_crop.png"
            if result.cutout is not None:
                result.cutout.save(cutout_path, format="PNG", optimize=True)
            if result.cropped is not None:
                result.cropped.save(crop_path, format="PNG", optimize=True)

            job.warnings = result.warnings
            job.background_removed_ratio = result.background_removed_ratio
            job.palette_used = result.palette_used
            job.result = result_info(
                self.settings,
                job.id,
                result,
                job.request.output_size,
                job.request.postprocess,
                cutout_path if result.cutout is not None else None,
                crop_path if result.cropped is not None else None,
                job.request.mode,
                candidates_generated=len(candidates),
                candidate_index=job.candidate_index,
                details=self._generation_details(
                    job,
                    width=job.request.output_size,
                    height=job.request.output_size,
                    transparent=result.image.mode == "RGBA",
                    postprocess=job.request.postprocess,
                    palette_colors=result.palette_used,
                    elapsed_seconds=round(time.monotonic() - started, 2),
                ),
            )
            job.completed_at = datetime.now(timezone.utc)
            self._save_job_metadata(job, original_path, pixel_path, preview_path, result, started)

            job.progress = 100
            job.status = JobStatus.COMPLETED
            job.stage_message = "완료"
            self._persist(job)
            logger.info(
                "Job %s completed in %.2fs (%sx%s, %s colors)",
                job.id,
                time.monotonic() - started,
                job.request.output_size,
                job.request.output_size,
                result.palette_used,
            )
        except asyncio.CancelledError:
            if job.status not in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
                self._mark_cancelled(job)
            raise
        except PixelForgeError as exc:
            if job.cancel_requested:
                self._mark_cancelled(job)
            else:
                job.status = JobStatus.ERROR
                job.stage_message = "오류 발생"
                job.error = exc.message
                job.error_code = exc.code
                job.completed_at = datetime.now(timezone.utc)
                self._persist(job)
                if exc.detail:
                    logger.error("Job %s failed [%s]: %s | %s", job.id, exc.code, exc.message, exc.detail)
                else:
                    logger.error("Job %s failed [%s]: %s", job.id, exc.code, exc.message)
        except Exception as exc:
            logger.exception("Job %s failed unexpectedly", job.id)
            if job.cancel_requested:
                self._mark_cancelled(job)
            else:
                job.status = JobStatus.ERROR
                job.stage_message = "오류 발생"
                job.error = f"예상하지 못한 오류가 발생했습니다: {exc}"
                job.error_code = "INTERNAL_ERROR"
                job.completed_at = datetime.now(timezone.utc)
                self._persist(job)
        finally:
            if ws_task:
                ws_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ws_task
            self._cleanup_reference_uploads(job)

    async def _set_prompt(self, job: Job) -> None:
        if job.request.kind in {"image", "reference"}:
            self._resolve_models(job)
            original_prompt = job.request.prompt
            original_negative = (job.request.negative_prompt or "").strip()
            job.prompt_original = original_prompt
            prompt = original_prompt
            negative = original_negative
            translated = False
            if job.request.translate_prompt and self.translator is not None:
                prompt_result = await asyncio.to_thread(
                    self.translator.translate, original_prompt
                )
                if prompt_result.error:
                    job.warnings.append(prompt_result.error)
                elif prompt_result.translated:
                    prompt = prompt_result.text
                    translated = True
                if original_negative:
                    negative_result = await asyncio.to_thread(
                        self.translator.translate, original_negative
                    )
                    if negative_result.error:
                        job.warnings.append(negative_result.error)
                    elif negative_result.translated:
                        negative = negative_result.text
            job.prompt_translated = translated

            trigger = lora_trigger(job.lora)
            if trigger and job.request.lora_strength > 0:
                pattern = re.compile(
                    rf"(?<![a-z0-9_]){re.escape(trigger)}(?![a-z0-9_])",
                    re.IGNORECASE,
                )
                if not pattern.search(prompt):
                    base = prompt.rstrip().rstrip(",")
                    prompt = f"{base}, {trigger}" if base.strip() else trigger
            job.prompt_used = prompt
            job.negative_used = negative
            job.prompt_plan = None
            return
        plan = await build_prompt_plan_async(
            job.request.prompt,
            job.request.negative_prompt,
            job.request.mode,
            job.request.transparent,
            job.request.output_size,
            self.settings.generation,
        )
        job.prompt_used = plan.positive
        job.negative_used = plan.negative
        job.prompt_plan = plan.as_dict()

    async def _check_models(self, job: Job) -> None:
        self._resolve_models(job)
        try:
            checkpoints, loras = await self.comfy.get_available_models(force=True)
        except Exception as exc:
            raise ComfyExecutionError(
                "ComfyUI에서 사용 가능한 모델 목록을 가져오지 못했습니다.",
                detail=str(exc),
            ) from exc

        checkpoint = job.checkpoint
        if checkpoint not in checkpoints:
            expected = Path(self.settings.comfyui.models_dir) / "checkpoints" / checkpoint
            available = ", ".join(sorted(checkpoints)) or "없음"
            raise ModelMissingError(
                f"체크포인트 '{checkpoint}'가 ComfyUI에 없습니다. 다음 위치에 파일을 넣어 주세요: {expected} (현재 체크포인트: {available})",
                detail=f"https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
            )
        if not is_sdxl_compatible(checkpoint):
            if job.request.kind == "reference":
                raise ReferenceCompatibilityError(
                    f"체크포인트 '{checkpoint}'는 SDXL 계열이 아니어서 IP-Adapter Plus를 "
                    "적용할 수 없습니다. SDXL 1.0, NoobAI, Pony, Illustrious 계열을 선택해 주세요."
                )
            raise ModelMissingError(
                f"체크포인트 '{checkpoint}'는 SDXL 텍스트→이미지 모델이 아닙니다. "
                "SDXL 호환 체크포인트를 선택하거나 모델 목록에서 새 모델을 받아 주세요."
            )

        lora = job.lora or ""
        if job.request.lora_strength > 0 and lora and lora not in loras:
            expected = Path(self.settings.comfyui.models_dir) / "loras" / lora
            available = ", ".join(sorted(loras)) or "없음"
            raise ModelMissingError(
                f"LoRA '{lora}'가 ComfyUI에 없습니다. 다음 위치에 파일을 넣어 주세요: {expected} (현재 LoRA: {available})",
                detail="https://huggingface.co/nerijs/pixel-art-xl/resolve/main/pixel-art-xl.safetensors",
            )

        if job.request.kind == "reference":
            capabilities = await get_reference_capabilities(
                self.settings, self.comfy, checkpoint
            )
            job.reference_face_available = capabilities.plus_face_model
            if not capabilities.available or capabilities.checkpoint_compatible is False:
                guidance = capabilities.guidance or capabilities.checkpoint_note
                raise ReferenceCompatibilityError(
                    "이미지 레퍼런스(IP-Adapter Plus)를 사용할 수 없습니다. "
                    + (guidance or "IP-Adapter Plus 설치 상태를 확인해 주세요."),
                    detail=capabilities.install_hint or None,
                )
            await self._check_identity_models(job, capabilities)

    async def _check_identity_models(
        self, job: Job, capabilities: Any
    ) -> None:
        """Validate the InstantID/PuLID stack before the job is queued."""
        engine = job.request.identity_engine
        if engine == "none":
            return
        identity = await get_identity_capabilities(self.settings, self.comfy)
        label = "InstantID" if engine == "instantid" else "PuLID"
        ready = identity.get("instantid_available" if engine == "instantid" else "pulid_available")
        if not ready:
            guidance = identity.get("identity_guidance") or (
                f"{label} 설치 상태를 확인해 주세요."
            )
            raise ReferenceCompatibilityError(
                f"얼굴 고정({label})을 사용할 수 없습니다. {guidance}",
                detail=capabilities.install_hint or None,
            )
        if engine == "instantid":
            job.identity_model_file = identity.get("instantid_file", "")
            job.identity_controlnet_file = identity.get("controlnet_file", "")
        else:
            job.identity_pulid_file = identity.get("pulid_file", "")
        if not job.identity_model_file and engine == "instantid":
            raise ReferenceCompatibilityError(
                "InstantID 모델 파일을 찾지 못했습니다. models/instantid 폴더를 확인해 주세요."
            )
        if not job.identity_controlnet_file and engine == "instantid":
            raise ReferenceCompatibilityError(
                "InstantID ControlNet을 찾지 못했습니다. models/controlnet 폴더를 확인해 주세요."
            )
        if not job.identity_pulid_file and engine == "pulid":
            raise ReferenceCompatibilityError(
                "PuLID 모델 파일을 찾지 못했습니다. models/pulid 폴더를 확인해 주세요."
            )

    def _resolve_models(self, job: Job) -> None:
        if not job.checkpoint:
            if job.request.kind == "image":
                default_checkpoint = self.settings.generation.image_checkpoint
            elif job.request.kind == "reference":
                default_checkpoint = self.settings.generation.reference_checkpoint
            else:
                default_checkpoint = self.settings.generation.checkpoint
            job.checkpoint = (
                job.request.checkpoint or default_checkpoint
            ).strip()
        if job.lora is None:
            if job.request.lora is None:
                if job.request.kind == "image":
                    job.lora = self.settings.generation.image_lora
                elif job.request.kind == "reference":
                    job.lora = self.settings.generation.reference_lora
                else:
                    job.lora = self.settings.generation.lora
            else:
                job.lora = job.request.lora.strip()

    def _build_workflow(
        self, job: Job, seed: int | None = None, candidate_index: int = 0
    ) -> dict[str, Any]:
        workflow_path = self.settings.workflow_path
        try:
            with workflow_path.open("r", encoding="utf-8") as handle:
                workflow = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ComfyExecutionError(
                f"워크플로 파일을 읽을 수 없습니다: {workflow_path}",
                detail=str(exc),
            ) from exc
        if not isinstance(workflow, dict):
            raise ComfyExecutionError("워크플로 JSON 형식이 올바르지 않습니다.")

        generation = self.settings.generation
        is_native = job.request.kind in {"image", "reference"}
        width = job.request.image_size if is_native else generation.base_width
        height = job.request.image_size if is_native else generation.base_height
        try:
            workflow["1"]["inputs"]["ckpt_name"] = job.checkpoint
            workflow["3"]["inputs"]["text"] = job.prompt_used or job.request.prompt
            workflow["4"]["inputs"]["text"] = job.negative_used or ""
            workflow["5"]["inputs"]["width"] = width
            workflow["5"]["inputs"]["height"] = height
            workflow["6"]["inputs"].update(
                {
                    "seed": job.seed_used if seed is None else seed,
                    "steps": job.request.steps,
                    "cfg": job.request.cfg,
                    "sampler_name": generation.sampler,
                    "scheduler": generation.scheduler,
                }
            )
            prefix = (
                "r"
                if job.request.kind == "reference"
                else "i"
                if job.request.kind == "image"
                else "c"
            )
            workflow["8"]["inputs"]["filename_prefix"] = (
                f"pixelforge/{job.id}_{prefix}{candidate_index}"
            )
        except (KeyError, TypeError) as exc:
            raise ComfyExecutionError(
                "워크플로에 필요한 노드가 없습니다. workflows/text_to_pixel.json을 확인해 주세요.",
                detail=str(exc),
            ) from exc

        lora_enabled = bool(job.lora) and job.request.lora_strength > 0
        if lora_enabled:
            workflow["2"]["inputs"]["lora_name"] = job.lora
            workflow["2"]["inputs"]["strength_model"] = job.request.lora_strength
            workflow["2"]["inputs"]["strength_clip"] = job.request.lora_strength
            base_model: list[Any] = ["2", 0]
        else:
            # Bypass LoRA entirely when strength is zero, so a missing LoRA file
            # does not block plain SDXL generation.
            workflow["3"]["inputs"]["clip"] = ["1", 1]
            workflow["4"]["inputs"]["clip"] = ["1", 1]
            workflow["6"]["inputs"]["model"] = ["1", 0]
            workflow.pop("2", None)
            base_model = ["1", 0]

        if job.request.kind == "reference":
            self._apply_reference_nodes(job, workflow, base_model)

        return workflow

    def _apply_identity_nodes(
        self,
        job: Job,
        workflow: dict[str, Any],
        current_model: list[Any],
    ) -> None:
        """Add an InstantID or PuLID face-identity stage to the workflow.

        InstantID patches the UNet attention with the InsightFace embedding and
        drives a face ControlNet, so it replaces the positive/negative
        conditioning as well. PuLID only patches the model.
        """
        engine = job.request.identity_engine
        if engine == "none" or not job.identity_image_file:
            return
        identity_image = job.identity_image_file
        weight = round(float(job.request.identity_weight), 3)

        if engine == "instantid":
            workflow["50"] = {
                "class_type": "InstantIDModelLoader",
                "inputs": {"instantid_file": job.identity_model_file},
            }
            workflow["51"] = {
                "class_type": "InstantIDFaceAnalysis",
                "inputs": {"provider": "CPU"},
            }
            workflow["52"] = {
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": job.identity_controlnet_file},
            }
            workflow["53"] = {
                "class_type": "LoadImage",
                "inputs": {"image": identity_image},
            }
            # The advanced node separates the face embedding weight from the
            # ControlNet (pose/structure) weight, so the prompt can still decide
            # the scene instead of copying the reference photo.
            workflow["54"] = {
                "class_type": "ApplyInstantIDAdvanced",
                "inputs": {
                    "instantid": ["50", 0],
                    "insightface": ["51", 0],
                    "control_net": ["52", 0],
                    "image": ["53", 0],
                    "model": current_model,
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                    "ip_weight": weight,
                    "cn_strength": round(float(job.request.identity_control_weight), 3),
                    "noise": round(float(job.request.identity_noise), 3),
                    "combine_embeds": "average",
                    "start_at": 0.0,
                    "end_at": 1.0,
                },
            }
            workflow["6"]["inputs"]["model"] = ["54", 0]
            workflow["6"]["inputs"]["positive"] = ["54", 1]
            workflow["6"]["inputs"]["negative"] = ["54", 2]
            return

        if engine == "pulid":
            workflow["60"] = {
                "class_type": "PulidModelLoader",
                "inputs": {"pulid_file": job.identity_pulid_file},
            }
            workflow["61"] = {
                "class_type": "PulidInsightFaceLoader",
                "inputs": {"provider": "CPU"},
            }
            workflow["62"] = {
                "class_type": "PulidEvaClipLoader",
                "inputs": {},
            }
            workflow["63"] = {
                "class_type": "LoadImage",
                "inputs": {"image": identity_image},
            }
            workflow["64"] = {
                "class_type": "ApplyPulid",
                "inputs": {
                    "model": current_model,
                    "pulid": ["60", 0],
                    "eva_clip": ["62", 0],
                    "face_analysis": ["61", 0],
                    "image": ["63", 0],
                    "method": job.request.identity_method,
                    "weight": weight,
                    "start_at": 0.0,
                    "end_at": 1.0,
                },
            }
            workflow["6"]["inputs"]["model"] = ["64", 0]

    @staticmethod
    def _reference_weight_type(focus: str) -> str:
        if focus == "style":
            return "style transfer"
        if focus == "pose":
            return "composition"
        if focus == "composition":
            return "composition precise"
        return "linear"

    def _apply_reference_nodes(
        self,
        job: Job,
        workflow: dict[str, Any],
        base_model: list[Any],
    ) -> None:
        """Insert IP-Adapter Plus loaders and a per-reference apply chain.

        Each reference gets its own LoadImage and IPAdapterAdvanced node, so the
        user can mix appearance, style, and composition references with
        independent strengths. Face-focused references use the Plus Face model
        when it is installed.

        The image used for face identity is skipped unless the user explicitly
        asks for its look as well: IP-Adapter's ``linear`` weight copies the
        whole photo (background, lighting, pose), which would drown out the
        text prompt.
        """
        identity_asset = (
            job.request.identity_image
            if job.request.identity_engine != "none"
            and not job.request.identity_include_style
            else None
        )
        pairs = [
            (usage, filename)
            for usage, filename in zip(job.reference_usage, job.reference_files)
            if usage.strength > 0 and usage.asset_id != identity_asset
        ]
        if not pairs:
            return
        use_face = job.reference_face_available and any(
            usage.focus == "face" for usage, _ in pairs
        )
        workflow["20"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": base_model, "preset": "PLUS (high strength)"},
        }
        if use_face:
            workflow["21"] = {
                "class_type": "IPAdapterUnifiedLoader",
                "inputs": {"model": base_model, "preset": "PLUS FACE (portraits)"},
            }

        current_model: list[Any] = ["20", 0]
        for index, (usage, filename) in enumerate(pairs):
            load_id = str(30 + index)
            apply_id = str(40 + index)
            workflow[load_id] = {
                "class_type": "LoadImage",
                "inputs": {"image": filename},
            }
            if usage.focus == "face" and use_face:
                ipadapter_link: list[Any] = ["21", 1]
            else:
                ipadapter_link = ["20", 1]
            workflow[apply_id] = {
                "class_type": "IPAdapterAdvanced",
                "inputs": {
                    "model": current_model,
                    "ipadapter": ipadapter_link,
                    "image": [load_id, 0],
                    "weight": round(float(usage.strength), 3),
                    "weight_type": self._reference_weight_type(usage.focus),
                    "combine_embeds": "concat",
                    "start_at": 0.0,
                    "end_at": 1.0,
                    "embeds_scaling": "V only",
                },
            }
            current_model = [apply_id, 0]
        workflow["6"]["inputs"]["model"] = current_model
        self._apply_identity_nodes(job, workflow, current_model)

    async def _wait_for_completion(self, job: Job, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.comfyui.job_timeout_seconds
        poll = max(0.3, self.settings.jobs.poll_interval_seconds)
        while True:
            if job.cancel_requested:
                await self.comfy.interrupt()
                await self.comfy.delete_queue_items([prompt_id])
                return {}
            if time.monotonic() > deadline:
                await self.comfy.interrupt()
                raise ComfyExecutionError(
                    f"이미지 생성이 {self.settings.comfyui.job_timeout_seconds}초 안에 끝나지 않았습니다. 스텝/해상도를 낮추거나 ComfyUI 상태를 확인해 주세요."
                )
            try:
                entry = await self.comfy.get_history(prompt_id)
            except Exception:
                entry = None
            if entry:
                status = entry.get("status") or {}
                status_str = str(status.get("status_str") or "")
                if status_str == "error":
                    message, code = ComfyClient.extract_execution_error(entry)
                    if code == "VRAM_OOM":
                        raise VramError(message)
                    if "no face detected" in message.lower():
                        raise ReferenceCompatibilityError(
                            "얼굴 고정용 참고 이미지에서 얼굴을 찾지 못했습니다. "
                            "얼굴이 정면으로 잘 보이는 사진을 사용하고 강도를 낮춰 보세요.",
                            detail=message,
                        )
                    raise ComfyExecutionError(message, code=code)
                outputs = entry.get("outputs") or {}
                if outputs and (status.get("completed") is not False):
                    return entry
                if status.get("completed") is True and not outputs:
                    raise ComfyExecutionError(
                        "ComfyUI가 완료되었지만 이미지가 없습니다. 워크플로의 SaveImage 노드를 확인해 주세요."
                    )
            await asyncio.sleep(poll)

    @staticmethod
    def _extract_image(entry: dict[str, Any]) -> tuple[str, str, str] | None:
        outputs = entry.get("outputs") or {}
        candidates: list[dict[str, Any]] = []
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    candidates.append(image)
        if not candidates:
            return None
        preferred = next((item for item in candidates if item.get("type") == "output"), candidates[0])
        return (
            str(preferred["filename"]),
            str(preferred.get("subfolder") or ""),
            str(preferred.get("type") or "output"),
        )

    async def _listen_progress(self, job: Job, client_id: str) -> None:
        uri = f"{self.settings.comfyui.ws_url}/ws?clientId={client_id}"
        try:
            async with websockets.connect(uri, open_timeout=5, close_timeout=2, max_size=2**20) as socket:
                async for raw in socket:
                    if isinstance(raw, bytes):
                        continue
                    try:
                        message = json.loads(raw)
                    except ValueError:
                        continue
                    self._apply_ws_message(job, message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("ComfyUI progress websocket closed for job %s: %s", job.id, exc)

    def _apply_ws_message(self, job: Job, message: dict[str, Any]) -> None:
        event_type = message.get("type")
        data = message.get("data") or {}
        prompt_id = data.get("prompt_id")
        if prompt_id:
            # The socket is opened just before /prompt returns, so the tail of
            # the previous job's events can arrive first. Ignore anything that
            # cannot be attributed to this job yet.
            if job.comfy_prompt_id is None or prompt_id != job.comfy_prompt_id:
                return
        if event_type == "progress":
            value = int(data.get("value") or 0)
            maximum = int(data.get("max") or job.request.steps or 1)
            job.step = value
            job.total_steps = maximum
            count = max(1, job.candidate_count)
            segment_start = 8.0 + 78.0 * job.candidate_index / count
            segment_end = 8.0 + 78.0 * (job.candidate_index + 1) / count
            progress = segment_start + (segment_end - segment_start) * value / max(1, maximum)
            job.progress = min(86, int(progress))
            prefix = (
                f"후보 {job.candidate_index + 1}/{count} 생성 중"
                if count > 1
                else "모델이 이미지를 생성하는 중"
            )
            job.stage_message = f"{prefix}... ({value}/{maximum})"
        elif event_type == "executing":
            node = data.get("node")
            count = max(1, job.candidate_count)
            prefix = (
                f"후보 {job.candidate_index + 1}/{count}"
                if count > 1
                else "모델"
            )
            if node in {"6"}:
                job.stage_message = f"{prefix} 이미지를 생성하는 중..."
            elif node in {"7"}:
                job.stage_message = f"{prefix} 이미지를 디코딩하는 중..."
                job.progress = max(job.progress, 84)
            elif node is None:
                if job.cancel_requested:
                    # ComfyUI emits an "executing: null" event when an
                    # interrupt lands; it is not real progress.
                    return
                job.stage_message = "생성 완료, 결과를 가져오는 중..."
                job.progress = max(job.progress, 86)
        elif event_type == "execution_error":
            message_text = str(data.get("exception_message") or "ComfyUI 실행 오류")
            job.error = message_text
            job.error_code = "COMFY_EXECUTION_ERROR"
        elif event_type == "status":
            status = data.get("status") or {}
            queue_remaining = (status.get("exec_info") or {}).get("queue_remaining")
            if queue_remaining is not None and job.status == JobStatus.GENERATING:
                job.stage_message = f"모델이 이미지를 생성하는 중... (대기열 {queue_remaining})"

    def _mark_cancelled(self, job: Job) -> None:
        job.status = JobStatus.CANCELLED
        job.stage_message = "취소됨"
        job.completed_at = datetime.now(timezone.utc)
        job.progress = min(job.progress, 99)
        self._persist(job)
        logger.info("Job %s cancelled", job.id)

    def _save_job_metadata(
        self,
        job: Job,
        original_path: Path,
        pixel_path: Path,
        preview_path: Path,
        result: PostProcessResult,
        started: float,
    ) -> None:
        data = {
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "request": job.request.model_dump(),
            "kind": job.request.kind,
            "seed_used": job.seed_used,
            "base_seed": job.base_seed,
            "prompt_original": job.prompt_original,
            "prompt_used": job.prompt_used,
            "prompt_translated": job.prompt_translated,
            "negative_used": job.negative_used,
            "output_size": job.request.output_size,
            "mode": job.request.mode,
            "original_file": original_path.name,
            "pixel_file": pixel_path.name,
            "preview_file": preview_path.name,
            "cutout_file": f"{job.id}_cutout.png" if result.cutout is not None else None,
            "crop_file": f"{job.id}_crop.png" if result.cropped is not None else None,
            "width": job.request.output_size,
            "height": job.request.output_size,
            "preview_scale": result.preview_scale,
            "palette_used": result.palette_used,
            "transparent": result.image.mode == "RGBA",
            "postprocess": job.request.postprocess,
            "resize_filter": result.resize_filter,
            "warnings": result.warnings,
            "background_removed_ratio": result.background_removed_ratio,
            "background_method": result.background_method,
            "mask_method": result.mask_method,
            "subject_fill": round(result.subject_fill, 4),
            "subject_area_ratio": round(result.subject_area_ratio, 4),
            "subject_components": result.subject_components,
            "largest_component_share": round(result.largest_component_share, 4),
            "subject_bbox": list(result.subject_bbox) if result.subject_bbox else None,
            "source_clipped": result.source_clipped,
            "panel_suspected": result.panel_suspected,
            "panel_score": round(result.panel_score, 4),
            "candidate_score": result.candidate_score,
            "candidates_requested": job.request.candidates,
            "candidates_generated": len(
                [item for item in job.candidate_summaries if item.get("status") == "ok"]
            ),
            "selected_candidate": job.candidate_index,
            "candidate_scores": job.candidate_scores,
            "candidate_summaries": job.candidate_summaries,
            "candidate_prompt_ids": job.candidate_prompt_ids,
            "quality": [asdict(check) for check in result.quality],
            "prompt_plan": job.prompt_plan,
            "generation": {
                "checkpoint": job.checkpoint or self.settings.generation.checkpoint,
                "lora": job.lora if job.lora is not None else self.settings.generation.lora,
                "lora_enabled": bool(job.lora) and job.request.lora_strength > 0,
                "steps": job.request.steps,
                "cfg": job.request.cfg,
                "lora_strength": job.request.lora_strength,
                "sampler": self.settings.generation.sampler,
                "scheduler": self.settings.generation.scheduler,
                "base_width": self.settings.generation.base_width,
                "base_height": self.settings.generation.base_height,
            },
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "comfy_prompt_id": job.comfy_prompt_id,
        }
        try:
            save_metadata(self.settings, job.id, data)
        except Exception:
            logger.exception("Failed to save metadata for job %s", job.id)

    def _cleanup_reference_uploads(self, job: Job) -> None:
        """Remove the temporary copies uploaded to ComfyUI's input folder.

        The originals stay in ``outputs/references/uploads`` so the user can
        reuse them, but ComfyUI's input folder should not grow without bound.
        """
        if not job.reference_files:
            return
        input_dir = Path(self.settings.comfyui.input_dir).expanduser()
        if not input_dir.is_dir():
            return
        for name in job.reference_files:
            try:
                target = input_dir / name
                if target.is_file():
                    target.unlink()
            except OSError:
                logger.debug("Could not remove ComfyUI input %s", name, exc_info=True)
        job.reference_files = []

    async def _prepare_references(self, job: Job) -> None:
        """Resolve stored reference assets and upload copies to ComfyUI.

        ComfyUI's LoadImage reads from its own input folder, so each job uploads
        a uniquely named copy. A finished job never reuses a filename that a
        later job might overwrite.
        """
        resolved = resolve_reference_assets(self.settings, job.request.reference_images)
        job.reference_usage = [
            usage_from_asset(item.asset, item.input) for item in resolved
        ]
        job.reference_files = []
        uploaded_by_asset: dict[str, str] = {}
        for index, item in enumerate(resolved):
            try:
                content = await asyncio.to_thread(item.path.read_bytes)
            except OSError as exc:
                raise ReferenceCompatibilityError(
                    "참고 이미지 파일을 읽지 못했습니다.",
                    detail=str(exc),
                ) from exc
            filename = f"pixelforge_ref_{job.id}_{index}_{item.asset.id}.png"
            uploaded = await self.comfy.upload_image(filename, content)
            job.reference_files.append(uploaded)
            uploaded_by_asset[item.asset.id] = uploaded
        if not job.reference_face_available and any(
            usage.focus == "face" for usage in job.reference_usage
        ):
            job.warnings.append(
                "IP-Adapter Plus Face 모델을 찾지 못해 얼굴 참고를 일반 Plus 모델로 적용합니다. "
                "얼굴 고정이 중요하면 ip-adapter-plus-face_sdxl_vit-h.safetensors를 설치해 주세요."
            )
        identity_asset = job.request.identity_image
        if job.request.identity_engine != "none" and identity_asset:
            # The identity image is always one of the reference images, so the
            # upload above already produced the ComfyUI input name.
            job.identity_image_file = uploaded_by_asset.get(identity_asset, "")

    def _attach_details(self, job: Job) -> None:
        """Fill in the generation inspector data for a restored job."""
        if job.result is None:
            return
        try:
            meta = load_metadata(self.settings, job.id) or {}
        except Exception:
            meta = {}
        details = build_generation_details(meta) if meta else None
        if details is None:
            return
        job.result = job.result.model_copy(update={"details": details})

    def _generation_details(
        self,
        job: Job,
        *,
        width: int,
        height: int,
        transparent: bool,
        postprocess: str | None,
        palette_colors: int = 0,
        elapsed_seconds: float = 0.0,
    ) -> GenerationDetails:
        """Describe the model/settings used by a finished job."""
        generation = self.settings.generation
        identity = self._identity_usage(job)
        meta = {
            "request": job.request.model_dump(),
            "prompt_original": job.prompt_original,
            "prompt_used": job.prompt_used,
            "negative_used": job.negative_used,
            "prompt_translated": job.prompt_translated,
            "seed_used": job.seed_used,
            "width": width,
            "height": height,
            "transparent": transparent,
            "postprocess": postprocess,
            "palette_used": palette_colors,
            "elapsed_seconds": elapsed_seconds,
            "references": [usage.model_dump() for usage in job.reference_usage],
            "identity": identity.model_dump() if identity else None,
            "generation": {
                "checkpoint": job.checkpoint
                or (
                    self.settings.generation.reference_checkpoint
                    if job.request.kind == "reference"
                    else self.settings.generation.image_checkpoint
                    if job.request.kind == "image"
                    else self.settings.generation.checkpoint
                ),
                "lora": job.lora if job.lora is not None else "",
                "lora_enabled": bool(job.lora) and job.request.lora_strength > 0,
                "steps": job.request.steps,
                "cfg": job.request.cfg,
                "lora_strength": job.request.lora_strength,
                "sampler": generation.sampler,
                "scheduler": generation.scheduler,
            },
        }
        return build_generation_details(meta)

    def _identity_usage(self, job: Job) -> IdentityUsage | None:
        """Describe the face identity engine applied to a reference job."""
        engine = job.request.identity_engine
        if engine == "none":
            return None
        source = next(
            (
                usage
                for usage in job.reference_usage
                if usage.asset_id == job.request.identity_image
            ),
            None,
        )
        return IdentityUsage(
            engine=engine,
            image=job.request.identity_image,
            name=source.name if source else "",
            url=source.url if source else "",
            weight=round(float(job.request.identity_weight), 3),
            method=job.request.identity_method,
            control_weight=round(float(job.request.identity_control_weight), 3),
            noise=round(float(job.request.identity_noise), 3),
            include_style=bool(job.request.identity_include_style),
        )

    def _save_native_metadata(
        self,
        job: Job,
        original_path: Path,
        image_path: Path,
        preview_path: Path,
        started: float,
    ) -> None:
        kind = job.request.kind
        data = {
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "request": job.request.model_dump(),
            "kind": kind,
            "seed_used": job.seed_used,
            "base_seed": job.base_seed,
            "prompt_original": job.prompt_original,
            "prompt_used": job.prompt_used,
            "prompt_translated": job.prompt_translated,
            "negative_used": job.negative_used,
            "image_size": job.request.image_size,
            "width": job.request.image_size,
            "height": job.request.image_size,
            "mode": job.request.mode,
            "original_file": original_path.name,
            "image_file": image_path.name,
            "preview_file": preview_path.name,
            "transparent": False,
            "postprocess": None,
            "warnings": job.warnings,
            "references": [usage.model_dump() for usage in job.reference_usage],
            "identity": (
                {
                    "engine": job.request.identity_engine,
                    "image": job.request.identity_image,
                    "weight": job.request.identity_weight,
                    "method": job.request.identity_method,
                    "control_weight": job.request.identity_control_weight,
                    "noise": job.request.identity_noise,
                    "include_style": job.request.identity_include_style,
                }
                if job.request.identity_engine != "none"
                else None
            ),            "candidates_requested": job.request.candidates,
            "candidates_generated": len(
                [item for item in job.candidate_summaries if item.get("status") == "ok"]
            ),
            "selected_candidate": 0,
            "candidate_scores": job.candidate_scores,
            "candidate_summaries": job.candidate_summaries,
            "candidate_prompt_ids": job.candidate_prompt_ids,
            "prompt_plan": None,
            "generation": {
                "checkpoint": job.checkpoint or (
                    self.settings.generation.reference_checkpoint
                    if kind == "reference"
                    else self.settings.generation.image_checkpoint
                ),
                "lora": job.lora if job.lora is not None else (
                    self.settings.generation.reference_lora
                    if kind == "reference"
                    else self.settings.generation.image_lora
                ),
                "lora_enabled": bool(job.lora) and job.request.lora_strength > 0,
                "steps": job.request.steps,
                "cfg": job.request.cfg,
                "lora_strength": job.request.lora_strength,
                "sampler": self.settings.generation.sampler,
                "scheduler": self.settings.generation.scheduler,
                "base_width": job.request.image_size,
                "base_height": job.request.image_size,
                "ipadapter": (
                    {
                        "preset": "PLUS (high strength)",
                        "face_preset": "PLUS FACE (portraits)"
                        if job.reference_face_available
                        else None,
                    }
                    if kind == "reference"
                    else None
                ),
            },
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "comfy_prompt_id": job.comfy_prompt_id,
        }
        try:
            save_metadata(self.settings, job.id, data)
        except Exception:
            logger.exception("Failed to save %s metadata for job %s", kind, job.id)

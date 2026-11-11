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
    JobStatus,
    JobView,
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
    VramError,
)
from app.services.model_catalog import is_sdxl_compatible
from app.services.model_downloads import lora_trigger
from app.services.outputs import (
    image_result_info,
    result_info,
    save_candidate_original,
    save_image_result,
    save_metadata,
    save_original,
    save_pixel_result,
)
from app.services.postprocess import PostProcessResult, postprocess_image
from app.services.prompt_engine import build_prompt_plan_async
from app.services.translator import Translator

logger = logging.getLogger("pixelforge.jobs")


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
                raise
            except Exception:
                logger.exception("Unhandled error while running job %s", job_id)
                if job.status not in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
                    job.status = JobStatus.ERROR
                    job.stage_message = "오류 발생"
                    job.error = "예상하지 못한 서버 오류가 발생했습니다. 로그를 확인해 주세요."
                    job.error_code = "INTERNAL_ERROR"
                    job.completed_at = datetime.now(timezone.utc)
            finally:
                self._active_id = None

    async def _run_job(self, job: Job) -> None:
        started = time.monotonic()
        ws_task: asyncio.Task | None = None
        is_image = job.request.kind == "image"
        try:
            if job.cancel_requested:
                self._mark_cancelled(job)
                return
            job.started_at = datetime.now(timezone.utc)
            job.status = JobStatus.PREPARING
            job.progress = 3
            job.stage_message = "프롬프트를 처리하는 중..."
            await self._set_prompt(job)

            job.stage_message = "ComfyUI 연결을 확인하는 중..."
            await self.launcher.ensure_running(self.comfy)

            job.stage_message = "모델을 확인하는 중..."
            await self._check_models(job)

            job.stage_message = "워크플로를 준비하는 중..."
            requested_candidates = int(
                job.request.candidates or self.settings.generation.default_candidates
            )
            job.candidate_count = (
                1
                if is_image
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
                    if is_image
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

                if is_image:
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
                            "kind": "image",
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

            if is_image:
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
                job.result = image_result_info(
                    self.settings,
                    job.id,
                    job.request.image_size,
                    job.request.mode,
                    candidates_generated=len(candidates),
                    candidate_index=0,
                    warnings=job.warnings,
                )
                job.completed_at = datetime.now(timezone.utc)
                self._save_image_metadata(job, original_path, image_path, preview_path, started)
                job.progress = 100
                job.status = JobStatus.COMPLETED
                job.stage_message = "완료"
                logger.info(
                    "Image job %s completed in %.2fs (%sx%s)",
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
            )
            job.completed_at = datetime.now(timezone.utc)
            self._save_job_metadata(job, original_path, pixel_path, preview_path, result, started)

            job.progress = 100
            job.status = JobStatus.COMPLETED
            job.stage_message = "완료"
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
        finally:
            if ws_task:
                ws_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ws_task

    async def _set_prompt(self, job: Job) -> None:
        if job.request.kind == "image":
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

    def _resolve_models(self, job: Job) -> None:
        if not job.checkpoint:
            if job.request.kind == "image":
                default_checkpoint = self.settings.generation.image_checkpoint
            else:
                default_checkpoint = self.settings.generation.checkpoint
            job.checkpoint = (
                job.request.checkpoint or default_checkpoint
            ).strip()
        if job.lora is None:
            if job.request.lora is None:
                if job.request.kind == "image":
                    job.lora = self.settings.generation.image_lora
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
        width = job.request.image_size if job.request.kind == "image" else generation.base_width
        height = job.request.image_size if job.request.kind == "image" else generation.base_height
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
            prefix = "i" if job.request.kind == "image" else "c"
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
        else:
            # Bypass LoRA entirely when strength is zero, so a missing LoRA file
            # does not block plain SDXL generation.
            workflow["3"]["inputs"]["clip"] = ["1", 1]
            workflow["4"]["inputs"]["clip"] = ["1", 1]
            workflow["6"]["inputs"]["model"] = ["1", 0]
            workflow.pop("2", None)

        return workflow

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

    def _save_image_metadata(
        self,
        job: Job,
        original_path: Path,
        image_path: Path,
        preview_path: Path,
        started: float,
    ) -> None:
        data = {
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "request": job.request.model_dump(),
            "kind": "image",
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
            "candidates_requested": job.request.candidates,
            "candidates_generated": len(
                [item for item in job.candidate_summaries if item.get("status") == "ok"]
            ),
            "selected_candidate": 0,
            "candidate_scores": job.candidate_scores,
            "candidate_summaries": job.candidate_summaries,
            "candidate_prompt_ids": job.candidate_prompt_ids,
            "prompt_plan": None,
            "generation": {
                "checkpoint": job.checkpoint or self.settings.generation.image_checkpoint,
                "lora": job.lora if job.lora is not None else self.settings.generation.image_lora,
                "lora_enabled": bool(job.lora) and job.request.lora_strength > 0,
                "steps": job.request.steps,
                "cfg": job.request.cfg,
                "lora_strength": job.request.lora_strength,
                "sampler": self.settings.generation.sampler,
                "scheduler": self.settings.generation.scheduler,
                "base_width": job.request.image_size,
                "base_height": job.request.image_size,
            },
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "comfy_prompt_id": job.comfy_prompt_id,
        }
        try:
            save_metadata(self.settings, job.id, data)
        except Exception:
            logger.exception("Failed to save image metadata for job %s", job.id)

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas.models import (
    CancelResponse,
    ComfyStatus,
    DeleteOutputResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateKind,
    GpuStatus,
    HealthResponse,
    JobListResponse,
    JobView,
    ModelAvailability,
    ModelCatalogResponse,
    ModelDownloadItem,
    ModelStatus,
    OutputsResponse,
    QueueStatus,
    ReferenceAsset,
    ReferenceCapabilities,
    ReferenceSamplesResponse,
    SystemStatusResponse,
    TranslateRequest,
    TranslateResponse,
)
from app.services.comfy_client import ComfyClient
from app.services.errors import JobConflictError, JobNotFoundError, PixelForgeError
from app.services.job_manager import JobManager
from app.services.model_catalog import model_files
from app.services.model_downloads import ModelDownloadManager
from app.services.outputs import delete_output, find_download_path, list_outputs
from app.services.references import (
    get_reference_capabilities,
    list_sample_assets,
    save_reference_upload,
)
from app.services.comic import ComicError, ComicService
from app.services.studio import StudioError, StudioService
from app.services.system_monitor import SystemMonitor

router = APIRouter(prefix="/api", tags=["pixelforge"])
studio_router = APIRouter(prefix="/studio", tags=["studio"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _comfy(request: Request) -> ComfyClient:
    return request.app.state.comfy


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _downloads(request: Request) -> ModelDownloadManager:
    return request.app.state.downloads


def _monitor(request: Request) -> SystemMonitor:
    return request.app.state.monitor


def _studio(request: Request) -> StudioService:
    return request.app.state.studio


def _comic(request: Request) -> ComicService:
    return request.app.state.comic


@router.post("/comic/page")
async def build_comic_page(payload: dict, request: Request) -> dict:
    """Assemble generated cuts into a comic page (PNG + PDF)."""
    comic = _comic(request)
    panels = payload.get("panels") or []
    resolved: list[dict[str, Any]] = []
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        source = str(panel.get("path") or panel.get("image") or "")
        if not source:
            continue
        path = _resolve_output_path(_settings(request), source)
        if path is None:
            raise ComicError(f"컷 이미지를 찾을 수 없습니다: {source}")
        resolved.append(
            {
                "path": str(path),
                "text": str(panel.get("text") or ""),
                "position": str(panel.get("position") or "top"),
            }
        )
    return comic.build_page(
        resolved,
        layout=str(payload.get("layout") or "2x2"),
        width=int(payload.get("width") or 1240),
        height=int(payload.get("height") or 1754),
        title=str(payload.get("title") or ""),
    )


@router.get("/comic/pages")
async def list_comic_pages(request: Request) -> dict:
    return {"items": _comic(request).list_pages()}


@router.get("/comic/page/{page_id}.pdf")
async def download_comic_pdf(page_id: str, request: Request) -> FileResponse:
    path = _comic(request).pdf_path(page_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"pixelforge_comic_{page_id}.pdf",
    )


@router.delete("/comic/page/{page_id}")
async def delete_comic_page(page_id: str, request: Request) -> dict:
    removed = _comic(request).delete_page(page_id)
    if not removed:
        raise ComicError("페이지를 찾지 못했습니다.")
    return {"id": page_id, "deleted": removed}


def _resolve_output_path(settings: Settings, source: str) -> Path | None:
    """Allow only files inside the PixelForge output folders.

    The UI passes asset URLs like ``/files/images/<job>_image_1024.png``; those
    map to ``outputs/images/...`` because ``/files`` is mounted on ``outputs``.
    """
    raw = str(source or "").strip()
    if not raw:
        return None
    if raw.startswith("/files/"):
        raw = raw[len("/files/") :]
    root = settings.resolve("outputs").resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (root / raw.lstrip("/\\")).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@router.get("/studio/status")
async def studio_status(request: Request) -> dict:
    studio = _studio(request)
    status = studio.status()
    status["allowed"] = True
    status["remote_blocked"] = False
    return status


@router.post("/studio/start")
async def studio_start(request: Request) -> dict:
    studio = _studio(request)
    await studio.ensure_running()
    return studio.status()


@studio_router.api_route("/", methods=["GET", "POST", "HEAD"])
async def studio_root(request: Request) -> Response:
    return await studio_proxy("", request)


@studio_router.api_route("/{path:path}", methods=["GET", "POST", "HEAD"])
async def studio_proxy(path: str, request: Request) -> Response:
    body = await request.body()
    headers = {key: value for key, value in request.headers.items()}
    status_code, content_type, payload = await _studio(request).proxy(
        request.method,
        path,
        request.url.query,
        headers,
        body,
    )
    return Response(
        content=payload,
        status_code=status_code,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate_prompt(payload: TranslateRequest, request: Request) -> TranslateResponse:
    translator = request.app.state.translator
    result = await asyncio.to_thread(translator.translate, payload.text)
    return TranslateResponse(
        source=result.source,
        text=result.text,
        translated=result.translated,
        model=result.model,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
    )


@router.get("/references/samples", response_model=ReferenceSamplesResponse)
async def reference_samples(request: Request) -> ReferenceSamplesResponse:
    return ReferenceSamplesResponse(items=list_sample_assets(_settings(request)))


@router.post("/references/upload", response_model=ReferenceAsset)
async def upload_reference(request: Request, file: UploadFile = File(...)) -> ReferenceAsset:
    content = await file.read()
    return await asyncio.to_thread(
        save_reference_upload,
        _settings(request),
        content,
        file.filename or "reference.png",
    )


@router.get("/references/capabilities", response_model=ReferenceCapabilities)
async def reference_capabilities(
    request: Request,
    checkpoint: str | None = Query(default=None),
) -> ReferenceCapabilities:
    return await get_reference_capabilities(_settings(request), _comfy(request), checkpoint)


@router.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest, request: Request) -> GenerateResponse:
    job = await _jobs(request).submit(payload)
    return GenerateResponse(job_id=job.job_id, status=job.status, queue_position=job.queue_position)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    kind: GenerateKind | None = Query(default=None),
) -> JobListResponse:
    return _jobs(request).list_recent(limit=limit, kind=kind)


@router.get("/jobs/{job_id}", response_model=JobView)
async def get_job(job_id: str, request: Request) -> JobView:
    return _jobs(request).get(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse)
async def cancel_job(job_id: str, request: Request) -> CancelResponse:
    return await _jobs(request).cancel(job_id)


@router.get("/outputs", response_model=OutputsResponse)
async def get_outputs(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    kind: GenerateKind = Query(default="pixel"),
) -> OutputsResponse:
    return list_outputs(_settings(request), limit=limit, kind=kind)


@router.delete("/outputs/{job_id}", response_model=DeleteOutputResponse)
async def delete_output_result(job_id: str, request: Request) -> DeleteOutputResponse:
    if _jobs(request).is_busy(job_id):
        raise JobConflictError(
            "진행 중이거나 대기 중인 작업의 결과는 삭제할 수 없습니다. 완료된 뒤 다시 시도해 주세요."
        )
    try:
        deleted = delete_output(_settings(request), job_id)
    except ValueError as exc:
        raise JobNotFoundError(str(exc)) from exc
    if not deleted:
        raise JobNotFoundError("삭제할 결과를 찾을 수 없습니다. 이미 삭제되었을 수 있습니다.")
    _jobs(request).forget(job_id)
    return DeleteOutputResponse(
        job_id=job_id,
        deleted=deleted,
        count=len(deleted),
        message=f"결과 파일 {len(deleted)}개를 삭제했습니다.",
    )


@router.get("/models/catalog", response_model=ModelCatalogResponse)
async def model_catalog(request: Request) -> ModelCatalogResponse:
    return _downloads(request).catalog()


@router.post("/models/downloads/{download_id}", response_model=ModelDownloadItem)
async def start_model_download(download_id: str, request: Request) -> ModelDownloadItem:
    return await _downloads(request).start(download_id)


@router.post("/models/downloads/{download_id}/cancel", response_model=ModelDownloadItem)
async def cancel_model_download(download_id: str, request: Request) -> ModelDownloadItem:
    return await _downloads(request).cancel(download_id)


@router.get("/download/{job_id}")
async def download_output(
    job_id: str,
    request: Request,
    kind: GenerateKind = Query(default="pixel"),
) -> FileResponse:
    path = find_download_path(_settings(request), job_id, kind=kind)
    if path is None:
        message = (
            "저장할 이미지를 찾을 수 없습니다."
            if kind in {"image", "reference"}
            else "저장할 픽셀 이미지를 찾을 수 없습니다."
        )
        raise JobNotFoundError(message)
    size = path.stem.rsplit("_", 1)[-1]
    if kind == "image":
        filename = f"pixelforge_{job_id}_image_{size}px.png"
    elif kind == "reference":
        filename = f"pixelforge_{job_id}_reference_{size}px.png"
    else:
        filename = f"pixelforge_{job_id}_{size}px.png"
    return FileResponse(path, media_type="image/png", filename=filename)


@router.get("/system", response_model=SystemStatusResponse)
async def system_status(request: Request) -> SystemStatusResponse:
    gpu, memory = await _monitor(request).snapshot()
    jobs = _jobs(request)
    if gpu is not None:
        gpu.state = "generating" if jobs.active_job() else "idle"
    active, pending = jobs.queue_counts()
    return SystemStatusResponse(
        gpu=gpu,
        memory=memory,
        queue=QueueStatus(active=active, pending=pending),
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    comfy = _comfy(request)
    jobs = _jobs(request)
    connected = False
    version: str | None = None
    comfy_error: str | None = None
    gpu, memory = await _monitor(request).snapshot()
    try:
        stats = await comfy.health()
        connected = True
        system = stats.get("system") or {}
        version = str(system.get("comfyui_version") or "") or None
        devices = stats.get("devices") or []
        if gpu is None and devices and isinstance(devices[0], dict):
            device = devices[0]
            total = int(device.get("vram_total") or 0)
            free = int(device.get("vram_free") or 0)
            gpu = GpuStatus(
                name=str(device.get("name") or "GPU"),
                vram_total=total,
                vram_free=free,
                vram_used=max(0, total - free),
                source="comfyui",
            )
    except PixelForgeError as exc:
        comfy_error = exc.message
    except Exception as exc:
        comfy_error = f"ComfyUI 연결 확인 실패: {exc}"
    if gpu is not None:
        gpu.state = "generating" if jobs.active_job() else "idle"

    checkpoints: set[str] = set()
    loras: set[str] = set()
    try:
        checkpoints, loras = await comfy.get_available_models()
    except Exception:
        pass
    models = ModelStatus(
        checkpoint=ModelAvailability(
            name=settings.generation.checkpoint,
            available=settings.generation.checkpoint in checkpoints,
        ),
        lora=ModelAvailability(
            name=settings.generation.lora,
            available=settings.generation.lora in loras,
        ),
        checkpoints=model_files(settings, "checkpoint", checkpoints),
        loras=model_files(settings, "lora", loras),
    )
    active, pending = jobs.queue_counts()
    return HealthResponse(
        status="ok" if connected else "degraded",
        app_version=settings.app.version,
        comfyui=ComfyStatus(
            connected=connected,
            url=settings.comfyui.normalized_url,
            version=version,
            error=comfy_error,
        ),
        gpu=gpu,
        memory=memory,
        models=models,
        queue=QueueStatus(active=active, pending=pending),
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/config")
async def config(request: Request) -> dict:
    settings = _settings(request)
    generation = settings.generation
    return {
        "app_name": settings.app.name,
        "app_version": settings.app.version,
        "comfyui_url": settings.comfyui.normalized_url,
        "checkpoint": generation.checkpoint,
        "lora": generation.lora,
        "output_sizes": generation.output_sizes,
        "default_output_size": generation.default_output_size,
        "default_steps": generation.steps,
        "default_cfg": generation.cfg,
        "default_lora_strength": generation.lora_strength,
        "default_transparent": generation.transparent_default,
        "default_postprocess": generation.default_postprocess,
        "default_palette_colors": generation.default_palette_colors,
        "default_resize_filter": generation.default_resize_filter,
        "default_candidates": generation.default_candidates,
        "max_candidates": generation.max_candidates,
        "candidate_options": [1, 2, 4, 6, 8],
        "palette_options": [0, 8, 16, 24, 32],
        "default_image_size": generation.default_image_size,
        "image_sizes": generation.image_sizes,
        "image_checkpoint": generation.image_checkpoint,
        "image_lora": generation.image_lora,
        "default_image_candidates": generation.image_default_candidates,
        "default_image_negative_prompt": generation.image_negative_prompt,
        "reference_checkpoint": generation.reference_checkpoint,
        "reference_lora": generation.reference_lora,
        "reference_default_size": generation.reference_default_size,
        "reference_default_strength": generation.reference_default_strength,
        "reference_default_focus": generation.reference_default_focus,
        "reference_max_references": generation.reference_max_references,
        "default_negative_prompt": generation.negative_prompt,
        "translation_enabled": settings.translation.enabled,
        "translation_model": Path(settings.translation.model_dir).name,
        "max_pending": settings.jobs.max_pending,
    }

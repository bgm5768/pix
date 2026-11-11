from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from app.config import Settings
from app.schemas.models import (
    CancelResponse,
    ComfyStatus,
    GenerateRequest,
    GenerateResponse,
    GenerateKind,
    GpuStatus,
    HealthResponse,
    JobView,
    ModelAvailability,
    ModelCatalogResponse,
    ModelDownloadItem,
    ModelStatus,
    OutputsResponse,
    QueueStatus,
)
from app.services.comfy_client import ComfyClient
from app.services.errors import JobNotFoundError, PixelForgeError
from app.services.job_manager import JobManager
from app.services.model_catalog import model_files
from app.services.model_downloads import ModelDownloadManager
from app.services.outputs import find_download_path, list_outputs

router = APIRouter(prefix="/api", tags=["pixelforge"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _comfy(request: Request) -> ComfyClient:
    return request.app.state.comfy


def _jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def _downloads(request: Request) -> ModelDownloadManager:
    return request.app.state.downloads


@router.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest, request: Request) -> GenerateResponse:
    job = await _jobs(request).submit(payload)
    return GenerateResponse(job_id=job.job_id, status=job.status, queue_position=job.queue_position)


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
            if kind == "image"
            else "저장할 픽셀 이미지를 찾을 수 없습니다."
        )
        raise JobNotFoundError(message)
    size = path.stem.rsplit("_", 1)[-1]
    if kind == "image":
        filename = f"pixelforge_{job_id}_image_{size}px.png"
    else:
        filename = f"pixelforge_{job_id}_{size}px.png"
    return FileResponse(path, media_type="image/png", filename=filename)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    comfy = _comfy(request)
    jobs = _jobs(request)
    connected = False
    version: str | None = None
    comfy_error: str | None = None
    gpu: GpuStatus | None = None
    try:
        stats = await comfy.health()
        connected = True
        system = stats.get("system") or {}
        version = str(system.get("comfyui_version") or "") or None
        devices = stats.get("devices") or []
        if devices and isinstance(devices[0], dict):
            device = devices[0]
            gpu = GpuStatus(
                name=str(device.get("name") or "GPU"),
                vram_total=int(device.get("vram_total") or 0),
                vram_free=int(device.get("vram_free") or 0),
                state="generating" if jobs.active_job() else "idle",
            )
    except PixelForgeError as exc:
        comfy_error = exc.message
    except Exception as exc:
        comfy_error = f"ComfyUI 연결 확인 실패: {exc}"

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
        "default_negative_prompt": generation.negative_prompt,
        "max_pending": settings.jobs.max_pending,
    }

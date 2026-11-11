from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from app.config import Settings
from app.schemas.models import ModelCatalogResponse, ModelDownloadItem
from app.services.comfy_client import ComfyClient
from app.services.errors import ModelDownloadError
from app.services.model_catalog import resolve_model_path

logger = logging.getLogger("pixelforge.downloads")

ModelKind = Literal["checkpoint", "lora"]


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    label: str
    kind: ModelKind
    filename: str
    url: str
    size_bytes: int
    description: str = ""
    trigger: str | None = None
    recommended_strength: float | None = None


# Curated, licence-safe SDXL downloads.  Keep this list small and explicit so
# the UI never points at an arbitrary/unverified URL.
CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        id="pixelartdiffusionxl-spriteshaper",
        label="PixelArtDiffusionXL · SpriteShaper",
        kind="checkpoint",
        filename="SDXL1.0_PixelArtDiffusionXL_SpriteShaper.safetensors",
        url=(
            "https://huggingface.co/nncyberpunk/"
            "SDXL1.0_PixelArtDiffusionXL_SpriteShaper/resolve/main/"
            "SDXL1.0_PixelArtDiffusionXL_SpriteShaper.safetensors?download=true"
        ),
        size_bytes=6_938_040_682,
        description="SDXL 기반 픽셀아트/스프라이트 특화 체크포인트",
    ),
    CatalogEntry(
        id="lustify-v2",
        label="LUSTIFY! v2.0",
        kind="checkpoint",
        filename="lustifySDXLNSFWSFW_v20.safetensors",
        url=(
            "https://huggingface.co/shootstuff/LUSTIFY-v2.0/resolve/main/"
            "lustifySDXLNSFWSFW_v20.safetensors?download=true"
        ),
        size_bytes=6_938_043_264,
        description=(
            "무검열 포토리얼 SDXL 체크포인트 · NSFW/SFW · Civitai 573152 v2.0 · "
            "상업적 이미지 생성 허용(크레딧 필요)"
        ),
    ),
    CatalogEntry(
        id="pixel-art-redmond-lite64",
        label="PixelArtRedmond · Lite64",
        kind="lora",
        filename="PixelArtRedmond-Lite64.safetensors",
        url=(
            "https://huggingface.co/artificialguybr/PixelArtRedmond/resolve/main/"
            "PixelArtRedmond-Lite64.safetensors?download=true"
        ),
        size_bytes=170_540_052,
        description="픽셀아트 전용 LoRA · SDXL 1.0 기반",
        recommended_strength=0.8,
    ),
    CatalogEntry(
        id="pixel-art-sdxl-dora-v09",
        label="Pixel Art SDXL DoRA v0.9",
        kind="lora",
        filename="pixel-art-sdxl-dora-v0-9.safetensors",
        url=(
            "https://huggingface.co/thliang01/pixel-art-sdxl-dora-v0-9/resolve/main/"
            "pixel-art-sdxl-dora-v0-9.safetensors?download=true"
        ),
        size_bytes=374_593_544,
        description="DoRA 방식 픽셀아트 LoRA · 강한 스타일화",
        recommended_strength=0.85,
    ),
    CatalogEntry(
        id="pixel-art-lora-sdxl",
        label="Pixel Art LoRA SDXL",
        kind="lora",
        filename="pixel-art-lora-sdxl.safetensors",
        url=(
            "https://huggingface.co/Hadimeeee/pixel-art-lora-sdxl/resolve/main/"
            "pytorch_lora_weights.safetensors?download=true"
        ),
        size_bytes=185_963_768,
        description="가벼운 범용 픽셀아트 LoRA · Apache-2.0",
        recommended_strength=0.7,
    ),
    CatalogEntry(
        id="sexy-slider-sdxl",
        label="NTC Slider · sexy",
        kind="lora",
        filename="sexy.safetensors",
        url=(
            "https://huggingface.co/ntc-ai/SDXL-LoRA-slider.sexy/resolve/main/"
            "sexy.safetensors?download=true"
        ),
        size_bytes=8_789_076,
        description="NSFW 강도 슬라이더 LoRA · MIT · SDXL 1.0 · 트리거 'sexy'",
        trigger="sexy",
        recommended_strength=1.2,
    ),
)

CATALOG_BY_ID = {entry.id: entry for entry in CATALOG}

# LoRA trigger words are injected into image prompts automatically so a
# selected LoRA actually takes effect even if the user does not know its
# trigger. Pixel prompts are handled by the prompt engine and stay untouched.
LORA_TRIGGERS: dict[str, str] = {
    entry.filename.replace("\\", "/").rsplit("/", 1)[-1].lower(): entry.trigger
    for entry in CATALOG
    if entry.kind == "lora" and entry.trigger
}


def lora_trigger(filename: str | None) -> str | None:
    if not filename:
        return None
    normalized = filename.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()
    return LORA_TRIGGERS.get(normalized)


@dataclass
class DownloadState:
    status: Literal["not_installed", "downloading", "installed", "error", "cancelled"] = "not_installed"
    downloaded_bytes: int = 0
    speed_bps: float = 0.0
    error: str | None = None
    started_at: float = 0.0
    started_bytes: int = 0
    task: asyncio.Task | None = field(default=None, repr=False)


class ModelDownloadManager:
    """Downloads curated model files into the ComfyUI models directory."""

    def __init__(self, settings: Settings, comfy: ComfyClient):
        self.settings = settings
        self.comfy = comfy
        self._states: dict[str, DownloadState] = {}
        self._lock = asyncio.Lock()

    def _entry(self, download_id: str) -> CatalogEntry:
        entry = CATALOG_BY_ID.get(download_id)
        if entry is None:
            raise ModelDownloadError("다운로드 목록에 없는 모델입니다.")
        return entry

    def _target(self, entry: CatalogEntry) -> Path:
        return resolve_model_path(self.settings, entry.kind, entry.filename)

    def _part(self, entry: CatalogEntry) -> Path:
        target = self._target(entry)
        return target.with_name(target.name + ".part")

    def _item(self, entry: CatalogEntry) -> ModelDownloadItem:
        target = self._target(entry)
        state = self._states.get(entry.id) or DownloadState()
        installed = target.exists() and target.stat().st_size > 0
        if installed:
            status = "installed"
            downloaded = target.stat().st_size
            progress = 100.0
        elif state.task is not None and not state.task.done():
            status = "downloading"
            downloaded = state.downloaded_bytes
            progress = (
                min(99.9, 100.0 * downloaded / entry.size_bytes)
                if entry.size_bytes
                else 0.0
            )
        else:
            part = self._part(entry)
            downloaded = part.stat().st_size if part.exists() else 0
            status = state.status if state.status in {"error", "cancelled"} else "not_installed"
            progress = (
                min(99.9, 100.0 * downloaded / entry.size_bytes)
                if entry.size_bytes and downloaded
                else 0.0
            )
        return ModelDownloadItem(
            id=entry.id,
            label=entry.label,
            kind=entry.kind,
            filename=entry.filename,
            description=entry.description,
            trigger=entry.trigger,
            recommended_strength=entry.recommended_strength,
            size_bytes=entry.size_bytes,
            status=status,  # type: ignore[arg-type]
            progress=round(progress, 1),
            downloaded_bytes=downloaded,
            speed_bps=state.speed_bps if status == "downloading" else 0.0,
            error=state.error if status == "error" else None,
        )

    def catalog(self) -> ModelCatalogResponse:
        return ModelCatalogResponse(
            items=[self._item(entry) for entry in CATALOG],
            models_dir=str(self.settings.comfyui.models_dir),
        )

    async def start(self, download_id: str) -> ModelDownloadItem:
        entry = self._entry(download_id)
        target = self._target(entry)
        if target.exists() and target.stat().st_size > 0:
            return self._item(entry)
        async with self._lock:
            state = self._states.setdefault(entry.id, DownloadState())
            if state.task is not None and not state.task.done():
                raise ModelDownloadError("이미 다운로드가 진행 중입니다.")
            part = self._part(entry)
            state.status = "downloading"
            state.error = None
            state.downloaded_bytes = part.stat().st_size if part.exists() else 0
            state.started_bytes = state.downloaded_bytes
            state.started_at = time.monotonic()
            state.speed_bps = 0.0
            state.task = asyncio.create_task(
                self._run(entry), name=f"model-download-{entry.id}"
            )
            logger.info("Model download started: %s", entry.label)
        return self._item(entry)

    async def cancel(self, download_id: str) -> ModelDownloadItem:
        entry = self._entry(download_id)
        async with self._lock:
            state = self._states.get(entry.id)
            if state is None or state.task is None or state.task.done():
                raise ModelDownloadError("진행 중인 다운로드가 없습니다.")
            state.task.cancel()
            state.status = "cancelled"
            state.speed_bps = 0.0
        return self._item(entry)

    async def close(self) -> None:
        tasks = [
            state.task
            for state in self._states.values()
            if state.task is not None and not state.task.done()
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                continue

    async def _run(self, entry: CatalogEntry) -> None:
        state = self._states.setdefault(entry.id, DownloadState())
        target = self._target(entry)
        part = self._part(entry)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry.size_bytes and part.exists() and part.stat().st_size == entry.size_bytes:
                part.replace(target)
                state.status = "installed"
                state.downloaded_bytes = entry.size_bytes
                state.speed_bps = 0.0
                await self._refresh_comfy()
                return

            await self._stream(entry, part, state)
            if entry.size_bytes and part.stat().st_size < entry.size_bytes:
                raise ModelDownloadError(
                    f"다운로드가 완료되지 않았습니다. ({part.stat().st_size:,}/{entry.size_bytes:,} bytes)"
                )
            size = part.stat().st_size
            part.replace(target)
            state.status = "installed"
            state.downloaded_bytes = size
            state.speed_bps = 0.0
            state.error = None
            logger.info("Model download completed: %s", entry.label)
            await self._refresh_comfy()
        except asyncio.CancelledError:
            state.status = "cancelled"
            state.speed_bps = 0.0
            logger.info("Model download cancelled: %s", entry.label)
            raise
        except Exception as exc:
            state.status = "error"
            state.error = str(exc)
            state.speed_bps = 0.0
            logger.exception("Model download failed: %s", entry.label)

    async def _stream(self, entry: CatalogEntry, part: Path, state: DownloadState) -> None:
        downloaded = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
        timeout = httpx.Timeout(connect=20.0, read=120.0, write=120.0, pool=20.0)
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            async with client.stream("GET", entry.url, headers=headers) as response:
                if response.status_code == 416 and downloaded:
                    return
                if response.status_code not in (200, 206):
                    raise ModelDownloadError(
                        f"모델 서버가 다운로드를 거부했습니다. (HTTP {response.status_code})"
                    )
                if response.status_code == 200:
                    downloaded = 0
                    state.downloaded_bytes = 0
                    state.started_bytes = 0
                mode = "ab" if response.status_code == 206 else "wb"
                with part.open(mode) as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        handle.write(chunk)
                        downloaded += len(chunk)
                        state.downloaded_bytes = downloaded
                        elapsed = max(0.001, time.monotonic() - state.started_at)
                        session_bytes = max(0, downloaded - state.started_bytes)
                        state.speed_bps = session_bytes / elapsed
        state.downloaded_bytes = downloaded

    async def _refresh_comfy(self) -> None:
        try:
            await self.comfy.get_available_models(force=True)
        except Exception:
            logger.debug("Could not refresh ComfyUI model cache", exc_info=True)

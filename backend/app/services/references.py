from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
from PIL import Image, ImageOps

from app.config import Settings
from app.schemas.models import (
    ReferenceAnalysis,
    ReferenceAsset,
    ReferenceCapabilities,
    ReferenceInput,
    ReferenceUsage,
)
from app.services.comfy_client import ComfyClient
from app.services.errors import ReferenceError
from app.services.model_catalog import is_sdxl_compatible

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_SIDE = 1536
SAMPLE_URL_PREFIX = "/reference-samples"
_SAMPLE_INDEX = "samples.json"
_SAMPLE_ID_RE = re.compile(r"^sample_[A-Za-z0-9_-]{1,60}$")
_UPLOAD_ID_RE = re.compile(r"^up_[a-f0-9]{20}$")
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}

_ANALYSIS_CACHE: dict[tuple[str, int, int], ReferenceAnalysis] = {}

_PLUS_RE = re.compile(r"plus[._-]sdxl[._-]vit[._-]h\.(safetensors|bin)$", re.IGNORECASE)
_PLUS_FACE_RE = re.compile(
    r"plus[._-]face[._-]sdxl[._-]vit[._-]h\.(safetensors|bin)$", re.IGNORECASE
)
_CLIP_VISION_RE = re.compile(
    r"(ViT[._-]H[._-]14.*s32B[._-]b79K|CLIP[._-]ViT[._-]H).*\.(safetensors|bin)$",
    re.IGNORECASE,
)


@dataclass
class ResolvedReference:
    input: ReferenceInput
    path: Path
    asset: ReferenceAsset


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:20]


def _safe_id(value: str) -> bool:
    return bool(_UPLOAD_ID_RE.fullmatch(value) or _SAMPLE_ID_RE.fullmatch(value))


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Flatten transparency onto white so transparent PNG references stay usable."""
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _orientation(width: int, height: int) -> str:
    if width > height * 1.05:
        return "landscape"
    if height > width * 1.05:
        return "portrait"
    return "square"


def _brightness_label(value: float) -> str:
    if value < 0.32:
        return "어두운 톤"
    if value < 0.48:
        return "차분한 톤"
    if value < 0.68:
        return "중간 밝기"
    return "밝은 톤"


def _saturation_label(value: float) -> str:
    if value < 0.18:
        return "저채도"
    if value < 0.42:
        return "자연스러운 채도"
    return "선명한 채도"


def analyze_image(image: Image.Image) -> ReferenceAnalysis:
    """Small deterministic analysis used by the reference cards.

    IP-Adapter itself reads the raw image embedding. This analysis is shown to
    the user (dominant palette, orientation, subject hint) and stored in job
    metadata so a reference is more than an opaque file name.
    """
    rgb = image.convert("RGB")
    width, height = rgb.size
    small = rgb.copy()
    small.thumbnail((96, 96), Image.Resampling.LANCZOS)
    array = np.asarray(small, dtype=np.float32)

    gray = array @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    brightness = float(np.clip(gray.mean() / 255.0, 0.0, 1.0))

    hsv = np.asarray(small.convert("HSV"), dtype=np.float32)
    saturation = float(np.clip(hsv[:, :, 1].mean() / 255.0, 0.0, 1.0))

    rg = array[:, :, 0] - array[:, :, 1]
    yb = 0.5 * (array[:, :, 0] + array[:, :, 1]) - array[:, :, 2]
    colorfulness = float(
        np.clip((np.std(rg) + np.std(yb)) / 220.0, 0.0, 1.0)
    )

    dominant: list[str] = []
    try:
        quantized = small.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette() or []
        colors = quantized.getcolors() or []
        colors.sort(key=lambda item: item[0], reverse=True)
        total = float(sum(count for count, _ in colors)) or 1.0
        for count, index in colors:
            if count / total < 0.04:
                continue
            offset = index * 3
            if offset + 2 >= len(palette):
                continue
            red, green, blue = palette[offset : offset + 3]
            dominant.append(f"#{red:02x}{green:02x}{blue:02x}")
            if len(dominant) >= 3:
                break
    except Exception:
        dominant = []

    skin = (
        (array[:, :, 0] > 95)
        & (array[:, :, 1] > 40)
        & (array[:, :, 2] > 20)
        & (array[:, :, 0] > array[:, :, 1] + 10)
        & (array[:, :, 0] > array[:, :, 2] + 10)
        & (np.abs(array[:, :, 0] - array[:, :, 1]) > 12)
    )
    height_px, width_px = array.shape[:2]
    # Faces cluster in the middle of a portrait, so the skin mask is only
    # trusted when it is concentrated in the central region. Warm fur and
    # sunset scenes also match the skin colour rule, so the border ratio acts
    # as a guard against those false positives.
    cy, cx = height_px // 2, width_px // 2
    center_slice = (
        slice(max(0, cy - height_px // 4), cy + height_px // 4),
        slice(max(0, cx - width_px // 4), cx + width_px // 4),
    )
    center_mask = np.zeros_like(skin)
    center_mask[center_slice] = True
    skin_center = float(skin[center_mask].mean()) if center_mask.any() else 0.0
    skin_border = float(skin[~center_mask].mean()) if (~center_mask).any() else 0.0
    subject_hint = (
        "인물/캐릭터 추정"
        if skin_center >= 0.16 and skin_center >= max(0.02, skin_border * 1.5)
        else ""
    )

    if not subject_hint:
        center = array[center_slice]
        border = np.concatenate(
            [
                array[: max(1, height_px // 8)].reshape(-1, 3),
                array[-max(1, height_px // 8) :].reshape(-1, 3),
                array[:, : max(1, width_px // 8)].reshape(-1, 3),
                array[:, -max(1, width_px // 8) :].reshape(-1, 3),
            ]
        )
        center_mean = center.reshape(-1, 3).mean(axis=0)
        border_mean = border.mean(axis=0)
        if float(np.linalg.norm(center_mean - border_mean)) >= 30:
            subject_hint = "중심 피사체"
        else:
            subject_hint = "장면/배경 중심"

    orientation = _orientation(width, height)
    orientation_label = {
        "portrait": "세로형",
        "landscape": "가로형",
        "square": "정사각형",
    }[orientation]
    parts = [orientation_label, _brightness_label(brightness), _saturation_label(saturation)]
    if subject_hint:
        parts.append(subject_hint)
    if dominant:
        parts.append(" · ".join(dominant))
    return ReferenceAnalysis(
        width=width,
        height=height,
        orientation=orientation,  # type: ignore[arg-type]
        brightness=round(brightness, 4),
        saturation=round(saturation, 4),
        colorfulness=round(colorfulness, 4),
        dominant_colors=dominant,
        subject_hint=subject_hint,
        summary=" · ".join(parts),
    )


def analyze_path(path: Path) -> ReferenceAnalysis:
    try:
        stat = path.stat()
    except OSError:
        raise ReferenceError("참고 이미지 파일을 읽을 수 없습니다.")
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _ANALYSIS_CACHE.get(key)
    if cached is not None:
        return cached.model_copy(deep=True)
    try:
        with Image.open(path) as image:
            image.load()
            analysis = analyze_image(image)
    except Exception as exc:
        raise ReferenceError("참고 이미지를 분석할 수 없습니다.", detail=str(exc)) from exc
    _ANALYSIS_CACHE[key] = analysis
    return analysis.model_copy(deep=True)


def _read_sidecar(settings: Settings, asset_id: str) -> dict[str, Any]:
    path = settings.reference_uploads_dir / f"{asset_id}.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def upload_asset(settings: Settings, asset_id: str) -> ReferenceAsset:
    if not _UPLOAD_ID_RE.fullmatch(asset_id):
        raise ReferenceError("잘못된 참고 이미지 ID입니다.")
    path = settings.reference_uploads_dir / f"{asset_id}.png"
    if not path.is_file():
        raise ReferenceError(
            "참고 이미지를 찾을 수 없습니다. 다시 업로드해 주세요.",
            detail=str(path),
        )
    sidecar = _read_sidecar(settings, asset_id)
    analysis = analyze_path(path)
    return ReferenceAsset(
        id=asset_id,
        name=str(sidecar.get("name") or "업로드한 참고 이미지"),
        url=f"/files/references/uploads/{asset_id}.png",
        source="upload",
        width=analysis.width,
        height=analysis.height,
        size_bytes=path.stat().st_size,
        hint=str(sidecar.get("hint") or ""),
        analysis=analysis,
    )


def save_reference_upload(settings: Settings, content: bytes, filename: str) -> ReferenceAsset:
    if not content:
        raise ReferenceError("빈 파일입니다. 이미지 파일을 선택해 주세요.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ReferenceError(
            f"참고 이미지는 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 이하만 업로드할 수 있습니다."
        )
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in _ALLOWED_SUFFIXES:
        raise ReferenceError("PNG, JPG, WEBP, BMP, GIF 이미지만 사용할 수 있습니다.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            rgb = _flatten_to_rgb(image)
    except Exception as exc:
        raise ReferenceError("이미지 파일을 읽을 수 없습니다.", detail=str(exc)) from exc

    if max(rgb.size) > MAX_IMAGE_SIDE:
        rgb.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG", optimize=True)
    normalized = buffer.getvalue()
    asset_id = f"up_{_hash_bytes(normalized)}"
    target = settings.reference_uploads_dir / f"{asset_id}.png"
    if not target.exists():
        target.write_bytes(normalized)
    sidecar = {
        "name": (Path(filename).name or "참고 이미지")[:120],
        "source": "upload",
    }
    try:
        with (settings.reference_uploads_dir / f"{asset_id}.json").open(
            "w", encoding="utf-8"
        ) as handle:
            json.dump(sidecar, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass
    analysis = analyze_path(target)
    return ReferenceAsset(
        id=asset_id,
        name=sidecar["name"],
        url=f"/files/references/uploads/{asset_id}.png",
        source="upload",
        width=analysis.width,
        height=analysis.height,
        size_bytes=target.stat().st_size,
        analysis=analysis,
    )


def _read_sample_index(settings: Settings) -> list[dict[str, Any]]:
    path = settings.reference_samples_dir / _SAMPLE_INDEX
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def list_sample_assets(settings: Settings) -> list[ReferenceAsset]:
    items: list[ReferenceAsset] = []
    for entry in _read_sample_index(settings):
        asset_id = str(entry.get("id") or "")
        filename = str(entry.get("file") or "")
        if not _SAMPLE_ID_RE.fullmatch(asset_id) or not filename:
            continue
        path = settings.reference_samples_dir / filename
        if not path.is_file():
            continue
        try:
            analysis = analyze_path(path)
        except ReferenceError:
            continue
        items.append(
            ReferenceAsset(
                id=asset_id,
                name=str(entry.get("name") or path.stem),
                url=f"{SAMPLE_URL_PREFIX}/{quote(filename)}",
                source="sample",
                width=analysis.width,
                height=analysis.height,
                size_bytes=path.stat().st_size,
                hint=str(entry.get("hint") or ""),
                analysis=analysis,
            )
        )
    return items


def _sample_path(settings: Settings, asset_id: str) -> Path | None:
    for entry in _read_sample_index(settings):
        if str(entry.get("id") or "") != asset_id:
            continue
        filename = str(entry.get("file") or "")
        if not filename:
            return None
        path = settings.reference_samples_dir / filename
        return path if path.is_file() else None
    return None


def resolve_reference_assets(
    settings: Settings, references: list[ReferenceInput]
) -> list[ResolvedReference]:
    resolved: list[ResolvedReference] = []
    for item in references:
        if not _safe_id(item.asset_id):
            raise ReferenceError("잘못된 참고 이미지 ID입니다.")
        if item.asset_id.startswith("sample_"):
            path = _sample_path(settings, item.asset_id)
            if path is None:
                raise ReferenceError(
                    "샘플 참고 이미지를 찾을 수 없습니다. 샘플 목록을 새로고침해 주세요."
                )
            asset = list_sample_assets(settings)
            selected = next((entry for entry in asset if entry.id == item.asset_id), None)
            if selected is None:
                raise ReferenceError("샘플 참고 이미지를 찾을 수 없습니다.")
        else:
            path = settings.reference_uploads_dir / f"{item.asset_id}.png"
            if not path.is_file():
                raise ReferenceError(
                    "업로드한 참고 이미지를 찾을 수 없습니다. 다시 업로드해 주세요."
                )
            selected = upload_asset(settings, item.asset_id)
        resolved.append(ResolvedReference(input=item, path=path, asset=selected))
    return resolved


def usage_from_asset(asset: ReferenceAsset, item: ReferenceInput) -> ReferenceUsage:
    return ReferenceUsage(
        asset_id=asset.id,
        name=asset.name,
        url=asset.url,
        focus=item.focus,
        strength=round(float(item.strength), 3),
        analysis_summary=asset.analysis.summary,
    )


def _node_files(info: dict[str, Any] | None, node: str, field: str) -> list[str]:
    if not isinstance(info, dict):
        return []
    node_info = info.get(node)
    if not isinstance(node_info, dict):
        return []
    inputs = node_info.get("input") or {}
    required = inputs.get("required") or {}
    entry = required.get(field)
    if isinstance(entry, (list, tuple)) and entry and isinstance(entry[0], list):
        return [str(item) for item in entry[0]]
    return []


async def _object_info(comfy: ComfyClient, node: str) -> dict[str, Any] | None:
    try:
        return await comfy.get_object_info(node)
    except Exception:
        return None


async def get_reference_capabilities(
    settings: Settings, comfy: ComfyClient, checkpoint: str | None = None
) -> ReferenceCapabilities:
    node_names = [
        "IPAdapterUnifiedLoader",
        "IPAdapterAdvanced",
        "IPAdapterModelLoader",
        "CLIPVisionLoader",
    ]
    infos = await asyncio.gather(
        *[_object_info(comfy, name) for name in node_names],
        return_exceptions=False,
    )
    info_by_name: dict[str, dict[str, Any] | None] = dict(zip(node_names, infos))
    node_installed = bool(
        info_by_name.get("IPAdapterUnifiedLoader") and info_by_name.get("IPAdapterAdvanced")
    )
    advanced_node_installed = bool(info_by_name.get("IPAdapterAdvanced"))
    ipadapter_files = _node_files(
        info_by_name.get("IPAdapterModelLoader"), "IPAdapterModelLoader", "ipadapter_file"
    )
    clip_files = _node_files(
        info_by_name.get("CLIPVisionLoader"), "CLIPVisionLoader", "clip_name"
    )
    plus_model = any(_PLUS_RE.search(Path(name).name) for name in ipadapter_files)
    plus_face_model = any(_PLUS_FACE_RE.search(Path(name).name) for name in ipadapter_files)
    clip_vision_model = any(_CLIP_VISION_RE.search(Path(name).name) for name in clip_files)
    available = node_installed and plus_model and clip_vision_model

    install_dir = Path(settings.comfyui.main_path).expanduser().parent
    models_dir = Path(settings.comfyui.models_dir).expanduser()
    custom_nodes = install_dir / "custom_nodes"
    guidance_parts: list[str] = []
    if not node_installed:
        guidance_parts.append(
            "ComfyUI_IPAdapter_plus 커스텀 노드가 없습니다. "
            f"{custom_nodes}에 git clone한 뒤 ComfyUI를 재시작해 주세요."
        )
    if not plus_model:
        guidance_parts.append(
            f"IP-Adapter Plus SDXL 모델이 없습니다. {models_dir / 'ipadapter'}에 "
            "ip-adapter-plus_sdxl_vit-h.safetensors를 넣어 주세요."
        )
    if not clip_vision_model:
        guidance_parts.append(
            f"CLIP ViT-H 이미지 인코더가 없습니다. {models_dir / 'clip_vision'}에 "
            "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors를 넣어 주세요."
        )
    guidance = " ".join(guidance_parts)

    if checkpoint:
        if not is_sdxl_compatible(checkpoint):
            checkpoint_compatible = False
            checkpoint_note = (
                "선택한 체크포인트는 SDXL 호환 목록에 없습니다. IP-Adapter Plus는 SDXL 계열 "
                "체크포인트에서만 안정적으로 동작합니다. SDXL 1.0, Pony, NoobAI, Illustrious "
                "계열을 선택해 주세요."
            )
        else:
            checkpoint_compatible = True
            lowered = checkpoint.lower()
            if any(token in lowered for token in ("noob", "illustrious", "pony")):
                checkpoint_note = (
                    "SDXL 기반 애니메 체크포인트로 IP-Adapter Plus가 적용됩니다. 애니메 모델에 "
                    "실사 참고 사진을 강하게(0.8 이상) 넣으면 결과가 무너질 수 있으니 "
                    "0.4~0.7 강도를 권장합니다. 얼굴 동일성을 유지해야 하면 "
                    "InstantID/PuLID를 별도로 검토하세요."
                )
            else:
                checkpoint_note = (
                    "SDXL 기반 체크포인트로 IP-Adapter Plus가 적용됩니다. 참고 이미지의 "
                    "외형·화풍·구도를 새 이미지에 반영합니다."
                )
    else:
        checkpoint_compatible = None
        checkpoint_note = "SDXL 계열 체크포인트를 선택하면 호환성 정보를 표시합니다."

    return ReferenceCapabilities(
        available=available,
        node_installed=node_installed,
        advanced_node_installed=advanced_node_installed,
        plus_model=plus_model,
        plus_face_model=plus_face_model,
        clip_vision_model=clip_vision_model,
        ipadapter_models=sorted(ipadapter_files),
        clip_vision_models=sorted(clip_files),
        checkpoint=checkpoint,
        checkpoint_compatible=checkpoint_compatible,
        checkpoint_note=checkpoint_note,
        guidance=guidance,
        install_hint=(
            "ComfyUI Manager에서 IPAdapter Plus를 설치하거나, custom_nodes에서 "
            "`git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus.git` 후 재시작하세요. "
            "모델 파일은 Hugging Face h94/IP-Adapter 저장소에서 받을 수 있습니다."
        ),
        instantid_note=(
            "InstantID는 InsightFace 얼굴 임베딩과 SDXL ControlNet을 사용해 인물 얼굴을 "
            "강하게 고정합니다. 별도 커스텀 노드·모델·insightface 설치가 필요하며, 단일 인물 "
            "초상에 적합합니다. 이번 구현에는 포함하지 않았습니다."
        ),
        pulid_note=(
            "PuLID는 SDXL UNet에 얼굴 특징을 주입해 정체성을 유지합니다. 별도 노드와 "
            "EVA-CLIP/얼굴 인식 모델이 필요하며, 설치 난이도와 VRAM 사용량이 IP-Adapter보다 "
            "높습니다. 얼굴 동일성이 핵심일 때 별도 검토 대상입니다."
        ),
        max_references=int(settings.generation.reference_max_references),
        presets=["PLUS (high strength)", "PLUS FACE (portraits)"],
    )

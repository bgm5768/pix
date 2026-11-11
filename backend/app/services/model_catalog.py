from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.schemas.models import ModelCategory, ModelFile

# ComfyUI can list every file in the checkpoints folder, including 3D,
# segmentation and video models.  These keywords flag files that cannot be
# used by the SDXL text-to-image workflow.
_NON_SDXL_KEYWORDS = (
    "hunyuan",
    "sam3",
    "sam_",
    "svd",
    "flux",
    "sd3",
    "stable-diffusion-3",
    "wan2",
    "ltxv",
    "kolors",
    "auraflow",
    "pixart",
    "playground",
    "cosxl",
    "controlnet",
    "ip-adapter",
    "clip_vision",
    "unet",
)

MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth"}

# Files that target the pixel-art pipeline. They stay hidden on the image
# generator page, and generic SDXL files stay hidden on the pixel page.
_PIXEL_KEYWORDS = (
    "pixel",
    "sprite",
    "8bit",
    "8-bit",
    "dot",
    "retro",
    "pixelart",
)


def is_sdxl_compatible(name: str) -> bool:
    lowered = name.lower()
    return not any(keyword in lowered for keyword in _NON_SDXL_KEYWORDS)


def model_category(name: str) -> ModelCategory:
    """Split checkpoints/LoRAs into pixel, image, and unsupported buckets."""
    if not is_sdxl_compatible(name):
        return "other"
    lowered = name.lower()
    if any(keyword in lowered for keyword in _PIXEL_KEYWORDS):
        return "pixel"
    return "image"


def _normalize(name: str) -> str:
    return name.replace("\\", "/").strip("/")


def _model_dir(settings: Settings, kind: str) -> Path:
    base = Path(settings.comfyui.models_dir)
    return base / ("checkpoints" if kind == "checkpoint" else "loras")


def _local_sizes(settings: Settings, kind: str) -> dict[str, int]:
    directory = _model_dir(settings, kind)
    sizes: dict[str, int] = {}
    if not directory.exists():
        return sizes
    try:
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in MODEL_SUFFIXES:
                try:
                    relative = path.relative_to(directory).as_posix()
                except ValueError:
                    relative = path.name
                sizes[relative] = path.stat().st_size
    except OSError:
        return sizes
    return sizes


def model_files(settings: Settings, kind: str, names: set[str]) -> list[ModelFile]:
    sizes = _local_sizes(settings, kind)
    items: list[ModelFile] = []
    for name in sorted(names):
        normalized = _normalize(name)
        items.append(
            ModelFile(
                name=name,
                size_bytes=sizes.get(normalized, 0),
                compatible=is_sdxl_compatible(name),
                category=model_category(name),
            )
        )
    return items


def resolve_model_path(settings: Settings, kind: str, name: str) -> Path:
    directory = _model_dir(settings, kind)
    relative = Path(_normalize(name))
    return directory / relative

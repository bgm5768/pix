from __future__ import annotations

import io
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from app.config import PROJECT_ROOT, Settings
from app.schemas.models import (
    OutputItem,
    OutputsResponse,
    QualityCheck,
    ReferenceUsage,
    ResultInfo,
)
from app.services.postprocess import PostProcessResult

_ASSET_MODES = {"icon", "character", "object", "tile"}
_RESIZE_FILTERS = {"nearest", "box", "lanczos"}


def _asset_mode(value: Any) -> str:
    value = str(value or "icon")
    return value if value in _ASSET_MODES else "icon"


def _resize_filter(value: Any) -> str:
    value = str(value or "nearest")
    return value if value in _RESIZE_FILTERS else "nearest"


def _quality_checks(value: Any) -> list[QualityCheck]:
    checks: list[QualityCheck] = []
    if not isinstance(value, list):
        return checks
    for item in value:
        if isinstance(item, QualityCheck):
            checks.append(item)
        elif isinstance(item, dict):
            try:
                checks.append(QualityCheck.model_validate(item))
            except Exception:
                continue
    return checks

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def _safe_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError("잘못된 작업 ID입니다.")
    return job_id


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_png(path: Path, image_bytes: bytes) -> None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            image.convert("RGB").save(path, format="PNG", optimize=True)
    except Exception:
        # Keep the raw bytes if Pillow cannot decode, so the user can inspect it.
        path.write_bytes(image_bytes)


def save_original(settings: Settings, job_id: str, image_bytes: bytes) -> Path:
    _safe_job_id(job_id)
    path = settings.originals_dir / f"{job_id}_original.png"
    _write_png(path, image_bytes)
    return path


def save_candidate_original(
    settings: Settings, job_id: str, index: int, image_bytes: bytes
) -> Path:
    """Preserve every generated candidate, not only the selected one."""
    _safe_job_id(job_id)
    path = settings.candidates_dir / f"{job_id}_c{int(index)}.png"
    _write_png(path, image_bytes)
    return path


def save_pixel_result(
    settings: Settings,
    job_id: str,
    result: PostProcessResult,
    output_size: int,
) -> tuple[Path, Path]:
    _safe_job_id(job_id)
    pixel_path = settings.pixel_dir / f"{job_id}_pixel_{output_size}.png"
    preview_path = settings.previews_dir / f"{job_id}_preview_{output_size}.png"
    result.image.save(pixel_path, format="PNG", optimize=True)
    result.preview.save(preview_path, format="PNG", optimize=True)
    return pixel_path, preview_path


def save_image_result(
    settings: Settings,
    job_id: str,
    image: Image.Image,
    image_size: int,
) -> tuple[Path, Path]:
    """Save the native SDXL image and a smaller gallery/result preview."""
    _safe_job_id(job_id)
    image_path = settings.images_dir / f"{job_id}_image_{image_size}.png"
    preview_path = settings.image_previews_dir / f"{job_id}_image_preview_{image_size}.png"
    rgb = image.convert("RGB")
    rgb.save(image_path, format="PNG", optimize=True)
    preview = rgb.copy()
    preview.thumbnail((640, 640), Image.Resampling.LANCZOS)
    preview.save(preview_path, format="PNG", optimize=True)
    return image_path, preview_path


def save_metadata(settings: Settings, job_id: str, data: dict[str, Any]) -> Path:
    _safe_job_id(job_id)
    path = settings.metadata_dir / f"{job_id}.json"
    payload = {"job_id": job_id, "saved_at": _iso_now(), **data}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def load_metadata(settings: Settings, job_id: str) -> dict[str, Any] | None:
    _safe_job_id(job_id)
    path = settings.metadata_dir / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def result_info(
    settings: Settings,
    job_id: str,
    result: PostProcessResult,
    output_size: int,
    postprocess: str = "quantize",
    cutout_path: Path | None = None,
    crop_path: Path | None = None,
    mode: str = "icon",
    candidates_generated: int = 1,
    candidate_index: int = 0,
) -> ResultInfo:
    _safe_job_id(job_id)
    if postprocess not in {"quantize", "nearest", "posterize"}:
        postprocess = "quantize"
    cutout_url = f"/files/cutouts/{cutout_path.name}" if cutout_path is not None else None
    crop_url = f"/files/crops/{crop_path.name}" if crop_path is not None else None
    return ResultInfo(
        original_url=f"/files/originals/{job_id}_original.png",
        cutout_url=cutout_url,
        crop_url=crop_url,
        pixel_url=f"/files/pixel_art/{job_id}_pixel_{output_size}.png",
        preview_url=f"/files/previews/{job_id}_preview_{output_size}.png",
        download_url=f"/api/download/{job_id}",
        width=output_size,
        height=output_size,
        preview_scale=result.preview_scale,
        palette_colors=result.palette_used,
        transparent=result.image.mode == "RGBA",
        postprocess=postprocess,  # type: ignore[arg-type]
        mode=_asset_mode(mode),  # type: ignore[arg-type]
        subject_fill=result.subject_fill,
        resize_filter=_resize_filter(result.resize_filter),  # type: ignore[arg-type]
        quality=[QualityCheck(**asdict(check)) for check in result.quality],
        warnings=result.warnings,
        candidates_generated=max(1, int(candidates_generated)),
        candidate_index=max(0, int(candidate_index)),
        candidate_score=float(result.candidate_score),
        panel_suspected=bool(result.panel_suspected),
    )


def image_result_info(
    settings: Settings,
    job_id: str,
    image_size: int,
    mode: str = "icon",
    candidates_generated: int = 1,
    candidate_index: int = 0,
    warnings: list[str] | None = None,
) -> ResultInfo:
    """Result metadata for the image generator page (no pixel postprocess)."""
    return native_result_info(
        settings,
        job_id,
        image_size,
        kind="image",
        mode=mode,
        candidates_generated=candidates_generated,
        candidate_index=candidate_index,
        warnings=warnings,
    )


def reference_result_info(
    settings: Settings,
    job_id: str,
    image_size: int,
    references: list[ReferenceUsage] | None = None,
    mode: str = "icon",
    candidates_generated: int = 1,
    candidate_index: int = 0,
    warnings: list[str] | None = None,
) -> ResultInfo:
    """Result metadata for the reference-conditioned image page."""
    return native_result_info(
        settings,
        job_id,
        image_size,
        kind="reference",
        references=references,
        mode=mode,
        candidates_generated=candidates_generated,
        candidate_index=candidate_index,
        warnings=warnings,
    )


def native_result_info(
    settings: Settings,
    job_id: str,
    image_size: int,
    kind: str = "image",
    references: list[ReferenceUsage] | None = None,
    mode: str = "icon",
    candidates_generated: int = 1,
    candidate_index: int = 0,
    warnings: list[str] | None = None,
) -> ResultInfo:
    """Shared result metadata for native SDXL pages (image/reference)."""
    _safe_job_id(job_id)
    if kind not in {"image", "reference"}:
        kind = "image"
    image_url = f"/files/images/{job_id}_image_{image_size}.png"
    preview_url = f"/files/image_previews/{job_id}_image_preview_{image_size}.png"
    return ResultInfo(
        original_url=f"/files/originals/{job_id}_original.png",
        preview_url=preview_url,
        image_url=image_url,
        image_preview_url=preview_url,
        download_url=f"/api/download/{job_id}?kind={kind}",
        width=int(image_size),
        height=int(image_size),
        preview_scale=1,
        palette_colors=0,
        transparent=False,
        postprocess="quantize",
        mode=_asset_mode(mode),  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        quality=[],
        warnings=list(warnings or []),
        candidates_generated=max(1, int(candidates_generated)),
        candidate_index=max(0, int(candidate_index)),
        candidate_score=0.0,
        panel_suspected=False,
        references=list(references or []),
    )


def _parse_size_from_name(name: str) -> int | None:
    match = re.search(r"_pixel_(\d+)\.png$", name)
    return int(match.group(1)) if match else None


def _parse_image_size_from_name(name: str) -> int | None:
    match = re.search(r"_image_(\d+)\.png$", name)
    return int(match.group(1)) if match else None


def _created_at(meta: dict[str, Any], path: Path) -> datetime:
    created_raw = meta.get("created_at") or meta.get("saved_at")
    try:
        created_at = datetime.fromisoformat(str(created_raw))
    except (TypeError, ValueError):
        created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at


def _list_pixel_outputs(settings: Settings, limit: int) -> OutputsResponse:
    files = sorted(
        settings.pixel_dir.glob("*_pixel_*.png"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    items: list[OutputItem] = []
    for pixel_path in files[:limit]:
        job_id = pixel_path.name.split("_pixel_")[0]
        if not _JOB_ID_RE.fullmatch(job_id):
            continue
        size = _parse_size_from_name(pixel_path.name)
        if size is None:
            continue
        meta = load_metadata(settings, job_id) or {}
        if str((meta.get("request") or {}).get("kind") or "pixel") != "pixel":
            continue
        created_at = _created_at(meta, pixel_path)

        original_path = settings.originals_dir / f"{job_id}_original.png"
        preview_path = settings.previews_dir / f"{job_id}_preview_{size}.png"
        cutout_path = settings.cutouts_dir / f"{job_id}_cutout.png"
        crop_path = settings.crops_dir / f"{job_id}_crop.png"
        request = meta.get("request") or {}
        postprocess = str(meta.get("postprocess") or "quantize")
        if postprocess not in {"quantize", "nearest", "posterize"}:
            postprocess = "quantize"
        items.append(
            OutputItem(
                job_id=job_id,
                pixel_url=f"/files/pixel_art/{pixel_path.name}",
                preview_url=f"/files/previews/{preview_path.name}",
                original_url=f"/files/originals/{original_path.name}",
                cutout_url=f"/files/cutouts/{cutout_path.name}" if cutout_path.exists() else None,
                crop_url=f"/files/crops/{crop_path.name}" if crop_path.exists() else None,
                download_url=f"/api/download/{job_id}",
                width=size,
                height=size,
                created_at=created_at,
                prompt=str(request.get("prompt") or meta.get("prompt_used") or ""),
                seed=meta.get("seed_used"),
                transparent=bool(meta.get("transparent", False)),
                postprocess=postprocess,  # type: ignore[arg-type]
                mode=_asset_mode(request.get("mode") or meta.get("mode")),  # type: ignore[arg-type]
                kind="pixel",
                output_size=size,
                palette_colors=int(meta.get("palette_used") or 0),
                subject_fill=float(meta.get("subject_fill") or 0.0),
                resize_filter=_resize_filter(meta.get("resize_filter")),  # type: ignore[arg-type]
                quality=_quality_checks(meta.get("quality")),
                candidates_generated=int(meta.get("candidates_generated") or 1),
                candidate_index=int(meta.get("selected_candidate") or 0),
                candidate_score=float(meta.get("candidate_score") or 0.0),
                panel_suspected=bool(meta.get("panel_suspected", False)),
            )
        )
    return OutputsResponse(items=items, total=len(files))


def _load_references(meta: dict[str, Any]) -> list[ReferenceUsage]:
    raw = meta.get("references")
    if not isinstance(raw, list):
        return []
    items: list[ReferenceUsage] = []
    for entry in raw:
        if isinstance(entry, ReferenceUsage):
            items.append(entry)
        elif isinstance(entry, dict):
            try:
                items.append(ReferenceUsage.model_validate(entry))
            except Exception:
                continue
    return items


def _list_native_outputs(settings: Settings, limit: int, kind: str) -> OutputsResponse:
    files = sorted(
        settings.images_dir.glob("*_image_*.png"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    items: list[OutputItem] = []
    for image_path in files[:limit]:
        job_id = image_path.name.split("_image_")[0]
        if not _JOB_ID_RE.fullmatch(job_id):
            continue
        size = _parse_image_size_from_name(image_path.name)
        if size is None:
            continue
        meta = load_metadata(settings, job_id) or {}
        meta_kind = str(meta.get("kind") or (meta.get("request") or {}).get("kind") or "image")
        if meta_kind != kind:
            continue
        created_at = _created_at(meta, image_path)

        original_path = settings.originals_dir / f"{job_id}_original.png"
        preview_path = settings.image_previews_dir / f"{job_id}_image_preview_{size}.png"
        preview_url = (
            f"/files/image_previews/{preview_path.name}"
            if preview_path.exists()
            else f"/files/images/{image_path.name}"
        )
        request = meta.get("request") or {}
        items.append(
            OutputItem(
                job_id=job_id,
                image_url=f"/files/images/{image_path.name}",
                preview_url=preview_url,
                original_url=f"/files/originals/{original_path.name}",
                download_url=f"/api/download/{job_id}?kind={kind}",
                width=size,
                height=size,
                created_at=created_at,
                prompt=str(request.get("prompt") or meta.get("prompt_used") or ""),
                seed=meta.get("seed_used"),
                transparent=False,
                postprocess="quantize",
                mode=_asset_mode(request.get("mode") or meta.get("mode")),  # type: ignore[arg-type]
                kind=kind,  # type: ignore[arg-type]
                output_size=size,
                palette_colors=0,
                subject_fill=0.0,
                resize_filter="nearest",
                quality=[],
                candidates_generated=int(meta.get("candidates_generated") or 1),
                candidate_index=int(meta.get("selected_candidate") or 0),
                candidate_score=0.0,
                panel_suspected=False,
                references=_load_references(meta),
            )
        )
    return OutputsResponse(items=items, total=len(files))


def list_outputs(settings: Settings, limit: int = 30, kind: str = "pixel") -> OutputsResponse:
    limit = max(1, min(100, int(limit)))
    if kind in {"image", "reference"}:
        return _list_native_outputs(settings, limit, kind)
    return _list_pixel_outputs(settings, limit)


def find_download_path(settings: Settings, job_id: str, kind: str = "pixel") -> Path | None:
    _safe_job_id(job_id)
    if kind in {"image", "reference"}:
        candidates = sorted(
            settings.images_dir.glob(f"{job_id}_image_*.png"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None
    candidates = sorted(
        settings.pixel_dir.glob(f"{job_id}_pixel_*.png"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def delete_output(settings: Settings, job_id: str) -> list[str]:
    """Remove every artifact belonging to a job.

    Files are named ``{job_id}_...`` in the output folders and
    ``{job_id}.json`` in metadata, so the job id is enough to find originals,
    candidates, cutouts, crops, previews, final images, and metadata.
    """
    _safe_job_id(job_id)
    directories = (
        settings.originals_dir,
        settings.pixel_dir,
        settings.previews_dir,
        settings.images_dir,
        settings.image_previews_dir,
        settings.cutouts_dir,
        settings.crops_dir,
        settings.candidates_dir,
    )
    removed: list[str] = []
    for directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob(f"{job_id}_*")):
            if not path.is_file():
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed.append(_display_path(path))
    metadata_path = settings.metadata_dir / f"{job_id}.json"
    if metadata_path.is_file():
        try:
            metadata_path.unlink()
        except OSError:
            pass
        else:
            removed.append(_display_path(metadata_path))
    return removed


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)

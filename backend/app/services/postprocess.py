from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from scipy import ndimage

from app.config import GenerationConfig

logger = logging.getLogger("pixelforge.postprocess")

_REMBG_SESSION = None
_REMBG_LOCK = threading.Lock()
_REMBG_DISABLED = False

_RESAMPLE = {
    "nearest": Image.Resampling.NEAREST,
    "box": Image.Resampling.BOX,
    "lanczos": Image.Resampling.LANCZOS,
}


@dataclass
class QualityCheck:
    key: str
    label: str
    passed: bool
    value: str = ""
    message: str = ""


@dataclass
class PostProcessResult:
    image: Image.Image
    preview: Image.Image
    preview_scale: int
    palette_used: int
    warnings: list[str] = field(default_factory=list)
    background_removed_ratio: float = 0.0
    background_method: str = "none"
    cutout: Image.Image | None = None
    cropped: Image.Image | None = None
    quality: list[QualityCheck] = field(default_factory=list)
    subject_fill: float = 0.0
    subject_area_ratio: float = 0.0
    subject_components: int = 0
    largest_component_share: float = 0.0
    subject_bbox: tuple[int, int, int, int] | None = None
    source_clipped: bool = False
    mask_method: str = "none"
    resize_filter: str = "nearest"
    output_size: int = 0
    fill_target: float = 0.0
    centre_offset: float = 0.0
    touches_edge: bool = False
    panel_suspected: bool = False
    panel_score: float = 0.0
    candidate_score: float = 0.0


# ---------------------------------------------------------------------------
# Background / subject extraction
# ---------------------------------------------------------------------------


def _get_rembg_session(generation: GenerationConfig):
    global _REMBG_SESSION, _REMBG_DISABLED
    if not generation.rembg_enabled or _REMBG_DISABLED:
        return None
    with _REMBG_LOCK:
        if _REMBG_SESSION is None:
            try:
                from rembg import new_session

                _REMBG_SESSION = new_session(generation.rembg_model)
            except Exception:
                logger.exception("rembg session could not be created")
                _REMBG_DISABLED = True
                return None
    return _REMBG_SESSION


def _rembg_mask(original: Image.Image, generation: GenerationConfig) -> tuple[np.ndarray, float] | None:
    """Run u2net on a padded copy of the image.

    u2net interprets pixel-art icons that fill the frame as a single texture and
    returns an almost fully opaque mask. Padding the image with the background
    colour gives the network enough context to find the actual silhouette.
    """
    session = _get_rembg_session(generation)
    if session is None:
        return None
    try:
        from rembg import remove

        rgb = original.convert("RGB")
        arr = np.array(rgb, dtype=np.uint8)
        pad_ratio = max(0.0, float(getattr(generation, "rembg_pad_ratio", 0.25)))
        pad = int(round(max(rgb.size) * pad_ratio))
        corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]], dtype=np.float32)
        border_colour = tuple(int(value) for value in np.median(corners, axis=0))
        if pad > 0:
            canvas = Image.new("RGB", (rgb.width + pad * 2, rgb.height + pad * 2), border_colour)
            canvas.paste(rgb, (pad, pad))
        else:
            canvas = rgb
        with _REMBG_LOCK:
            result = remove(
                canvas,
                session=session,
                alpha_matting=False,
                post_process_mask=False,
            )
        if not isinstance(result, Image.Image):
            return None
        alpha = np.asarray(result.convert("RGBA"), dtype=np.uint8)[:, :, 3]
        if pad > 0:
            alpha = alpha[pad : pad + rgb.height, pad : pad + rgb.width]
        mask = alpha >= 128
        ratio = float(mask.mean())
        if mask.any():
            ys, xs = np.where(mask)
            width = int(xs.max() - xs.min() + 1)
            height = int(ys.max() - ys.min() + 1)
        else:
            width = height = 0
        min_ratio = float(getattr(generation, "rembg_min_ratio", 0.02))
        max_ratio = float(getattr(generation, "rembg_max_ratio", 0.985))
        min_side = min(rgb.size) * 0.05
        if (
            ratio < min_ratio
            or ratio > max_ratio
            or width < min_side
            or height < min_side
        ):
            return None
        return mask, ratio
    except Exception:
        logger.exception("rembg segmentation failed")
        return None


def _border_key_mask(original: Image.Image, generation: GenerationConfig) -> tuple[np.ndarray, float, tuple[int, int, int]] | None:
    """Flood-fill the flat border colour from the image edges.

    Returns (background_mask, dominance, dominant_color). The mask is only
    trusted when the border is dominated by one colour; otherwise a generated
    scene background would be keyed out incorrectly.
    """
    arr = np.array(original.convert("RGB"), dtype=np.int32)
    height, width, _ = arr.shape
    border = np.concatenate([arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]], axis=0)
    keys = border // 24
    unique, counts = np.unique(keys, axis=0, return_counts=True)
    if len(unique) == 0:
        return None
    order = int(np.argmax(counts))
    dominant = unique[order].astype(np.int32) * 24 + 12
    dominance = float(counts[order]) / max(1, int(counts.sum()))
    if dominance < float(getattr(generation, "background_key_min_dominance", 0.5)):
        return None
    tolerance = float(getattr(generation, "background_key_tolerance", 28))
    distance = np.sqrt(np.sum((arr - dominant) ** 2, axis=2))
    similar = distance <= tolerance
    labels, _ = ndimage.label(similar, structure=np.ones((3, 3), dtype=bool))
    border_labels = set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
    border_labels |= set(labels[:, 0].tolist()) | set(labels[:, -1].tolist())
    border_labels.discard(0)
    if not border_labels:
        return None
    background = np.isin(labels, list(border_labels))
    colour = tuple(int(value) for value in dominant)
    return background, dominance, colour


def _legacy_background_mask(rgb: np.ndarray, tolerance: float = 45.0) -> np.ndarray:
    """Previous border-colour flood fill, kept as a final fallback."""
    height, width, _ = rgb.shape
    pixels = rgb.astype(np.int32)
    border = np.concatenate(
        [pixels[0, :, :], pixels[-1, :, :], pixels[:, 0, :], pixels[:, -1, :]], axis=0
    )
    keys = border // 16
    unique, counts = np.unique(keys, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:6]
    candidates = unique[order].astype(np.int32) * 16 + 8
    corners = np.array(
        [pixels[0, 0], pixels[0, -1], pixels[-1, 0], pixels[-1, -1]], dtype=np.int32
    )
    candidates = np.vstack([candidates, corners])
    diff = pixels[:, :, None, :] - candidates[None, None, :, :]
    dist2 = np.sum(diff * diff, axis=3)
    similar = np.min(dist2, axis=2) <= int(tolerance * tolerance)
    labels, _ = ndimage.label(similar, structure=np.ones((3, 3), dtype=bool))
    border_labels = set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
    border_labels |= set(labels[:, 0].tolist()) | set(labels[:, -1].tolist())
    border_labels.discard(0)
    return np.isin(labels, list(border_labels))


def _component_stats(mask: np.ndarray) -> list[dict[str, Any]]:
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    stats: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        component = labels == index
        area = int(component.sum())
        if area == 0:
            continue
        ys, xs = np.where(component)
        stats.append(
            {
                "index": index,
                "area": area,
                "mask": component,
                "bbox": (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                "centre": (float(xs.mean()), float(ys.mean())),
            }
        )
    stats.sort(key=lambda item: item["area"], reverse=True)
    return stats


def _bbox_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0)
    dy = max(by0 - ay1, ay0 - by1, 0)
    return float((dx * dx + dy * dy) ** 0.5)


def _select_subject(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Keep the main object and discard duplicate objects / far-away fragments.

    Detached details that overlap or touch the main bounding box (a roof piece,
    a sword, a wheel) are kept. A second copy of the same object in a sprite
    sheet is usually a similar-sized component outside that box and is dropped.
    """
    height, width = mask.shape
    stats = _component_stats(mask)
    if not stats:
        return mask, {
            "raw_components": 0,
            "final_components": 0,
            "main_share": 0.0,
            "bbox": (0, 0, width, height),
        }
    image_centre = np.array([width / 2.0, height / 2.0])
    diagonal = float((width * width + height * height) ** 0.5)

    def score(item: dict[str, Any]) -> float:
        centre = np.array(item["centre"])
        centrality = 1.0 - float(np.linalg.norm(centre - image_centre)) / max(1.0, diagonal / 2.0)
        return float(item["area"]) * (1.0 + 0.12 * max(0.0, centrality))

    main = max(stats, key=score)
    main_area = int(main["area"])
    main_box = main["bbox"]
    kept = main["mask"].copy()
    merged_components = 1

    for item in stats:
        if item is main:
            continue
        area = int(item["area"])
        if area < max(6, int(main_area * 0.002)):
            continue
        box = item["bbox"]
        overlaps = _bbox_distance(box, main_box) == 0.0
        # Only keep detached details that are clearly subordinate to the main
        # object. A second object/character in a sprite sheet is usually a
        # similar-sized component, even when its bounding box touches the main
        # one, so a generous 60% threshold would let duplicates through.
        if overlaps and area < main_area * 0.35:
            kept |= item["mask"]
            merged_components += 1
        elif _bbox_distance(box, main_box) <= diagonal * 0.015 and area < main_area * 0.25:
            kept |= item["mask"]
            merged_components += 1

    kept = ndimage.binary_fill_holes(kept)
    kept = ndimage.binary_closing(kept, structure=np.ones((3, 3), dtype=bool), iterations=1)

    # Drop any isolated specks created by closing.
    final_stats = _component_stats(kept)
    if final_stats:
        largest = final_stats[0]["area"]
        cleaned = np.zeros_like(kept)
        for item in final_stats:
            if item["area"] >= max(4, int(largest * 0.002)):
                cleaned |= item["mask"]
        kept = cleaned

    ys, xs = np.where(kept)
    if len(ys) == 0:
        return mask, {
            "raw_components": len(stats),
            "final_components": 0,
            "main_share": 0.0,
            "bbox": (0, 0, width, height),
        }
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    final_stats = _component_stats(kept)
    largest = final_stats[0]["area"] if final_stats else int(kept.sum())
    return kept, {
        "raw_components": len(stats),
        "merged_components": merged_components,
        "final_components": len(final_stats),
        "main_share": float(largest) / max(1, int(kept.sum())),
        "bbox": bbox,
    }


# ---------------------------------------------------------------------------
# Pixel rendering
# ---------------------------------------------------------------------------


def _resize_rgba(image: Image.Image, size: tuple[int, int], resample) -> np.ndarray:
    """Resize RGBA without dark/white fringes and return (RGB, alpha)."""
    if resample is Image.Resampling.NEAREST:
        resized = image.resize(size, Image.Resampling.NEAREST)
        arr = np.asarray(resized, dtype=np.uint8)
        return arr[:, :, :3].copy(), arr[:, :, 3]
    arr = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4] / 255.0
    premultiplied = rgb * alpha

    def resize_channel(channel: np.ndarray) -> np.ndarray:
        picture = Image.fromarray(channel.astype(np.float32))
        return np.asarray(picture.resize(size, resample), dtype=np.float32)

    red = resize_channel(premultiplied[:, :, 0])
    green = resize_channel(premultiplied[:, :, 1])
    blue = resize_channel(premultiplied[:, :, 2])
    alpha_small = np.clip(resize_channel(alpha[:, :, 0] * 255.0) / 255.0, 0.0, 1.0)
    safe = np.maximum(alpha_small, 1e-4)[:, :, None]
    rgb_small = np.clip(np.stack([red, green, blue], axis=2) / safe, 0, 255).astype(np.uint8)
    return rgb_small, (alpha_small * 255.0).astype(np.uint8)


def _remove_isolated(mask: np.ndarray) -> np.ndarray:
    """Clear opaque pixels with no 4-connected opaque neighbour."""
    if not mask.any():
        return mask
    padded = np.pad(mask, 1, constant_values=False)
    neighbours = (
        padded[:-2, 1:-1].astype(np.uint8)
        + padded[2:, 1:-1].astype(np.uint8)
        + padded[1:-1, :-2].astype(np.uint8)
        + padded[1:-1, 2:].astype(np.uint8)
    )
    return mask & (neighbours > 0)


def _quantize(image: Image.Image, colors: int) -> Image.Image:
    colors = max(2, min(64, int(colors)))
    arr = np.array(image, dtype=np.uint8)
    if arr.ndim != 3:
        return image
    alpha = arr[:, :, 3] if arr.shape[2] == 4 else None
    rgb = arr[:, :, :3]
    mask = alpha > 0 if alpha is not None else np.ones(rgb.shape[:2], dtype=bool)
    if not mask.any():
        return image
    work = rgb.copy()
    if (~mask).any():
        work[~mask] = np.median(rgb[mask], axis=0).astype(np.uint8)
    quantized = Image.fromarray(work).quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    result = np.array(quantized.convert("RGB"), dtype=np.uint8)
    if alpha is not None:
        result = np.dstack([result, np.where(mask, 255, 0).astype(np.uint8)])
        return Image.fromarray(result, mode="RGBA")
    return Image.fromarray(result, mode="RGB")


def _despeckle(image: Image.Image) -> Image.Image:
    """Remove lone pixels and majority-replace 3-of-4 neighbour noise.

    Unlike the previous implementation this never replaces a pixel merely
    because its four neighbours differ; that caused detail to melt away on
    32x32 outputs.
    """
    arr = np.array(image, dtype=np.uint8)
    if arr.ndim != 3:
        return image
    alpha = arr[:, :, 3] if arr.shape[2] == 4 else None
    mask = alpha > 0 if alpha is not None else np.ones(arr.shape[:2], dtype=bool)
    mask = _remove_isolated(mask)
    rgb = arr[:, :, :3].copy()
    height, width = mask.shape
    for _ in range(2):
        changed = False
        result = rgb.copy()
        for y in range(height):
            for x in range(width):
                if not mask[y, x]:
                    continue
                neighbours: list[np.ndarray] = []
                if y > 0 and mask[y - 1, x]:
                    neighbours.append(rgb[y - 1, x])
                if y + 1 < height and mask[y + 1, x]:
                    neighbours.append(rgb[y + 1, x])
                if x > 0 and mask[y, x - 1]:
                    neighbours.append(rgb[y, x - 1])
                if x + 1 < width and mask[y, x + 1]:
                    neighbours.append(rgb[y, x + 1])
                if len(neighbours) < 3:
                    continue
                values, counts = np.unique(np.stack(neighbours), axis=0, return_counts=True)
                if len(values) == 1:
                    continue
                best = values[int(np.argmax(counts))]
                if int(counts.max()) >= 3 and not np.array_equal(best, rgb[y, x]):
                    result[y, x] = best
                    changed = True
        rgb = result
        if not changed:
            break
    if alpha is not None:
        return Image.fromarray(
            np.dstack([rgb, np.where(mask, 255, 0).astype(np.uint8)]), mode="RGBA"
        )
    return Image.fromarray(rgb, mode="RGB")


def _preview_scale(size: int) -> int:
    return max(1, 512 // size)


def _count_palette(image: Image.Image) -> int:
    arr = np.asarray(image)
    if arr.ndim != 3:
        return 0
    if arr.shape[2] == 4:
        opaque = arr[arr[:, :, 3] > 0][:, :3]
    else:
        opaque = arr.reshape(-1, 3)
    if opaque.size == 0:
        return 0
    return int(np.unique(opaque, axis=0).shape[0])


def _subject_metrics_from_mask(mask: np.ndarray) -> dict[str, Any]:
    if not mask.any():
        return {
            "bbox": None,
            "bbox_width": 0,
            "bbox_height": 0,
            "fill": 0.0,
            "area_ratio": 0.0,
            "centre_offset": 0.0,
            "components": 0,
            "largest_share": 0.0,
            "touches_edge": False,
        }
    ys, xs = np.where(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    height, width = mask.shape
    bbox_w, bbox_h = x1 - x0, y1 - y0
    stats = _component_stats(mask)
    largest = stats[0]["area"] if stats else int(mask.sum())
    centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    offset = float(((centre[0] - width / 2.0) ** 2 + (centre[1] - height / 2.0) ** 2) ** 0.5)
    touches = x0 <= 0 or y0 <= 0 or x1 >= width or y1 >= height
    return {
        "bbox": (x0, y0, x1, y1),
        "bbox_width": bbox_w,
        "bbox_height": bbox_h,
        "fill": max(bbox_w, bbox_h) / max(1, width),
        "area_ratio": float(mask.mean()),
        "centre_offset": offset,
        "components": len(stats),
        "largest_share": float(largest) / max(1, int(mask.sum())),
        "touches_edge": bool(touches),
    }


def _panel_metrics(rgb: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    """Estimate whether the extracted subject includes a card/panel background.

    A card or panel usually has a nearly rectangular alpha footprint, a large
    flat light area, and a uniform border band.  This is deliberately a soft
    score: uncertain cases produce a warning and are re-ranked, never deleted.
    """
    if not mask.any():
        return {
            "rectangularity": 0.0,
            "light_fraction": 0.0,
            "border_uniformity": 0.0,
            "border_std": 0.0,
            "square_ratio": 0.0,
            "panel_score": 0.0,
        }
    ys, xs = np.where(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    bbox_w, bbox_h = max(1, x1 - x0), max(1, y1 - y0)
    bbox_area = max(1, bbox_w * bbox_h)
    rectangularity = float(mask.sum()) / bbox_area
    square_ratio = min(bbox_w, bbox_h) / max(bbox_w, bbox_h)

    pixels = rgb[mask]
    if pixels.size == 0:
        light_fraction = 0.0
    else:
        light_fraction = float(
            ((pixels.min(axis=1) > 170) & ((pixels.max(axis=1) - pixels.min(axis=1)) < 45)).mean()
        )

    # Sample a 3px band just inside the bounding box.  Only opaque pixels are
    # used so transparent padding cannot make a card look uniform.
    bands: list[np.ndarray] = []
    for inset in (1, 2, 3):
        top, bottom = y0 + inset, y1 - inset
        left, right = x0 + inset, x1 - inset
        if top >= bottom or left >= right:
            continue
        for y in (top, bottom - 1):
            if y0 <= y < y1:
                row_mask = mask[y, left:right]
                if row_mask.any():
                    bands.append(rgb[y, left:right][row_mask])
        for x in (left, right - 1):
            if x0 <= x < x1:
                col_mask = mask[top:bottom, x]
                if col_mask.any():
                    bands.append(rgb[top:bottom, x][col_mask])
    if bands:
        border = np.concatenate(bands, axis=0).astype(np.float32)
        if border.size:
            median = np.median(border, axis=0)
            distances = np.linalg.norm(border - median, axis=1)
            border_uniformity = float((distances <= 14.0).mean())
            border_std = float(border.std(axis=0).mean())
        else:
            border_uniformity = 0.0
            border_std = 0.0
    else:
        border_uniformity = 0.0
        border_std = 0.0

    rect_score = float(np.clip((rectangularity - 0.88) / 0.12, 0.0, 1.0))
    light_score = float(np.clip((light_fraction - 0.15) / 0.45, 0.0, 1.0))
    uniform_score = float(np.clip((border_uniformity - 0.50) / 0.45, 0.0, 1.0))
    uniform_score *= float(np.clip((12.0 - border_std) / 10.0, 0.0, 1.0))
    panel_score = 0.30 * rect_score + 0.50 * light_score + 0.20 * uniform_score

    return {
        "rectangularity": round(rectangularity, 4),
        "light_fraction": round(light_fraction, 4),
        "border_uniformity": round(border_uniformity, 4),
        "border_std": round(border_std, 2),
        "square_ratio": round(square_ratio, 4),
        "panel_score": round(panel_score, 4),
    }


def _score_candidate(
    quality: list[QualityCheck],
    *,
    panel_score: float,
    panel_suspected: bool,
    source_clipped: bool,
    components: int,
    largest_share: float,
    fill: float,
    fill_target: float,
    centre_offset: float,
    target_size: int,
) -> float:
    """Rank one generated candidate before the best result is selected."""
    total = max(1, len(quality))
    passed = sum(1 for check in quality if check.passed)
    score = 100.0 * passed / total
    score -= 60.0 * max(0.0, float(panel_score))
    if panel_suspected:
        score -= 8.0
    score -= 18.0 * max(0, int(components) - 1)
    if source_clipped:
        score -= 15.0
    score -= min(6.0, abs(float(fill) - float(fill_target)) * 20.0)
    score -= min(4.0, max(0.0, 1.0 - float(largest_share)) * 20.0)
    offset_limit = max(1.0, float(target_size) * 0.06)
    score -= min(4.0, max(0.0, float(centre_offset)) / offset_limit * 4.0)
    return round(score, 2)


def _build_quality(
    image: Image.Image,
    target_size: int,
    transparent: bool,
    mode: str,
    metrics: dict[str, Any],
    source_clipped: bool,
    preview: Image.Image,
    preview_scale: int,
    palette_used: int,
    panel_suspected: bool = False,
) -> list[QualityCheck]:
    checks: list[QualityCheck] = []
    fill = float(metrics.get("fill") or 0.0)
    centre_offset = float(metrics.get("centre_offset") or 0.0)
    components = int(metrics.get("components") or 0)
    largest_share = float(metrics.get("largest_share") or 0.0)
    touches = bool(metrics.get("touches_edge"))
    check_subject = mode != "tile"

    if check_subject:
        if mode == "character":
            fill_ok = 0.75 <= fill <= 0.98
            fill_range = "75~98%"
        else:
            fill_ok = 0.72 <= fill <= 0.90
            fill_range = "72~90%"
        checks.append(
            QualityCheck(
                "subject_size",
                "피사체 크기",
                fill_ok,
                f"{fill * 100:.0f}%",
                f"피사체가 캔버스의 {fill_range}를 차지해야 합니다.",
            )
        )
        checks.append(
            QualityCheck(
                "centered",
                "중앙 배치",
                centre_offset <= max(1.0, target_size * 0.06),
                f"오프셋 {centre_offset:.1f}px",
                "피사체 중심이 캔버스 중앙에서 6% 이내여야 합니다.",
            )
        )
        checks.append(
            QualityCheck(
                "single_subject",
                "단일 오브젝트",
                components <= 1 or largest_share >= 0.97,
                f"{components}개 / 최대 {largest_share * 100:.0f}%",
                "하나의 오브젝트만 남아야 합니다.",
            )
        )
        checks.append(
            QualityCheck(
                "no_card_panel",
                "카드/패널 없음",
                not panel_suspected,
                "의심" if panel_suspected else "없음",
                "피사체 뒤에 카드/패널/사각 배경이 남지 않아야 합니다.",
            )
        )
        checks.append(
            QualityCheck(
                "not_clipped",
                "잘림 없음",
                not touches,
                "여백 확보" if not touches else "캔버스 경계에 닿음",
                "피사체가 출력 캔버스 가장자리에서 잘리지 않아야 합니다.",
            )
        )
        checks.append(
            QualityCheck(
                "source_not_clipped",
                "원본 잘림 확인",
                not source_clipped,
                "원본 내부" if not source_clipped else "원본 경계에 닿음",
                "원본 생성 이미지에서 피사체가 잘렸는지 확인하세요.",
            )
        )

    if transparent and check_subject:
        alpha_ok = metrics.get("bbox") is not None and 0.03 <= float(metrics.get("area_ratio") or 0.0) <= 0.97
        checks.append(
            QualityCheck(
                "transparent_alpha",
                "투명 배경",
                alpha_ok,
                f"불투명 {float(metrics.get('area_ratio') or 0.0) * 100:.0f}%",
                "투명 PNG의 알파 채널이 정상이어야 합니다.",
            )
        )

    checks.append(
        QualityCheck(
            "output_size",
            "출력 해상도",
            image.width == target_size and image.height == target_size,
            f"{image.width}×{image.height}",
            f"{target_size}×{target_size} PNG여야 합니다.",
        )
    )
    preview_ok = (
        preview.width == target_size * preview_scale
        and preview.height == target_size * preview_scale
        and preview_scale >= 1
    )
    checks.append(
        QualityCheck(
            "nearest_preview",
            "픽셀 경계 유지",
            preview_ok,
            f"×{preview_scale} NN",
            "미리보기는 nearest-neighbor로 확대되어야 합니다.",
        )
    )
    checks.append(
        QualityCheck(
            "palette",
            "팔레트",
            palette_used > 0,
            f"{palette_used}색",
            "색상 팔레트를 계산할 수 있어야 합니다.",
        )
    )
    return checks


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def postprocess_image(
    original: Image.Image,
    target_size: int,
    mode: str,
    palette_colors: int,
    transparent: bool,
    generation: GenerationConfig,
    asset_mode: str = "icon",
    resize_filter: str = "nearest",
) -> PostProcessResult:
    target_size = int(target_size)
    if target_size < 8 or target_size > 512:
        raise ValueError("출력 해상도는 8~512px 사이여야 합니다.")
    asset_mode = asset_mode if asset_mode in {"icon", "character", "object", "tile"} else "icon"
    resize_filter = resize_filter if resize_filter in _RESAMPLE else "nearest"
    resample = _RESAMPLE[resize_filter]
    if asset_mode == "tile":
        resize_filter = "box"
        resample = Image.Resampling.BOX

    rgb_source = original.convert("RGB")
    warnings: list[str] = []
    mask: np.ndarray | None = None
    method = "none"
    removed_ratio = 0.0
    cutout_image: Image.Image | None = None
    cropped_image: Image.Image | None = None
    background_colour = (255, 255, 255)
    panel_suspected = False
    panel_score = 0.0

    # --- 1. Subject / background analysis ---------------------------------
    if asset_mode != "tile":
        rembg_result = _rembg_mask(rgb_source, generation)
        key_result = _border_key_mask(rgb_source, generation)
        if key_result is not None:
            key_mask, _, background_colour = key_result
        else:
            key_mask = None

        if rembg_result is not None:
            rembg_mask, rembg_ratio = rembg_result
            if key_mask is not None:
                combined = rembg_mask & ~key_mask
                # Only trust the colour key if it does not devour the subject.
                if combined.sum() >= rembg_mask.sum() * 0.30:
                    mask = combined
                    method = "rembg+colorkey"
                else:
                    mask = rembg_mask
                    method = "rembg"
            else:
                mask = rembg_mask
                method = "rembg"
        elif key_mask is not None and 0.02 < float((~key_mask).mean()) < 0.98:
            mask = ~key_mask
            method = "colorkey"
        else:
            legacy = _legacy_background_mask(np.array(rgb_source, dtype=np.uint8))
            fg_ratio = float((~legacy).mean())
            if 0.02 < fg_ratio < 0.98:
                mask = ~legacy
                method = "floodfill"
            else:
                warnings.append(
                    "배경을 안정적으로 분리하지 못했습니다. 프롬프트에 'plain solid white background'를 넣거나 "
                    "투명 배경을 끄면 더 안정적입니다."
                )

        if mask is not None:
            selected, selection = _select_subject(mask)
            raw_components = int(selection.get("raw_components") or 0)
            if raw_components > 1:
                warnings.append(
                    f"여러 오브젝트/파편 {raw_components}개가 감지되어 가장 큰 피사체 하나만 사용했습니다. "
                    "원본 이미지는 보존되어 있습니다."
                )
            if int(selection.get("final_components") or 0) > 1:
                warnings.append(
                    "피사체에 분리된 작은 파편이 남아 있습니다. 미리보기를 확인해 주세요."
                )
            mask = selected
            panel = _panel_metrics(np.array(rgb_source, dtype=np.uint8), mask)
            panel_score = float(panel.get("panel_score") or 0.0)
            panel_suspected = panel_score >= 0.42
            if panel_suspected:
                warnings.append(
                    "카드/패널/사각 배경이 의심됩니다. 다른 후보를 선택했거나 원본과 최종 결과를 비교해 주세요."
                )
            keep_ratio = float(mask.mean())
            removed_ratio = 1.0 - keep_ratio
            cutout_rgba = np.dstack(
                [
                    np.array(rgb_source, dtype=np.uint8),
                    np.where(mask, 255, 0).astype(np.uint8),
                ]
            )
            cutout_image = Image.fromarray(cutout_rgba, mode="RGBA")
            if removed_ratio < 0.01:
                warnings.append(
                    "배경을 거의 제거하지 못했습니다. 원본과 최종 결과를 비교해 주세요."
                )

    # --- 2. Crop and scale the subject -----------------------------------
    if mask is not None and asset_mode != "tile":
        ys, xs = np.where(mask)
        if len(ys) >= 4:
            x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
            touch_count = sum(
                [x0 <= 0, y0 <= 0, x1 >= rgb_source.width, y1 >= rgb_source.height]
            )
            source_clipped = touch_count >= 2
            pad = max(2, int(round(max(x1 - x0, y1 - y0) * 0.03)))
            crop_box = (
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(rgb_source.width, x1 + pad),
                min(rgb_source.height, y1 + pad),
            )
            cropped_arr = np.array(cutout_image, dtype=np.uint8)[
                crop_box[1] : crop_box[3], crop_box[0] : crop_box[2]
            ]
            cropped_image = Image.fromarray(cropped_arr, mode="RGBA")
        else:
            source_clipped = True
            crop_box = None
    else:
        crop_box = None
        source_clipped = False

    fill_target = {
        "icon": float(getattr(generation, "subject_fill_icon", 0.80)),
        "character": float(getattr(generation, "subject_fill_character", 0.86)),
        "object": float(getattr(generation, "subject_fill_object", 0.82)),
        "tile": 1.0,
    }.get(asset_mode, 0.80)
    fill_target = min(0.92, max(0.60, fill_target))

    canvas_rgb = np.full((target_size, target_size, 3), background_colour, dtype=np.uint8)
    canvas_mask = np.zeros((target_size, target_size), dtype=bool)

    if mask is not None and crop_box is not None and cropped_image is not None:
        crop_h = crop_box[3] - crop_box[1]
        crop_w = crop_box[2] - crop_box[0]
        scale = (target_size * fill_target) / max(1, max(crop_h, crop_w))
        new_w = max(1, int(round(crop_w * scale)))
        new_h = max(1, int(round(crop_h * scale)))
        rgb_small, alpha_small = _resize_rgba(cropped_image, (new_w, new_h), resample)
        resized_mask = _remove_isolated(alpha_small >= (128 if resize_filter != "nearest" else 1))
        resized_mask = _remove_small_mask_islands(resized_mask)
        off_x = (target_size - new_w) // 2
        off_y = (target_size - new_h) // 2
        ys2, xs2 = np.where(resized_mask)
        if len(ys2):
            ty = ys2 + off_y
            tx = xs2 + off_x
            valid = (ty >= 0) & (ty < target_size) & (tx >= 0) & (tx < target_size)
            canvas_rgb[ty[valid], tx[valid]] = rgb_small[ys2[valid], xs2[valid]]
            canvas_mask[ty[valid], tx[valid]] = True
    elif asset_mode == "tile":
        resized = rgb_source.resize((target_size, target_size), Image.Resampling.BOX)
        canvas_rgb = np.array(resized, dtype=np.uint8)
        canvas_mask = np.ones((target_size, target_size), dtype=bool)
    else:
        # No reliable mask: fall back to resizing the whole image, but warn.
        resized = rgb_source.resize((target_size, target_size), resample)
        canvas_rgb = np.array(resized, dtype=np.uint8)
        canvas_mask = np.ones((target_size, target_size), dtype=bool)
        if transparent:
            warnings.append(
                "피사체를 분리하지 못해 원본 전체를 축소했습니다. 투명 배경을 끄거나 프롬프트를 조정해 주세요."
            )

    subject_mask_canvas = canvas_mask.copy()
    if not transparent or asset_mode == "tile":
        canvas_mask = np.ones((target_size, target_size), dtype=bool)

    # --- 3. Palette cleanup ----------------------------------------------
    small = Image.fromarray(canvas_rgb, mode="RGB")
    if mode == "posterize":
        small = ImageOps.posterize(small, bits=4)
    if mode in {"quantize", "posterize"} and int(palette_colors) > 0:
        if canvas_mask.any() and (~canvas_mask).any():
            work = np.array(small, dtype=np.uint8)
            work[~canvas_mask] = np.median(work[canvas_mask], axis=0).astype(np.uint8)
            small_for_palette = Image.fromarray(work, mode="RGB")
        else:
            small_for_palette = small
        small = _quantize(small_for_palette, int(palette_colors))
        small = _despeckle(small)

    if transparent and asset_mode != "tile":
        rgb_final = np.array(small.convert("RGB"), dtype=np.uint8)
        alpha = np.where(canvas_mask, 255, 0).astype(np.uint8)
        small = Image.fromarray(np.dstack([rgb_final, alpha]), mode="RGBA")
    else:
        small = small.convert("RGB")

    # Recompute removed ratio from the final mask
    if mask is not None:
        removed_ratio = float((~mask).mean())

    scale = _preview_scale(target_size)
    preview = small.resize(
        (target_size * scale, target_size * scale), Image.Resampling.NEAREST
    )
    palette_used = _count_palette(small)
    metrics = _subject_metrics_from_mask(subject_mask_canvas)
    quality = _build_quality(
        small,
        target_size,
        transparent,
        asset_mode,
        metrics,
        source_clipped,
        preview,
        scale,
        palette_used,
        panel_suspected=panel_suspected,
    )
    if asset_mode != "tile":
        failed = [check.label for check in quality if not check.passed and check.key != "source_not_clipped"]
        if failed:
            warnings.append("자동 검증 확인 필요: " + ", ".join(failed) + " (결과는 보존됩니다)")

    subject_fill = float(metrics.get("fill") or 0.0)
    centre_offset = float(metrics.get("centre_offset") or 0.0)
    candidate_score = _score_candidate(
        quality,
        panel_score=panel_score,
        panel_suspected=panel_suspected,
        source_clipped=source_clipped,
        components=int(metrics.get("components") or 0),
        largest_share=float(metrics.get("largest_share") or 0.0),
        fill=subject_fill,
        fill_target=fill_target,
        centre_offset=centre_offset,
        target_size=target_size,
    )

    return PostProcessResult(
        image=small,
        preview=preview,
        preview_scale=scale,
        palette_used=palette_used,
        warnings=warnings,
        background_removed_ratio=removed_ratio,
        background_method=method,
        cutout=cutout_image,
        cropped=cropped_image,
        quality=quality,
        subject_fill=subject_fill,
        subject_area_ratio=float(metrics.get("area_ratio") or 0.0),
        subject_components=int(metrics.get("components") or 0),
        largest_component_share=float(metrics.get("largest_share") or 0.0),
        subject_bbox=metrics.get("bbox"),
        source_clipped=source_clipped,
        mask_method=method,
        resize_filter=resize_filter,
        output_size=target_size,
        fill_target=fill_target,
        centre_offset=centre_offset,
        touches_edge=bool(metrics.get("touches_edge")),
        panel_suspected=panel_suspected,
        panel_score=panel_score,
        candidate_score=candidate_score,
    )


def _remove_small_mask_islands(mask: np.ndarray) -> np.ndarray:
    """Remove 1-2 pixel islands introduced by resizing."""
    stats = _component_stats(mask)
    if len(stats) <= 1:
        return mask
    largest = max(1, stats[0]["area"])
    cleaned = np.zeros_like(mask)
    for item in stats:
        if item["area"] >= max(2, int(largest * 0.01)):
            cleaned |= item["mask"]
    return cleaned

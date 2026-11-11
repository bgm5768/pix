"""Prototype the improved subject-extraction and pixelation pipeline.

Not part of the app yet: used to compare resize filters, masking and outline
options on real SDXL generations.
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from rembg import new_session, remove
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "prototype"
SESSION = new_session("u2net")


def padded_rembg(image: Image.Image, pad_ratio: float = 0.25) -> np.ndarray:
    arr = np.array(image.convert("RGB"))
    pad = int(max(image.size) * pad_ratio)
    corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]])
    color = tuple(int(v) for v in np.median(corners, axis=0))
    canvas = Image.new("RGB", (image.width + 2 * pad, image.height + 2 * pad), color)
    canvas.paste(image, (pad, pad))
    result = remove(canvas, session=SESSION, alpha_matting=False, post_process_mask=False)
    mask = np.array(result)[:, :, 3] >= 128
    return mask[pad : pad + image.height, pad : pad + image.width]


def background_key(image: Image.Image, tolerance: int = 26) -> tuple[np.ndarray, bool]:
    """Flood-fill a flat border colour. Returns (background, reliable)."""
    arr = np.array(image.convert("RGB"), dtype=np.int32)
    height, width, _ = arr.shape
    border = np.concatenate([arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]], axis=0)
    keys = border // 24
    unique, counts = np.unique(keys, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1]
    dominant = unique[order[0]].astype(np.int32) * 24 + 12
    dominance = counts[order[0]] / max(1, counts.sum())
    distance = np.sqrt(np.sum((arr - dominant) ** 2, axis=2))
    similar = distance <= tolerance
    visited = np.zeros((height, width), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((0, x)); queue.append((height - 1, x))
    for y in range(height):
        queue.append((y, 0)); queue.append((y, width - 1))
    while queue:
        y, x = queue.popleft()
        if visited[y, x] or not similar[y, x]:
            continue
        visited[y, x] = True
        if y > 0:
            queue.append((y - 1, x))
        if y + 1 < height:
            queue.append((y + 1, x))
        if x > 0:
            queue.append((y, x - 1))
        if x + 1 < width:
            queue.append((y, x + 1))
    return visited, dominance >= 0.55


def components(mask: np.ndarray) -> list[tuple[int, np.ndarray, tuple[int, int, int, int]]]:
    labels, count = ndimage.label(mask)
    result = []
    for index in range(1, count + 1):
        component = labels == index
        area = int(component.sum())
        if area == 0:
            continue
        ys, xs = np.where(component)
        result.append((area, component, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)))
    result.sort(key=lambda item: item[0], reverse=True)
    return result


def select_subject(mask: np.ndarray) -> tuple[np.ndarray, dict]:
    height, width = mask.shape
    items = components(mask)
    if not items:
        return mask, {"components": 0}
    main_area, main_mask, main_box = items[0]
    kept = main_mask.copy()
    mx0, my0, mx1, my1 = main_box
    diag = (width * width + height * height) ** 0.5
    for area, component, box in items[1:]:
        x0, y0, x1, y1 = box
        overlap = not (x1 <= mx0 or x0 >= mx1 or y1 <= my0 or y0 >= my1)
        dx = max(mx0 - x1, x0 - mx1, 0)
        dy = max(my0 - y1, y0 - my1, 0)
        distance = (dx * dx + dy * dy) ** 0.5
        if overlap and area < main_area * 0.6:
            kept |= component
        elif distance <= diag * 0.02 and area < main_area * 0.25:
            kept |= component
    kept = ndimage.binary_fill_holes(kept)
    kept = ndimage.binary_closing(kept, structure=np.ones((3, 3)), iterations=1)
    # Keep only the component containing the main subject after closing.
    labels, count = ndimage.label(kept)
    if count > 1:
        values, counts = np.unique(labels[main_mask], return_counts=True)
        values = values[values > 0]
        if len(values):
            best = values[np.argmax([np.sum(labels == value) for value in values])]
            kept = labels == best
    ys, xs = np.where(kept)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return kept, {
        "components": len(items),
        "kept_components": 1,
        "main_area": main_area,
        "bbox": box,
    }


def resize_rgba(image: Image.Image, size: tuple[int, int], resample) -> Image.Image:
    arr = np.array(image.convert("RGBA"), dtype=np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3:4] / 255.0
    pre = rgb * alpha

    def channel(data: np.ndarray) -> np.ndarray:
        return np.array(Image.fromarray(data.astype(np.float32)).resize(size, resample), dtype=np.float32)

    red, green, blue = (channel(pre[:, :, i]) for i in range(3))
    small_alpha = np.clip(channel(alpha[:, :, 0] * 255.0) / 255.0, 0.0, 1.0)
    safe = np.maximum(small_alpha, 1e-4)[:, :, None]
    small_rgb = np.clip(np.stack([red, green, blue], axis=2) / safe, 0, 255)
    mask = small_alpha >= 0.5
    return Image.fromarray(np.dstack([small_rgb.astype(np.uint8), np.where(mask, 255, 0).astype(np.uint8)]), "RGBA")


def quantize(image: Image.Image, colors: int) -> Image.Image:
    arr = np.array(image, dtype=np.uint8)
    mask = arr[:, :, 3] > 0
    work = arr[:, :, :3].copy()
    if mask.any() and (~mask).any():
        work[~mask] = np.median(work[mask], axis=0).astype(np.uint8)
    q = Image.fromarray(work).quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rgb = np.array(q.convert("RGB"), dtype=np.uint8)
    return Image.fromarray(np.dstack([rgb, np.where(mask, 255, 0).astype(np.uint8)]), "RGBA")


def despeckle(image: Image.Image) -> Image.Image:
    arr = np.array(image, dtype=np.uint8)
    rgb = arr[:, :, :3].copy()
    mask = arr[:, :, 3] > 0
    changed = True
    for _ in range(2):
        if not changed:
            break
        changed = False
        for y in range(arr.shape[0]):
            for x in range(arr.shape[1]):
                if not mask[y, x]:
                    continue
                neighbours = []
                if y > 0 and mask[y - 1, x]:
                    neighbours.append(rgb[y - 1, x])
                if y + 1 < arr.shape[0] and mask[y + 1, x]:
                    neighbours.append(rgb[y + 1, x])
                if x > 0 and mask[y, x - 1]:
                    neighbours.append(rgb[y, x - 1])
                if x + 1 < arr.shape[1] and mask[y, x + 1]:
                    neighbours.append(rgb[y, x + 1])
                if len(neighbours) < 2:
                    continue
                values, counts = np.unique(np.stack(neighbours), axis=0, return_counts=True)
                if len(values) == 1:
                    continue
                best = values[int(np.argmax(counts))]
                if counts.max() >= 3 and not np.array_equal(best, rgb[y, x]):
                    rgb[y, x] = best
                    changed = True
    return Image.fromarray(np.dstack([rgb, np.where(mask, 255, 0).astype(np.uint8)]), "RGBA")


def add_outline(image: Image.Image, strength: float = 0.45) -> Image.Image:
    arr = np.array(image, dtype=np.float32)
    rgb = arr[:, :, :3]
    mask = arr[:, :, 3] > 0
    padded = np.pad(mask, 1, constant_values=False)
    boundary = mask & ~(
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    ys, xs = np.where(boundary)
    if len(ys) == 0:
        return image
    outline = np.median(rgb[mask], axis=0) * (1 - strength) * 0.35
    rgb[ys, xs] = outline
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), arr[:, :, 3].astype(np.uint8)]), "RGBA")


def render(source: Image.Image, target: int, resample, outline: bool, prequant: bool, fill: float = 0.80, colors: int = 24, save_mask: str | None = None) -> tuple[Image.Image, dict]:
    seg = padded_rembg(source)
    key, reliable = background_key(source)
    mask = seg & ~key if reliable else seg
    if mask.sum() < seg.sum() * 0.15:
        mask = seg
    mask, info = select_subject(mask)
    info["rembg_ratio"] = float(seg.mean())
    info["key_ratio"] = float(key.mean())
    info["key_reliable"] = reliable
    if save_mask:
        OUT.mkdir(parents=True, exist_ok=True)
        Image.fromarray((mask * 255).astype(np.uint8)).save(OUT / f"{save_mask}_mask.png")
        Image.fromarray((seg * 255).astype(np.uint8)).save(OUT / f"{save_mask}_rembg.png")
    x0, y0, x1, y1 = info["bbox"]
    pad = max(2, int(max(x1 - x0, y1 - y0) * 0.03))
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(source.width, x1 + pad); y1 = min(source.height, y1 + pad)
    crop = source.crop((x0, y0, x1, y1)).convert("RGBA")
    crop.putalpha(Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8)))
    if prequant:
        crop = quantize(crop, 24)
    crop = crop.filter(ImageFilter.MedianFilter(3))
    crop_h, crop_w = crop.height, crop.width
    scale = (target * fill) / max(crop_h, crop_w)
    new_w, new_h = max(1, round(crop_w * scale)), max(1, round(crop_h * scale))
    small = resize_rgba(crop, (new_w, new_h), resample)
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    canvas.paste(small, ((target - new_w) // 2, (target - new_h) // 2), small)
    small = quantize(canvas, colors)
    small = despeckle(small)
    if outline:
        small = add_outline(small)
    return small, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--name", default="")
    parser.add_argument("--resample", default="box", choices=["nearest", "box", "lanczos"])
    parser.add_argument("--outline", action="store_true")
    parser.add_argument("--prequant", action="store_true")
    parser.add_argument("--colors", type=int, default=24)
    parser.add_argument("--fill", type=float, default=0.80)
    parser.add_argument("--targets", default="32,64,128")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(args.source).convert("RGB")
    name = args.name or Path(args.source).stem
    resample = {
        "nearest": Image.Resampling.NEAREST,
        "box": Image.Resampling.BOX,
        "lanczos": Image.Resampling.LANCZOS,
    }[args.resample]
    info = {}
    for target in [int(item) for item in args.targets.split(",")]:
        image, info = render(
            source, target, resample, args.outline, args.prequant,
            fill=args.fill, colors=args.colors,
            save_mask=name if target == 32 else None,
        )
        image.resize((target * 8, target * 8), Image.Resampling.NEAREST).save(
            OUT / f"{name}_{target}_{args.resample}_outline{int(args.outline)}_pre{int(args.prequant)}_c{args.colors}.png"
        )
        print(target, info)


if __name__ == "__main__":
    main()

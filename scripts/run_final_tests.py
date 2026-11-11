# -*- coding: utf-8 -*-
"""Run the five required prompts at 32/64/128 and write a metrics report.

Every job goes through the real backend -> ComfyUI -> postprocess pipeline.
Originals, cutouts, crops, pixel PNGs and previews are preserved by the app.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765/api"
OUT_DIR = ROOT / "experiments"
OUT_DIR.mkdir(exist_ok=True)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

CASES = [
    ("library", "도서관 아이콘 만들어줘", "icon"),
    ("cat", "귀여운 고양이 캐릭터 한 명 만들어줘", "character"),
    ("tree", "나무 한 그루 만들어줘", "object"),
    ("apple", "빨간색 사과 하나 만들어줘", "object"),
    ("school", "작은 픽셀아트 학교 건물 만들어줘", "icon"),
]
SIZES = [(32, 16), (64, 24), (128, 32)]
SEED = 1234567


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as response:
        return json.loads(response.read())


def image_metrics(path: Path) -> dict:
    image = Image.open(path)
    arr = np.asarray(image)
    if arr.ndim == 3 and arr.shape[2] == 4:
        mask = arr[:, :, 3] > 0
        rgb = arr[:, :, :3]
    else:
        mask = np.ones(arr.shape[:2], dtype=bool)
        rgb = arr
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return {"empty": True}
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    bbox_w = bbox[2] - bbox[0]
    bbox_h = bbox[3] - bbox[1]
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    areas = sorted((int((labels == i).sum()) for i in range(1, count + 1)), reverse=True)
    colours = int(np.unique(rgb[mask], axis=0).shape[0])
    return {
        "mode": image.mode,
        "size": list(image.size),
        "bbox": list(bbox),
        "fill": max(bbox_w, bbox_h) / image.width,
        "opaque_ratio": float(mask.mean()),
        "components": len(areas),
        "largest_share": areas[0] / max(1, sum(areas)),
        "colours": colours,
    }


def label_font(size: int = 14):
    for name in ("malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    records = []
    for case_id, prompt, mode in CASES:
        for size, palette in SIZES:
            payload = {
                "prompt": prompt,
                "mode": mode,
                "output_size": size,
                "seed": SEED,
                "steps": 28,
                "cfg": 6.0,
                "lora_strength": 0.8,
                "transparent": True,
                "postprocess": "quantize",
                "palette_colors": palette,
                "resize_filter": "nearest",
                "candidates": 4,
            }
            response = post("/generate", payload)
            job_id = response["job_id"]
            print(f"[{case_id} {size}px] submitted {job_id}", flush=True)
            while True:
                time.sleep(1.5)
                job = get(f"/jobs/{job_id}")
                if job["status"] in {"completed", "error", "cancelled"}:
                    break
            if job["status"] != "completed":
                print(f"  FAILED: {job.get('error')}", flush=True)
                records.append(
                    {
                        "case": case_id,
                        "prompt": prompt,
                        "mode": mode,
                        "size": size,
                        "palette": palette,
                        "job_id": job_id,
                        "status": job["status"],
                        "error": job.get("error"),
                    }
                )
                continue
            result = job["result"]
            pixel_path = ROOT / "outputs" / "pixel_art" / f"{job_id}_pixel_{size}.png"
            metrics = image_metrics(pixel_path)
            record = {
                "case": case_id,
                "prompt": prompt,
                "mode": mode,
                "size": size,
                "palette_requested": palette,
                "job_id": job_id,
                "status": job["status"],
                "seed": job["seed_used"],
                "base_seed": job.get("base_seed"),
                "candidates_generated": result.get("candidates_generated"),
                "selected_candidate": result.get("candidate_index"),
                "candidate_score": result.get("candidate_score"),
                "panel_suspected": result.get("panel_suspected"),
                "subject": job["prompt_plan"]["subject"],
                "source": job["prompt_plan"]["source"],
                "prompt_used": job["prompt_used"],
                "result": {
                    "pixel_url": result["pixel_url"],
                    "cutout_url": result["cutout_url"],
                    "crop_url": result["crop_url"],
                    "preview_url": result["preview_url"],
                    "original_url": result["original_url"],
                    "subject_fill": result["subject_fill"],
                    "palette_colors": result["palette_colors"],
                    "resize_filter": result["resize_filter"],
                    "warnings": result["warnings"],
                    "quality": result["quality"],
                },
                "metrics": metrics,
            }
            records.append(record)
            passed = sum(1 for check in result["quality"] if check["passed"])
            total = len(result["quality"])
            print(
                f"  {job_id} fill={metrics['fill']:.3f} colours={metrics['colours']} "
                f"components={metrics['components']} quality={passed}/{total}",
                flush=True,
            )

    report_path = OUT_DIR / f"final_tests_{STAMP}.json"
    report_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {report_path}")

    # Contact sheet: rows = prompts, columns = 32/64/128 (preview rendered at 256px).
    cell = 256
    label_w = 150
    header_h = 34
    width = label_w + cell * len(SIZES)
    height = header_h + cell * len(CASES)
    sheet = Image.new("RGB", (width, height), (18, 22, 30))
    draw = ImageDraw.Draw(sheet)
    font = label_font(16)
    for col, (size, _) in enumerate(SIZES):
        draw.text((label_w + col * cell + 10, 9), f"{size} x {size}", fill=(220, 230, 240), font=font)
    for row, (case_id, prompt, mode) in enumerate(CASES):
        y = header_h + row * cell
        draw.text((10, y + 10), case_id, fill=(220, 230, 240), font=font)
        draw.text((10, y + 32), mode, fill=(130, 150, 175), font=font)
        for col, (size, _) in enumerate(SIZES):
            match = next(
                (item for item in records if item["case"] == case_id and item["size"] == size),
                None,
            )
            if not match or match["status"] != "completed":
                continue
            preview = Image.open(ROOT / "outputs" / "previews" / f"{match['job_id']}_preview_{size}.png")
            preview = preview.resize((cell, cell), Image.Resampling.NEAREST)
            sheet.paste(preview, (label_w + col * cell, y))
    sheet_path = OUT_DIR / f"final_tests_{STAMP}.png"
    sheet.save(sheet_path)
    print(f"contact sheet: {sheet_path}")


if __name__ == "__main__":
    main()

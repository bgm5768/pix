# -*- coding: utf-8 -*-
"""Compare nearest / box / lanczos on the same generated original."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services.postprocess import postprocess_image  # noqa: E402

JOB_ID = "42b7eb87222b"  # library icon, 2026-11-10 final test
SIZE = 64
PALETTE = 24
FILTERS = ["nearest", "box", "lanczos"]


def font(size: int = 16):
    for name in ("malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


settings = get_settings()
original = Image.open(ROOT / "outputs" / "originals" / f"{JOB_ID}_original.png").convert("RGB")
cell = 256
label_h = 30
sheet = Image.new("RGB", (cell * len(FILTERS), cell + label_h), (18, 22, 30))
draw = ImageDraw.Draw(sheet)
font = font()

for index, filter_name in enumerate(FILTERS):
    result = postprocess_image(
        original,
        SIZE,
        "quantize",
        PALETTE,
        True,
        settings.generation,
        "icon",
        filter_name,
    )
    path = ROOT / "experiments" / f"resize_{filter_name}_{JOB_ID}_{SIZE}.png"
    result.image.save(path)
    upscaled = result.image.resize((cell, cell), Image.Resampling.NEAREST)
    checker = Image.new("RGB", (cell, cell), (38, 44, 55))
    mask = Image.new("L", (cell, cell), 0)
    mask.paste(upscaled.getchannel("A").resize((cell, cell), Image.Resampling.NEAREST), (0, 0))
    checker.paste(upscaled.convert("RGB"), (0, 0), mask)
    sheet.paste(checker, (index * cell, label_h))
    draw.text(
        (index * cell + 10, 7),
        f"{filter_name.upper()}  ·  {result.palette_used} colors  ·  fill {result.subject_fill * 100:.0f}%",
        fill=(220, 230, 240),
        font=font,
    )
    print(filter_name, result.palette_used, round(result.subject_fill, 3), path)

out = ROOT / "experiments" / f"resize_compare_{JOB_ID}_{SIZE}.png"
sheet.save(out)
print("comparison:", out)

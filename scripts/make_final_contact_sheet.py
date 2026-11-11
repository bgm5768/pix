# -*- coding: utf-8 -*-
"""Build a checkerboard contact sheet from the latest final-test report."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPORTS = sorted((ROOT / "experiments").glob("final_tests_*.json"))
if not REPORTS:
    raise SystemExit("final_tests_*.json not found")
report_path = REPORTS[-1]
records = json.loads(report_path.read_text(encoding="utf-8"))

CASES = [
    ("library", "library icon"),
    ("cat", "cat character"),
    ("tree", "tree object"),
    ("apple", "apple object"),
    ("school", "school icon"),
]
SIZES = [32, 64, 128]
CELL = 256
LABEL_W = 170
HEADER_H = 36


def font(size: int = 15):
    for name in ("malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def checker(size: int, step: int = 16) -> Image.Image:
    image = Image.new("RGB", (size, size), (34, 39, 48))
    draw = ImageDraw.Draw(image)
    for y in range(0, size, step):
        for x in range(0, size, step):
            if (x // step + y // step) % 2 == 0:
                draw.rectangle((x, y, x + step - 1, y + step - 1), fill=(44, 50, 61))
    return image


sheet = Image.new("RGB", (LABEL_W + CELL * len(SIZES), HEADER_H + CELL * len(CASES)), (18, 22, 30))
draw = ImageDraw.Draw(sheet)
label_font = font(16)
small_font = font(11)

for column, size in enumerate(SIZES):
    draw.text(
        (LABEL_W + column * CELL + 10, 9),
        f"{size} x {size}",
        fill=(220, 230, 240),
        font=label_font,
    )

for row, (case_id, description) in enumerate(CASES):
    y = HEADER_H + row * CELL
    draw.text((12, y + 12), case_id, fill=(220, 230, 240), font=label_font)
    draw.text((12, y + 34), description, fill=(130, 150, 175), font=small_font)
    for column, size in enumerate(SIZES):
        record = next(
            (item for item in records if item["case"] == case_id and item["size"] == size),
            None,
        )
        if not record or record["status"] != "completed":
            continue
        preview_path = ROOT / "outputs" / "previews" / f"{record['job_id']}_preview_{size}.png"
        preview = Image.open(preview_path).convert("RGBA").resize((CELL, CELL), Image.Resampling.NEAREST)
        cell = checker(CELL)
        cell.paste(preview.convert("RGB"), (0, 0), preview.getchannel("A"))
        sheet.paste(cell, (LABEL_W + column * CELL, y))
        draw.rectangle(
            (LABEL_W + column * CELL, y, LABEL_W + column * CELL + CELL - 1, y + CELL - 1),
            outline=(55, 63, 76),
        )
        draw.text(
            (LABEL_W + column * CELL + 8, y + CELL - 20),
            f"fill {record['metrics']['fill'] * 100:.0f}% · {record['metrics']['colours']} colors",
            fill=(150, 165, 185),
            font=small_font,
        )

out = report_path.with_name(report_path.stem + "_checker.png")
sheet.save(out)
print(out)

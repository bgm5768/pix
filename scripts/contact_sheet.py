"""Build labelled contact sheets from experiment outputs."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern")
    parser.add_argument("--out", required=True)
    parser.add_argument("--cell", type=int, default=256)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--thumb", type=int, default=220)
    args = parser.parse_args()

    files = sorted((ROOT / "experiments").glob(args.pattern))
    if not files:
        raise SystemExit("no files")
    rows = (len(files) + args.cols - 1) // args.cols
    label_h = 22
    sheet = Image.new("RGB", (args.cols * args.cell, rows * (args.cell + label_h)), (30, 30, 34))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((args.thumb, args.thumb), Image.Resampling.LANCZOS)
        x = (index % args.cols) * args.cell
        y = (index // args.cols) * (args.cell + label_h)
        sheet.paste(image, (x + (args.cell - image.width) // 2, y + (args.cell - image.height) // 2))
        draw.text((x + 4, y + args.cell + 3), path.stem[:44], fill=(220, 220, 225), font=font)
    out = ROOT / "experiments" / args.out
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()

from __future__ import annotations

import io
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.services.errors import PixelForgeError

# Comic page layouts: rows x columns of equally sized panels.
LAYOUTS: dict[str, tuple[int, int]] = {
    "1x1": (1, 1),
    "1x2": (1, 2),
    "2x1": (2, 1),
    "2x2": (2, 2),
    "1x3": (1, 3),
    "3x1": (3, 1),
    "2x3": (2, 3),
}

SYSTEM_FONTS = (
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
)

_MARGIN = 46
_GAP = 22


class ComicError(PixelForgeError):
    code = "COMIC_ERROR"
    status_code = 400


@dataclass
class ComicPanel:
    image_path: Path
    text: str = ""
    position: str = "top"  # top | bottom | none


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in SYSTEM_FONTS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to a pixel width.

    Korean/Japanese text has no spaces, so a word longer than the line is split
    per character instead of overflowing the bubble.
    """
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}".strip()
            if font.getlength(candidate) <= max_width or not current:
                current = candidate
                continue
            lines.append(current)
            current = ""
            # The word alone may still be wider than the bubble (no-space text).
            piece = word
            while piece:
                cut = len(piece)
                while cut > 1 and font.getlength(piece[:cut]) > max_width:
                    cut -= 1
                lines.append(piece[:cut])
                piece = piece[cut:]
        if current:
            lines.append(current)
    return lines


def _draw_bubble(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    tail: str = "bottom",
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=26, fill=(255, 255, 255), outline=(20, 20, 20), width=3)
    if tail == "bottom":
        cx = (x0 + x1) // 2
        draw.polygon(
            [(cx - 16, y1 - 2), (cx + 16, y1 - 2), (cx - 4, y1 + 26)],
            fill=(255, 255, 255),
            outline=(20, 20, 20),
        )
        draw.line([(cx - 16, y1 - 2), (cx - 4, y1 + 26)], fill=(20, 20, 20), width=3)
        draw.line([(cx + 16, y1 - 2), (cx - 4, y1 + 26)], fill=(20, 20, 20), width=3)
    elif tail == "top":
        cx = (x0 + x1) // 2
        draw.polygon(
            [(cx - 16, y0 + 2), (cx + 16, y0 + 2), (cx - 4, y0 - 26)],
            fill=(255, 255, 255),
            outline=(20, 20, 20),
        )
        draw.line([(cx - 16, y0 + 2), (cx - 4, y0 - 26)], fill=(20, 20, 20), width=3)
        draw.line([(cx + 16, y0 + 2), (cx - 4, y0 - 26)], fill=(20, 20, 20), width=3)
    if not text.strip():
        return
    inner_width = x1 - x0 - 36
    lines = _wrap(text, font, inner_width)
    line_height = int(font.size * 1.35)
    total = line_height * len(lines)
    y = y0 + max(12, ((y1 - y0) - total) // 2)
    for line in lines:
        width = font.getlength(line)
        draw.text(((x0 + x1) / 2 - width / 2, y), line, fill=(20, 20, 20), font=font)
        y += line_height


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Crop-to-fill so every panel has the same size (like a comic page)."""
    target_w, target_h = size
    src_ratio = image.width / image.height
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_w = int(image.height * dst_ratio)
        left = (image.width - new_w) // 2
        image = image.crop((left, 0, left + new_w, image.height))
    else:
        new_h = int(image.width / dst_ratio)
        top = (image.height - new_h) // 2
        image = image.crop((0, top, image.width, top + new_h))
    return image.resize((target_w, target_h), Image.LANCZOS)


class ComicService:
    """Assembles generated cuts into comic pages with speech bubbles."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def pages_dir(self) -> Path:
        return self.settings.resolve(self.settings.storage.comic_pages_dir)

    def ensure_dirs(self) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def build_page(
        self,
        panels: list[dict[str, Any]],
        layout: str = "2x2",
        width: int = 1240,
        height: int = 1754,
        title: str = "",
    ) -> dict[str, Any]:
        if not panels:
            raise ComicError("페이지에 넣을 컷이 없습니다.")
        if layout not in LAYOUTS:
            raise ComicError(f"알 수 없는 레이아웃입니다: {layout}")
        rows, cols = LAYOUTS[layout]
        if len(panels) > rows * cols:
            raise ComicError(
                f"이 레이아웃에는 최대 {rows * cols}컷까지 들어갑니다 (현재 {len(panels)}컷)."
            )
        width = max(600, min(int(width), 2400))
        height = max(600, min(int(height), 3400))
        self.ensure_dirs()

        page = Image.new("RGB", (width, height), (247, 246, 242))
        draw = ImageDraw.Draw(page)
        title_height = 78 if title.strip() else 0
        draw.rectangle(
            (0, 0, width - 1, height - 1), outline=(24, 24, 28), width=4
        )
        if title.strip():
            title_font = _font(40)
            tw = title_font.getlength(title.strip())
            draw.text(
                ((width - tw) / 2, 20),
                title.strip(),
                fill=(28, 28, 32),
                font=title_font,
            )
            draw.line(
                [(60, title_height - 12), (width - 60, title_height - 12)],
                fill=(24, 24, 28),
                width=3,
            )

        cell_w = (width - _MARGIN * 2 - _GAP * (cols - 1)) // cols
        cell_h = (height - _MARGIN * 2 - title_height - _GAP * (rows - 1)) // rows
        bubble_font = _font(max(20, cell_w // 22))

        for index, panel in enumerate(panels):
            source = Path(str(panel.get("path") or ""))
            if not source.is_file():
                raise ComicError(f"컷 이미지를 찾을 수 없습니다: {source.name}")
            with Image.open(source) as raw:
                raw.load()
                picture = _fit(raw.convert("RGB"), (cell_w, cell_h))
            row = index // cols
            col = index % cols
            x = _MARGIN + col * (cell_w + _GAP)
            y = _MARGIN + title_height + row * (cell_h + _GAP)
            page.paste(picture, (x, y))
            draw.rectangle((x, y, x + cell_w, y + cell_h), outline=(24, 24, 28), width=3)
            text = str(panel.get("text") or "")
            if text.strip():
                max_text_width = cell_w - 64
                lines = _wrap(text, bubble_font, max_text_width)
                text_width = max(
                    (bubble_font.getlength(line) for line in lines if line.strip()),
                    default=bubble_font.size,
                )
                bubble_w = int(min(max_text_width + 36, max(200, text_width + 36)))
                line_height = int(bubble_font.size * 1.35)
                bubble_h = line_height * len(lines) + 30
                position = str(panel.get("position") or "top")
                if position == "bottom":
                    bx0 = x + 20
                    by0 = y + cell_h - bubble_h - 24
                    tail = "bottom"
                elif position == "none":
                    bx0 = x + 20
                    by0 = y + 20
                    tail = "top"
                else:
                    bx0 = x + 20
                    by0 = y + 20
                    tail = "bottom"
                _draw_bubble(
                    draw,
                    (bx0, by0, bx0 + bubble_w, by0 + bubble_h),
                    text,
                    bubble_font,
                    tail,
                )

        page_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        page_path = self.pages_dir / f"page_{page_id}.png"
        page.save(page_path, format="PNG", optimize=True)

        pdf_path = self.pages_dir / f"page_{page_id}.pdf"
        page.save(pdf_path, format="PDF", resolution=150.0)

        meta = {
            "id": page_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "layout": layout,
            "width": width,
            "height": height,
            "title": title,
            "panels": [
                {
                    "path": str(panel.get("path") or ""),
                    "text": str(panel.get("text") or ""),
                    "position": str(panel.get("position") or "top"),
                }
                for panel in panels
            ],
        }
        (self.pages_dir / f"page_{page_id}.json").write_text(
            __import__("json").dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "id": page_id,
            "image_url": f"/files/comic_pages/page_{page_id}.png",
            "pdf_url": f"/api/comic/page/{page_id}.pdf",
            "layout": layout,
            "width": width,
            "height": height,
            "title": title,
            "panel_count": len(panels),
        }

    def list_pages(self, limit: int = 24) -> list[dict[str, Any]]:
        self.ensure_dirs()
        items: list[dict[str, Any]] = []
        for meta_path in sorted(
            self.pages_dir.glob("page_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit]:
            try:
                meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            page_id = str(meta.get("id") or "")
            items.append(
                {
                    "id": page_id,
                    "created_at": meta.get("created_at"),
                    "layout": meta.get("layout"),
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                    "title": meta.get("title"),
                    "panel_count": len(meta.get("panels") or []),
                    "image_url": f"/files/comic_pages/page_{page_id}.png",
                    "pdf_url": f"/api/comic/page/{page_id}.pdf",
                }
            )
        return items

    def page_path(self, page_id: str) -> Path:
        if not re.fullmatch(r"[0-9A-Za-z_]{4,64}", page_id or ""):
            raise ComicError("잘못된 페이지 ID입니다.")
        path = self.pages_dir / f"page_{page_id}.png"
        if not path.is_file():
            raise ComicError("페이지를 찾을 수 없습니다.")
        return path

    def pdf_path(self, page_id: str) -> Path:
        if not re.fullmatch(r"[0-9A-Za-z_]{4,64}", page_id or ""):
            raise ComicError("잘못된 페이지 ID입니다.")
        path = self.pages_dir / f"page_{page_id}.pdf"
        if not path.is_file():
            raise ComicError("PDF를 찾을 수 없습니다.")
        return path

    def delete_page(self, page_id: str) -> int:
        removed = 0
        for suffix in (".png", ".pdf", ".json"):
            path = self.pages_dir / f"page_{page_id}{suffix}"
            if path.is_file():
                path.unlink()
                removed += 1
        return removed

#!/usr/bin/env python3
"""Generate a simple typographic cover (no source artwork) with Pillow.

Standard-Ebooks-ish layout: dark field, centred serif title, a thin accent rule,
subtitle, and author. Writes assets/cover.jpg (1400×2100), read by build_epub.py.
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "cover.jpg")

W, H = 1400, 2100
BG = (24, 24, 27)        # near-black charcoal
INK = (233, 227, 214)    # warm cream
ACCENT = (158, 39, 41)   # deep red rule

TITLE_LINES = ["THE JURY", "BOX"]
SUBTITLE = ["The Mystery Reviews of", "JOHN DICKSON CARR", "1964-1976"]
AUTHOR = "JOHN DICKSON CARR"

# Prefer a refined serif; fall back to whatever Latin serif is present.
SERIF = [
    ("/System/Library/Fonts/Supplemental/Didot.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Baskerville.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", 0),
    ("/System/Library/Fonts/Times.ttc", 0),
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path, idx in SERIF:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def centered(draw: ImageDraw.ImageDraw, y: int, text: str, fnt, fill) -> int:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) // 2 - bbox[0], y - bbox[1]), text, font=fnt, fill=fill)
    return bbox[3] - bbox[1]


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Thin double border
    d.rectangle([54, 54, W - 54, H - 54], outline=INK, width=3)
    d.rectangle([70, 70, W - 70, H - 70], outline=INK, width=1)

    title_font = font(176)
    sub_font = font(52)
    name_font = font(58)
    year_font = font(46)

    y = 420
    for line in TITLE_LINES:
        h = centered(d, y, line, title_font, INK)
        y += h + 36

    y += 40
    d.line([(W // 2 - 190, y), (W // 2 + 190, y)], fill=ACCENT, width=6)
    y += 80

    centered(d, y, SUBTITLE[0], sub_font, INK)
    y += 84
    centered(d, y, SUBTITLE[1], name_font, INK)
    y += 96
    centered(d, y, SUBTITLE[2], year_font, INK)

    img.save(OUT, "JPEG", quality=92)
    print(f"wrote {OUT}  ({W}×{H})")


if __name__ == "__main__":
    main()

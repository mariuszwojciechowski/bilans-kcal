"""Wyodrębnia okrągły znak (badge) z pełnego logo Fit Krasnal.

Użycie:  .venv/bin/python scripts/extract_logo.py <plik_z_logo.png|jpg|webp>

Zapisuje do app/static/:
  logo.png        — okrągły znak 512x512 z przezroczystym tłem (bez napisu KRASNAL)
  favicon-32.png, apple-touch-icon.png (180), icon-192.png, icon-512.png
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
BG_THRESHOLD = 242  # piksele jaśniejsze niż to traktujemy jako tło (kanwa off-white)


def find_badge_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box największego skupiska nie-tłowych pikseli w górnych ~72% obrazu
    (poniżej zwykle leży wordmark, który pomijamy)."""
    gray = ImageOps.grayscale(img)
    w, h = gray.size
    top_area = gray.crop((0, 0, w, int(h * 0.72)))
    mask = top_area.point(lambda p: 255 if p < BG_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("Nie znalazłem znaku — obraz wygląda na pusty/jednolity.")
    return bbox


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    img = Image.open(src).convert("RGBA")

    left, top, right, bottom = find_badge_bbox(img)
    # kwadrat wokół znaku z małym marginesem
    cx, cy = (left + right) // 2, (top + bottom) // 2
    r = int(max(right - left, bottom - top) / 2 * 1.02)
    square = img.crop((cx - r, cy - r, cx + r, cy + r))

    # maska kołowa -> przezroczystość poza znakiem
    size = square.size[0]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    square.putalpha(mask)

    STATIC.mkdir(parents=True, exist_ok=True)
    logo = square.resize((512, 512), Image.LANCZOS)
    logo.save(STATIC / "logo.png")
    for name, px in [("favicon-32.png", 32), ("apple-touch-icon.png", 180),
                     ("icon-192.png", 192), ("icon-512.png", 512)]:
        logo.resize((px, px), Image.LANCZOS).save(STATIC / name)
    print(f"Zapisano znak i ikony w {STATIC}")


if __name__ == "__main__":
    main()

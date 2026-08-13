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
# Piksele jaśniejsze niż próg traktujemy jako tło. 235 odcina zarówno kanwę
# off-white (~245-250), jak i delikatną winietę wokół znaku (~236-241).
BG_THRESHOLD = 235


def flatten_on_white(img: Image.Image) -> Image.Image:
    """Przezroczystość -> białe tło (inaczej alfa czernieje w skali szarości)."""
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(white, img)


def _row_widths(mask: Image.Image) -> list[int]:
    d = mask.load()
    w, h = mask.size
    widths = []
    for y in range(h):
        xs = [x for x in range(0, w, 4) if d[x, y]]
        widths.append(xs[-1] - xs[0] if xs else 0)
    return widths


def find_badge_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box znaku (koła) z pominięciem wordmarku pod nim.

    Znak zwęża się ku dołowi jak koło; wordmark pod spodem jest szeroki.
    Idziemy po profilu szerokości wierszy od góry i tniemy w miejscu,
    gdzie szerokość spada poniżej 5% maksimum — to dół znaku."""
    gray = ImageOps.grayscale(flatten_on_white(img).convert("RGB"))
    mask = gray.point(lambda p: 255 if p < BG_THRESHOLD else 0)
    widths = _row_widths(mask)

    content_rows = [y for y, wd in enumerate(widths) if wd > 0]
    if not content_rows:
        raise SystemExit("Nie znalazłem znaku — obraz wygląda na pusty/jednolity.")
    top = content_rows[0]
    max_width = max(widths)
    # znak (koło) leży NAD wordmarkiem, który bywa równie szeroki — dlatego
    # idziemy od góry: wejście w szeroką część koła, potem pierwszy zapad
    wide_from = next(y for y in content_rows if widths[y] >= 0.6 * max_width)
    bottom = content_rows[-1]
    for y in range(wide_from, content_rows[-1] + 1):
        if widths[y] < 0.05 * max_width:
            bottom = y
            break

    badge_area = mask.crop((0, top, mask.width, bottom))
    left, _, right, _ = badge_area.getbbox()
    return left, top, right, bottom


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    img = flatten_on_white(Image.open(src).convert("RGBA"))

    left, top, right, bottom = find_badge_bbox(img)

    # wybiel wszystko poniżej znaku (wordmark), żeby nie wszedł w kolisty kadr
    ImageDraw.Draw(img).rectangle((0, bottom, img.width, img.height),
                                  fill=(255, 255, 255, 255))

    diameter = max(right - left, bottom - top)
    r = diameter // 2
    cx = (left + right) // 2
    cy = (top + bottom) // 2

    # kadr dopełniany bielą (crop poza obraz doklejałby czerń)
    canvas = Image.new("RGBA", (2 * r, 2 * r), (255, 255, 255, 255))
    sx0, sy0 = max(0, cx - r), max(0, cy - r)
    sx1, sy1 = min(img.width, cx + r), min(img.height, cy + r)
    canvas.paste(img.crop((sx0, sy0, sx1, sy1)), (sx0 - (cx - r), sy0 - (cy - r)))
    square = canvas

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

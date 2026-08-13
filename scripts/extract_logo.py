"""Wyodrębnia znak (badge) z pełnego pliku logo Fit Krasnal.

Użycie:  .venv/bin/python scripts/extract_logo.py <plik_z_logo.png|jpg|webp>

Działanie: znajduje bounding box grafiki (z pominięciem ewentualnego wordmarku
pod znakiem), wycina go i robi tło przezroczystym przez flood-fill jasnych
pikseli OD NAROŻNIKÓW (białe detale wewnątrz grafiki zostają nietknięte).
Nie zakłada, że znak jest kołem — działa też dla kompozycji wystających poza okrąg.

Zapisuje do app/static/:  logo.png (512, przezroczyste tło),
favicon-32.png, apple-touch-icon.png (180), icon-192.png, icon-512.png
(ikony kwadratowe na tle #F9FAF8 — iOS wypełnia przezroczystość czernią)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
# Piksele jaśniejsze niż próg traktujemy jako tło (kanwa off-white ~245-250,
# winieta ~236-241).
BG_THRESHOLD = 235
BG_CANVAS = (249, 250, 248)  # background_main z palety
SENTINEL = (255, 0, 255, 255)  # kolor roboczy flood-filla


def flatten_on_white(img: Image.Image) -> Image.Image:
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
    """Bbox znaku. Jeśli pod znakiem jest wordmark oddzielony pustą przerwą,
    zostaje odcięty; znak ciągły (np. koła roweru u dołu) przechodzi w całości."""
    gray = ImageOps.grayscale(img.convert("RGB"))
    mask = gray.point(lambda p: 255 if p < BG_THRESHOLD else 0)
    widths = _row_widths(mask)

    content_rows = [y for y, wd in enumerate(widths) if wd > 0]
    if not content_rows:
        raise SystemExit("Nie znalazłem znaku — obraz wygląda na pusty/jednolity.")
    top, bottom = content_rows[0], content_rows[-1]

    # wordmark: szeroki blok po PUSTEJ przerwie — tnij na przerwie
    gap_start = None
    for y in range(top, bottom + 1):
        if widths[y] == 0:
            if gap_start is None:
                gap_start = y
        elif gap_start is not None:
            if y - gap_start >= 8:  # realna przerwa, nie szum
                bottom = gap_start
                break
            gap_start = None

    area = mask.crop((0, top, mask.width, bottom + 1))
    left, _, right, _ = area.getbbox()
    return left, top, right, bottom + 1


def make_background_transparent(img: Image.Image) -> Image.Image:
    """Flood-fill jasnego tła od narożników sentinelem, potem sentinel -> alpha 0."""
    img = img.convert("RGBA")
    w, h = img.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        try:
            ImageDraw.floodfill(img, corner, SENTINEL, thresh=28)
        except (ValueError, RecursionError):
            pass
    data = img.getdata()
    img.putdata([(0, 0, 0, 0) if px[:3] == SENTINEL[:3] else px for px in data])
    return img


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    img = flatten_on_white(Image.open(src).convert("RGBA"))

    left, top, right, bottom = find_badge_bbox(img)
    m = int(max(right - left, bottom - top) * 0.02)
    crop = img.crop((max(0, left - m), max(0, top - m),
                     min(img.width, right + m), min(img.height, bottom + m)))
    art = make_background_transparent(crop)

    # dopełnij do kwadratu (przezroczyście) i przeskaluj
    side = max(art.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
    logo = square.resize((512, 512), Image.LANCZOS)

    STATIC.mkdir(parents=True, exist_ok=True)
    logo.save(STATIC / "logo.png")

    # ikony kwadratowe na tle marki
    for name, px in [("apple-touch-icon.png", 180), ("icon-192.png", 192),
                     ("icon-512.png", 512)]:
        canvas = Image.new("RGBA", (px, px), (*BG_CANVAS, 255))
        margin = int(px * 0.06)
        scaled = logo.resize((px - 2 * margin, px - 2 * margin), Image.LANCZOS)
        canvas.paste(scaled, (margin, margin), scaled)
        canvas.convert("RGB").save(STATIC / name)
    logo.resize((32, 32), Image.LANCZOS).save(STATIC / "favicon-32.png")
    print(f"Zapisano znak i ikony w {STATIC}")


if __name__ == "__main__":
    main()

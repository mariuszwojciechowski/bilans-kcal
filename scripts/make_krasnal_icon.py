"""Wycina głowę krasnala z pełnej grafiki źródłowej i robi z niej maskę alfa
72×72 do użycia jako `background: currentColor` + `mask-image` w CSS
(patrz TODO/DONE „Podmiana ikony krasnala z prawdziwej grafiki 24×24").

Użycie:  .venv/bin/python scripts/make_krasnal_icon.py [ścieżka_źródła] [--stroke N]

Domyślne źródło: data/krasnal-icon-source.png (poza repo — data/ jest
w .gitignore). Źródło to czarna kreska na białym tle, bez przezroczystości
(alfa=255 wszędzie), więc próg jasności zamiast flood-filla.

Zapisuje app/static/krasnal-24.png (RGB czarny, alfa = maska tuszu) oraz
podgląd kontrolny (kompozyt 20/24 px na tle jasnym i ciemnym, pokolorowany
na --stone) do /tmp — ścieżka wypisana na końcu."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "data" / "krasnal-icon-source.png"
INK_THRESHOLD = 128  # kreska czysto czarna, tło czysto białe — próg nie jest wrażliwy
# Dobrana wizualnie (kroki 1-2 planu): przy skali ~1200px -> 72px (~17x),
# MaxFilter(11) daje po zeskalowaniu kreskę ~0.7px — czapka i broda czytelne
# jako zwarte kształty, twarz się nie zlewa w plamę.
DEFAULT_STROKE = 11


def build_mask(src: Path, stroke: int) -> Image.Image:
    if not src.exists():
        raise SystemExit(f"Nie znalazłem źródła {src} — plik jest poza repo (data/ w .gitignore).")
    gray = Image.open(src).convert("L")
    ink = gray.point(lambda p: 255 if p < INK_THRESHOLD else 0)
    bbox = ink.getbbox()
    if bbox is None:
        raise SystemExit("Nie znalazłem kreski — obraz wygląda na pusty/jednolity.")

    left, top, right, bottom = bbox
    crop = ink.crop(bbox)

    # dopełnienie do kwadratu (przezroczyście) + margines 4% boku
    side = max(crop.width, crop.height)
    margin = int(side * 0.04)
    square_side = side + 2 * margin
    square = Image.new("L", (square_side, square_side), 0)
    square.paste(crop, ((square_side - crop.width) // 2, (square_side - crop.height) // 2))

    if stroke > 1:
        square = square.filter(ImageFilter.MaxFilter(stroke))

    return square.resize((72, 72), Image.LANCZOS)


def make_preview(mask: Image.Image, out_path: Path) -> None:
    bg_colors = {"light": (249, 250, 248), "dark": (19, 23, 21)}
    fg_colors = {"light": (108, 117, 125), "dark": (154, 163, 157)}
    sizes = (20, 24)
    pad = 12
    cell_w = sum(sizes) + pad * (len(sizes) + 1)
    canvas = Image.new("RGB", (cell_w * 2, 24 + pad * 2), (255, 255, 255))
    for col, theme in enumerate(("light", "dark")):
        tile = Image.new("RGBA", (cell_w, 24 + pad * 2), (*bg_colors[theme], 255))
        colored = Image.new("RGBA", mask.size, (*fg_colors[theme], 0))
        colored.putalpha(mask)
        x = pad
        for size in sizes:
            icon = colored.resize((size, size), Image.LANCZOS)
            tile.paste(icon, (x, pad), icon)
            x += size + pad
        canvas.paste(tile, (col * cell_w, 0))
    canvas.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=str(DEFAULT_SOURCE))
    parser.add_argument("--stroke", type=int, default=DEFAULT_STROKE)
    args = parser.parse_args()

    mask = build_mask(Path(args.source).expanduser(), args.stroke)

    STATIC.mkdir(parents=True, exist_ok=True)
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.putalpha(mask)
    out_path = STATIC / "krasnal-24.png"
    out.save(out_path, optimize=True)
    print(f"Zapisano {out_path}")

    preview_path = Path(f"/tmp/krasnal-icon-preview-stroke{args.stroke}.png")
    make_preview(mask, preview_path)
    print(f"Podgląd: {preview_path}")


if __name__ == "__main__":
    main()

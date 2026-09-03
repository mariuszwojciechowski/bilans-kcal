"""Wariant czarno-biały znaku (z app/static/logo.png):

  logo-bw.png — twarde czarno-białe (styl stempla/grawiury), jedyny wariant
  faktycznie renderowany w szablonach (patrz {% if has_logo %} w app/templates/).

Użycie:  .venv/bin/python scripts/logo_variants.py
"""

from pathlib import Path

from PIL import Image, ImageOps

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def main() -> None:
    src = STATIC / "logo.png"
    if not src.exists():
        raise SystemExit("Brak app/static/logo.png — najpierw uruchom extract_logo.py")
    img = Image.open(src).convert("RGBA")
    alpha = img.getchannel("A")

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=1)

    bw = gray.point(lambda p: 0 if p < 150 else 255)
    hard = Image.merge("LA", (bw, alpha)).convert("RGBA")
    hard.save(STATIC / "logo-bw.png")

    print(f"Zapisano logo-bw.png w {STATIC}")


if __name__ == "__main__":
    main()

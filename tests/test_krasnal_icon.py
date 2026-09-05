"""Ikona krasnala przy komunikatach (TODO/DONE „Podmiana ikony krasnala
z prawdziwej grafiki 24×24"): `krasnalSays()` w mobile.html odwołuje się do
`/static/krasnal-24.png`, wygenerowanego przez `scripts/make_krasnal_icon.py`.
Ten test pilnuje, żeby ścieżka użyta w JS/CSS naprawdę istniała, była
serwowana i żeby plik był sensowną maską alfa (nie pustą, nie bez
przezroczystości)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
MOBILE_TEMPLATE = Path(__file__).resolve().parent.parent / "app" / "templates" / "mobile.html"


def test_krasnal_icon_static_file_served_200():
    with TestClient(app) as client:
        r = client.get("/static/krasnal-24.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"


def test_krasnal_icon_is_alpha_mask_72x72():
    img = Image.open(STATIC / "krasnal-24.png")
    assert img.size == (72, 72)
    assert "A" in img.getbands()

    w, h = img.size
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    for x, y in corners:
        assert img.getpixel((x, y))[3] == 0, f"róg {(x, y)} powinien być przezroczysty"

    mid_x = w // 2
    center_column_has_ink = any(
        img.getpixel((mid_x, y))[3] > 0 for y in range(h)
    )
    assert center_column_has_ink, "środkowa kolumna powinna zawierać tusz (nie pusta maska)"


def test_mobile_template_icon_paths_are_served():
    text = MOBILE_TEMPLATE.read_text(encoding="utf-8")
    paths = set(re.findall(r"/static/krasnal-[\w.@-]+\.png", text))
    assert paths, "szablon powinien odwoływać się do co najmniej jednej grafiki krasnal-*.png"
    with TestClient(app) as client:
        for path in paths:
            r = client.get(path)
            assert r.status_code == 200, f"{path} nie jest serwowana"

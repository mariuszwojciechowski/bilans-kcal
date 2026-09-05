"""Ikona krasnala przy komunikatach (TODO/DONE „Ikona krasnala przy
komunikatach"): `krasnalSays()` w mobile.html odwołuje się dziś do
`/static/icon-192.png` (właściciel jeszcze nie dostarczył wyciętej
`krasnal-24.png` — patrz TODO.md). Ten test pilnuje, żeby ścieżka użyta
w JS naprawdę istniała i była serwowana."""
from fastapi.testclient import TestClient

from app.main import app


def test_krasnal_icon_static_file_served_200():
    with TestClient(app) as client:
        r = client.get("/static/icon-192.png")
        assert r.status_code == 200

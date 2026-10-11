"""Utwardzenie publicznych interfejsów (app/middleware.py, main.install_hardening):
nagłówki bezpieczeństwa, CSRF po origin, filtr Host, limit zdjęcia."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import install_hardening
from app.middleware import CSP


def _mini(**kw):
    """Mała aplikacja z tym samym zestawem middleware co produkcyjna."""
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.post("/api/thing")
    def post_thing():
        return {"ok": True}

    @app.post("/api/meals/photo")
    async def photo():
        return {"ok": True}

    defaults = dict(debug=True, allowed_hosts=["*"], photo_limit=1024)
    defaults.update(kw)
    install_hardening(app, **defaults)
    return TestClient(app)


def test_security_headers_present_and_hsts_only_outside_debug():
    r = _mini(debug=True).get("/ping")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["permissions-policy"] == "camera=(self), geolocation=()"
    assert r.headers["content-security-policy"] == CSP
    assert "frame-ancestors 'none'" in CSP and "https://accounts.google.com" in CSP
    assert "strict-transport-security" not in r.headers
    r = _mini(debug=False).get("/ping")
    assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_real_app_login_page_has_headers():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/login")
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("headers", [
    {"origin": "https://evil.example"},
    {"referer": "https://evil.example/page"},
    {"sec-fetch-site": "cross-site", "origin": "http://testserver"},
    {"sec-fetch-site": "same-site"},
])
def test_csrf_rejects_foreign_origin(headers):
    r = _mini().post("/api/thing", headers=headers)
    assert r.status_code == 403
    assert "odrzucone" in r.json()["detail"]


@pytest.mark.parametrize("headers", [
    {},                                                        # curl / TestClient
    {"origin": "http://testserver"},                           # ta sama strona
    {"origin": "http://testserver", "sec-fetch-site": "same-origin"},   # przeglądarka / Capacitor
    {"sec-fetch-site": "none"},                                # wpisanie adresu ręcznie
    {"referer": "http://testserver/mobile"},
])
def test_csrf_allows_same_origin(headers):
    assert _mini().post("/api/thing", headers=headers).status_code == 200


def test_csrf_ignores_safe_methods():
    assert _mini().get("/ping", headers={"origin": "https://evil.example"}).status_code == 200


def test_trusted_host_filter():
    c = _mini(allowed_hosts=["fit.example"])
    assert c.get("/ping", headers={"host": "fit.example"}).status_code == 200
    assert c.get("/ping", headers={"host": "evil.example"}).status_code == 400
    assert _mini(allowed_hosts=["*"]).get("/ping", headers={"host": "anything"}).status_code == 200


def test_photo_body_limit_by_content_length():
    c = _mini(photo_limit=1024)
    r = c.post("/api/meals/photo", content=b"x" * 2048,
               headers={"content-type": "application/octet-stream"})
    assert r.status_code == 413 and "za duże" in r.json()["detail"]
    r = c.post("/api/meals/photo", content=b"x" * 100,
               headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200
    # inne ścieżki bez limitu
    assert c.post("/api/thing", content=b"x" * 2048).status_code == 200

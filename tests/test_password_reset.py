"""Reset hasła mailem: /password-reset → link → nowe hasło.

Anti-enumeracja (ta sama odpowiedź niezależnie od tego, czy konto istnieje),
jednorazowość tokenu, TTL 60 min, throttle 3 żądania/h, tryb oidc → 404.
Mail mockujemy — serwis bez klucza Resend tylko loguje (patrz services/mail).
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import PasswordResetToken, UsageDaily, User
from app.services import password_reset as reset_service

INVITE = "test-invite-code"
OLD = "tajnehaslo1"
NEW = "nowehaslo22"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'reset.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
    auth._failed.clear()
    auth._invite_throttle.attempts.clear()
    reset_service._request_times.clear()          # throttle globalny w procesie

    monkeypatch.setattr("app.services.mail.send_password_reset", _fake_mail)

    from app.main import app

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = _override
    with TestClient(app, follow_redirects=False) as c:
        c.session_factory = SessionLocal
        yield c
    app.dependency_overrides.clear()


_SENT: list[str] = []          # adresy URL wyłapane z linków resetu


def _fake_mail(to: str, url: str) -> bool:
    _SENT.append(url)
    return True


@pytest.fixture(autouse=True)
def _clean_mail_log():
    _SENT.clear()
    yield
    _SENT.clear()


def _register(client, email="tester@example.com", password=OLD):
    resp = client.post("/register", data={
        "email": email, "password": password, "password2": password,
        "invite_code": INVITE,
    })
    assert resp.status_code == 303


def _request(client, email="tester@example.com"):
    resp = client.post("/password-reset/request", data={"email": email})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/password-reset?sent=1"


def _last_token() -> str:
    """Token z ostatniego wychwycenego linku (po `/password-reset/`)."""
    assert _SENT, "mail nie został wysłany"
    return _SENT[-1].rsplit("/password-reset/", 1)[1]


# ── żądanie linku ──────────────────────────────────────────────────────────

def test_login_page_links_to_reset(client):
    assert '/password-reset"' in client.get("/login").text


def test_request_sends_link_and_anti_enumerates(client):
    _register(client)
    _request(client)

    assert len(_SENT) == 1
    url = _SENT[0]
    assert url.startswith("https://fit.krasnal.cc/password-reset/")
    assert len(_last_token()) >= 32

    # nieistniejące konto: ta sama odpowiedź, zero maili
    _request(client, email="nie-ma-takiego@example.com")
    assert len(_SENT) == 1

    # w bazie leży tylko SHA-256 tokenu, nie token
    db = client.session_factory()
    row = db.scalars(select(PasswordResetToken)).one()
    assert row.token_hash != _last_token()
    assert len(row.token_hash) == 64
    db.close()


def test_request_is_throttled_to_three_per_hour(client):
    _register(client)
    for _ in range(5):
        _request(client)
    assert len(_SENT) == reset_service.MAX_REQUESTS_PER_HOUR


def test_request_bumps_usage_only_when_sent(client):
    _register(client)
    _request(client)

    db = client.session_factory()
    rows = db.scalars(select(UsageDaily).where(
        UsageDaily.event == "password_reset_request")).all()
    assert rows and rows[0].count == 1
    db.close()

    # nieistniejące konto nie zostawia śladu na /usage
    _request(client, email="nie-ma-takiego@example.com")
    db = client.session_factory()
    rows = db.scalars(select(UsageDaily).where(
        UsageDaily.event == "password_reset_request")).all()
    assert rows and rows[0].count == 1
    db.close()


# ── strona z tokenem i ustawienie hasła ────────────────────────────────────

def test_full_reset_flow(client):
    _register(client)
    _request(client)
    token = _last_token()

    page = client.get(f"/password-reset/{token}")
    assert page.status_code == 200 and "Nowe hasło" in page.text

    resp = client.post(f"/password-reset/{token}",
                       data={"password": NEW, "password2": NEW})
    assert resp.headers["location"] == "/login?changed=1"

    # nowym hasłem loguje, starym nie; zielony baner na /login
    assert "Hasło zmienione" in client.get("/login?changed=1").text
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": OLD}).headers["location"] == "/login?error=bad"
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": NEW}).headers["location"] == "/"


def test_token_is_single_use(client):
    _register(client)
    _request(client)
    token = _last_token()

    first = client.post(f"/password-reset/{token}",
                        data={"password": NEW, "password2": NEW})
    assert first.headers["location"] == "/login?changed=1"

    second = client.post(f"/password-reset/{token}",
                         data={"password": "inneh3slo9", "password2": "inneh3slo9"})
    assert second.headers["location"] == f"/password-reset/{token}?error=invalid"

    # hasło z pierwszej próby zostało
    db = client.session_factory()
    user = db.scalars(select(User)).one()
    assert auth.verify_password(NEW, user.password_hash)
    db.close()


def test_peek_does_not_consume_token(client):
    """GET (np. skaner podglądający link) nie może spurżować tokenu."""
    _register(client)
    _request(client)

    page1 = client.get(f"/password-reset/{_last_token()}")
    page2 = client.get(f"/password-reset/{_last_token()}")
    assert page1.status_code == page2.status_code == 200

    resp = client.post(f"/password-reset/{_last_token()}",
                       data={"password": NEW, "password2": NEW})
    assert resp.headers["location"] == "/login?changed=1"


def test_expired_token_is_invalid(client):
    _register(client)
    _request(client)
    token = _last_token()

    db = client.session_factory()
    db.scalars(select(PasswordResetToken)).one().expires_at = (
        datetime.utcnow() - timedelta(minutes=1))
    db.commit()
    db.close()

    page = client.get(f"/password-reset/{token}")
    assert "Poproś o nowy link" in page.text
    resp = client.post(f"/password-reset/{token}",
                       data={"password": NEW, "password2": NEW})
    assert resp.headers["location"] == f"/password-reset/{token}?error=invalid"


def test_new_password_validated(client):
    _register(client)
    _request(client)
    token = _last_token()

    resp = client.post(f"/password-reset/{token}",
                       data={"password": NEW, "password2": "inne12345"})
    assert resp.headers["location"] == f"/password-reset/{token}?error=mismatch"

    resp = client.post(f"/password-reset/{token}",
                       data={"password": "krotkie", "password2": "krotkie"})
    assert resp.headers["location"] == f"/password-reset/{token}?error=short"

    # token przeżył błędne próby — hasło da się ustawić
    resp = client.post(f"/password-reset/{token}",
                       data={"password": NEW, "password2": NEW})
    assert resp.headers["location"] == "/login?changed=1"


def test_garbage_token_rejected(client):
    _register(client)
    page = client.get("/password-reset/abc-nie-tamten-token")
    assert "Poproś o nowy link" in page.text


def test_google_account_can_set_password_by_reset(client):
    _register(client)
    db = client.session_factory()
    db.scalars(select(User)).one().password_hash = None    # symulacja konta Google
    db.commit()
    db.close()

    _request(client)
    resp = client.post(f"/password-reset/{_last_token()}",
                       data={"password": NEW, "password2": NEW})
    assert resp.headers["location"] == "/login?changed=1"

    db = client.session_factory()
    assert auth.verify_password(NEW, db.scalars(select(User)).one().password_hash)
    db.close()


def test_reset_bumps_usage_and_clears_login_lockout(client):
    _register(client)
    for _ in range(5):    # zablokuj konto nieudanymi próbami
        client.post("/login", data={"email": "tester@example.com",
                                    "password": "zle-haslo-x"})
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": OLD}).headers["location"] == "/login?error=locked"

    _request(client)
    client.post(f"/password-reset/{_last_token()}",
                data={"password": NEW, "password2": NEW})

    # reset zdejmował blokadę: nowym hasłem loguje od razu
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": NEW}).headers["location"] == "/"

    db = client.session_factory()
    events = {r.event for r in db.scalars(select(UsageDaily)).all()}
    assert {"password_reset_request", "password_reset_done"} <= events
    db.close()


def test_reset_routes_are_404_in_oidc_mode(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.AUTH_MODE", "oidc")
    assert client.get("/password-reset").status_code == 404
    assert client.post("/password-reset/request",
                       data={"email": "x@example.com"}).status_code == 404
    assert client.get("/password-reset/jakis-token").status_code == 404
    assert client.post("/password-reset/jakis-token",
                       data={"password": NEW, "password2": NEW}).status_code == 404

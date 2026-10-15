"""Zmiana hasła w Ustawieniach (POST /settings/password) i karty na /settings.

Konta założone przez Google (password_hash is None) ustawiają tu PIERWSZE
hasło; konta hasłowe zmieniają istniejące po podaniu obecnego.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import UsageDaily, User

INVITE = "test-invite-code"
OLD = "tajnehaslo1"
NEW = "nowehaslo22"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'password.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
    auth._failed.clear()                      # throttle jest globalny w procesie
    auth._invite_throttle.attempts.clear()

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


def _register(client, email="tester@example.com", password=OLD):
    resp = client.post("/register", data={
        "email": email, "password": password, "password2": password,
        "invite_code": INVITE,
    })
    assert resp.status_code == 303


def _change(client, old=OLD, new=NEW, new2=None):
    return client.post("/settings/password", data={
        "old_password": old,
        "new_password": new,
        "password2": new2 if new2 is not None else new,
    })


def test_change_password_happy_path(client):
    _register(client)
    resp = _change(client)
    assert resp.status_code == 303 and resp.headers["location"] == "/settings?saved=1"

    db = client.session_factory()
    user = db.scalars(select(User)).one()
    assert auth.verify_password(NEW, user.password_hash)
    assert not auth.verify_password(OLD, user.password_hash)
    db.close()

    # nowe hasło loguje, stare już nie
    client.post("/logout")
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": OLD}).headers["location"] == "/login?error=bad"
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": NEW}).headers["location"] == "/"


def test_change_password_requires_current_one(client):
    _register(client)
    resp = _change(client, old="zle-stare")
    assert resp.headers["location"] == "/settings?error=bad_password"

    db = client.session_factory()
    user = db.scalars(select(User)).one()
    assert auth.verify_password(OLD, user.password_hash)   # bez zmian
    db.close()


def test_change_password_validates_new_one(client):
    _register(client)
    assert _change(client, new2="inne1234").headers["location"] == "/settings?error=mismatch"
    assert _change(client, new="krotkie").headers["location"] == "/settings?error=short"

    db = client.session_factory()
    user = db.scalars(select(User)).one()
    assert auth.verify_password(OLD, user.password_hash)   # żadna próba nie zapisała
    db.close()


def test_google_account_sets_first_password(client):
    """Konto z rejestracji Google nie ma hasła — karta pokazuje „Ustaw hasło"
    i przyjmuje formularz bez pola obecnego hasła."""
    _register(client)

    db = client.session_factory()
    db.scalars(select(User)).one().password_hash = None    # symulacja konta Google
    db.commit()

    page = client.get("/settings")
    assert "Ustaw hasło" in page.text and "Obecne hasło" not in page.text

    resp = client.post("/settings/password", data={"new_password": NEW, "password2": NEW})
    assert resp.headers["location"] == "/settings?saved=1"

    user = db.scalars(select(User)).one()
    assert auth.verify_password(NEW, user.password_hash)
    db.close()

    # od teraz działa zwykłe logowanie hasłem
    client.post("/logout")
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": NEW}).headers["location"] == "/"


def test_password_card_abides_by_oidc_mode(client, monkeypatch):
    """W trybie oidc hasła nie istnieją: karta zniknięcie, POST → 404
    (jak POST /login i /register)."""
    _register(client)
    monkeypatch.setattr("app.routers.settings.AUTH_MODE", "oidc")

    assert "Zmiana hasła" not in client.get("/settings").text
    assert _change(client).status_code == 404


def test_password_change_bumps_usage(client):
    """Krok „Statystyki": zmiana hasła zostawia ślad na /usage."""
    _register(client)
    assert _change(client).status_code == 303

    db = client.session_factory()
    rows = db.scalars(select(UsageDaily).where(
        UsageDaily.event == "password_change")).all()
    assert rows and rows[0].count == 1
    db.close()


# ── JSON API dla widoku /mobile (SPA) ──────────────────────────────────────

def _api_change(client, old=OLD, new=NEW, new2=None):
    return client.post("/api/settings/password", json={
        "old_password": old,
        "new_password": new,
        "password2": new2 if new2 is not None else new,
    })


def test_api_change_password_happy_path(client):
    _register(client)
    resp = _api_change(client)
    assert resp.status_code == 200 and resp.json() == {"ok": True}

    db = client.session_factory()
    assert auth.verify_password(NEW, db.scalars(select(User)).one().password_hash)
    db.close()


def test_api_change_password_errors_are_400_with_detail(client):
    """Błędy wracają jako `detail` (mobile pokazuje go pod formularzem)."""
    _register(client)
    bad_old = _api_change(client, old="zle")
    assert bad_old.status_code == 400
    assert "obecne hasło" in bad_old.json()["detail"]

    mismatch = client.post("/api/settings/password", json={
        "old_password": OLD, "new_password": NEW, "password2": "inne1234",
    })
    assert "identyczne" in mismatch.json()["detail"]

    short = client.post("/api/settings/password", json={
        "old_password": OLD, "new_password": "krotkie", "password2": "krotkie",
    })
    assert "za krótkie" in short.json()["detail"]

    db = client.session_factory()
    assert auth.verify_password(OLD, db.scalars(select(User)).one().password_hash)
    db.close()


def test_api_settings_reports_password_state(client):
    """/api/settings mówi /mobile, jaką kartę hasła pokazać."""
    _register(client)
    got = client.get("/api/settings").json()
    assert got["has_password"] is True and got["password_enabled"] is True

    db = client.session_factory()
    db.scalars(select(User)).one().password_hash = None   # konto z Google
    db.commit()
    db.close()

    assert client.get("/api/settings").json()["has_password"] is False


def test_api_password_hidden_in_oidc_mode(client, monkeypatch):
    _register(client)
    monkeypatch.setattr("app.routers.settings.AUTH_MODE", "oidc")

    resp = client.get("/api/settings")
    assert resp.json()["password_enabled"] is False
    assert _api_change(client).status_code == 404


def test_api_google_account_sets_first_password(client):
    """Konto z Google ustawia pierwsze hasło bez pola obecnego."""
    _register(client)

    db = client.session_factory()
    db.scalars(select(User)).one().password_hash = None
    db.commit()
    db.close()

    resp = client.post("/api/settings/password",
                       json={"new_password": NEW, "password2": NEW})
    assert resp.status_code == 200

    db = client.session_factory()
    assert auth.verify_password(NEW, db.scalars(select(User)).one().password_hash)
    db.close()

    client.post("/logout")
    assert client.post("/login", data={"email": "tester@example.com",
                                       "password": NEW}).headers["location"] == "/"

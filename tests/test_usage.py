"""Statystyki użycia (TODO.md „Statystyki użycia — adopcja i najczęściej
klikane opcje"). Wzorzec `client` jak w test_consent.py."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import UsageDaily, User
from app.services import usage

INVITE = "test-invite-code"
ADMIN_EMAIL = "admin@example.com"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
    monkeypatch.setattr("app.deps.ADMIN_EMAIL", ADMIN_EMAIL)
    auth._failed.clear()
    from app.main import app

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = _override
    with TestClient(app, follow_redirects=False) as c:
        c._SessionLocal = SessionLocal
        yield c
    app.dependency_overrides.clear()


def _register(client, email="alice@example.com"):
    data = {"email": email, "password": "tajnehaslo1", "password2": "tajnehaslo1",
            "invite_code": INVITE}
    r = client.post("/register", data=data)
    assert r.status_code == 303 and r.headers["location"] == "/", r.headers


def test_bump_creates_row_and_increments_same_day(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bump.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    db.add(User(email="t@t"))
    db.commit()
    user_id = db.scalar(select(User.id))

    usage.bump(db, user_id, "login")
    usage.bump(db, user_id, "login")

    rows = db.scalars(select(UsageDaily)).all()
    assert len(rows) == 1
    assert rows[0].count == 2
    assert rows[0].event == "login"
    assert rows[0].date == date.today()


def test_user_ref_stable_and_distinct_per_user():
    ref1a = usage.user_ref(1)
    ref1b = usage.user_ref(1)
    ref2 = usage.user_ref(2)
    assert ref1a == ref1b
    assert ref1a != ref2
    assert len(ref1a) == 12


def test_api_usage_unknown_event_is_422_and_writes_nothing(client):
    _register(client)
    r = client.post("/api/usage", json={"event": "not_a_real_event"})
    assert r.status_code == 422

    db = client._SessionLocal()
    assert db.scalars(select(UsageDaily)).all() == []
    db.close()


def test_api_usage_known_event_bumps_counter(client):
    _register(client)
    r = client.post("/api/usage", json={"event": "tab_trends"})
    assert r.status_code == 204

    db = client._SessionLocal()
    rows = db.scalars(select(UsageDaily)).all()
    assert len(rows) == 1
    assert rows[0].event == "tab_trends"
    db.close()


def test_usage_page_for_non_admin_is_404(client):
    _register(client, email="alice@example.com")
    r = client.get("/usage")
    assert r.status_code == 404


def test_usage_page_for_admin_ok_without_email_leak(client, monkeypatch):
    monkeypatch.setattr("app.services.usage.ADMIN_EMAIL", ADMIN_EMAIL)
    _register(client, email="alice@example.com")
    r = client.post("/api/usage", json={"event": "tab_today"})
    assert r.status_code == 204
    _register(client, email=ADMIN_EMAIL)  # ostatnia rejestracja = bieżąca sesja
    r = client.post("/api/usage", json={"event": "tab_today"})  # generuje trochę danych
    assert r.status_code == 204

    r = client.get("/usage")
    assert r.status_code == 200
    assert ADMIN_EMAIL not in r.text
    # domyślny scope="others" — pseudonim admina nie wchodzi, alice tak
    assert usage.user_ref(2) not in r.text
    assert usage.user_ref(1) in r.text


def test_usage_scope_switch_others_all_me(client, monkeypatch):
    monkeypatch.setattr("app.services.usage.ADMIN_EMAIL", ADMIN_EMAIL)
    _register(client, email="alice@example.com")
    r = client.post("/api/usage", json={"event": "tab_today"})
    assert r.status_code == 204
    _register(client, email=ADMIN_EMAIL)
    r = client.post("/api/usage", json={"event": "tab_today"})
    assert r.status_code == 204

    admin_ref = usage.user_ref(2)
    alice_ref = usage.user_ref(1)

    r = client.get("/usage?scope=others")
    assert r.status_code == 200
    assert admin_ref not in r.text
    assert alice_ref in r.text
    assert "Moje dni" not in r.text

    r = client.get("/usage?scope=all")
    assert r.status_code == 200
    assert admin_ref in r.text
    assert alice_ref in r.text
    assert "(ja)" in r.text
    assert "Moje dni" not in r.text

    r = client.get("/usage?scope=me")
    assert r.status_code == 200
    assert admin_ref in r.text
    assert alice_ref not in r.text
    assert "Moje dni" in r.text
    assert ADMIN_EMAIL not in r.text


def test_usage_scope_invalid_is_422(client):
    _register(client, email=ADMIN_EMAIL)
    r = client.get("/usage?scope=xyz")
    assert r.status_code == 422


def test_meal_text_bumps_meal_text_counter(client, monkeypatch):
    _register(client, email="alice@example.com")
    r = client.post("/api/settings/consent", json={"granted": True})
    assert r.status_code == 200

    monkeypatch.setattr("app.services.meal_vision.llm_configured", lambda *a, **kw: False)
    r = client.post("/api/meals/text", data={"description": "kanapka"})
    assert r.status_code == 200

    db = client._SessionLocal()
    rows = db.scalars(select(UsageDaily).where(UsageDaily.event == "meal_text")).all()
    assert len(rows) == 1 and rows[0].count == 1
    db.close()


def test_bump_failure_does_not_break_endpoint(client, monkeypatch):
    """Najważniejszy test w tym pliku — awaria zapisu statystyk (błąd wewnątrz
    bump()) nie może zepsuć odpowiedzi endpointu, który tylko przy okazji ją
    zgłasza. bump() łapie wyjątek sam — nie polegamy na endpoincie."""
    _register(client, email="alice@example.com")

    def _boom(*a, **kw):
        raise RuntimeError("db is on fire")

    monkeypatch.setattr("app.services.usage.user_ref", _boom)
    r = client.post("/api/settings/consent", json={"granted": True})
    assert r.status_code == 200
    monkeypatch.setattr("app.services.meal_vision.llm_configured", lambda *a, **kw: False)

    r = client.post("/api/meals/text", data={"description": "kanapka"})
    assert r.status_code == 200, r.text  # bump padło po cichu, endpoint nie ucierpiał

    db = client._SessionLocal()
    assert db.scalars(select(UsageDaily)).all() == []  # nic nie zostało zapisane
    db.close()


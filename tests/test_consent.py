"""RODO: nota /prywatnosc, zgoda na LLM, retencja (TODO.md).

Wzorzec `client` jak w test_birth_year.py — rejestracja przez prawdziwy
endpoint, nie ORM wprost. `process_queue` jest testowany osobno na poziomie
serwisu (jak w test_queue_settings.py), bo otwiera własną sesję DB."""
from datetime import date, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth, db as app_db
from app.db import Base, db_session
from app.models import PendingMeal, User
from app.services import consent, meal_queue
from app.services.meal_vision import MealEstimate, MealItem

INVITE = "test-invite-code"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'consent.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.main.INVITE_CODE", INVITE)
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
        c._SessionLocal = SessionLocal  # do zaglądania w bazę z testów
        yield c
    app.dependency_overrides.clear()


def _register(client, email="alice@example.com", consent_checked=False):
    data = {"email": email, "password": "tajnehaslo1", "password2": "tajnehaslo1",
            "invite_code": INVITE}
    if consent_checked:
        data["consent_llm_photos"] = "true"
    r = client.post("/register", data=data)
    assert r.status_code == 303 and r.headers["location"] == "/", r.headers


def test_privacy_page_ok_without_login(client):
    r = client.get("/prywatnosc")
    assert r.status_code == 200
    assert "prywatn" in r.text.lower()


def test_register_without_checkbox_has_no_consent(client):
    _register(client, consent_checked=False)
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["consent_llm_photos"] is False


def test_register_with_checkbox_grants_consent(client):
    _register(client, consent_checked=True)
    r = client.get("/api/settings")
    assert r.json()["consent_llm_photos"] is True


def test_meal_text_without_consent_is_409(client):
    _register(client, consent_checked=False)
    r = client.post("/api/meals/text", data={"description": "jajecznica"})
    assert r.status_code == 409
    assert "zgod" in r.json()["detail"].lower()


def test_meal_text_after_grant_is_not_409(client, monkeypatch):
    _register(client, consent_checked=False)

    def _fake_estimate(*a, **kw):
        return MealEstimate(
            description="jajecznica",
            items=[MealItem(name="jajko", mass_g=60, kcal=90, protein_g=7,
                            fat_g=6.5, carbs_g=0.5, confidence="high")],
            assumptions=[], kcal_min=80, kcal_max=100,
        )

    monkeypatch.setattr("app.main.meal_vision.llm_configured", lambda *a, **kw: True)
    monkeypatch.setattr("app.main.meal_vision.estimate_from_text", _fake_estimate)

    r = client.post("/api/settings/consent", json={"granted": True})
    assert r.status_code == 200

    r = client.post("/api/meals/text", data={"description": "jajecznica"})
    assert r.status_code == 200, r.text
    assert r.json()["kcal"] == 90


def test_withdraw_consent_deletes_pending_queue(client, monkeypatch):
    _register(client, consent_checked=True)

    # bez klucza LLM -> ląduje w kolejce
    monkeypatch.setattr("app.main.meal_vision.llm_configured", lambda *a, **kw: False)
    r = client.post("/api/meals/text", data={"description": "kanapka"})
    assert r.status_code == 200 and r.json()["queued"] is True

    db = client._SessionLocal()
    assert len(db.scalars(select(PendingMeal)).all()) == 1
    db.close()

    r = client.post("/api/settings/consent", json={"granted": False})
    assert r.status_code == 200

    db = client._SessionLocal()
    assert len(db.scalars(select(PendingMeal)).all()) == 0
    db.close()


def test_consent_in_older_privacy_version_counts_as_no_consent(client, monkeypatch):
    _register(client, consent_checked=True)
    monkeypatch.setattr("app.services.consent.PRIVACY_VERSION", "2099-01-01")
    monkeypatch.setattr("app.main.PRIVACY_VERSION", "2099-01-01")
    r = client.get("/api/settings")
    assert r.json()["consent_llm_photos"] is False


def test_transfer_export_never_contains_llm_keys(client):
    """Test-strażnik (plan „Szyfrowanie sekretów" pkt 7) — eksport transferu
    nie może kiedyś zacząć wyciekać kluczy LLM."""
    _register(client, consent_checked=True)
    r = client.post("/api/settings/llm", json={"gemini_api_key": "AIzaSecretTestKey123"})
    assert r.status_code == 200
    payload = client.get("/api/transfer/export").json()
    assert "AIzaSecretTestKey123" not in str(payload)


def test_process_queue_skips_without_consent(tmp_path, monkeypatch):
    """process_queue otwiera własną sesję (get_session) — testujemy na poziomie serwisu."""
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(meal_queue, "PHOTOS_DIR", tmp_path / "photos")
    monkeypatch.setattr(app_db, "get_session", lambda: SessionLocal())

    db = SessionLocal()
    db.add(User(email="t@t"))
    db.commit()
    user_id = db.scalar(select(User.id))
    meal_queue.enqueue(db, user_id, date.today(), time(12, 0), description="kanapka")
    db.close()

    result = meal_queue.process_queue(user_id)
    assert result == {"processed": 0, "failed": 0}

    db = SessionLocal()
    assert len(db.scalars(select(PendingMeal)).all()) == 1  # nic nie ruszone
    db.close()

    consent.grant(SessionLocal(), user_id)
    db = SessionLocal()
    assert consent.has_consent(db, user_id)
    db.close()

"""Moje posiłki przez prawdziwe endpointy: izolacja między użytkownikami.

Testy w test_saved_meals.py sprawdzają model na poziomie ORM — przeszłyby
nawet, gdyby endpointy leakowały cudze dane. Tu dwóch użytkowników z osobnymi
sesjami (TestClient per user) uderza w API: lista, /use, DELETE i eksport
transferu nie mogą widzieć posiłków drugiego użytkownika."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session

INVITE = "test-invite-code"


@pytest.fixture
def clients(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'iso.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.main.INVITE_CODE", INVITE)
    auth._failed.clear()          # throttle jest globalny w procesie
    from app.main import app

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = _override
    with TestClient(app, follow_redirects=False) as a, \
         TestClient(app, follow_redirects=False) as b:
        for c, email in ((a, "alice@example.com"), (b, "bob@example.com")):
            r = c.post("/register", data={"email": email, "password": "tajnehaslo1",
                                          "password2": "tajnehaslo1", "invite_code": INVITE})
            assert r.status_code == 303 and r.headers["location"] == "/", r.headers
        yield a, b
    app.dependency_overrides.clear()


MEAL = {"name": "Sekretna jajecznica Alice", "kcal": 250, "protein_g": 15,
        "fat_g": 18, "carbs_g": 2}


def test_saved_meals_not_shared_between_users(clients):
    alice, bob = clients

    r = alice.post("/api/saved-meals", json=MEAL)
    assert r.status_code == 201
    meal_id = r.json()["id"]

    # Alice widzi swój posiłek, Bob ma pustą listę
    assert [m["name"] for m in alice.get("/api/saved-meals").json()] \
        == ["Sekretna jajecznica Alice"]
    assert bob.get("/api/saved-meals").json() == []

    # Bob nie może użyć ani skasować posiłku Alice po ID
    assert bob.post(f"/api/saved-meals/{meal_id}/use").status_code == 404
    assert bob.delete(f"/api/saved-meals/{meal_id}").status_code == 404

    # posiłek Alice nietknięty, /use działa dla właścicielki
    assert alice.post(f"/api/saved-meals/{meal_id}/use").status_code == 200

    # eksport transferu Boba nie zawiera posiłków Alice
    assert bob.get("/api/transfer/export").json()["saved_meals"] == []
    export_a = alice.get("/api/transfer/export").json()
    assert [m["name"] for m in export_a["saved_meals"]] == ["Sekretna jajecznica Alice"]


def test_saved_meals_require_auth(clients):
    from app.main import app
    with TestClient(app, follow_redirects=False) as anon:
        assert anon.get("/api/saved-meals").status_code == 401
        assert anon.post("/api/saved-meals", json=MEAL).status_code == 401

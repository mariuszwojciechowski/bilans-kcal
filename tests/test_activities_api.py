"""Testy API aktywności: POST /api/activities, DELETE, day_report z aktywnościami.

Wzorzec jak w test_saved_meals_api.py: prawdziwe zapytania przez TestClient,
sesja przez /register, profil i waga seedowane przez API (nie ORM wprost) —
inaczej rejestrowany użytkownik nie ma danych i /api/activities / /api/day
zwracają 409."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, _migrate, db_session
from app.models import Activity, WeightLog

INVITE = "test-invite-code"
WEIGHT_KG = 75


@pytest.fixture
def clients(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'activities.db'}")
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
            r = c.put("/api/profile", json={
                "birth_date": "1990-01-01", "sex": "M", "height_cm": 180,
            })
            assert r.status_code == 200, r.text
            r = c.post("/api/weight", json={
                "date": date.today().isoformat(), "weight_kg": WEIGHT_KG,
            })
            assert r.status_code == 200, r.text
        yield a, b, SessionLocal
    app.dependency_overrides.clear()


def test_running_with_distance_ignores_intensity(clients):
    alice, _, _ = clients
    resp = alice.post("/api/activities", json={
        "type": "running", "intensity": "lekka", "duration_min": 60, "distance_km": 5,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kcal"] == WEIGHT_KG * 5      # 375 — dystans, nie intensywność
    assert "bieg" in body["explanation"]


def test_cycling_uses_met_even_with_distance(clients):
    alice, _, _ = clients
    resp = alice.post("/api/activities", json={
        "type": "cycling", "intensity": "intensywna", "duration_min": 60,
        "distance_km": 999,                    # ignorowany
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["kcal"] == 750          # MET 10.0 × 75 kg × 1 h


def test_swimming_uses_met_even_with_distance(clients):
    alice, _, _ = clients
    resp = alice.post("/api/activities", json={
        "type": "swimming", "intensity": "intensywna", "duration_min": 60,
        "distance_km": 2,                      # informacyjny, ignorowany
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["kcal"] == 750          # MET 10.0 × 75 kg × 1 h


def test_steps_default_when_no_entry(clients):
    alice, _, _ = clients
    today = date.today().isoformat()
    resp = alice.get(f"/api/day/{today}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["steps"] == 5000
    assert body["steps_default"] is True


def test_delete_manual_activity_only(clients):
    alice, _, SessionLocal = clients

    resp = alice.post("/api/activities", json={
        "type": "running", "intensity": "umiarkowana", "duration_min": 30,
    })
    activity_id = resp.json()["id"]

    # cudza aktywność (garminowa, wstawiona bezpośrednio do bazy) — 404
    db = SessionLocal()
    garmin_activity = Activity(
        user_id=1, date=date.today(), type="running", duration_s=1800,
        distance_m=5000, kcal_garmin=420, garmin_id="garmin-12345", source="garmin",
    )
    db.add(garmin_activity)
    db.commit()
    db.refresh(garmin_activity)
    garmin_id = garmin_activity.id
    db.close()
    assert alice.delete(f"/api/activities/{garmin_id}").status_code == 404

    # własna, ręczna — OK, potem już nie istnieje
    assert alice.delete(f"/api/activities/{activity_id}").status_code == 200
    assert alice.delete(f"/api/activities/{activity_id}").status_code == 404


def test_activity_isolation_between_users(clients):
    alice, bob, _ = clients

    alice.post("/api/activities", json={
        "type": "running", "intensity": "umiarkowana", "duration_min": 30,
    })

    today = date.today().isoformat()
    a_activities = alice.get(f"/api/day/{today}").json()["activities"]
    b_activities = bob.get(f"/api/day/{today}").json()["activities"]

    assert len(a_activities) == 1
    assert b_activities == []


def test_migration_backfills_garmin_source(tmp_path):
    """Baza ze STARYM schematem `activity` (bez `source`) — po _migrate()
    kolumna istnieje z domyślnym 'garmin', a ORM select/insert nie wywala
    `no such column`. To jest dokładnie klasa błędu, która położyła prod."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old_schema.db'}")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE activity (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                garmin_id VARCHAR,
                date DATE NOT NULL,
                type VARCHAR NOT NULL,
                duration_s INTEGER NOT NULL,
                distance_m FLOAT,
                kcal_garmin INTEGER,
                avg_hr INTEGER
            )
        """))
        conn.execute(text("""
            INSERT INTO activity (user_id, garmin_id, date, type, duration_s,
                                   distance_m, kcal_garmin, avg_hr)
            VALUES (1, 'garmin-old-1', :today, 'running', 1800, 5000, 420, 150)
        """), {"today": date.today().isoformat()})
        conn.commit()

    _migrate(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    existing = db.scalar(select(Activity).where(Activity.garmin_id == "garmin-old-1"))
    assert existing is not None
    assert existing.source == "garmin"          # backfill

    new_activity = Activity(
        user_id=1, date=date.today(), type="cycling", duration_s=3600,
        kcal_garmin=500, garmin_id="garmin-old-2",
    )
    db.add(new_activity)
    db.commit()                                  # wywaliłoby się bez migracji
    db.refresh(new_activity)
    assert new_activity.source == "garmin"
    db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

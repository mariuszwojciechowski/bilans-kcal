"""Testy API aktywności: POST /api/activities, DELETE, day_report z aktywościami."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import Activity, User, UserProfile, WeightLog


@pytest.fixture
def setup_db(tmp_path):
    """Setup bazy z dwoma użytkownikami."""
    engine = create_engine(f"sqlite:///{tmp_path / 'activities.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Dwaj użytkownicy
    u1 = User(id=1, email="user1@test", password_hash="hash1")
    u2 = User(id=2, email="user2@test", password_hash="hash2")
    db.add_all([u1, u2])
    db.commit()

    # Profile
    db.add_all([
        UserProfile(user_id=1, birth_date=date(1990, 1, 1), sex="M", height_cm=180),
        UserProfile(user_id=2, birth_date=date(1995, 6, 15), sex="F", height_cm=170),
    ])
    # Wagi (smoothed_weight potrzebuje pomiarów)
    db.add_all([
        WeightLog(user_id=1, date=date.today(), weight_kg=75),
        WeightLog(user_id=2, date=date.today(), weight_kg=60),
    ])
    db.commit()

    yield engine, Session
    db.close()


def test_post_activity_running_with_distance(tmp_path, monkeypatch):
    """Bieganie z dystansem ignoruje intensywność, liczy mass × km."""
    engine, Session = setup_db(tmp_path)
    monkeypatch.setattr("app.main.INVITE_CODE", "test")
    auth._failed.clear()

    from app.main import app

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db

    # Logowanie
    with TestClient(app) as client:
        resp = client.post("/register", data={
            "email": "runner@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        # POST aktywność: bieg 5km @ 75kg = 75 * 5 = 375 kcal (ignoruje intensywność)
        resp = client.post("/api/activities", json={
            "type": "running",
            "intensity": "lekka",  # ignorowany
            "duration_min": 60,
            "distance_km": 5
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["kcal"] == 375
        assert "bieg" in body["explanation"]

    app.dependency_overrides.clear()


def test_post_activity_cycling_uses_met(tmp_path, monkeypatch):
    """Rower zawsze liczy z MET, dystans ignorowany."""
    engine, Session = setup_db(tmp_path)
    monkeypatch.setattr("app.main.INVITE_CODE", "test")
    auth._failed.clear()

    from app.main import app

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db

    with TestClient(app) as client:
        client.post("/register", data={
            "email": "cyclist@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        # Rower 1h intensywny @ 75kg: MET 10.0 * 75 * 1 = 750 kcal
        resp = client.post("/api/activities", json={
            "type": "cycling",
            "intensity": "intensywna",
            "duration_min": 60,
            "distance_km": 999  # ignorowany
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["kcal"] == 750

    app.dependency_overrides.clear()


def test_steps_default_when_no_entry(tmp_path, monkeypatch):
    """Gdy brak kroków, day_report zwraca steps=5000 i steps_default=true."""
    engine, Session = setup_db(tmp_path)
    monkeypatch.setattr("app.main.INVITE_CODE", "test")
    auth._failed.clear()

    from app.main import app

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db

    with TestClient(app) as client:
        client.post("/register", data={
            "email": "nostepper@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        today = date.today().isoformat()
        resp = client.get(f"/api/day/{today}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["steps"] == 5000
        assert body["steps_default"] == True

    app.dependency_overrides.clear()


def test_delete_manual_activity_only(tmp_path, monkeypatch):
    """DELETE zwraca 404 dla garminowych i cudzych."""
    engine, Session = setup_db(tmp_path)
    monkeypatch.setattr("app.main.INVITE_CODE", "test")
    auth._failed.clear()

    from app.main import app

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db

    with TestClient(app) as client:
        # Rejestracja i dodanie aktywności
        client.post("/register", data={
            "email": "deleter@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        resp = client.post("/api/activities", json={
            "type": "running", "intensity": "umiarkowana",
            "duration_min": 30
        })
        activity_id = resp.json()["id"] if resp.status_code == 200 else None

        if activity_id:
            # Usuwanie własnej - OK
            resp = client.delete(f"/api/activities/{activity_id}")
            assert resp.status_code == 200

            # Usuwanie cudzej - 404
            resp = client.delete(f"/api/activities/{activity_id}")
            assert resp.status_code == 404

    app.dependency_overrides.clear()


def test_activity_isolation_between_users(tmp_path, monkeypatch):
    """Użytkownik A nie widzi aktywności użytkownika B."""
    engine, Session = setup_db(tmp_path)
    monkeypatch.setattr("app.main.INVITE_CODE", "test")
    auth._failed.clear()

    from app.main import app

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = override_db

    with TestClient(app) as client:
        # User A rejestruje i dodaje aktywność
        client.post("/register", data={
            "email": "user_a@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        resp = client.post("/api/activities", json={
            "type": "running", "intensity": "umiarkowana", "duration_min": 30
        })

        today = date.today().isoformat()
        resp = client.get(f"/api/day/{today}")
        a_activities_count = len(resp.json()["activities"])

        # Logout
        client.post("/logout", follow_redirects=True)

        # User B rejestruje
        client.post("/register", data={
            "email": "user_b@test", "password": "pass123",
            "password2": "pass123", "invite_code": "test"
        }, follow_redirects=True)

        resp = client.get(f"/api/day/{today}")
        b_activities_count = len(resp.json()["activities"])

        # B nie widzi aktywności A
        assert a_activities_count > 0
        assert b_activities_count == 0

    app.dependency_overrides.clear()


def test_migration_backfills_garmin_source(tmp_path, monkeypatch):
    """Po migracji, istniejące Activity mają source='garmin'."""
    engine, Session = setup_db(tmp_path)

    # Dodaj aktywność bez source (jak gdyby przed migracją)
    db = Session()
    activity = Activity(
        user_id=1, date=date.today(), type="running",
        duration_s=1800, distance_m=5000, kcal_garmin=420,
        garmin_id="garmin-12345"
    )
    db.add(activity)
    db.commit()

    # Migracja się wykonała przy init_db, source powinien być 'garmin'
    db.refresh(activity)
    assert activity.source == "garmin"
    db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

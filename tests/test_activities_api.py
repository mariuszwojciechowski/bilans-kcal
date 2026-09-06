"""Testy API aktywności: POST /api/activities, DELETE, day_report z aktywnościami.

Wzorzec jak w test_saved_meals_api.py: prawdziwe zapytania przez TestClient,
sesja przez /register, profil i waga seedowane przez API (nie ORM wprost) —
inaczej rejestrowany użytkownik nie ma danych i /api/activities / /api/day
zwracają 409."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from tests.conftest import app_today

from app import auth
from app.db import Base, _migrate, db_session
from app.models import Activity, DailySummary, WeightLog
from app.services.energy import DEFAULT_STEPS, age_years, bmr_mifflin, tdee_theoretical

INVITE = "test-invite-code"
WEIGHT_KG = 75


@pytest.fixture
def clients(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'activities.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
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
                "date": app_today().isoformat(), "weight_kg": WEIGHT_KG,
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


def test_duration_s_takes_precedence_over_duration_min(clients):
    """mm:ss w UI parsuje się do sekund — duration_s musi wygrywać z duration_min,
    które frontend wysyła tylko dla kompatybilności ze starszymi klientami."""
    alice, _, _ = clients
    from app.services.energy import manual_activity_kcal
    expected_kcal, _ = manual_activity_kcal("cycling", "umiarkowana", 1798, None, WEIGHT_KG)

    resp = alice.post("/api/activities", json={
        "type": "cycling", "intensity": "umiarkowana",
        "duration_min": 999,       # celowo błędne — duration_s ma pierwszeństwo
        "duration_s": 1798,        # 29.97 min
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["kcal"] == round(expected_kcal)


def test_steps_default_when_no_entry(clients):
    alice, _, _ = clients
    today = app_today().isoformat()
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
        user_id=1, date=app_today(), type="running", duration_s=1800,
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

    today = app_today().isoformat()
    a_activities = alice.get(f"/api/day/{today}").json()["activities"]
    b_activities = bob.get(f"/api/day/{today}").json()["activities"]

    assert len(a_activities) == 1
    assert b_activities == []


def _user_id(SessionLocal, email):
    from app.models import User
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.email == email)).id
    finally:
        db.close()


def _seed_summary(SessionLocal, user_id, day, **kwargs):
    db = SessionLocal()
    try:
        db.add(DailySummary(user_id=user_id, date=day, **kwargs))
        db.commit()
    finally:
        db.close()


def test_closed_garmin_day_plus_manual_activity_sums_to_kcal_out(clients):
    alice, _, SessionLocal = clients
    today = app_today()

    resp = alice.post("/api/activities", json={
        "type": "running", "intensity": "umiarkowana", "duration_min": 30,
    })
    manual_kcal = resp.json()["kcal"]                # MET 10.0 × 75 kg × 0.5 h = 375

    _seed_summary(SessionLocal, _user_id(SessionLocal, "alice@example.com"), today,
                  kcal_total_garmin=2000, steps=8000, complete=True)

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    assert body["kcal_out"] == 2000 + manual_kcal    # Garmin nie widział ręcznego wpisu
    assert body["out_breakdown"]["total"] == body["kcal_out"]


def test_steps_kcal_floors_at_zero_when_measured_below_bmr(clients):
    alice, _, SessionLocal = clients
    today = app_today()

    _seed_summary(SessionLocal, _user_id(SessionLocal, "alice@example.com"), today,
                  kcal_total_garmin=1000, steps=8000, complete=True)  # < BMR sam w sobie

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    assert body["kcal_out"] == 1000
    assert body["out_breakdown"]["steps_kcal"] == 0
    assert body["out_breakdown"]["total"] == 1000


def test_steps_kcal_matches_model_neat_without_garmin(clients):
    alice, _, _ = clients
    today = app_today()

    age = age_years(date(1990, 1, 1), today)
    tdee = tdee_theoretical(
        weight_kg=WEIGHT_KG, height_cm=180, age=age, sex="M",
        steps=DEFAULT_STEPS, activities=[], kcal_in=0,
    )

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    assert body["out_breakdown"]["steps_kcal"] == round(tdee.neat)
    assert body["out_breakdown"]["total"] == round(tdee.total)


def test_est_steps_present_for_manual_run_absent_for_strength(clients):
    alice, _, _ = clients
    today = app_today()

    alice.post("/api/activities", json={
        "type": "running", "intensity": "lekka", "duration_min": 40, "distance_km": 5,
    })
    alice.post("/api/activities", json={
        "type": "strength_training", "intensity": "umiarkowana", "duration_min": 45,
    })

    activities = alice.get(f"/api/day/{today.isoformat()}").json()["activities"]
    running = next(a for a in activities if a["type"] == "running")
    strength = next(a for a in activities if a["type"] == "strength_training")

    assert running["est_steps"] == 7000        # 5 km × 1400 kroków/km
    assert "est_steps" not in strength


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
        """), {"today": app_today().isoformat()})
        conn.commit()

    _migrate(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    existing = db.scalar(select(Activity).where(Activity.garmin_id == "garmin-old-1"))
    assert existing is not None
    assert existing.source == "garmin"          # backfill

    new_activity = Activity(
        user_id=1, date=app_today(), type="cycling", duration_s=3600,
        kcal_garmin=500, garmin_id="garmin-old-2",
    )
    db.add(new_activity)
    db.commit()                                  # wywaliłoby się bez migracji
    db.refresh(new_activity)
    assert new_activity.source == "garmin"
    db.close()


def test_migration_adds_activity_watch_columns(tmp_path):
    """Baza ze schematem sprzed `kcal_bmr_garmin`/`steps` na `activity` — po
    `_migrate()` kolumny istnieją (NULL, bez backfillu), insert/select działa."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old_schema2.db'}")
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
                avg_hr INTEGER,
                source VARCHAR DEFAULT 'garmin'
            )
        """))
        conn.execute(text("""
            INSERT INTO activity (user_id, garmin_id, date, type, duration_s,
                                   distance_m, kcal_garmin, avg_hr, source)
            VALUES (1, 'garmin-old-3', :today, 'running', 1800, 5000, 420, 150, 'garmin')
        """), {"today": app_today().isoformat()})
        conn.commit()

    _migrate(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    existing = db.scalar(select(Activity).where(Activity.garmin_id == "garmin-old-3"))
    assert existing is not None
    assert existing.kcal_bmr_garmin is None
    assert existing.steps is None

    new_activity = Activity(
        user_id=1, date=app_today(), type="walking", duration_s=1800,
        kcal_garmin=200, kcal_bmr_garmin=80, steps=2000, garmin_id="garmin-old-4",
    )
    db.add(new_activity)
    db.commit()                                  # wywaliłoby się bez migracji
    db.refresh(new_activity)
    assert new_activity.kcal_bmr_garmin == 80
    assert new_activity.steps == 2000
    db.close()


def test_day_in_progress_walk_reproduces_symptom_and_uses_garmin_net(clients):
    """Odtworzenie objawu z 2026-09-05 (patrz TODO.md „Poprawa wyliczania kcal
    na dzień w toku"): marsz 4,5h liczony MET 5.0 przez cały czas trwania
    zawyżał model o >1000 kcal. Dzień w toku ma teraz brać pomiar Garmina
    netto z aktywności, bez `max` z modelem teoretycznym."""
    alice, _, SessionLocal = clients
    today = app_today()
    user_id = _user_id(SessionLocal, "alice@example.com")

    _seed_summary(SessionLocal, user_id, today,
                  kcal_total_garmin=2889, kcal_active_garmin=1087, kcal_bmr_garmin=1802,
                  steps=16038, complete=False)

    db = SessionLocal()
    db.add(Activity(user_id=user_id, date=today, type="walking", duration_s=16200,
                    kcal_garmin=839, kcal_bmr_garmin=341, steps=11704,
                    garmin_id="walk-1", source="garmin"))
    db.add(Activity(user_id=user_id, date=today, type="cycling", duration_s=2760,
                    kcal_garmin=475, kcal_bmr_garmin=58,
                    garmin_id="ride-1", source="garmin"))
    db.commit()
    db.close()

    body = alice.get(f"/api/day/{today.isoformat()}").json()

    assert body["kcal_out"] == 2889
    assert body["out_breakdown"]["kind"] == "garmin"
    assert body["out_breakdown"]["activities_kcal"] == 498 + 417
    assert body["out_breakdown"]["steps_kcal"] == 172

    # strażnik: model teoretyczny dla tego samego dnia nie odjeżdża >15% od
    # pomiaru Garmina — to jest dokładnie klasa błędu, która dała 4213 zamiast 2889
    assert 0.85 * 2889 <= body["tdee_model"]["total"] <= 1.15 * 2889

    # jedyne celowe przesunięcie: zaokrąglenie w dół do 50, nigdy więcej niż surowa różnica
    raw_diff = (body["forecast_kcal"] - body["target_deficit_kcal"]) - body["kcal_in"]
    assert body["remaining_kcal"] % 50 == 0
    assert body["remaining_kcal"] <= raw_diff

    # cel dnia — jawna liczba, do której odnosi się "zostało dziś"; dla dnia
    # w toku liczona z PROGNOZY pełnej doby, nie z pomiaru „dotąd" (DONE.md
    # „Cel dnia z prognozy pełnej doby")
    assert body["forecast_kcal"] >= body["kcal_out"]
    assert body["target_kcal"] == round(
        body["forecast_kcal"] * body["calibration_factor"] - body["target_deficit_kcal"]
    )


def test_day_in_progress_target_uses_full_day_forecast_with_baseline_neat(clients):
    """Poranek (2026-09-06): Garmin podaje wydatek narastająco — 811 kcal o 9:00
    dawało cel dnia 737. Cel ma iść z prognozy: zmierzone + spoczynek do
    północy + zwyczajny ruch (mediana z domkniętych dni) do końca czuwania."""
    alice, _, SessionLocal = clients
    today = app_today()
    user_id = _user_id(SessionLocal, "alice@example.com")

    # 7 domkniętych dni bez treningów, aktywne 400/300/500/400/400/900/400 -> mediana 400
    for i, active in enumerate([400, 300, 500, 400, 400, 900, 400], start=1):
        _seed_summary(SessionLocal, user_id, today - timedelta(days=i),
                      kcal_total_garmin=1800 + active, kcal_active_garmin=active,
                      kcal_bmr_garmin=1800, steps=6000, complete=True)
    # dziś: synchronizacja o 07:00 UTC (09:00 CEST / 08:00 CET)
    _seed_summary(SessionLocal, user_id, today,
                  kcal_total_garmin=811, kcal_active_garmin=60, kcal_bmr_garmin=751,
                  steps=1200, complete=False,
                  sync_ts=datetime(today.year, today.month, today.day, 7, 0))

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    f = body["forecast"]

    assert body["kcal_out"] == 811                      # pomiar zostaje faktem
    assert f["measured"] == 811
    assert f["baseline_neat"] == 400 and f["baseline_days"] == 7
    assert 14 <= f["hours_left"] <= 17                  # 09:00 CEST albo 08:00 CET
    assert f["bmr_full"] > 751                          # narastające BMR Garmina przegrywa z Mifflinem
    assert f["resting_left"] == round(f["bmr_full"] / 24 * f["hours_left"])
    # części są zaokrąglane osobno — suma może różnić się o 1 od zaokrąglonej całości
    assert abs(body["forecast_kcal"] - (f["measured"] + f["resting_left"] + f["neat_left"])) <= 1
    assert body["forecast_kcal"] > 2000                 # nie 811
    assert body["target_kcal"] == round(
        body["forecast_kcal"] * body["calibration_factor"] - body["target_deficit_kcal"]
    )

    # pierwsza prognoza dnia zapisana raz — do porównania z pomiarem końcowym na /usage
    db = SessionLocal()
    saved = db.scalar(select(DailySummary.forecast_total_kcal).where(
        DailySummary.user_id == user_id, DailySummary.date == today))
    db.close()
    assert saved == body["forecast_kcal"]


def test_closed_day_has_no_forecast_and_target_from_measurement(clients):
    alice, _, SessionLocal = clients
    today = app_today()
    user_id = _user_id(SessionLocal, "alice@example.com")
    _seed_summary(SessionLocal, user_id, today, kcal_total_garmin=2400, kcal_active_garmin=600,
                  steps=9000, complete=True)

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    assert body["forecast"] is None
    assert body["forecast_kcal"] == body["kcal_out"] == 2400
    assert body["target_kcal"] == round(2400 * body["calibration_factor"] - body["target_deficit_kcal"])


def test_baseline_neat_falls_back_to_default_steps_with_little_history(clients):
    alice, _, SessionLocal = clients
    today = app_today()
    user_id = _user_id(SessionLocal, "alice@example.com")
    _seed_summary(SessionLocal, user_id, today - timedelta(days=1), kcal_total_garmin=2200,
                  kcal_active_garmin=400, complete=True)          # tylko 1 dzień < minimum 3
    _seed_summary(SessionLocal, user_id, today, kcal_total_garmin=900, kcal_active_garmin=50,
                  steps=1000, complete=False)

    body = alice.get(f"/api/day/{today.isoformat()}").json()
    f = body["forecast"]
    assert f["baseline_days"] == 0
    assert f["baseline_neat"] == round(DEFAULT_STEPS * WEIGHT_KG * 0.00057)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

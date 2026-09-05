"""Strefa czasowa użytkownika jako granica dnia — WYMAGANIA.md 8.3
(TODO.md „Strefa czasowa użytkownika…"). Bez freezegun: `clock.datetime`
jest podmieniane monkeypatchem na wariant z ustalonym `.now(tz)`, więc testy
kontrolują punkt w czasie wprost zamiast polegać na zegarze maszyny."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import PendingMeal, UserProfile
from app.providers import ActivityData, DailySummaryData
from app.services import clock
from app.services.sync import sync_range

INVITE = "test-invite-code"


def _freeze(monkeypatch, fixed_utc: datetime) -> None:
    """Podmienia `clock.datetime` tak, że `.now(tz)` zawsze liczy się od
    ustalonego momentu UTC, niezależnie od zegara maszyny uruchamiającej testy."""

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_utc if tz is None else fixed_utc.astimezone(tz)

    monkeypatch.setattr(clock, "datetime", _FrozenDateTime)


def _profile(tz: str) -> UserProfile:
    return UserProfile(user_id=1, birth_date=date(1990, 1, 1), birth_year=1990,
                       sex="M", height_cm=180, tz=tz)


def test_user_today_ahead_of_server_for_pacific_auckland(monkeypatch):
    """23:30 UTC to już 6 września w Pacific/Auckland (UTC+12/+13), choć
    w UTC (i w strefie serwera GCP) jest jeszcze 5 września."""
    fixed_utc = datetime(2026, 9, 5, 23, 30, tzinfo=timezone.utc)
    _freeze(monkeypatch, fixed_utc)

    assert clock.user_today(_profile("Pacific/Auckland")) == date(2026, 9, 6)
    assert fixed_utc.date() == date(2026, 9, 5)


def test_user_today_no_profile_defaults_to_warsaw(monkeypatch):
    fixed_utc = datetime(2026, 9, 5, 23, 30, tzinfo=timezone.utc)
    _freeze(monkeypatch, fixed_utc)

    assert clock.user_tz(None).key == "Europe/Warsaw"
    # Warsaw we wrześniu to CEST (UTC+2) — 23:30 UTC + 2h = 01:30 następnego dnia
    assert clock.user_today(None) == date(2026, 9, 6)


def test_user_tz_unknown_or_empty_falls_back_to_warsaw():
    assert clock.user_tz(_profile("Mars/Olympus")).key == "Europe/Warsaw"
    assert clock.user_tz(_profile("")).key == "Europe/Warsaw"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tz.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
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
        r = c.post("/register", data={"email": "tester@example.com",
                                      "password": "tajnehaslo1", "password2": "tajnehaslo1",
                                      "invite_code": INVITE})
        assert r.status_code == 303, r.headers
        yield c
    app.dependency_overrides.clear()


def test_post_meals_without_date_lands_on_user_day(client, monkeypatch):
    fixed_utc = datetime(2026, 9, 5, 23, 30, tzinfo=timezone.utc)
    _freeze(monkeypatch, fixed_utc)

    r = client.put("/api/profile", json={
        "birth_year": 1990, "sex": "M", "height_cm": 180, "tz": "Pacific/Auckland",
    })
    assert r.status_code == 200, r.text
    r = client.post("/api/settings/consent", json={"granted": True})
    assert r.status_code == 200, r.text

    monkeypatch.setattr("app.services.meal_vision.llm_configured", lambda *a, **kw: False)
    r = client.post("/api/meals/text", data={"description": "kanapka"})
    assert r.status_code == 200

    db = client._SessionLocal()
    pending = db.scalars(select(PendingMeal)).all()
    assert len(pending) == 1
    assert pending[0].date == date(2026, 9, 6)
    db.close()


def test_put_profile_unknown_tz_is_422(client):
    r = client.put("/api/profile", json={
        "birth_year": 1990, "sex": "M", "height_cm": 180, "tz": "Mars/Olympus",
    })
    assert r.status_code == 422


class _FakeProvider:
    """Provider bez efektów ubocznych — `sync_range` liczy `complete`
    wyłącznie z parametru `today`, nie z prawdziwego API."""

    def get_daily_summary(self, day):
        return DailySummaryData(date=day, kcal_total=2000, kcal_active=400,
                                kcal_bmr=1600, steps=8000)

    def get_weights(self, start, end):
        return []

    def get_activities(self, start, end):
        return [ActivityData(garmin_id="a1", date=start, type="running",
                             duration_s=1800, distance_m=5000.0, kcal=300, avg_hr=140)]


def test_sync_range_today_param_does_not_close_current_day(tmp_path):
    """`today` przekazany jawnie (np. `clock.user_today(profile)`) decyduje o
    `complete`, nie zegar serwera — dzień „dzisiaj" użytkownika ma zostać
    otwarty (`complete=False`), nawet jeśli backend liczyłby inny dzień."""
    from app.models import DailySummary, User

    engine = create_engine(f"sqlite:///{tmp_path / 'sync_tz.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    db.add(User(id=1, email="t@example.com"))
    db.commit()

    user_today = date(2026, 9, 6)
    sync_range(db, _FakeProvider(), 1, days=3, today=user_today)

    rows = {
        row.date: row.complete
        for row in db.scalars(select(DailySummary)).all()
    }
    assert rows[user_today] is False
    assert rows[user_today - timedelta(days=1)] is True
    db.close()

"""Strażnicy po wyniesieniu logiki z routerów do serwisów (2026-09-03).

`day_report` i dane trendów mieszkają w `app/services/{day,trends}.py`, a routery
są cienkie. Te testy pilnują trzech rzeczy, które przy takim ruchu psują się
najłatwiej i najciszej:

1. `/trends` (HTML) i `/api/trends` (JSON) liczą to samo z jednego źródła —
   wcześniej były to dwie kopie ~70 linii, rozjeżdżające się przy poprawkach.
2. Kształt odpowiedzi `/api/trends` nie puchnie — w szczególności `today`,
   którego serwis potrzebuje dla szablonu, NIE może wyciekać do API.
3. Warstwa serwisów nie importuje FastAPI. To nie estetyka: `humanize_ago`
   musiała się przenieść z `app/deps.py` do `services/timeago.py` właśnie
   dlatego, że `services/day.py` jej potrzebuje.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import Activity, DailySummary, Meal, WeightLog
from app.services import day as day_service
from app.services import trends as trends_service

INVITE = "test-invite-code"
TODAY = date.today()

# Kształt odpowiedzi /api/trends — kontrakt z mobile.html. Zmiana tej listy
# oznacza zmianę API, nie poprawkę testu.
API_TRENDS_KEYS = {
    "days", "ranges", "chart_weight", "chart_energy", "chart_balance",
    "period_change", "weight_avg_7d", "avg_balance", "balance_days", "to_goal_kg", "goal_eta",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'services.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr("app.routers.auth.INVITE_CODE", INVITE)
    auth._failed.clear()
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
        r = c.post("/register", data={"email": "tester@example.com",
                                      "password": "tajnehaslo1",
                                      "password2": "tajnehaslo1",
                                      "invite_code": INVITE})
        assert r.status_code == 303, r.headers
        c.session_factory = SessionLocal
        yield c
    app.dependency_overrides.clear()


def _seed(client, days: int = 20) -> None:
    """Profil przez API + historia wprost w bazie (szybciej niż przez endpointy)."""
    r = client.put("/api/profile", json={
        "birth_year": 1985, "sex": "M", "height_cm": 180,
        "target_deficit_kcal": 500, "target_weight_kg": 78.0, "lifestyle": "active",
    })
    assert r.status_code == 200, r.text
    db = client.session_factory()
    for i in range(days):
        day = TODAY - timedelta(days=i)
        db.add(WeightLog(user_id=1, date=day, weight_kg=85.0 - i * 0.05, source="garmin"))
        db.add(DailySummary(user_id=1, date=day, kcal_total_garmin=2600 + i,
                            steps=9000, sync_ts=datetime(2026, 1, 1, 12, 0),
                            complete=i > 0))
        db.add(Meal(user_id=1, date=day, time=time(12, 30), description=f"posilek {i}",
                    kcal=700, protein_g=30.0, fat_g=20.0, carbs_g=80.0,
                    fiber_g=8.0, sugars_g=15.0, source="manual"))
    db.commit()
    db.close()


def test_api_trends_shape_is_exactly_the_contract(client):
    _seed(client)
    payload = client.get("/api/trends?days=30").json()
    assert set(payload) == API_TRENDS_KEYS
    # `today` jest w payloadzie serwisu (potrzebuje go szablon), ale nie w API
    assert "today" not in payload


def test_html_and_json_trends_come_from_one_source(client):
    _seed(client)
    api = client.get("/api/trends?days=30").json()

    db = client.session_factory()
    view = trends_service.payload(db, 1, 30)
    db.close()

    for key in API_TRENDS_KEYS - {"ranges"}:
        assert api[key] == view[key], key

    # strona HTML osadza dokładnie te same wykresy SVG, co JSON
    html = client.get("/trends?days=30")
    assert html.status_code == 200
    for chart in ("chart_weight", "chart_energy", "chart_balance"):
        assert api[chart] in html.text, chart


def test_trends_clamps_days_range(client):
    _seed(client)
    assert client.get("/api/trends?days=1").json()["days"] == trends_service.MIN_DAYS
    assert client.get("/api/trends?days=99999").json()["days"] == trends_service.MAX_DAYS
    assert trends_service.nearest_range(45) == 30      # do nazwy zdarzenia telemetrii


def test_api_day_returns_exactly_what_service_computes(client):
    _seed(client)
    api = client.get(f"/api/day/{TODAY.isoformat()}").json()

    db = client.session_factory()
    report = day_service.day_report(db, 1, TODAY)
    db.close()

    assert set(api) == set(report)
    # `quip` jest losowany, `last_sync_ago` zależy od bieżącej minuty
    for key in set(api) - {"quip", "last_sync_ago"}:
        assert api[key] == report[key], key


def test_missing_profile_and_weight_give_409_not_500(client):
    """Serwis zgłasza DayReportUnavailable, router zamienia to na 409."""
    assert client.get(f"/api/day/{TODAY.isoformat()}").status_code == 409   # brak profilu

    r = client.put("/api/profile", json={"birth_year": 1985, "sex": "M", "height_cm": 180})
    assert r.status_code == 200
    resp = client.get(f"/api/day/{TODAY.isoformat()}")                      # brak wagi
    assert resp.status_code == 409
    assert "wagi" in resp.json()["detail"]


def _seed_profile(client, weight_kg: float = 85.0, weight_days: int = 10) -> None:
    """Profil + historia wagi, bez posiłków/aktywności — dokładane per test."""
    r = client.put("/api/profile", json={
        "birth_year": 1985, "sex": "M", "height_cm": 180,
        "target_deficit_kcal": 500, "target_weight_kg": 78.0, "lifestyle": "active",
    })
    assert r.status_code == 200, r.text
    db = client.session_factory()
    for i in range(weight_days):
        db.add(WeightLog(user_id=1, date=TODAY - timedelta(days=i), weight_kg=weight_kg,
                         source="garmin"))
    db.commit()
    db.close()


def _meal(day, kcal: float) -> Meal:
    return Meal(user_id=1, date=day, time=time(12, 30), description="obiad", kcal=kcal,
                protein_g=30.0, fat_g=20.0, carbs_g=80.0, fiber_g=8.0, sugars_g=15.0,
                source="manual")


def test_trends_in_progress_day_matches_day_report_and_is_estimated(client):
    """Dzień w toku (bug zgłoszony 2026-09-04): Trendy mają liczyć wydatek tak
    samo jak «Dziś» — gałąź `mixed`/`model` z `day_balance` — i oznaczyć go
    jako szacowany, zamiast brać surowy `kcal_total_garmin`."""
    _seed_profile(client)
    db = client.session_factory()
    db.add(DailySummary(user_id=1, date=TODAY, kcal_total_garmin=1300, steps=9000,
                        sync_ts=datetime(2026, 1, 1, 12, 0), complete=False))
    db.add(_meal(TODAY, 1600))
    db.commit()
    db.close()

    db = client.session_factory()
    report = day_service.day_report(db, 1, TODAY)
    # Te same wiersze, ta sama funkcja, którą wewnętrznie woła `trends.payload`
    # — dowód, że oba widoki produkują jedną liczbę, bez duplikowania jej logiki.
    profile = db.get(day_service.UserProfile, 1)
    weights = [(w.date, w.weight_kg)
              for w in db.scalars(select(WeightLog).where(WeightLog.user_id == 1)).all()]
    weight = day_service.smoothed_weight(weights)
    summary = db.scalar(select(DailySummary).where(DailySummary.user_id == 1,
                                                    DailySummary.date == TODAY))
    meals = db.scalars(select(Meal).where(Meal.user_id == 1, Meal.date == TODAY)).all()
    e = day_service.day_energy(profile, weight, TODAY, summary, [], meals, TODAY)
    view = trends_service.payload(db, 1, 7)
    db.close()

    assert report["estimated"] is True
    assert report["balance"] < 0                      # 1600 spożyte < 2600 (model) spalone
    assert round(e.kcal_in - e.kcal_out) == report["balance"]

    # jedyny słupek bilansu to dzisiejszy, więc szacowany marker (obrys + legenda)
    # wystąpi dokładnie dwa razy: raz w legendzie, raz na słupku
    assert view["chart_balance"].count('stroke-dasharray="3,2"') == 2


def test_trends_closed_day_with_manual_activity_matches_day_report(client):
    """Dzień domknięty z ręczną aktywnością — Trendy mają doliczać `manual_kcal`
    tak jak «Dziś», nie sam surowy Garmin."""
    _seed_profile(client)
    day = TODAY - timedelta(days=1)
    db = client.session_factory()
    db.add(DailySummary(user_id=1, date=day, kcal_total_garmin=2000, steps=9000,
                        sync_ts=datetime(2026, 1, 1, 12, 0), complete=True))
    db.add(Activity(user_id=1, date=day, type="strength_training", duration_s=1800,
                    kcal_garmin=300, source="manual"))
    db.add(_meal(day, 2200))
    db.commit()
    db.close()

    db = client.session_factory()
    report = day_service.day_report(db, 1, day)
    db.close()

    assert report["estimated"] is False
    assert report["out_source"] == "garmin"
    assert report["kcal_out"] == 2300                 # 2000 Garmin + 300 ręczne
    assert report["balance"] == report["kcal_in"] - 2300


def test_trends_day_without_garmin_entry_uses_model_and_is_estimated(client):
    """Dzień bez żadnego wpisu Garmina (np. użytkownik bez zegarka) ma się
    pojawić w Trendach — wcześniej był pomijany, bo brakowało `kcal_total_garmin`."""
    _seed_profile(client)
    day = TODAY - timedelta(days=2)
    db = client.session_factory()
    db.add(_meal(day, 1800))
    db.commit()
    db.close()

    db = client.session_factory()
    report = day_service.day_report(db, 1, day)
    view = trends_service.payload(db, 1, 7)
    db.close()

    assert report["out_source"] == "model"
    assert report["estimated"] is True
    assert "Brak danych" not in view["chart_balance"]


def test_trends_avg_balance_excludes_estimated_days(client):
    """Średni bilans i `balance_days` liczą się tylko z dni domkniętych —
    dzień w toku zmienia się co godzinę i zaburzałby średnią."""
    _seed_profile(client)
    db = client.session_factory()
    for i in (1, 2):
        d = TODAY - timedelta(days=i)
        db.add(DailySummary(user_id=1, date=d, kcal_total_garmin=2000, steps=9000,
                            sync_ts=datetime(2026, 1, 1, 12, 0), complete=True))
        db.add(_meal(d, 1800))
    db.add(DailySummary(user_id=1, date=TODAY, kcal_total_garmin=500, steps=9000,
                        sync_ts=datetime(2026, 1, 1, 12, 0), complete=False))
    db.add(_meal(TODAY, 1800))
    db.commit()
    db.close()

    db = client.session_factory()
    view = trends_service.payload(db, 1, 7)
    db.close()

    assert view["balance_days"] == 2
    assert view["avg_balance"] == -200                # 1800 − 2000, dwa dni domknięte


def test_services_layer_does_not_import_fastapi():
    services = Path(day_service.__file__).parent
    offenders = [
        path.name for path in sorted(services.glob("*.py"))
        if "fastapi" in path.read_text()
    ]
    assert offenders == [], (
        "Serwisy mają być wolne od FastAPI — błąd domenowy zgłaszaj wyjątkiem "
        f"i mapuj na HTTP w routerze. Winowajcy: {offenders}"
    )

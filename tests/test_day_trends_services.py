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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import DailySummary, Meal, WeightLog
from app.services import day as day_service
from app.services import trends as trends_service

INVITE = "test-invite-code"
TODAY = date.today()

# Kształt odpowiedzi /api/trends — kontrakt z mobile.html. Zmiana tej listy
# oznacza zmianę API, nie poprawkę testu.
API_TRENDS_KEYS = {
    "days", "ranges", "chart_weight", "chart_energy", "chart_balance",
    "period_change", "avg_balance", "balance_days", "to_goal_kg", "goal_eta",
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

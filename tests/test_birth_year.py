"""Rok urodzenia zamiast pełnej daty (minimalizacja danych, TODO.md).

Migracja addytywna `birth_year` na starym schemacie, walidacja API, zgodność
wstecz z klientami/plikami transferu wysyłającymi jeszcze `birth_date`,
i round-trip eksportu/importu w obie strony."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, _migrate, db_session
from app.models import UserProfile

INVITE = "test-invite-code"


def test_migration_backfills_birth_year_from_birth_date(tmp_path):
    """Baza ze STARYM schematem `user_profile` (bez `birth_year`) — po _migrate()
    kolumna istnieje i jest wypełniona rokiem z `birth_date`."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old_profile.db'}")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE user_profile (
                user_id INTEGER PRIMARY KEY,
                birth_date DATE NOT NULL,
                sex VARCHAR(1) NOT NULL,
                height_cm FLOAT NOT NULL,
                target_deficit_kcal INTEGER DEFAULT 500,
                target_weight_kg FLOAT,
                lifestyle VARCHAR DEFAULT 'active' NOT NULL,
                tz VARCHAR DEFAULT 'Europe/Warsaw' NOT NULL
            )
        """))
        conn.execute(text(
            "INSERT INTO user_profile (user_id, birth_date, sex, height_cm) "
            "VALUES (1, '1990-03-20', 'M', 180)"
        ))
        conn.commit()

    _migrate(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    profile = db.get(UserProfile, 1)
    assert profile.birth_year == 1990
    assert profile.birth_date.isoformat() == "1990-03-20"  # legacy — nie nadpisujemy


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'birthyear.db'}")
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
        r = c.post("/register", data={"email": "alice@example.com", "password": "tajnehaslo1",
                                      "password2": "tajnehaslo1", "invite_code": INVITE})
        assert r.status_code == 303 and r.headers["location"] == "/", r.headers
        yield c
    app.dependency_overrides.clear()


def test_put_profile_with_birth_year(client):
    r = client.put("/api/profile", json={"birth_year": 1990, "sex": "M", "height_cm": 180})
    assert r.status_code == 200, r.text

    got = client.get("/api/profile").json()
    assert got["birth_year"] == 1990
    assert "birth_date" not in got  # minimalizacja — nie wystawiamy pełnej daty


def test_put_profile_with_legacy_birth_date_still_works(client):
    r = client.put("/api/profile", json={"birth_date": "1985-06-15", "sex": "F", "height_cm": 165})
    assert r.status_code == 200, r.text
    assert client.get("/api/profile").json()["birth_year"] == 1985


def test_put_profile_without_birth_year_or_date_422(client):
    r = client.put("/api/profile", json={"sex": "M", "height_cm": 180})
    assert r.status_code == 422


def test_put_profile_birth_year_out_of_range_422(client):
    r = client.put("/api/profile", json={"birth_year": 1850, "sex": "M", "height_cm": 180})
    assert r.status_code == 422
    r = client.put("/api/profile", json={"birth_year": date.today().year + 1,
                                         "sex": "M", "height_cm": 180})
    assert r.status_code == 422


def test_day_report_uses_birth_year_for_age(client):
    client.put("/api/profile", json={"birth_year": 1990, "sex": "M", "height_cm": 180})
    client.post("/api/weight", json={"date": date.today().isoformat(), "weight_kg": 80})
    r = client.get(f"/api/day/{date.today().isoformat()}")
    assert r.status_code == 200, r.text  # nie wywala się na profilu bez birth_date w JSON-ie


def test_transfer_roundtrip_exports_birth_year_not_birth_date(client):
    client.put("/api/profile", json={"birth_year": 1990, "sex": "M", "height_cm": 180})
    payload = client.get("/api/transfer/export").json()
    assert payload["profile"]["birth_year"] == 1990
    assert "birth_date" not in payload["profile"]


def test_transfer_import_accepts_old_file_with_birth_date(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'import_old.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    from app.models import User
    from app.services import transfer

    db.add(User(email="t@t"))
    db.commit()

    old_payload = {
        "format": "fit-krasnal-transfer", "version": 1, "source": "desktop",
        "profile": {"birth_date": "1985-06-15", "sex": "M", "height_cm": 180,
                    "target_deficit_kcal": 500, "target_weight_kg": None,
                    "lifestyle": "active", "tz": "Europe/Warsaw"},
    }
    counts = transfer.import_payload(db, 1, old_payload)
    assert counts["profile"] == 1
    profile = db.get(UserProfile, 1)
    assert profile.birth_year == 1985

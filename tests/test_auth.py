import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import User

INVITE = "test-invite-code"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    monkeypatch.setattr("app.main.INVITE_CODE", INVITE)
    auth._failed.clear()                      # throttle jest globalny w procesie
    auth._invite_throttle.attempts.clear()    # ten sam powód (klucz: IP klienta)

    from app.main import app

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_session] = _override
    # follow_redirects=False: chcemy widzieć 303 i Location, nie stronę docelową
    with TestClient(app, follow_redirects=False) as c:
        c.session_factory = SessionLocal
        yield c
    app.dependency_overrides.clear()


def _register(client, email="tester@example.com", password="tajnehaslo1",
              password2=None, invite=INVITE):
    return client.post("/register", data={
        "email": email, "password": password,
        "password2": password2 if password2 is not None else password,
        "invite_code": invite,
    })


def test_password_hash_roundtrip():
    hashed = auth.hash_password("tajnehaslo1")
    assert hashed != "tajnehaslo1"                      # nie trzymamy plaintextu
    assert auth.verify_password("tajnehaslo1", hashed)
    assert not auth.verify_password("zle", hashed)
    assert not auth.verify_password("cokolwiek", None)  # konto bez hasła


def test_register_creates_account_and_logs_in(client):
    resp = _register(client)
    assert resp.status_code == 303 and resp.headers["location"] == "/"

    db = client.session_factory()
    user = db.scalar(select(User).where(User.email == "tester@example.com"))
    assert user is not None and user.password_hash
    db.close()


def test_register_rejects_bad_invite_and_weak_password(client):
    assert _register(client, invite="zly-kod").headers["location"] == "/register?error=invite"
    assert _register(client, password="krotkie").headers["location"] == "/register?error=short"
    assert (_register(client, password="tajnehaslo1", password2="inne1234")
            .headers["location"] == "/register?error=mismatch")

    db = client.session_factory()
    assert db.scalars(select(User)).all() == []   # żadna próba nie założyła konta
    db.close()


def test_register_rejects_duplicate_email(client):
    _register(client)
    assert _register(client).headers["location"] == "/register?error=taken"


def test_login_success_and_wrong_password(client):
    _register(client)
    client.post("/logout")

    bad = client.post("/login", data={"email": "tester@example.com", "password": "zle"})
    assert bad.headers["location"] == "/login?error=bad"

    ok = client.post("/login", data={"email": "tester@example.com",
                                     "password": "tajnehaslo1"})
    assert ok.headers["location"] == "/"


def test_login_is_rate_limited_after_repeated_failures(client):
    _register(client)
    client.post("/logout")

    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        client.post("/login", data={"email": "tester@example.com", "password": "zle"})

    # nawet poprawne hasło jest teraz odrzucane — blokada, nie "bad"
    blocked = client.post("/login", data={"email": "tester@example.com",
                                          "password": "tajnehaslo1"})
    assert blocked.headers["location"] == "/login?error=locked"


def test_successful_login_resets_failed_attempts(client):
    _register(client)
    client.post("/logout")

    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        client.post("/login", data={"email": "tester@example.com", "password": "zle"})
    client.post("/login", data={"email": "tester@example.com", "password": "tajnehaslo1"})

    assert not auth.is_locked_out("tester@example.com")


def test_login_page_renders_without_session(client):
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_register_is_rate_limited_after_bad_invite_codes(client):
    """Kod zaproszenia to jeden wspólny statyczny sekret, a mechanizm jest
    opisany w publicznym repo — bez limitu prób da się go zgadywać online."""
    for i in range(auth.MAX_INVITE_ATTEMPTS):
        resp = _register(client, email=f"attacker{i}@example.com", invite="zly-kod")
        assert resp.headers["location"] == "/register?error=invite"

    # po wyczerpaniu prób odbijamy nawet POPRAWNY kod — inaczej limit nic nie daje
    blocked = _register(client, email="attacker-final@example.com")
    assert blocked.headers["location"] == "/register?error=locked"


def test_register_bad_invite_counter_resets_after_success(client):
    for i in range(auth.MAX_INVITE_ATTEMPTS - 1):
        _register(client, email=f"literowka{i}@example.com", invite="zly-kod")

    assert _register(client).headers["location"] == "/"      # poprawny kod przechodzi
    assert not auth.invite_is_locked("testclient")


def test_client_ip_takes_last_forwarded_entry():
    """Caddy dopisuje prawdziwy adres peera na KOŃCU X-Forwarded-For, więc
    wcześniejsze wpisy mogą być podstawione przez klienta — liczenie limitu po
    nich pozwalałoby obejść blokadę jednym nagłówkiem."""
    class _Req:
        def __init__(self, headers, host="10.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    assert auth.client_ip(_Req({"x-forwarded-for": "1.2.3.4, 203.0.113.7"})) == "203.0.113.7"
    assert auth.client_ip(_Req({})) == "10.0.0.1"


def test_api_returns_401_when_not_logged_in(client):
    """Klienci JSON (mobile/curl) dostają 401, nie redirect."""
    for path in ("/api/profile", "/api/day/2026-08-27", "/api/transfer/export"):
        r = client.get(path)
        assert r.status_code == 401, path


def test_html_pages_redirect_to_login_when_not_logged_in(client):
    """Przeglądarki (Accept: text/html) na 401 dostają redirect na /login."""
    for path in ("/", "/settings", "/trends"):
        r = client.get(path, headers={"accept": "text/html"})
        assert r.status_code == 303, path
        assert r.headers["location"] == "/login"


def test_manual_weight_and_steps_endpoints(client):
    """Mobile bez Garmina: /api/weight i /api/day/{day}/steps."""
    from app.models import WeightLog, DailySummary
    _register(client, email="mobile@test")

    assert client.post("/api/weight", json={
        "date": "2026-08-27", "weight_kg": 80.5,
    }).status_code == 200
    # upsert: drugi wpis na ten sam dzień nadpisuje, nie tworzy drugiego rekordu
    assert client.post("/api/weight", json={
        "date": "2026-08-27", "weight_kg": 80.7,
    }).status_code == 200

    db = client.session_factory()
    rows = db.scalars(select(WeightLog)).all()
    assert len(rows) == 1 and rows[0].weight_kg == 80.7 and rows[0].source == "manual"
    db.close()

    assert client.post("/api/weight", json={
        "date": "2026-08-27", "weight_kg": 5,          # nierealne
    }).status_code == 422

    assert client.post("/api/day/2026-08-27/steps", json={"steps": 12345}).status_code == 200
    db = client.session_factory()
    ds = db.scalars(select(DailySummary)).one()
    assert ds.steps == 12345
    db.close()


def test_settings_page_reflects_saved_llm_key_without_env(client, monkeypatch):
    """Klucz Gemini w AppSetting, env procesu pusty (typowy stan po restarcie
    serwera lub cudzy user). Settings musi pokazac klucz jako zapisany i backend
    jako aktywny (gemini) — bez sprzecznosci."""
    from app.services import settings as ss

    _register(client)
    db = client.session_factory()
    user = db.scalars(select(User)).one()
    ss.set_setting(db, user.id, "gemini_api_key", "AIza-testowy-klucz")
    db.close()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "zapisany:" in resp.text          # klucz w bazie
    assert "brak — posiłki trafiają do kolejki" not in resp.text


def test_mobile_view_requires_auth_and_renders(client):
    # bez sesji: redirect na /login (HTML)
    r = client.get("/mobile", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"] == "/login"

    _register(client, email="m@test")
    r = client.get("/mobile")
    assert r.status_code == 200
    assert "Fit Krasnal" in r.text
    assert "/api/day/" in r.text     # cienki klient używa API


def test_weight_and_steps_require_auth(client):
    assert client.post("/api/weight", json={"date": "2026-08-27",
                                             "weight_kg": 80}).status_code == 401
    assert client.post("/api/day/2026-08-27/steps",
                        json={"steps": 1000}).status_code == 401


def test_two_users_do_not_see_each_others_profile(client):
    """Rejestracja B nie może zobaczyć/nadpisać profilu A."""
    _register(client, email="alice@example.com")
    client.put("/api/profile", json={
        "birth_date": "1990-01-01", "sex": "F", "height_cm": 170,
    })
    client.post("/logout")

    _register(client, email="bob@example.com")
    resp = client.get("/api/profile")
    assert resp.status_code == 404          # Bob nie widzi profilu Alicji

    client.put("/api/profile", json={
        "birth_date": "1985-06-15", "sex": "M", "height_cm": 180,
    })

    got_bob = client.get("/api/profile").json()
    assert got_bob["sex"] == "M" and got_bob["height_cm"] == 180

    client.post("/logout")
    client.post("/login", data={"email": "alice@example.com", "password": "tajnehaslo1"})
    got_alice = client.get("/api/profile").json()
    assert got_alice["sex"] == "F" and got_alice["height_cm"] == 170  # A nadal ma swoje

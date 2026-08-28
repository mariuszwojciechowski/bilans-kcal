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
    auth._failed.clear()          # throttle jest globalny w procesie

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

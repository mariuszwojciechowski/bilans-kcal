"""Logowanie przez Google (OIDC) — bez sieci: klient authlib jest atrapą.

Sprawdzamy kontrakt routera, nie authlib: allowlista, tworzenie konta bez
hasła, dopasowanie po `sub` przy kolejnym logowaniu, tryb `oidc` chowający
ścieżki hasłowe.
"""
import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import Base, db_session
from app.models import User
from app.routers import oidc

ALLOWED = "ala@example.com"


class FakeGoogle:
    """Atrapa `oauth.google`: zamiast Google zwraca gotowe claims ID tokenu."""

    def __init__(self, claims):
        self.claims = claims
        self.redirect_uri = None

    async def authorize_redirect(self, request, redirect_uri):
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?state=x",
                                status_code=302)

    async def authorize_access_token(self, request):
        return {"access_token": "t", "userinfo": dict(self.claims)}


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'oidc.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(oidc, "AUTH_MODE", "both")
    monkeypatch.setattr("app.routers.auth.AUTH_MODE", "both")
    monkeypatch.setattr(oidc, "ALLOWED_EMAILS", frozenset({ALLOWED}))
    monkeypatch.setattr(oidc, "PUBLIC_URL", "https://example.test")
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
        c.session_factory = SessionLocal
        yield c
    app.dependency_overrides.clear()


def _use(monkeypatch, claims):
    fake = FakeGoogle(claims)
    monkeypatch.setattr(oidc, "google_client", lambda: fake)
    return fake


def _claims(email=ALLOWED, sub="sub-123", verified=True):
    return {"sub": sub, "email": email, "email_verified": verified, "iss": "https://accounts.google.com"}


def test_start_redirects_to_google_with_callback_uri(client, monkeypatch):
    fake = _use(monkeypatch, _claims())
    r = client.get("/auth/google")
    assert r.status_code == 302 and "accounts.google.com" in r.headers["location"]
    assert fake.redirect_uri == "https://example.test/auth/google/callback"


def test_callback_denies_email_outside_allowlist_and_creates_nothing(client, monkeypatch):
    _use(monkeypatch, _claims(email="obcy@example.com"))
    r = client.get("/auth/google/callback?code=c&state=s")
    assert r.status_code == 403
    assert "Konto nieuprawnione" in r.text
    with client.session_factory() as db:
        assert db.scalar(select(User)) is None
    assert client.get("/api/settings").status_code == 401     # brak sesji


def test_callback_requires_verified_email(client, monkeypatch):
    _use(monkeypatch, _claims(verified=False))
    r = client.get("/auth/google/callback?code=c&state=s")
    assert r.status_code == 403
    with client.session_factory() as db:
        assert db.scalar(select(User)) is None


def test_callback_allowed_creates_passwordless_user_and_logs_in(client, monkeypatch):
    _use(monkeypatch, _claims())
    r = client.get("/auth/google/callback?code=c&state=s")
    assert r.status_code == 303 and r.headers["location"] == "/"
    with client.session_factory() as db:
        user = db.scalar(select(User))
        assert user.email == ALLOWED
        assert user.password_hash is None
        assert user.google_sub == "sub-123"
    assert client.get("/api/settings").status_code == 200     # sesja działa
    # konto bez hasła nie wchodzi hasłem (tryb both)
    r = client.post("/login", data={"email": ALLOWED, "password": "cokolwiek1"})
    assert r.status_code == 303 and "error=bad" in r.headers["location"]


def test_second_login_matches_by_sub_even_if_email_changed(client, monkeypatch):
    _use(monkeypatch, _claims())
    client.get("/auth/google/callback?code=c&state=s")
    client.post("/logout")
    # ten sam `sub`, inny e-mail (też na allowliście) → to samo konto, bez duplikatu
    monkeypatch.setattr(oidc, "ALLOWED_EMAILS", frozenset({ALLOWED, "nowa@example.com"}))
    _use(monkeypatch, _claims(email="nowa@example.com"))
    r = client.get("/auth/google/callback?code=c&state=s")
    assert r.status_code == 303
    with client.session_factory() as db:
        users = db.scalars(select(User)).all()
        assert len(users) == 1 and users[0].email == ALLOWED


def test_existing_password_account_gets_sub_on_first_google_login(client, monkeypatch):
    with client.session_factory() as db:
        db.add(User(email=ALLOWED, password_hash=auth.hash_password("tajnehaslo1")))
        db.commit()
    _use(monkeypatch, _claims())
    r = client.get("/auth/google/callback?code=c&state=s")
    assert r.status_code == 303
    with client.session_factory() as db:
        user = db.scalar(select(User))
        assert user.google_sub == "sub-123"
        assert user.password_hash is not None                # hasło zostaje


def test_oidc_mode_hides_password_routes(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.AUTH_MODE", "oidc")
    monkeypatch.setattr(oidc, "AUTH_MODE", "oidc")
    monkeypatch.setattr("app.routers.auth.INVITE_CODE", "kod")
    page = client.get("/login")
    assert page.status_code == 200
    assert "Zaloguj przez Google" in page.text
    assert 'action="/login"' not in page.text
    assert client.post("/login", data={"email": ALLOWED, "password": "x"}).status_code == 404
    assert client.get("/register").status_code == 404
    assert client.post("/register", data={"email": ALLOWED, "password": "x", "password2": "x",
                                          "invite_code": "kod"}).status_code == 404


def test_password_mode_has_no_google_routes(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.AUTH_MODE", "password")
    monkeypatch.setattr(oidc, "AUTH_MODE", "password")
    page = client.get("/login")
    assert "Zaloguj przez Google" not in page.text and 'action="/login"' in page.text
    assert client.get("/auth/google").status_code == 404
    assert client.get("/auth/google/callback?code=c&state=s").status_code == 404

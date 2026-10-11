"""Logowanie przez Google (OpenID Connect, authlib).

Przepływ authorization code + PKCE; `state` i `nonce` trzyma authlib w sesji
(podpisane ciasteczko). Tożsamość bierzemy wyłącznie z ID tokenu, który authlib
weryfikuje (issuer, audience, exp, nonce) w `authorize_access_token`.

Konto wchodzi tylko z allowlisty `FIT_KRASNAL_ALLOWED_EMAILS` i tylko ze
zweryfikowanym e-mailem. Dopasowanie: najpierw po `User.google_sub` (stały
identyfikator konta Google), potem po e-mailu (konto z hasłem z czasów przed
OIDC — wtedy dopisujemy `sub`). Nowe konto ma `password_hash=None`, więc nigdy
nie zaloguje się hasłem.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..config import (ALLOWED_EMAILS, AUTH_MODE, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                      PUBLIC_URL)
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import User
from ..services import usage as usage_service

router = APIRouter()

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
_oauth = None


def oidc_enabled() -> bool:
    return AUTH_MODE in ("oidc", "both")


def google_client():
    """Klient authlib budowany leniwie (metadane Google pobiera przy pierwszym
    użyciu). Testy podmieniają tę funkcję na atrapę."""
    global _oauth
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(503, "Logowanie Google nie jest skonfigurowane.")
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth
        _oauth = OAuth()
        _oauth.register(
            name="google",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url=GOOGLE_METADATA_URL,
            client_kwargs={"scope": "openid email", "code_challenge_method": "S256"},
        )
    return _oauth.google


def _redirect_uri() -> str:
    return f"{PUBLIC_URL}/auth/google/callback"


def _denied(request: Request) -> HTMLResponse:
    """403 bez tworzenia konta i bez zdradzania, które adresy są na liście."""
    return templates.TemplateResponse(
        request, "login.html",
        {"error": "Konto nieuprawnione — ten adres e-mail nie ma dostępu do tej instancji.",
         "has_logo": (STATIC_DIR / "logo.png").exists(), "auth_mode": AUTH_MODE},
        status_code=403,
    )


@router.get("/auth/google")
async def google_start(request: Request):
    if not oidc_enabled():
        raise HTTPException(404)
    return await google_client().authorize_redirect(request, _redirect_uri())


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(db_session)):
    if not oidc_enabled():
        raise HTTPException(404)
    client = google_client()
    try:
        token = await client.authorize_access_token(request)
    except Exception:
        # zły/stary `state`, odrzucony kod, nieprawidłowy ID token — bez szczegółów na zewnątrz
        return RedirectResponse("/login?error=google", status_code=303)
    claims = token.get("userinfo") if isinstance(token, dict) else None
    if not claims or not claims.get("sub"):
        return RedirectResponse("/login?error=google", status_code=303)
    email = str(claims.get("email") or "").strip().lower()
    if not email or not claims.get("email_verified"):
        return _denied(request)
    if email not in ALLOWED_EMAILS:
        return _denied(request)

    sub = str(claims["sub"])
    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=None, google_sub=sub)
            db.add(user)
        else:
            user.google_sub = sub
        db.commit()
    auth.login_user(request, user)
    usage_service.bump(db, user.id, "login_google")
    return RedirectResponse("/", status_code=303)

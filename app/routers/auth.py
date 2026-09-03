"""Logowanie, rejestracja, wylogowanie, polityka prywatności."""
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..config import INVITE_CODE, PRIVACY_VERSION
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import User
from ..services import consent as consent_service
from ..services import usage as usage_service

router = APIRouter()

LOGIN_ERRORS = {
    "bad": "Nieprawidłowy e-mail lub hasło.",
    "locked": (f"Za dużo nieudanych prób. Odczekaj "
               f"{auth.LOCKOUT_S // 60} minut i spróbuj ponownie."),
}
REGISTER_ERRORS = {
    "invite": "Nieprawidłowy kod zaproszenia.",
    "mismatch": "Hasła nie są identyczne.",
    "short": f"Hasło musi mieć co najmniej {auth.MIN_PASSWORD_LEN} znaków.",
    "long": "Hasło jest za długie (maks. 72 bajty).",
    "taken": "Konto z tym adresem już istnieje.",
    "locked": (f"Za dużo nieprawidłowych kodów zaproszenia. Odczekaj "
               f"{auth.INVITE_LOCKOUT_S // 60} minut i spróbuj ponownie."),
}


def _auth_page(request: Request, template: str, errors: dict, error: str | None):
    return templates.TemplateResponse(
        request,
        template,
        {
            "error": errors.get(error) if error else None,
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    return _auth_page(request, "login.html", LOGIN_ERRORS, error)


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 db: Session = Depends(db_session)):
    email = email.strip().lower()
    if auth.is_locked_out(email):
        return RedirectResponse("/login?error=locked", status_code=303)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not auth.verify_password(password, user.password_hash):
        auth.note_failed_login(email)
        return RedirectResponse("/login?error=bad", status_code=303)
    auth.reset_failed_login(email)
    auth.login_user(request, user)
    usage_service.bump(db, user.id, "login")
    return RedirectResponse("/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str | None = None):
    if not INVITE_CODE:
        raise HTTPException(503, "Rejestracja jest wyłączona.")
    return _auth_page(request, "register.html", REGISTER_ERRORS, error)


@router.post("/register")
def register_submit(request: Request, email: str = Form(...), password: str = Form(...),
                    password2: str = Form(...), invite_code: str = Form(...),
                    consent_llm_photos: bool = Form(False),
                    db: Session = Depends(db_session)):
    if not INVITE_CODE:
        raise HTTPException(503, "Rejestracja jest wyłączona.")
    ip = auth.client_ip(request)
    if auth.invite_is_locked(ip):
        return RedirectResponse("/register?error=locked", status_code=303)
    if not secrets.compare_digest(invite_code.strip(), INVITE_CODE):
        auth.note_failed_invite(ip)
        return RedirectResponse("/register?error=invite", status_code=303)
    auth.reset_failed_invite(ip)
    problem = auth.password_problem(password, password2)
    if problem:
        return RedirectResponse(f"/register?error={problem}", status_code=303)
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        return RedirectResponse("/register?error=taken", status_code=303)
    user = User(email=email, password_hash=auth.hash_password(password))
    db.add(user)
    db.commit()
    if consent_llm_photos:
        consent_service.grant(db, user.id)
    auth.login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.get("/prywatnosc", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {"has_logo": (STATIC_DIR / "logo.png").exists(), "privacy_version": PRIVACY_VERSION},
    )


@router.post("/logout")
def logout_submit(request: Request):
    auth.logout_user(request)
    return RedirectResponse("/login", status_code=303)

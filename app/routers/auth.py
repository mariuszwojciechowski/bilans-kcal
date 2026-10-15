"""Logowanie, rejestracja, wylogowanie, reset hasła, polityka prywatności."""
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..config import AUTH_MODE, INVITE_CODE, PRIVACY_VERSION, PUBLIC_URL
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import User
from ..services import consent as consent_service
from ..services import password_reset as reset_service
from ..services import usage as usage_service

router = APIRouter()

LOGIN_ERRORS = {
    "bad": "Nieprawidłowy e-mail lub hasło.",
    "locked": (f"Za dużo nieudanych prób. Odczekaj "
               f"{auth.LOCKOUT_S // 60} minut i spróbuj ponownie."),
    "google": "Logowanie przez Google nie powiodło się. Spróbuj ponownie.",
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
RESET_ERRORS = {
    "invalid": "Ten link wygasł albo został już użyty — poproś o nowy.",
    "mismatch": "Nowe hasła nie są identyczne.",
    "short": f"Nowe hasło musi mieć co najmniej {auth.MIN_PASSWORD_LEN} znaków.",
    "long": "Nowe hasło jest za długie (maks. 72 bajty).",
}


def _auth_page(request: Request, template: str, errors: dict, error: str | None,
               extra: dict | None = None):
    return templates.TemplateResponse(
        request,
        template,
        {
            "error": errors.get(error) if error else None,
            "has_logo": (STATIC_DIR / "logo.png").exists(),
            "auth_mode": AUTH_MODE,
            **(extra or {}),
        },
    )


def _password_routes_enabled() -> None:
    """W trybie `oidc` hasła nie ma: formularze POST /login i /register → 404,
    jakby ich nie było (nie 403 — nie ma po co ogłaszać, że istnieją)."""
    if AUTH_MODE == "oidc":
        raise HTTPException(404)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None,
               changed: str | None = None):
    # `changed` — po udanym resecie hasła: zielony baner zamiast strony „wyślij link"
    return _auth_page(request, "login.html", LOGIN_ERRORS, error,
                      {"changed": changed})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 db: Session = Depends(db_session)):
    _password_routes_enabled()
    email = email.strip().lower()
    if auth.is_locked_out(email):
        return RedirectResponse("/login?error=locked", status_code=303)
    user = db.scalar(select(User).where(User.email == email))
    # Konto bez hasła (założone przez Google) nigdy nie wchodzi hasłem —
    # verify_password(…, None) i tak zwraca False, ale niech to będzie jawne.
    if (user is None or user.password_hash is None
            or not auth.verify_password(password, user.password_hash)):
        auth.note_failed_login(email)
        return RedirectResponse("/login?error=bad", status_code=303)
    auth.reset_failed_login(email)
    auth.login_user(request, user)
    usage_service.bump(db, user.id, "login")
    return RedirectResponse("/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str | None = None):
    _password_routes_enabled()
    if not INVITE_CODE:
        raise HTTPException(503, "Rejestracja jest wyłączona.")
    return _auth_page(request, "register.html", REGISTER_ERRORS, error)


@router.post("/register")
def register_submit(request: Request, email: str = Form(...), password: str = Form(...),
                    password2: str = Form(...), invite_code: str = Form(...),
                    consent_llm_photos: bool = Form(False),
                    db: Session = Depends(db_session)):
    _password_routes_enabled()
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


@router.get("/password-reset", response_class=HTMLResponse)
def password_reset_page(request: Request, sent: str | None = None):
    """Formularz „podaj e-mail". Server-rendered: sesji jeszcze nie ma, więc
    /mobile nie istnieje — jedyny słuszny wyjątek od zasady „rozwijamy tylko
    /mobile" (CLAUDE.md)."""
    _password_routes_enabled()
    return _auth_page(request, "password_reset.html", RESET_ERRORS, None,
                      {"sent": sent})


@router.post("/password-reset/request")
def password_reset_request(request: Request, email: str = Form(...),
                           db: Session = Depends(db_session)):
    """Anti-enumeracja: zawsze ta sama odpowiedź, mail tylko gdy konto
    istnieje (i nie wpadł w throttle) — z zewnątrz nieodróżnialne."""
    _password_routes_enabled()
    base_url = PUBLIC_URL or str(request.base_url).rstrip("/")
    sent = reset_service.request_reset(db, email.strip().lower(), base_url)
    if sent:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        usage_service.bump(db, user.id, "password_reset_request")
    return RedirectResponse("/password-reset?sent=1", status_code=303)


@router.get("/password-reset/{token}", response_class=HTMLResponse)
def password_reset_token_page(request: Request, token: str,
                              db: Session = Depends(db_session),
                              error: str | None = None):
    _password_routes_enabled()
    try:
        reset_service.peek(db, token)   # podgląd — nie zużywa (skanery linków)
    except reset_service.ResetTokenInvalid:
        error = "invalid"
    return _auth_page(request, "password_reset_new.html", RESET_ERRORS, error,
                      {"token": token, "invalid": error == "invalid"})


@router.post("/password-reset/{token}")
def password_reset_submit(request: Request, token: str,
                          password: str = Form(...), password2: str = Form(...),
                          db: Session = Depends(db_session)):
    _password_routes_enabled()
    problem = auth.password_problem(password, password2)
    if problem:
        return RedirectResponse(f"/password-reset/{token}?error={problem}",
                                status_code=303)
    try:
        user = reset_service.consume(db, token)
    except reset_service.ResetTokenInvalid:
        return RedirectResponse(f"/password-reset/{token}?error=invalid",
                                status_code=303)
    user.password_hash = auth.hash_password(password)
    auth.reset_failed_login(user.email)
    db.commit()
    usage_service.bump(db, user.id, "password_reset_done")
    return RedirectResponse("/login?changed=1", status_code=303)


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

"""Logowanie i sesja użytkownika (multi-user pilot).

Sesja to podpisane ciasteczko (Starlette SessionMiddleware) trzymające tylko
user_id — brak tabeli sesji, wylogowanie = wyczyszczenie ciasteczka.
"""

import threading
import time as time_module

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import db_session
from .models import User

# bcrypt tnie hasło do 72 bajtów — dłuższe odrzucamy zamiast po cichu skracać
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LEN = 8

# Ochrona przed zgadywaniem hasła: publiczny endpoint /login bez limitu jest
# trywialnie brute-forceable. Ten sam wzorzec co throttle w services/sync.py.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_S = 15 * 60
_failed: dict[str, tuple[int, float]] = {}   # email -> (liczba prób, czas ostatniej)
_failed_lock = threading.Lock()


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def password_problem(password: str, password2: str) -> str | None:
    """Zwraca kod błędu do ?error=... albo None, gdy hasło jest w porządku."""
    if password != password2:
        return "mismatch"
    if len(password) < MIN_PASSWORD_LEN:
        return "short"
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return "long"
    return None


def is_locked_out(email: str) -> bool:
    with _failed_lock:
        attempts, last = _failed.get(email, (0, 0.0))
        if attempts < MAX_FAILED_ATTEMPTS:
            return False
        if time_module.monotonic() - last >= LOCKOUT_S:
            del _failed[email]          # blokada wygasła
            return False
        return True


def note_failed_login(email: str) -> None:
    with _failed_lock:
        attempts, _ = _failed.get(email, (0, 0.0))
        _failed[email] = (attempts + 1, time_module.monotonic())


def reset_failed_login(email: str) -> None:
    with _failed_lock:
        _failed.pop(email, None)


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    """Zależność FastAPI: użytkownik z sesji. Zastępuje dawne local_user().

    Rzuca 401 — dla stron HTML globalny handler w main.py zamienia to na
    przekierowanie na /login.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(401, "Nie zalogowano")
    user = db.get(User, user_id)
    if user is None:                     # konto skasowane, a ciasteczko zostało
        request.session.clear()
        raise HTTPException(401, "Nie zalogowano")
    return user

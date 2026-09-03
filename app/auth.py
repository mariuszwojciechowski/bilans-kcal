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

# Ochrona przed zgadywaniem kodu zaproszenia: /register bramkuje jeden wspólny,
# statyczny sekret, a mechanizm jest opisany w publicznym repo — bez limitu prób
# kod da się zgadywać online. Klucz to IP (adres e-mail wybiera atakujący, więc
# liczenie po nim nic nie daje). Limit luźniejszy niż przy haśle: tester
# przepisujący kod z SMS-a ma prawo się kilka razy pomylić.
MAX_INVITE_ATTEMPTS = 10
INVITE_LOCKOUT_S = 15 * 60


class AttemptThrottle:
    """Licznik nieudanych prób w pamięci procesu.

    Jeden worker (patrz CLAUDE.md „Nie ustaw uvicorn workers > 1") — przy wielu
    procesach liczniki rozjechałyby się i limit byłby N-krotnie luźniejszy.
    Słownik jest ograniczony `max_keys`: bez tego ktoś, kto strzela unikalnymi
    kluczami (e-mail per próba), rośnie nam pamięć procesu bez ograniczeń.
    """

    def __init__(self, max_attempts: int, lockout_s: int, max_keys: int = 10_000) -> None:
        self.max_attempts = max_attempts
        self.lockout_s = lockout_s
        self.max_keys = max_keys
        # klucz -> (liczba prób, czas ostatniej próby). Mutowany W MIEJSCU —
        # nigdy nie podmieniaj tego obiektu, bo `_failed` niżej jest jego aliasem.
        self.attempts: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        """Woływane pod zamkniętym lockiem. Najpierw wygasłe, a jeśli to nie
        wystarczy — najstarsze wpisy (blokada napastnika i tak wygasa sama)."""
        for key, (_, last) in list(self.attempts.items()):
            if now - last >= self.lockout_s:
                del self.attempts[key]
        if len(self.attempts) > self.max_keys:
            oldest = sorted(self.attempts.items(), key=lambda kv: kv[1][1])
            for key, _ in oldest[: len(self.attempts) - self.max_keys]:
                del self.attempts[key]

    def is_locked(self, key: str) -> bool:
        with self._lock:
            attempts, last = self.attempts.get(key, (0, 0.0))
            if attempts < self.max_attempts:
                return False
            if time_module.monotonic() - last >= self.lockout_s:
                del self.attempts[key]          # blokada wygasła
                return False
            return True

    def note_failure(self, key: str) -> None:
        with self._lock:
            now = time_module.monotonic()
            attempts, _ = self.attempts.get(key, (0, 0.0))
            self.attempts[key] = (attempts + 1, now)
            if len(self.attempts) > self.max_keys:
                self._prune(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self.attempts.pop(key, None)


_login_throttle = AttemptThrottle(MAX_FAILED_ATTEMPTS, LOCKOUT_S)
_invite_throttle = AttemptThrottle(MAX_INVITE_ATTEMPTS, INVITE_LOCKOUT_S)

# Alias zgodnościowy: fixture'y testów robią `auth._failed.clear()`. To ten sam
# obiekt, którym operuje _login_throttle (patrz komentarz przy `attempts`).
_failed = _login_throttle.attempts


def client_ip(request: Request) -> str:
    """Adres klienta widziany przez Caddy.

    Bierzemy OSTATNI wpis `X-Forwarded-For`: Caddy dopisuje na końcu prawdziwy
    adres peera, więc wcześniejsze wpisy mogą być podstawione przez klienta
    (nagłówek jest w pełni pod jego kontrolą). Bez proxy (dev, testy) —
    adres z gniazda."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


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
    return _login_throttle.is_locked(email)


def note_failed_login(email: str) -> None:
    _login_throttle.note_failure(email)


def reset_failed_login(email: str) -> None:
    _login_throttle.reset(email)


def invite_is_locked(ip: str) -> bool:
    return _invite_throttle.is_locked(ip)


def note_failed_invite(ip: str) -> None:
    _invite_throttle.note_failure(ip)


def reset_failed_invite(ip: str) -> None:
    _invite_throttle.reset(ip)


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

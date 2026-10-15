"""Reset hasła linkiem mailowym — logika domenowa, wolna od FastAPI.

Token: 32 bajty `secrets.token_urlsafe`, w bazie tylko SHA-256. TTL
`TOKEN_TTL_MIN` (60 min), jednorazowość atomowym UPDATE-em (żądania idą
w threadpoolu, więc peek-then-mark by się wyścigał). Throttle w pamięci
procesu — legalne przy jednym workerze (CLAUDE.md: `workers > 1` zakazane).

Anti-enumeracja: `request` zwraca bool „wysłano?", a router niezależnie od
niego pokazuje zawsze tę samą odpowiedź — z zewnątrz nie widać, czy konto
istnieje.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import PasswordResetToken, User
from . import mail

TOKEN_TTL_MIN = 60
MAX_REQUESTS_PER_HOUR = 3

# email → lista timestampów żądań w ostatniej godzinie (throttle w pamięci)
_request_times: dict[str, list[datetime]] = {}


class ResetTokenInvalid(Exception):
    """Token nie istnieje, wygasł albo został już użyty."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _throttled(email: str) -> bool:
    now = datetime.utcnow()
    times = [t for t in _request_times.get(email, [])
             if now - t < timedelta(hours=1)]
    if len(times) >= MAX_REQUESTS_PER_HOUR:
        _request_times[email] = times
        return True
    times.append(now)
    _request_times[email] = times
    return False


def request_reset(db: Session, email: str, base_url: str) -> bool:
    """Żądanie linku resetu. Zwraca True, gdy wysłano maila; False dla
    nieistniejącego konta albo przy throttle — router nie odróżnia tych
    odpowiedzi. `base_url` (PUBLIC_URL) musi być jawne, bo serwis nie zna
    kontekstu żądania."""
    if _throttled(email):
        return False
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return False
    _cleanup(db, user.id)
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=_hash(token),
        expires_at=datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MIN),
    ))
    db.commit()
    return mail.send_password_reset(email, f"{base_url}/password-reset/{token}")


def peek(db: Session, token: str) -> User:
    """Walidacja tokenu bez jego zużycia (podgląd przy GET strony hasła —
    skanery podglądające link nie mogą spurzować tokenu)."""
    row = db.scalar(select(PasswordResetToken)
                    .where(PasswordResetToken.token_hash == _hash(token)))
    if (row is None or row.used_at is not None
            or row.expires_at < datetime.utcnow()):
        raise ResetTokenInvalid()
    user = db.get(User, row.user_id)
    if user is None:
        raise ResetTokenInvalid()
    return user


def consume(db: Session, token: str) -> User:
    """Jednorazowe pobranie tokenu — atomowy UPDATE chroni przed użyciem
    dwa razy z dwóch wątków. Unieważnia też wszystkie pozostałe tokeny
    usera (jeden reset = jeden ważny link)."""
    now = datetime.utcnow()
    res = db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.token_hash == _hash(token),
               PasswordResetToken.used_at.is_(None),
               PasswordResetToken.expires_at > now)
        .values(used_at=now))
    if res.rowcount != 1:
        raise ResetTokenInvalid()
    row = db.scalar(select(PasswordResetToken)
                    .where(PasswordResetToken.token_hash == _hash(token)))
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == row.user_id,
               PasswordResetToken.used_at.is_(None))
        .values(used_at=now))
    db.commit()
    return db.get(User, row.user_id)


def _cleanup(db: Session, user_id: int) -> None:
    """Kasuje stare tokeny usera przed wystawieniem nowego — tabela nie
    rośnie w nieskończoność, a stare linki przestają istnieć naprawdę."""
    db.execute(delete(PasswordResetToken).where(
        PasswordResetToken.user_id == user_id,
        (PasswordResetToken.used_at.is_not(None))
        | (PasswordResetToken.expires_at < datetime.utcnow())))

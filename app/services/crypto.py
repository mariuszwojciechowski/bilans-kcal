"""Szyfrowanie sekretów użytkownika (klucze LLM, tokeny Garmina) — Fernet.

Zakres ochrony (świadomie ograniczony, decyzja właściciela 2026-09-03): chroni
kopię bazy, backup i eksport katalogu danych. NIE chroni przed kimś, kto ma
roota na żywej VM — klucz szyfrujący i baza leżą na tej samej maszynie."""

import re

from cryptography.fernet import Fernet

from ..config import DEBUG, ENC_KEY, SECRET_KEY

PREFIX = "enc:v1:"

_HKDF_SALT = b"fit-krasnal-enc-v1"


def _dev_key_from_secret(secret_key: str) -> bytes:
    """HKDF-SHA256 deterministyczny z SECRET_KEY — tylko dla dev/testów bez
    skonfigurowanego FIT_KRASNAL_ENC_KEY (żeby działały bez dodatkowej zmiennej)."""
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=b"app-enc-key")
    raw = hkdf.derive(secret_key.encode())
    return base64.urlsafe_b64encode(raw)


def _key() -> bytes:
    if ENC_KEY:
        return ENC_KEY.encode() if isinstance(ENC_KEY, str) else ENC_KEY
    if DEBUG:
        return _dev_key_from_secret(SECRET_KEY)
    raise RuntimeError(
        "FIT_KRASNAL_ENC_KEY nie jest ustawiony, a FIT_KRASNAL_DEBUG nie jest "
        "włączone — proces nie może bezpiecznie szyfrować sekretów. Ustaw "
        "FIT_KRASNAL_ENC_KEY w /etc/fit-krasnal/env."
    )


def _fernet() -> Fernet:
    # Bez cache'owania globalnego — testy monkeypatchują klucz w locie i nie
    # chcemy trzymać Fernet zbudowanego ze starego klucza między testami.
    return Fernet(_key())


def encrypt(value: str) -> str:
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def decrypt(value: str) -> str:
    """Wartość bez prefiksu przechodzi bez zmian — to jest ścieżka migracyjna
    (stary plaintext), nie błąd."""
    if not is_encrypted(value):
        return value
    token = value[len(PREFIX):]
    return _fernet().decrypt(token.encode()).decode()


_SECRET_PATTERNS = [
    re.compile(r"AIza[\w-]{10,}"),
    re.compile(r"sk-ant-[\w-]{10,}"),
]


def scrub(text: str) -> str:
    """Maskuje klucze API rozpoznawalne w treści wyjątku, żeby nie wyciekły do
    logów (biblioteki HTTP czasem wsadzają klucz w URL błędu)."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def migrate_plaintext_settings(db) -> int:
    """Szyfruje istniejące wiersze AppSetting z SECRET_SETTING_KEYS zapisane
    jeszcze plaintextem. Idempotentne — już zaszyfrowane wiersze (prefiks
    enc:v1:) są pomijane. Wołane przy starcie procesu."""
    from sqlalchemy import select

    from ..models import AppSetting
    from . import settings as settings_service

    rows = db.scalars(
        select(AppSetting).where(AppSetting.key.in_(settings_service.SECRET_SETTING_KEYS))
    ).all()
    migrated = 0
    for row in rows:
        if not is_encrypted(row.value):
            row.value = encrypt(row.value)
            migrated += 1
    if migrated:
        db.commit()
    return migrated

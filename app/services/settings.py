"""Ustawienia aplikacji per użytkownik (klucze LLM itd.).

Multi-user: klucze LLM z bazy przekazywane są jako argumenty do meal_vision.*
per request (get_llm_keys). apply_llm_env zostawiony jako pomoc dla skryptów
i testów legacy, ale route'y appki nie korzystają z niego."""

import os
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting
from . import crypto


class LlmKeys(NamedTuple):
    gemini: str | None
    anthropic: str | None

# klucz ustawienia -> zmienna środowiskowa czytana przez meal_vision
LLM_KEYS = {
    "gemini_api_key": "GEMINI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}

# Wartości tych kluczy leżą w bazie zaszyfrowane (crypto.encrypt/decrypt) —
# sekrety użytkownika trzymamy TYLKO przez ten serwis, nigdy wprost w AppSetting.
SECRET_SETTING_KEYS = {"gemini_api_key", "anthropic_api_key", "garmin_tokens"}


def get_setting(db: Session, user_id: int, key: str) -> str | None:
    row = db.get(AppSetting, (user_id, key))
    if row is None:
        return None
    return crypto.decrypt(row.value) if key in SECRET_SETTING_KEYS else row.value


def set_setting(db: Session, user_id: int, key: str, value: str | None) -> None:
    row = db.get(AppSetting, (user_id, key))
    if value:
        stored = crypto.encrypt(value) if key in SECRET_SETTING_KEYS else value
        if row is None:
            db.add(AppSetting(user_id=user_id, key=key, value=stored))
        else:
            row.value = stored
    elif row is not None:
        db.delete(row)
    db.commit()


def all_settings(db: Session, user_id: int) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.user_id == user_id)).all()
    return {
        r.key: (crypto.decrypt(r.value) if r.key in SECRET_SETTING_KEYS else r.value)
        for r in rows
    }


def apply_llm_env(db: Session, user_id: int) -> None:
    """LEGACY: odbija klucze LLM z bazy do środowiska. Route'y appki tego już nie
    używają (przekazują klucze bezpośrednio przez get_llm_keys); zostawione dla
    skryptów lokalnych i testów, które ustawiają klucz przez env."""
    stored = all_settings(db, user_id)
    for key, env_name in LLM_KEYS.items():
        if stored.get(key):
            os.environ[env_name] = stored[key]


def get_llm_keys(db: Session, user_id: int) -> LlmKeys:
    """Klucze LLM tego usera z AppSetting — do przekazania per request do
    meal_vision.*. Zwraca None dla brakujących kluczy (nie fallback do env)."""
    stored = all_settings(db, user_id)
    return LlmKeys(
        gemini=stored.get("gemini_api_key"),
        anthropic=stored.get("anthropic_api_key"),
    )


def masked(value: str | None) -> str | None:
    if not value:
        return None
    return "•" * 6 + value[-4:] if len(value) > 4 else "•" * len(value)

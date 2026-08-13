"""Ustawienia aplikacji per użytkownik (klucze LLM itd.).

MVP jest single-user, a backendy LLM czytają klucze ze środowiska — dlatego po
zapisaniu/odczycie ustawień odbijamy je w os.environ (`apply_llm_env`).
Przy wersji multi-user trzeba będzie przekazywać klucze per żądanie."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting

# klucz ustawienia -> zmienna środowiskowa czytana przez meal_vision
LLM_KEYS = {
    "gemini_api_key": "GEMINI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def get_setting(db: Session, user_id: int, key: str) -> str | None:
    row = db.get(AppSetting, (user_id, key))
    return row.value if row else None


def set_setting(db: Session, user_id: int, key: str, value: str | None) -> None:
    row = db.get(AppSetting, (user_id, key))
    if value:
        if row is None:
            db.add(AppSetting(user_id=user_id, key=key, value=value))
        else:
            row.value = value
    elif row is not None:
        db.delete(row)
    db.commit()


def all_settings(db: Session, user_id: int) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.user_id == user_id)).all()
    return {r.key: r.value for r in rows}


def apply_llm_env(db: Session, user_id: int) -> None:
    """Odbija klucze LLM z bazy do środowiska (nadpisuje — baza jest źródłem prawdy,
    ale nie kasuje zmiennej ustawionej ręcznie w środowisku, gdy w bazie pusto)."""
    stored = all_settings(db, user_id)
    for key, env_name in LLM_KEYS.items():
        if stored.get(key):
            os.environ[env_name] = stored[key]


def masked(value: str | None) -> str | None:
    if not value:
        return None
    return "•" * 6 + value[-4:] if len(value) > 4 else "•" * len(value)

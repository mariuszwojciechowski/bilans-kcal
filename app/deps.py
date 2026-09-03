"""Współdzielone zależności FastAPI (Depends) i pomocnicze obiekty (templates, STATIC_DIR)
używane przez routery w app/routers/."""
from datetime import datetime
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import auth
from .config import ADMIN_EMAIL
from .db import db_session
from .models import User
from .services import consent as consent_service

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def humanize_ago(dt: datetime | None) -> str | None:
    """'1d 21h 12m temu' — z dokładnością do minut."""
    if dt is None:
        return None
    seconds = max(int((datetime.utcnow() - dt).total_seconds()), 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts) + " temu"


def require_llm_consent(db: Session = Depends(db_session),
                        user: User = Depends(auth.current_user)) -> None:
    """Bramka RODO: bez zgody na LLM (settings/consent) zdjęcia i opisy nie mogą
    trafić do Gemini/Anthropic — ani wprost, ani przez kolejkę."""
    if not consent_service.has_consent(db, user.id, consent_service.LLM_PHOTOS):
        raise HTTPException(
            409, "Brak zgody na wysyłanie zdjęć do zewnętrznego modelu — włącz ją w Ustawieniach")


def require_admin(user: User = Depends(auth.current_user)) -> User:
    """Nie-admin dostaje 404, nie 403 — nie ma po co ogłaszać, że taki widok
    w ogóle istnieje."""
    if user.email != ADMIN_EMAIL:
        raise HTTPException(404)
    return user

"""Współdzielone zależności FastAPI (Depends) i pomocnicze obiekty (templates, STATIC_DIR)
używane przez routery w app/routers/."""
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

# `humanize_ago` mieszka w `services/timeago.py`: potrzebuje jej też
# `services/day.py`, a warstwa serwisów nie importuje FastAPI (ten plik importuje).


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

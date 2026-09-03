"""Zgoda RODO na wysyłanie zdjęć i opisów posiłków do zewnętrznego LLM
(Google Gemini / Anthropic). Zgoda jest per-wersja noty (PRIVACY_VERSION) —
zmiana treści noty unieważnia stare zgody bez usuwania ich historii."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PRIVACY_VERSION
from ..models import Consent

LLM_PHOTOS = "llm_photos"


def has_consent(db: Session, user_id: int, kind: str = LLM_PHOTOS) -> bool:
    """Aktywna zgoda w BIEŻĄCEJ wersji noty. Zgoda z poprzedniej wersji liczy
    się jak brak zgody — treść noty się zmieniła, trzeba zdecydować na nowo."""
    return current(db, user_id, kind) is not None


def current(db: Session, user_id: int, kind: str = LLM_PHOTOS) -> Consent | None:
    return db.scalar(
        select(Consent)
        .where(Consent.user_id == user_id, Consent.kind == kind,
               Consent.version == PRIVACY_VERSION, Consent.withdrawn_at.is_(None))
        .order_by(Consent.granted_at.desc())
    )


def grant(db: Session, user_id: int, kind: str = LLM_PHOTOS) -> Consent:
    row = Consent(user_id=user_id, kind=kind, version=PRIVACY_VERSION)
    db.add(row)
    db.commit()
    return row


def withdraw(db: Session, user_id: int, kind: str = LLM_PHOTOS) -> None:
    rows = db.scalars(
        select(Consent).where(Consent.user_id == user_id, Consent.kind == kind,
                              Consent.withdrawn_at.is_(None))
    ).all()
    now = datetime.utcnow()
    for row in rows:
        row.withdrawn_at = now
    db.commit()

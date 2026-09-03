"""Zgoda RODO na wysyłanie zdjęć i opisów posiłków do zewnętrznego LLM
(Google Gemini / Anthropic). Zgoda jest per-wersja noty (PRIVACY_VERSION) —
zmiana treści noty unieważnia stare zgody bez usuwania ich historii."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import PRIVACY_VERSION
from ..models import Consent, User

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


def admin_overview(db: Session) -> list[dict]:
    """Kto, na co i kiedy wyraził zgodę — z e-mailem, dla rozliczalności RODO.
    W przeciwieństwie do /usage (celowo zanonimizowany) to widok wyłącznie
    dla admina: jeden wiersz per (użytkownik, rodzaj zgody, jaki kiedykolwiek
    wystąpił), stan najnowszego wpisu; użytkownik bez żadnej zgody dostaje
    jeden wiersz „brak zgody"."""
    users = db.scalars(select(User).order_by(User.email)).all()
    consents = db.scalars(select(Consent)).all()
    by_user: dict[int, list[Consent]] = {}
    for c in consents:
        by_user.setdefault(c.user_id, []).append(c)

    out = []
    for u in users:
        user_rows = sorted(by_user.get(u.id, []), key=lambda r: r.granted_at, reverse=True)
        if not user_rows:
            out.append({"email": u.email, "kind": LLM_PHOTOS, "version": None,
                        "granted_at": None, "withdrawn_at": None, "status": "brak zgody"})
            continue
        seen_kinds: set[str] = set()
        for r in user_rows:
            if r.kind in seen_kinds:
                continue
            seen_kinds.add(r.kind)
            if r.withdrawn_at is not None:
                status = "wycofana"
            elif r.version != PRIVACY_VERSION:
                status = "nieaktualna wersja noty"
            else:
                status = "aktualna"
            out.append({"email": u.email, "kind": r.kind, "version": r.version,
                        "granted_at": r.granted_at, "withdrawn_at": r.withdrawn_at,
                        "status": status})
    return out

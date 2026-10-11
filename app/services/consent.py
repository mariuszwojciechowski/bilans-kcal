"""Zgoda RODO na wysyłanie zdjęć i opisów posiłków do zewnętrznego LLM
(Google Gemini / Anthropic). Zgoda jest per-wersja noty (PRIVACY_VERSION) —
zmiana treści noty unieważnia stare zgody bez usuwania ich historii."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..config import PRIVACY_VERSION
from ..models import Consent, User

LLM_PHOTOS = "llm_photos"
STRAVA = "strava"


def has_consent(db: Session, user_id: int, kind: str = LLM_PHOTOS) -> bool:
    """Czy wolno wysyłać dane: zgoda w bieżącej wersji noty albo — do
    CONSENT_DEADLINE — okres przejściowy (starsza zgoda lub brak decyzji)."""
    return effective(db, user_id, kind) is not None or in_grace(db, user_id, kind)


def in_grace(db: Session, user_id: int, kind: str = LLM_PHOTOS,
             today: date | None = None) -> bool:
    """Okres przejściowy dla szacowania LLM: do CONSENT_DEADLINE nikt, kto nie
    podjął decyzji (brak jakiegokolwiek wpisu), nie jest blokowany. Wycofanie
    jest decyzją i blokuje zawsze. Tylko LLM — zgoda Stravy działa jak dotąd."""
    if kind != LLM_PHOTOS or (today or date.today()) > config.CONSENT_DEADLINE:
        return False
    return db.scalar(
        select(Consent.id).where(Consent.user_id == user_id, Consent.kind == kind)
    ) is None


def effective(db: Session, user_id: int, kind: str = LLM_PHOTOS,
              today: date | None = None) -> Consent | None:
    """Zgoda, która dziś obowiązuje: `current`, a gdy jej brak i termin jeszcze
    nie minął — najnowsza niewycofana zgoda w dowolnej wersji. Wycofanie zawsze
    wygrywa (wycofane wiersze nigdy nie wchodzą do wyniku)."""
    row = current(db, user_id, kind)
    if row is not None:
        return row
    if (today or date.today()) > config.CONSENT_DEADLINE:
        return None
    return db.scalar(
        select(Consent)
        .where(Consent.user_id == user_id, Consent.kind == kind,
               Consent.withdrawn_at.is_(None))
        .order_by(Consent.granted_at.desc())
    )


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

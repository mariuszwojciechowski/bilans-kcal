"""Statystyki użycia i rozliczalność RODO (tylko admin)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth
from ..config import PRIVACY_VERSION
from ..db import db_session
from ..deps import STATIC_DIR, require_admin, templates
from ..models import User
from ..services import consent as consent_service
from ..services import usage as usage_service

router = APIRouter()


@router.get("/usage", response_class=HTMLResponse)
def usage_page(request: Request, db: Session = Depends(db_session),
              user: User = Depends(require_admin)):
    stats = usage_service.dashboard_stats(db)
    return templates.TemplateResponse(
        request,
        "usage.html",
        {**stats, "has_logo": (STATIC_DIR / "logo.png").exists()},
    )


@router.get("/admin/consents", response_class=HTMLResponse)
def admin_consents_page(request: Request, db: Session = Depends(db_session),
                        user: User = Depends(require_admin)):
    """Rozliczalność RODO: kto i na co wyraził zgodę — z e-mailem, w
    przeciwieństwie do zanonimizowanego /usage."""
    return templates.TemplateResponse(
        request,
        "admin_consents.html",
        {"rows": consent_service.admin_overview(db), "privacy_version": PRIVACY_VERSION,
         "has_logo": (STATIC_DIR / "logo.png").exists()},
    )


class UsageEventIn(BaseModel):
    event: str


@router.post("/api/usage", status_code=204)
def api_usage(data: UsageEventIn, db: Session = Depends(db_session),
             user: User = Depends(auth.current_user)):
    """Zdarzenia czysto klienckie — te, które nie mają odpowiednika po
    stronie serwera (przełączanie zakładek, otwarcie wpisu ręcznego...)."""
    if data.event not in usage_service.EVENTS:
        raise HTTPException(422, "Nieznane zdarzenie")
    usage_service.bump(db, user.id, data.event)
    return Response(status_code=204)

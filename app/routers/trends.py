"""Trendy: strona HTML (wykresy SVG) i JSON API dla mobilnego SPA.

Oba widoki biorą dane z `services.trends.payload` — router odpowiada tylko za
telemetrię i kształt odpowiedzi (kontekst szablonu vs JSON).
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import User, UserProfile
from ..services import trends as trends_service
from ..services import usage as usage_service
from ..services.clock import user_today
from ..services.sync import maybe_sync

router = APIRouter()


def _bump_trends(db: Session, user_id: int, days: int) -> None:
    """Dwa zdarzenia na wejście: samo otwarcie widoku i wybrany zakres."""
    usage_service.bump(db, user_id, "trends_view")
    usage_service.bump(db, user_id, f"trends_{trends_service.nearest_range(days)}")


@router.get("/trends", response_class=HTMLResponse)
def trends(
    request: Request,
    background: BackgroundTasks,
    days: int = 30,
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    background.add_task(maybe_sync, user.id)
    days = trends_service.clamp_days(days)
    _bump_trends(db, user.id, days)

    profile = db.get(UserProfile, user.id)
    view = trends_service.payload(db, user.id, days, today=user_today(profile))
    today = view.pop("today")
    return templates.TemplateResponse(
        request,
        "trends.html",
        {
            **view,
            "ranges": trends_service.TREND_RANGES,
            "today": today.isoformat(),
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


# ── Trendy API (JSON + SVG) — dla mobilnego SPA ───────────────────────────

@router.get("/api/trends")
def api_trends_data(days: int = 30, db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    days = trends_service.clamp_days(days)
    _bump_trends(db, user.id, days)

    profile = db.get(UserProfile, user.id)
    view = trends_service.payload(db, user.id, days, today=user_today(profile))
    view.pop("today")      # data jest potrzebna tylko szablonowi HTML
    return {
        **view,
        "ranges": [{"days": d, "label": label} for d, label in trends_service.TREND_RANGES],
    }

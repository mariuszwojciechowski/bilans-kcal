"""Strona główna aplikacji (jeden responsywny widok mobile+desktop)."""
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import auth
from ..config import ADMIN_EMAIL, APP_VERSION
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import User, UserProfile
from ..services.calibration import run_catch_up
from ..services.clock import user_today
from ..services.sync import maybe_sync

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/mobile", response_class=HTMLResponse)
def dashboard(request: Request, background: BackgroundTasks,
              db: Session = Depends(db_session),
              user: User = Depends(auth.current_user)):
    """Jedyny widok aplikacji — responsive, działa na telefonie i desktopie."""
    background.add_task(maybe_sync, user.id)
    background.add_task(run_catch_up, user.id)
    profile = db.get(UserProfile, user.id)
    return templates.TemplateResponse(
        request,
        "mobile.html",
        {"has_logo": (STATIC_DIR / "logo.png").exists(),
         "is_admin": user.email == ADMIN_EMAIL,
         "app_version": APP_VERSION,
         "today": user_today(profile).isoformat()},
    )

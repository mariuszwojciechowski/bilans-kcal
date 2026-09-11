"""Ustawienia: strona HTML (formularze) i JSON API dla mobilnego SPA."""
import json
from datetime import date

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth
from ..config import ADMIN_EMAIL, CONSENT_DEADLINE, PRIVACY_VERSION, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import DailySummary, PendingMeal, User, UserProfile
from ..providers import garmin as garmin_provider
from ..providers import strava as strava_provider
from ..services import consent as consent_service
from ..services import meal_queue, meal_vision
from ..services import settings as settings_service
from ..services import usage as usage_service
from ..services.macros import lifestyle_options
from ..services.timeago import humanize_ago

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(db_session),
                  user: User = Depends(auth.current_user),
                  saved: str | None = None, mfa: str | None = None,
                  error: str | None = None):
    stored = settings_service.all_settings(db, user.id)
    keys = settings_service.get_llm_keys(db, user.id)
    profile = db.get(UserProfile, user.id)
    last_sync = db.scalar(
        select(func.max(DailySummary.sync_ts)).where(DailySummary.user_id == user.id)
    )
    pending_count = db.scalar(
        select(func.count(PendingMeal.id)).where(PendingMeal.user_id == user.id)
    )
    consent_row = consent_service.current(db, user.id)
    strava_consent = consent_service.current(db, user.id, consent_service.STRAVA)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "is_admin": user.email == ADMIN_EMAIL,
            "garmin_connected": garmin_provider.tokens_present(db, user.id),
            "strava_connected": strava_provider.tokens_present(db, user.id),
            "strava_consent_granted": strava_consent is not None,
            "last_sync_ago": humanize_ago(last_sync),
            "gemini_masked": settings_service.masked(stored.get("gemini_api_key")),
            "claude_masked": settings_service.masked(stored.get("anthropic_api_key")),
            "backend": (meal_vision.pick_backend(keys.gemini, keys.anthropic)
                         if meal_vision.llm_configured(keys.gemini, keys.anthropic) else None),
            "pending_count": pending_count or 0,
            "retention_days": meal_queue.RETENTION_DAYS,
            "target_weight_kg": profile.target_weight_kg if profile else None,
            "lifestyle": (profile.lifestyle if profile else None) or "active",
            "lifestyle_options": lifestyle_options(),
            "consent_granted": consent_row is not None,
            "consent_granted_at": consent_row.granted_at if consent_row else None,
            "privacy_version": PRIVACY_VERSION,
            "saved": saved, "mfa": mfa, "error": error,
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


@router.post("/settings/consent")
def settings_consent(granted: bool = Form(...), db: Session = Depends(db_session),
                     user: User = Depends(auth.current_user)):
    """Włączenie/wycofanie zgody na wysyłanie zdjęć i opisów posiłków do LLM."""
    if granted:
        consent_service.grant(db, user.id)
    else:
        consent_service.withdraw(db, user.id)
        for pending in db.scalars(
            select(PendingMeal).where(PendingMeal.user_id == user.id)
        ).all():
            meal_queue.delete_pending(db, pending)
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/llm")
def settings_llm(
    background: BackgroundTasks,
    gemini_api_key: str = Form(""),
    anthropic_api_key: str = Form(""),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """Zapis kluczy LLM (puste pole = bez zmian). Po zapisie: przetworzenie kolejki."""
    if gemini_api_key.strip():
        settings_service.set_setting(db, user.id, "gemini_api_key", gemini_api_key.strip())
    if anthropic_api_key.strip():
        settings_service.set_setting(db, user.id, "anthropic_api_key", anthropic_api_key.strip())
    usage_service.bump(db, user.id, "llm_key_save")
    background.add_task(meal_queue.process_queue, user.id)
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/lifestyle")
def settings_lifestyle(lifestyle: str = Form(...), db: Session = Depends(db_session),
                       user: User = Depends(auth.current_user)):
    """Styl życia — zmienia zakresy makro (białko g/kg, węgle g/kg u trenujących)."""
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Najpierw skonfiguruj profil na dashboardzie")
    if lifestyle not in lifestyle_options():
        raise HTTPException(422, "Nieznany styl życia")
    profile.lifestyle = lifestyle
    db.commit()
    usage_service.bump(db, user.id, "lifestyle_save")
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/goal")
def settings_goal(target_weight_kg: float = Form(...), db: Session = Depends(db_session),
                  user: User = Depends(auth.current_user)):
    """Cel wagi — rysowany na trendach, używany w tekstach motywacyjnych."""
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Najpierw skonfiguruj profil na dashboardzie")
    profile.target_weight_kg = target_weight_kg
    db.commit()
    usage_service.bump(db, user.id, "goal_save")
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/garmin")
def settings_garmin(email: str = Form(...), password: str = Form(...),
                    db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    """Logowanie do Garmina z ustawień. Hasło idzie tylko do biblioteki Garmina."""
    try:
        result = garmin_provider.interactive_login_start(db, email.strip(), password, user.id)
    except Exception as exc:
        return RedirectResponse(f"/settings?error={exc.__class__.__name__}", status_code=303)
    if result == "mfa":
        usage_service.bump(db, user.id, "garmin_mfa")
        return RedirectResponse("/settings?mfa=1", status_code=303)
    usage_service.bump(db, user.id, "garmin_connect_ok")
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings/garmin/mfa")
def settings_garmin_mfa(code: str = Form(...), db: Session = Depends(db_session),
                        user: User = Depends(auth.current_user)):
    try:
        garmin_provider.interactive_login_mfa(db, code.strip(), user.id)
    except Exception as exc:
        return RedirectResponse(f"/settings?error={exc.__class__.__name__}", status_code=303)
    usage_service.bump(db, user.id, "garmin_connect_ok")
    return RedirectResponse("/settings?saved=1", status_code=303)


# ── Strava OAuth ─────────────────────────────────────────────────────────

@router.post("/settings/strava/connect")
def settings_strava_connect(consent_granted: bool = Form(False),
                            db: Session = Depends(db_session),
                            user: User = Depends(auth.current_user)):
    """Inicjacja OAuth do Stravy. Waliduje checkbox zgody, granting się dzieje
    w callbacku. Jeśli zgoda już istnieje, bypass checkbox."""
    has_consent = consent_service.has_consent(db, user.id, consent_service.STRAVA)
    if not has_consent and not consent_granted:
        return RedirectResponse("/settings?error=ConsentRequired", status_code=303)

    if not has_consent:
        consent_service.grant(db, user.id, consent_service.STRAVA)

    # Redirect do Stravy
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        return RedirectResponse("/settings?error=StravaNotConfigured", status_code=303)

    import secrets
    state = secrets.token_urlsafe(32)
    # Stan trzymamy w sesji (w Stravie nie jest bezpieczne, ale MVP)
    return RedirectResponse(
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        # Strava zna tylko: read, read_all, profile:read_all, profile:write,
        # activity:read, activity:read_all, activity:write. Wcześniejsze
        # `activity:read_only` nie istnieje — Strava odrzucała autoryzację
        # (`field: scope, code: invalid`). `read_all` obejmuje też aktywności
        # prywatne („Tylko ja"): brakująca aktywność = zafałszowany bilans.
        f"&scope=activity:read_all"
        f"&approval_prompt=auto"
        f"&state={state}",
        status_code=302
    )


@router.get("/settings/strava/callback")
def settings_strava_callback(code: str = Query(...), error: str | None = Query(None),
                             db: Session = Depends(db_session),
                             user: User = Depends(auth.current_user)):
    """Callback OAuth z Stravy — wymienia code na tokeny i zapisuje je."""
    if error:
        return RedirectResponse(f"/settings?error=StravaOAuth", status_code=303)

    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        return RedirectResponse("/settings?error=StravaNotConfigured", status_code=303)

    try:
        resp = httpx.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        resp.raise_for_status()
        token_data = resp.json()

        # Zapis tokens (access_token, refresh_token, expires_at)
        blob = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "scope": token_data.get("scope"),
        }
        settings_service.set_setting(db, user.id, strava_provider.STRAVA_TOKENS_KEY, json.dumps(blob))
        usage_service.bump(db, user.id, "strava_connect_ok")
        return RedirectResponse("/settings?saved=1", status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/settings?error={exc.__class__.__name__}", status_code=303)


@router.post("/settings/strava/disconnect")
def settings_strava_disconnect(db: Session = Depends(db_session),
                               user: User = Depends(auth.current_user)):
    """Odłączenie konta Stravy. Kasuje tokeny i opcjonalnie woła deauthorize u Stravy."""
    # Pobranie tokenu przed skasowaniem
    blob_str = settings_service.get_setting(db, user.id, strava_provider.STRAVA_TOKENS_KEY)

    # Kasowanie lokalnie
    settings_service.set_setting(db, user.id, strava_provider.STRAVA_TOKENS_KEY, None)
    usage_service.bump(db, user.id, "strava_disconnect")

    # Opcjonalny deauthorize do Stravy (Strava wymaga tego w ToS)
    if blob_str:
        try:
            blob = json.loads(blob_str)
            access_token = blob.get("access_token")
            if access_token:
                httpx.post(
                    "https://www.strava.com/oauth/deauthorize",
                    data={"access_token": access_token},
                    timeout=5,
                )
        except Exception:
            pass  # Błąd deauthorize nie blokuje lokalnego usunięcia

    return RedirectResponse("/settings?saved=1", status_code=303)


# ── Ustawienia API (JSON) — dla mobilnego SPA ─────────────────────────────

@router.get("/api/settings")
def api_get_settings(db: Session = Depends(db_session),
                     user: User = Depends(auth.current_user)):
    stored = settings_service.all_settings(db, user.id)
    keys = settings_service.get_llm_keys(db, user.id)
    consent_row = consent_service.current(db, user.id)
    strava_consent = consent_service.current(db, user.id, consent_service.STRAVA)
    today = date.today()
    return {
        "gemini_masked": settings_service.masked(stored.get("gemini_api_key")),
        "anthropic_masked": settings_service.masked(stored.get("anthropic_api_key")),
        "backend": (meal_vision.pick_backend(keys.gemini, keys.anthropic)
                    if meal_vision.llm_configured(keys.gemini, keys.anthropic) else None),
        "garmin_connected": garmin_provider.tokens_present(db, user.id),
        "strava_connected": strava_provider.tokens_present(db, user.id),
        "strava_consent_granted": strava_consent is not None,
        "lifestyle_options": lifestyle_options(),
        "consent_llm_photos": consent_row is not None,
        "consent_granted_at": consent_row.granted_at.isoformat() if consent_row else None,
        "privacy_version": PRIVACY_VERSION,
        "consent_deadline": CONSENT_DEADLINE.isoformat(),
        "consent_deadline_passed": today > CONSENT_DEADLINE,
    }


class ConsentIn(BaseModel):
    granted: bool


@router.post("/api/settings/consent")
def api_settings_consent(data: ConsentIn, db: Session = Depends(db_session),
                         user: User = Depends(auth.current_user)):
    if data.granted:
        consent_service.grant(db, user.id)
    else:
        consent_service.withdraw(db, user.id)
        for pending in db.scalars(
            select(PendingMeal).where(PendingMeal.user_id == user.id)
        ).all():
            meal_queue.delete_pending(db, pending)
    return {"ok": True}


class LlmKeysIn(BaseModel):
    gemini_api_key: str = ""
    anthropic_api_key: str = ""


@router.post("/api/settings/llm")
def api_save_llm(data: LlmKeysIn, background: BackgroundTasks,
                 db: Session = Depends(db_session),
                 user: User = Depends(auth.current_user)):
    if data.gemini_api_key.strip():
        settings_service.set_setting(db, user.id, "gemini_api_key", data.gemini_api_key.strip())
    if data.anthropic_api_key.strip():
        settings_service.set_setting(db, user.id, "anthropic_api_key", data.anthropic_api_key.strip())
    usage_service.bump(db, user.id, "llm_key_save")
    background.add_task(meal_queue.process_queue, user.id)
    return {"ok": True}

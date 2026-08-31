import json
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
                     Query, Request, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import auth
from .config import (DEBUG, INVITE_CODE, MAX_PHOTO_BYTES, PHOTOS_DIR, SECRET_KEY,
                     ensure_dirs)
from .db import db_session, get_session, init_db
from .models import Activity, DailySummary, Meal, PendingMeal, SavedMeal, User, UserProfile, WeightLog
from .providers import garmin as garmin_provider
from .providers.garmin import GarminNotLoggedIn, GarminProvider
from .services import meal_queue, meal_vision, quips, transfer
from .services import settings as settings_service
from .services.balance import day_balance, deficit_warning, projected_weekly_change_kg
from .services.charts import Series, bar_chart, line_chart
from .services.energy import age_years, smoothed_weight, tdee_theoretical
from .services.macros import coverage, lifestyle_options, who_targets
from .services.sync import mark_attempt, maybe_sync, sync_range

app = FastAPI(title="Fit Krasnal")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=not DEBUG,   # lokalny dev po http potrzebuje https_only=False
    same_site="lax",
)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    init_db()
    # Klucze LLM aplikują się per-użytkownika w /settings/llm — przy multi-user
    # nie ma "tego jednego" usera do zasilenia na starcie. Kolejka posiłków jest
    # globalna (retencja 21 dni), więc jej sprzątanie zostawiamy.
    db = get_session()
    try:
        meal_queue.purge_expired(db)
    finally:
        db.close()


# 401 z current_user na stronie HTML → redirect na /login (przeglądarka).
# Endpointy JSON /api/* zostawiamy jako 401 (dla klientów, np. mobile).
@app.exception_handler(HTTPException)
async def _redirect_html_on_401(request: Request, exc: HTTPException):
    from fastapi.exception_handlers import http_exception_handler
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login", status_code=303)
    return await http_exception_handler(request, exc)


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


# ── Logowanie / rejestracja ───────────────────────────────────────────────

LOGIN_ERRORS = {
    "bad": "Nieprawidłowy e-mail lub hasło.",
    "locked": (f"Za dużo nieudanych prób. Odczekaj "
               f"{auth.LOCKOUT_S // 60} minut i spróbuj ponownie."),
}
REGISTER_ERRORS = {
    "invite": "Nieprawidłowy kod zaproszenia.",
    "mismatch": "Hasła nie są identyczne.",
    "short": f"Hasło musi mieć co najmniej {auth.MIN_PASSWORD_LEN} znaków.",
    "long": "Hasło jest za długie (maks. 72 bajty).",
    "taken": "Konto z tym adresem już istnieje.",
}


def _auth_page(request: Request, template: str, errors: dict, error: str | None):
    return templates.TemplateResponse(
        request,
        template,
        {
            "error": errors.get(error) if error else None,
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    return _auth_page(request, "login.html", LOGIN_ERRORS, error)


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                 db: Session = Depends(db_session)):
    email = email.strip().lower()
    if auth.is_locked_out(email):
        return RedirectResponse("/login?error=locked", status_code=303)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not auth.verify_password(password, user.password_hash):
        auth.note_failed_login(email)
        return RedirectResponse("/login?error=bad", status_code=303)
    auth.reset_failed_login(email)
    auth.login_user(request, user)
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str | None = None):
    if not INVITE_CODE:
        raise HTTPException(503, "Rejestracja jest wyłączona.")
    return _auth_page(request, "register.html", REGISTER_ERRORS, error)


@app.post("/register")
def register_submit(request: Request, email: str = Form(...), password: str = Form(...),
                    password2: str = Form(...), invite_code: str = Form(...),
                    db: Session = Depends(db_session)):
    if not INVITE_CODE:
        raise HTTPException(503, "Rejestracja jest wyłączona.")
    if not secrets.compare_digest(invite_code.strip(), INVITE_CODE):
        return RedirectResponse("/register?error=invite", status_code=303)
    problem = auth.password_problem(password, password2)
    if problem:
        return RedirectResponse(f"/register?error={problem}", status_code=303)
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        return RedirectResponse("/register?error=taken", status_code=303)
    user = User(email=email, password_hash=auth.hash_password(password))
    db.add(user)
    db.commit()
    auth.login_user(request, user)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout_submit(request: Request):
    auth.logout_user(request)
    return RedirectResponse("/login", status_code=303)


# ── Profil ────────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    birth_date: date
    sex: str  # 'M' | 'F'
    height_cm: float
    target_deficit_kcal: int = 500
    target_weight_kg: float | None = None  # cel ciężaru
    lifestyle: str = "active"
    tz: str = "Europe/Warsaw"


@app.get("/api/profile")
def get_profile(db: Session = Depends(db_session), user: User = Depends(auth.current_user)):
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(404, "Profil nie jest jeszcze skonfigurowany")
    return profile


@app.put("/api/profile")
def put_profile(data: ProfileIn, db: Session = Depends(db_session),
                user: User = Depends(auth.current_user)):
    if data.sex.upper() not in ("M", "F"):
        raise HTTPException(422, "sex musi być 'M' lub 'F'")
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id, birth_date=data.birth_date,
                              sex=data.sex.upper(), height_cm=data.height_cm)
        db.add(profile)
    profile.birth_date = data.birth_date
    profile.sex = data.sex.upper()
    profile.height_cm = data.height_cm
    profile.target_deficit_kcal = data.target_deficit_kcal
    if data.target_weight_kg is not None:
        profile.target_weight_kg = data.target_weight_kg
    if data.lifestyle in lifestyle_options():
        profile.lifestyle = data.lifestyle
    profile.tz = data.tz
    db.commit()
    return {"ok": True}


# ── Synchronizacja Garmin ─────────────────────────────────────────────────

@app.post("/api/sync")
def sync(days: int = 7, db: Session = Depends(db_session),
         user: User = Depends(auth.current_user)):
    """Ręczna synchronizacja — bez throttla, synchronicznie, zwraca liczniki."""
    mark_attempt(user.id)
    try:
        return sync_range(db, GarminProvider(user.id), user.id, days=days)
    except GarminNotLoggedIn as exc:
        raise HTTPException(409, str(exc))


# ── Ręczny wpis wagi i kroków (dla mobile, bez Garmina) ──────────────────

class WeightIn(BaseModel):
    date: date
    weight_kg: float


@app.post("/api/weight")
def save_weight(data: WeightIn, db: Session = Depends(db_session),
                user: User = Depends(auth.current_user)):
    """Ręczny wpis wagi z mobile (świadome odstępstwo od D3 — desktop bierze
    tylko z Garmina). Upsert po (user_id, date): jeden pomiar na dzień."""
    if not 20 <= data.weight_kg <= 300:
        raise HTTPException(422, "waga poza sensownym zakresem (20-300 kg)")
    existing = db.scalar(select(WeightLog).where(
        WeightLog.user_id == user.id, WeightLog.date == data.date))
    if existing:
        existing.weight_kg = data.weight_kg
        existing.source = "manual"
    else:
        db.add(WeightLog(user_id=user.id, date=data.date,
                          weight_kg=data.weight_kg, source="manual"))
    db.commit()
    return {"ok": True}


class StepsIn(BaseModel):
    steps: int


@app.post("/api/day/{day}/steps")
def save_steps(day: date, data: StepsIn, db: Session = Depends(db_session),
               user: User = Depends(auth.current_user)):
    """Ręczny wpis kroków (mobile). Upsert po (user_id, date)."""
    if not 0 <= data.steps <= 200_000:
        raise HTTPException(422, "kroki poza sensownym zakresem")
    summary = db.scalar(select(DailySummary).where(
        DailySummary.user_id == user.id, DailySummary.date == day))
    if summary:
        summary.steps = data.steps
    else:
        db.add(DailySummary(user_id=user.id, date=day, steps=data.steps))
    db.commit()
    return {"ok": True}


# ── Raport dzienny ────────────────────────────────────────────────────────

def day_report(db: Session, user_id: int, day: date) -> dict:
    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(409, "Najpierw skonfiguruj profil (PUT /api/profile)")

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user_id)).all()
    ]
    weight = smoothed_weight(weights)
    if weight is None:
        raise HTTPException(409, "Brak pomiarów wagi — zsynchronizuj Garmina (POST /api/sync)")

    summary = db.scalar(
        select(DailySummary).where(DailySummary.user_id == user_id, DailySummary.date == day)
    )
    activities = db.scalars(
        select(Activity).where(Activity.user_id == user_id, Activity.date == day)
    ).all()
    meals = db.scalars(
        select(Meal).where(Meal.user_id == user_id, Meal.date == day).order_by(Meal.time.desc())
    ).all()
    pending = db.scalars(
        select(PendingMeal).where(PendingMeal.user_id == user_id, PendingMeal.date == day)
        .order_by(PendingMeal.created_at)
    ).all()
    last_sync = db.scalar(
        select(func.max(DailySummary.sync_ts)).where(DailySummary.user_id == user_id)
    )

    kcal_in = sum(m.kcal for m in meals)
    tdee = tdee_theoretical(
        weight_kg=weight,
        height_cm=profile.height_cm,
        age=age_years(profile.birth_date, day),
        sex=profile.sex,
        steps=(summary.steps if summary and summary.steps else 0),
        activities=[
            {"type": a.type, "duration_s": a.duration_s, "distance_m": a.distance_m}
            for a in activities
        ],
        kcal_in=kcal_in,
    )
    bal = day_balance(
        kcal_in=kcal_in,
        garmin_total=(summary.kcal_total_garmin if summary else None),
        model_tdee=tdee.total,
        day_complete=bool(summary and summary.complete),
    )
    e_target = bal.kcal_out - profile.target_deficit_kcal
    targets = who_targets(e_target, weight, sex=profile.sex,
                          age=age_years(profile.birth_date, day),
                          lifestyle=profile.lifestyle or "active")
    macros = coverage(
        targets,
        protein_g=sum(m.protein_g for m in meals),
        fat_g=sum(m.fat_g for m in meals),
        carbs_g=sum(m.carbs_g for m in meals),
        fiber_g=sum(m.fiber_g for m in meals),
        sugars_g=sum(m.sugars_g for m in meals),
    )
    return {
        "date": day.isoformat(),
        "weight_smoothed_kg": round(weight, 1),
        "kcal_in": round(kcal_in),
        "kcal_out": round(bal.kcal_out),
        "out_source": bal.out_source,
        "estimated": bal.estimated,
        "balance": round(bal.balance),
        "target_deficit_kcal": profile.target_deficit_kcal,
        "remaining_kcal": round(e_target - kcal_in),
        "projected_weekly_change_kg": round(projected_weekly_change_kg(bal.balance), 2),
        "deficit_warning": deficit_warning(profile.target_deficit_kcal, bal.kcal_out),
        "tdee_model": {
            "bmr": round(tdee.bmr),
            "neat": round(tdee.neat),
            "activities": round(tdee.activities),
            "tef": round(tdee.tef),
            "total": round(tdee.total),
        },
        "steps": summary.steps if summary else None,
        "last_sync_ago": humanize_ago(last_sync),
        "macros": macros,
        "target_weight_kg": profile.target_weight_kg,
        "to_goal_kg": (
            round(weight - profile.target_weight_kg, 1)
            if profile.target_weight_kg else None
        ),
        "quip": quips.pick(
            kcal_in, e_target, bal.balance, macros,
            weight_to_goal_kg=(round(weight - profile.target_weight_kg, 1)
                               if profile.target_weight_kg else None),
        ),
        "norms_group_label": (
            {"adult": "dorośli 18–64 lat", "senior": "seniorzy 65+"}.get(
                targets.group_id, targets.group_id
            )
            + ", " + {"M": "mężczyźni", "F": "kobiety"}.get(profile.sex, profile.sex)
            + " · " + targets.lifestyle_label
        ),
        "pending_meals": [
            {
                "id": p.id,
                "time": p.time.isoformat() if p.time else None,
                "label": p.description or (p.note or "zdjęcie"),
                "has_photo": bool(p.photo_path),
            }
            for p in pending
        ],
        "meals": [
            {
                "id": m.id,
                "time": m.time.isoformat() if m.time else None,
                "description": m.description,
                "kcal": m.kcal,
                "kcal_range": [m.kcal_min, m.kcal_max],
                "protein_g": m.protein_g,
                "fat_g": m.fat_g,
                "carbs_g": m.carbs_g,
            }
            for m in meals
        ],
        "activities": [
            {"type": a.type, "duration_s": a.duration_s, "distance_m": a.distance_m,
             "kcal_garmin": a.kcal_garmin}
            for a in activities
        ],
    }


@app.get("/api/day/{day}")
def get_day(day: date, db: Session = Depends(db_session),
            user: User = Depends(auth.current_user)):
    return day_report(db, user.id, day)


# ── Posiłki ───────────────────────────────────────────────────────────────

def _queue_meal(db: Session, user_id: int, day: date, reason: str,
                description: str | None = None, note: str | None = None,
                photo_bytes: bytes | None = None) -> dict:
    meal_queue.enqueue(db, user_id, day, datetime.now().time(), description=description,
                       note=note, photo_bytes=photo_bytes)
    return {
        "queued": True,
        "message": f"Posiłek zapisany do kolejki ({reason}). Zostanie przetworzony "
                   f"automatycznie, gdy LLM będzie dostępny (retencja: 21 dni).",
    }


@app.post("/api/meals/photo")
async def estimate_meal_photo(
    background: BackgroundTasks,
    photo: UploadFile = File(...),
    note: str | None = Form(None),
    day: date | None = Form(None),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """Krok 1: zdjęcie → szacunek (draft do korekty; nic nie zapisujemy).
    Bez klucza LLM / bez internetu: posiłek trafia do kolejki offline."""
    background.add_task(maybe_sync, user.id)
    keys = settings_service.get_llm_keys(db, user.id)
    data = await photo.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Zdjęcie za duże (limit 15 MB)")
    try:
        data = meal_queue.downscale_photo(data)
    except Exception as exc:
        raise HTTPException(422, f"Nie można odczytać zdjęcia: {exc}")
    ext = "jpg"
    target_day = day or date.today()
    if not meal_vision.llm_configured(keys.gemini, keys.anthropic):
        return _queue_meal(db, user.id, target_day, "brak klucza LLM",
                           note=note, photo_bytes=data)
    try:
        estimate = meal_vision.estimate_from_photo(data, ext, note,
                                                    gemini_key=keys.gemini,
                                                    anthropic_key=keys.anthropic)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        return _queue_meal(db, user.id, target_day, "szacowanie nie powiodło się",
                           note=note, photo_bytes=data)
    # zdjęcia nie przechowujemy — po przetworzeniu jest niepotrzebne (decyzja: retencja tylko w kolejce)
    return {"photo_path": None, "kcal": round(estimate.kcal), **estimate.model_dump()}


@app.post("/api/meals/text")
def estimate_meal_text(
    background: BackgroundTasks,
    description: str = Form(...),
    day: date | None = Form(None),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """Krok 1 (wariant tekstowy): opis → szacunek. Fallback: kolejka offline."""
    background.add_task(maybe_sync, user.id)
    keys = settings_service.get_llm_keys(db, user.id)
    target_day = day or date.today()
    if not meal_vision.llm_configured(keys.gemini, keys.anthropic):
        return _queue_meal(db, user.id, target_day, "brak klucza LLM", description=description)
    try:
        estimate = meal_vision.estimate_from_text(description,
                                                   gemini_key=keys.gemini,
                                                   anthropic_key=keys.anthropic)
    except Exception:
        return _queue_meal(db, user.id, target_day, "szacowanie nie powiodło się",
                           description=description)
    return {"photo_path": None, "kcal": round(estimate.kcal), **estimate.model_dump()}


class MealIn(BaseModel):
    date: date
    time: str | None = None
    description: str
    photo_path: str | None = None
    kcal: float
    kcal_min: float | None = None
    kcal_max: float | None = None
    protein_g: float = 0
    fat_g: float = 0
    carbs_g: float = 0
    fiber_g: float = 0
    sugars_g: float = 0
    items: list | None = None
    assumptions: list | None = None
    source: str = "photo"


@app.post("/api/meals")
def save_meal(data: MealIn, background: BackgroundTasks,
              db: Session = Depends(db_session),
              user: User = Depends(auth.current_user)):
    """Krok 2: zapis posiłku (po ewentualnej korekcie użytkownika)."""
    background.add_task(maybe_sync, user.id)
    meal = Meal(
        user_id=user.id,
        date=data.date,
        time=datetime.strptime(data.time, "%H:%M").time() if data.time else datetime.now().time(),
        description=data.description,
        photo_path=data.photo_path,
        kcal=round(data.kcal),
        kcal_min=round(data.kcal_min) if data.kcal_min else None,
        kcal_max=round(data.kcal_max) if data.kcal_max else None,
        protein_g=data.protein_g,
        fat_g=data.fat_g,
        carbs_g=data.carbs_g,
        fiber_g=data.fiber_g,
        sugars_g=data.sugars_g,
        items_json=json.dumps(data.items, ensure_ascii=False) if data.items else None,
        assumptions_json=json.dumps(data.assumptions, ensure_ascii=False) if data.assumptions else None,
        source=data.source,
    )
    db.add(meal)
    db.commit()
    return {"id": meal.id}


@app.delete("/api/meals/{meal_id}")
def delete_meal(meal_id: int, db: Session = Depends(db_session),
                user: User = Depends(auth.current_user)):
    meal = db.get(Meal, meal_id)
    if meal is None or meal.user_id != user.id:
        raise HTTPException(404)
    db.delete(meal)
    db.commit()
    return {"ok": True}


@app.delete("/api/queue/{pending_id}")
def delete_pending(pending_id: int, db: Session = Depends(db_session),
                   user: User = Depends(auth.current_user)):
    """Usunięcie wpisu z kolejki offline (bez przetwarzania przez LLM)."""
    pending = db.get(PendingMeal, pending_id)
    if pending is None or pending.user_id != user.id:
        raise HTTPException(404)
    meal_queue.delete_pending(db, pending)
    return {"ok": True}


# ── Dashboard ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/mobile", response_class=HTMLResponse)
def dashboard(request: Request, background: BackgroundTasks,
              user: User = Depends(auth.current_user)):
    """Jedyny widok aplikacji — responsive, działa na telefonie i desktopie."""
    background.add_task(maybe_sync, user.id)
    return templates.TemplateResponse(
        request,
        "mobile.html",
        {"has_logo": (STATIC_DIR / "logo.png").exists()},
    )


# ── Ustawienia ────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
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
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "garmin_connected": garmin_provider.tokens_present(user.id),
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
            "saved": saved, "mfa": mfa, "error": error,
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


@app.post("/settings/llm")
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
    background.add_task(meal_queue.process_queue, user.id)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/lifestyle")
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
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/goal")
def settings_goal(target_weight_kg: float = Form(...), db: Session = Depends(db_session),
                  user: User = Depends(auth.current_user)):
    """Cel ciężaru — rysowany na trendach, używany w tekstach motywacyjnych."""
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(409, "Najpierw skonfiguruj profil na dashboardzie")
    profile.target_weight_kg = target_weight_kg
    db.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/garmin")
def settings_garmin(email: str = Form(...), password: str = Form(...),
                    user: User = Depends(auth.current_user)):
    """Logowanie do Garmina z ustawień. Hasło idzie tylko do biblioteki Garmina."""
    try:
        result = garmin_provider.interactive_login_start(email.strip(), password, user.id)
    except Exception as exc:
        return RedirectResponse(f"/settings?error={exc.__class__.__name__}", status_code=303)
    if result == "mfa":
        return RedirectResponse("/settings?mfa=1", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.post("/settings/garmin/mfa")
def settings_garmin_mfa(code: str = Form(...), user: User = Depends(auth.current_user)):
    try:
        garmin_provider.interactive_login_mfa(code.strip(), user.id)
    except Exception as exc:
        return RedirectResponse(f"/settings?error={exc.__class__.__name__}", status_code=303)
    return RedirectResponse("/settings?saved=1", status_code=303)


# ── Przenoszenie danych między urządzeniami ───────────────────────────────

@app.get("/api/transfer/export")
def transfer_export(db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    """'Przygotuj dane do przeniesienia na inne urządzenie' — plik JSON do pobrania."""
    payload = transfer.export_payload(db, user.id)
    return Response(
        json.dumps(payload, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition":
                 f'attachment; filename="fit-krasnal-{date.today().isoformat()}.json"'},
    )


@app.post("/api/transfer/import")
async def transfer_import(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    """'Wczytaj dane z innego urządzenia' — scala plik transferu (desktop lub telefon)."""
    try:
        payload = json.loads(await file.read())
        counts = transfer.import_payload(db, user.id, payload)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(422, f"Nieprawidłowy plik transferu: {exc}")
    background.add_task(meal_queue.process_queue, user.id)
    return counts


@app.post("/api/queue/process")
def queue_process(background: BackgroundTasks,
                  user: User = Depends(auth.current_user)):
    background.add_task(meal_queue.process_queue, user.id)
    return {"ok": True}


# ── Trendy ────────────────────────────────────────────────────────────────

TREND_RANGES = [(7, "Tydzień"), (30, "Miesiąc"), (90, "Kwartał"), (180, "Pół roku")]


@app.get("/trends", response_class=HTMLResponse)
def trends(
    request: Request,
    background: BackgroundTasks,
    days: int = 30,
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    background.add_task(maybe_sync, user.id)
    days = max(2, min(days, 366))
    today = date.today()
    start = today - timedelta(days=days - 1)
    profile = db.get(UserProfile, user.id)
    target_weight = profile.target_weight_kg if profile else None

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date >= start)
        ).all()
    ]
    smoothed = []
    all_weights = sorted(
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user.id)).all()
    )
    for d, _ in weights:
        window = [kg for wd, kg in all_weights if 0 <= (d - wd).days < 7]
        if window:
            smoothed.append((d, sum(window) / len(window)))

    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == user.id, DailySummary.date >= start)
    ).all()
    kcal_out = [(s.date, float(s.kcal_total_garmin)) for s in summaries if s.kcal_total_garmin]

    meals = db.scalars(
        select(Meal).where(Meal.user_id == user.id, Meal.date >= start)
    ).all()
    kcal_in_by_day: dict[date, float] = {}
    for m in meals:
        kcal_in_by_day[m.date] = kcal_in_by_day.get(m.date, 0) + m.kcal
    kcal_in = sorted(kcal_in_by_day.items())

    out_by_day = dict(kcal_out)
    balance = [
        (d, kcal - out_by_day[d]) for d, kcal in kcal_in if d in out_by_day
    ]

    weight_series = [
        Series("pomiary", "#8DC63F", weights, dots=True, width=1.5),
        Series("średnia 7 dni", "#1A4D3A", smoothed),
    ]
    if target_weight and weights:
        weight_series.append(
            Series("cel", "#DC3545", [(start, target_weight), (today, target_weight)],
                   dash=True, width=1.5)
        )
    chart_weight = line_chart(weight_series, start, today, y_fmt="{:.1f}")
    chart_energy = line_chart(
        [
            Series("spożyte", "#8DC63F", kcal_in, dots=True),
            Series("spalone (Garmin)", "#3A7A5C", kcal_out, dots=True),
        ],
        start, today,
    )
    chart_balance = bar_chart(balance, start, today)

    period_change = None
    if len(smoothed) >= 2:
        period_change = round(smoothed[-1][1] - smoothed[0][1], 1)
    avg_balance = round(sum(v for _, v in balance) / len(balance)) if balance else None

    return templates.TemplateResponse(
        request,
        "trends.html",
        {
            "days": days,
            "ranges": TREND_RANGES,
            "chart_weight": chart_weight,
            "chart_energy": chart_energy,
            "chart_balance": chart_balance,
            "period_change": period_change,
            "avg_balance": avg_balance,
            "balance_days": len(balance),
            "to_goal_kg": (round(smoothed[-1][1] - target_weight, 1)
                           if target_weight and smoothed else None),
            "today": today.isoformat(),
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


# ── PWA — pliki publiczne (bez auth) ─────────────────────────────────────

@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
def pwa_sw():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})


# ── Ustawienia API (JSON) — dla mobilnego SPA ─────────────────────────────

@app.get("/api/settings")
def api_get_settings(db: Session = Depends(db_session),
                     user: User = Depends(auth.current_user)):
    stored = settings_service.all_settings(db, user.id)
    keys = settings_service.get_llm_keys(db, user.id)
    return {
        "gemini_masked": settings_service.masked(stored.get("gemini_api_key")),
        "anthropic_masked": settings_service.masked(stored.get("anthropic_api_key")),
        "backend": (meal_vision.pick_backend(keys.gemini, keys.anthropic)
                    if meal_vision.llm_configured(keys.gemini, keys.anthropic) else None),
        "garmin_connected": garmin_provider.tokens_present(user.id),
        "lifestyle_options": lifestyle_options(),
    }


class LlmKeysIn(BaseModel):
    gemini_api_key: str = ""
    anthropic_api_key: str = ""


class SavedMealIn(BaseModel):
    name: str
    kcal: float
    kcal_min: float | None = None
    kcal_max: float | None = None
    protein_g: float = 0
    fat_g: float = 0
    carbs_g: float = 0
    fiber_g: float = 0
    sugars_g: float = 0
    items: list | None = None
    assumptions: list | None = None


@app.post("/api/settings/llm")
def api_save_llm(data: LlmKeysIn, background: BackgroundTasks,
                 db: Session = Depends(db_session),
                 user: User = Depends(auth.current_user)):
    if data.gemini_api_key.strip():
        settings_service.set_setting(db, user.id, "gemini_api_key", data.gemini_api_key.strip())
    if data.anthropic_api_key.strip():
        settings_service.set_setting(db, user.id, "anthropic_api_key", data.anthropic_api_key.strip())
    background.add_task(meal_queue.process_queue, user.id)
    return {"ok": True}


# ── Moje posiłki (zapisane szablony) ─────────────────────────────────────

@app.get("/api/saved-meals")
def get_saved_meals(db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    meals = db.scalars(
        select(SavedMeal).where(SavedMeal.user_id == user.id)
        .order_by(SavedMeal.last_used_at.desc())
    ).all()
    return [
        {"id": m.id, "name": m.name, "kcal": m.kcal,
         "kcal_min": m.kcal_min, "kcal_max": m.kcal_max,
         "protein_g": m.protein_g, "fat_g": m.fat_g, "carbs_g": m.carbs_g,
         "fiber_g": m.fiber_g, "sugars_g": m.sugars_g}
        for m in meals
    ]


@app.post("/api/saved-meals", status_code=201)
def create_saved_meal(data: SavedMealIn, db: Session = Depends(db_session),
                      user: User = Depends(auth.current_user)):
    sm = SavedMeal(
        user_id=user.id, name=data.name, kcal=round(data.kcal),
        kcal_min=round(data.kcal_min) if data.kcal_min else None,
        kcal_max=round(data.kcal_max) if data.kcal_max else None,
        protein_g=data.protein_g, fat_g=data.fat_g, carbs_g=data.carbs_g,
        fiber_g=data.fiber_g, sugars_g=data.sugars_g,
        items_json=json.dumps(data.items, ensure_ascii=False) if data.items else None,
        assumptions_json=json.dumps(data.assumptions, ensure_ascii=False) if data.assumptions else None,
    )
    db.add(sm)
    db.commit()
    return {"id": sm.id}


@app.delete("/api/saved-meals/{meal_id}")
def delete_saved_meal(meal_id: int, db: Session = Depends(db_session),
                      user: User = Depends(auth.current_user)):
    sm = db.get(SavedMeal, meal_id)
    if sm is None or sm.user_id != user.id:
        raise HTTPException(404)
    db.delete(sm)
    db.commit()
    return {"ok": True}


@app.post("/api/saved-meals/{meal_id}/use")
def use_saved_meal(meal_id: int, db: Session = Depends(db_session),
                   user: User = Depends(auth.current_user)):
    sm = db.get(SavedMeal, meal_id)
    if sm is None or sm.user_id != user.id:
        raise HTTPException(404)
    sm.last_used_at = datetime.utcnow()
    db.commit()
    return {
        "description": sm.name,
        "kcal": sm.kcal, "kcal_min": sm.kcal_min, "kcal_max": sm.kcal_max,
        "protein_g": sm.protein_g, "fat_g": sm.fat_g, "carbs_g": sm.carbs_g,
        "fiber_g": sm.fiber_g, "sugars_g": sm.sugars_g,
        "items": json.loads(sm.items_json) if sm.items_json else [],
        "assumptions": json.loads(sm.assumptions_json) if sm.assumptions_json else [],
    }


# ── Trendy API (JSON + SVG) — dla mobilnego SPA ───────────────────────────

@app.get("/api/trends")
def api_trends_data(days: int = 30, db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    days = max(2, min(days, 366))
    today = date.today()
    start = today - timedelta(days=days - 1)
    profile = db.get(UserProfile, user.id)
    target_weight = profile.target_weight_kg if profile else None

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date >= start)
        ).all()
    ]
    all_weights = sorted(
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user.id)).all()
    )
    smoothed = []
    for d, _ in weights:
        window = [kg for wd, kg in all_weights if 0 <= (d - wd).days < 7]
        if window:
            smoothed.append((d, sum(window) / len(window)))

    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == user.id, DailySummary.date >= start)
    ).all()
    kcal_out = [(s.date, float(s.kcal_total_garmin)) for s in summaries if s.kcal_total_garmin]

    meals = db.scalars(
        select(Meal).where(Meal.user_id == user.id, Meal.date >= start)
    ).all()
    kcal_in_by_day: dict[date, float] = {}
    for m in meals:
        kcal_in_by_day[m.date] = kcal_in_by_day.get(m.date, 0) + m.kcal
    kcal_in = sorted(kcal_in_by_day.items())

    out_by_day = dict(kcal_out)
    balance = [(d, kcal - out_by_day[d]) for d, kcal in kcal_in if d in out_by_day]

    weight_series = [
        Series("pomiary", "#8DC63F", weights, dots=True, width=1.5),
        Series("średnia 7 dni", "#1A4D3A", smoothed),
    ]
    if target_weight and weights:
        weight_series.append(
            Series("cel", "#DC3545", [(start, target_weight), (today, target_weight)],
                   dash=True, width=1.5)
        )

    period_change = None
    if len(smoothed) >= 2:
        period_change = round(smoothed[-1][1] - smoothed[0][1], 1)
    avg_balance = round(sum(v for _, v in balance) / len(balance)) if balance else None

    return {
        "days": days,
        "ranges": [{"days": d, "label": l} for d, l in TREND_RANGES],
        "chart_weight": line_chart(weight_series, start, today, y_fmt="{:.1f}"),
        "chart_energy": line_chart(
            [Series("spożyte", "#8DC63F", kcal_in, dots=True),
             Series("spalone (Garmin)", "#3A7A5C", kcal_out, dots=True)],
            start, today,
        ),
        "chart_balance": bar_chart(balance, start, today),
        "period_change": period_change,
        "avg_balance": avg_balance,
        "balance_days": len(balance),
        "to_goal_kg": (round(smoothed[-1][1] - target_weight, 1)
                       if target_weight and smoothed else None),
    }


@app.post("/profile-form")
def profile_form(
    birth_date: date = Form(...),
    sex: str = Form(...),
    height_cm: float = Form(...),
    target_deficit_kcal: int = Form(500),
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    put_profile(
        ProfileIn(birth_date=birth_date, sex=sex, height_cm=height_cm,
                  target_deficit_kcal=target_deficit_kcal),
        db,
        user,
    )
    return RedirectResponse("/", status_code=303)

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
                     Query, Request, UploadFile)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import MAX_PHOTO_BYTES, PHOTOS_DIR, ensure_dirs
from .db import get_session, init_db
from .models import Activity, DailySummary, Meal, User, UserProfile, WeightLog
from .providers.garmin import GarminNotLoggedIn, GarminProvider
from .services import meal_vision
from .services.balance import day_balance, deficit_warning, projected_weekly_change_kg
from .services.charts import Series, bar_chart, line_chart
from .services.energy import age_years, smoothed_weight, tdee_theoretical
from .services.macros import coverage, who_targets
from .services.sync import mark_attempt, maybe_sync, sync_range

app = FastAPI(title="Fit Krasnal")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

LOCAL_USER_EMAIL = "local@fit-krasnal"


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    init_db()


def db_session():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def local_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(email=LOCAL_USER_EMAIL)
        db.add(user)
        db.commit()
    return user


# ── Profil ────────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    birth_date: date
    sex: str  # 'M' | 'F'
    height_cm: float
    target_deficit_kcal: int = 500
    tz: str = "Europe/Warsaw"


@app.get("/api/profile")
def get_profile(db: Session = Depends(db_session)):
    user = local_user(db)
    profile = db.get(UserProfile, user.id)
    if profile is None:
        raise HTTPException(404, "Profil nie jest jeszcze skonfigurowany")
    return profile


@app.put("/api/profile")
def put_profile(data: ProfileIn, db: Session = Depends(db_session)):
    if data.sex.upper() not in ("M", "F"):
        raise HTTPException(422, "sex musi być 'M' lub 'F'")
    user = local_user(db)
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id, birth_date=data.birth_date,
                              sex=data.sex.upper(), height_cm=data.height_cm)
        db.add(profile)
    profile.birth_date = data.birth_date
    profile.sex = data.sex.upper()
    profile.height_cm = data.height_cm
    profile.target_deficit_kcal = data.target_deficit_kcal
    profile.tz = data.tz
    db.commit()
    return {"ok": True}


# ── Synchronizacja Garmin ─────────────────────────────────────────────────

@app.post("/api/sync")
def sync(days: int = 7, db: Session = Depends(db_session)):
    """Ręczna synchronizacja — bez throttla, synchronicznie, zwraca liczniki."""
    user = local_user(db)
    mark_attempt(user.id)
    try:
        return sync_range(db, GarminProvider(), user.id, days=days)
    except GarminNotLoggedIn as exc:
        raise HTTPException(409, str(exc))


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
        select(Meal).where(Meal.user_id == user_id, Meal.date == day).order_by(Meal.time)
    ).all()

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
                          age=age_years(profile.birth_date, day))
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
        "macros": macros,
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
def get_day(day: date, db: Session = Depends(db_session)):
    user = local_user(db)
    return day_report(db, user.id, day)


# ── Posiłki ───────────────────────────────────────────────────────────────

@app.post("/api/meals/photo")
async def estimate_meal_photo(
    background: BackgroundTasks,
    photo: UploadFile = File(...),
    note: str | None = Form(None),
    db: Session = Depends(db_session),
):
    """Krok 1: zdjęcie → szacunek (draft do korekty; nic nie zapisujemy)."""
    background.add_task(maybe_sync, local_user(db).id)
    data = await photo.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Zdjęcie za duże (limit 15 MB)")
    ext = (photo.filename or "jpg").rsplit(".", 1)[-1]
    try:
        estimate = meal_vision.estimate_from_photo(data, ext, note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except meal_vision.MealVisionNotConfigured as exc:
        raise HTTPException(503, str(exc))
    photo_name = f"{datetime.now():%Y%m%d_%H%M%S}.{ext.lower()}"
    (PHOTOS_DIR / photo_name).write_bytes(data)
    return {"photo_path": photo_name, "kcal": round(estimate.kcal), **estimate.model_dump()}


@app.post("/api/meals/text")
def estimate_meal_text(
    background: BackgroundTasks,
    description: str = Form(...),
    db: Session = Depends(db_session),
):
    """Krok 1 (wariant tekstowy): opis → szacunek."""
    background.add_task(maybe_sync, local_user(db).id)
    try:
        estimate = meal_vision.estimate_from_text(description)
    except meal_vision.MealVisionNotConfigured as exc:
        raise HTTPException(503, str(exc))
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
def save_meal(data: MealIn, background: BackgroundTasks, db: Session = Depends(db_session)):
    """Krok 2: zapis posiłku (po ewentualnej korekcie użytkownika)."""
    user = local_user(db)
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
def delete_meal(meal_id: int, db: Session = Depends(db_session)):
    user = local_user(db)
    meal = db.get(Meal, meal_id)
    if meal is None or meal.user_id != user.id:
        raise HTTPException(404)
    db.delete(meal)
    db.commit()
    return {"ok": True}


# ── Dashboard (server-rendered) ───────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    background: BackgroundTasks,
    view: date | None = Query(None, alias="date"),
    db: Session = Depends(db_session),
):
    user = local_user(db)
    background.add_task(maybe_sync, user.id)  # auto-odświeżenie przy wejściu (throttle 10 min)
    view_day = min(view or date.today(), date.today())
    profile = db.get(UserProfile, user.id)
    report = None
    error = None
    if profile is not None:
        try:
            report = day_report(db, user.id, view_day)
        except HTTPException as exc:
            error = exc.detail
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "profile": profile,
            "report": report,
            "error": error,
            "today": date.today().isoformat(),
            "view_date": view_day.isoformat(),
            "is_today": view_day == date.today(),
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


# ── Trendy ────────────────────────────────────────────────────────────────

TREND_RANGES = [(7, "Tydzień"), (30, "Miesiąc"), (90, "Kwartał"), (180, "Pół roku")]


@app.get("/trends", response_class=HTMLResponse)
def trends(
    request: Request,
    background: BackgroundTasks,
    days: int = 30,
    db: Session = Depends(db_session),
):
    user = local_user(db)
    background.add_task(maybe_sync, user.id)
    days = max(2, min(days, 366))
    today = date.today()
    start = today - timedelta(days=days - 1)

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

    chart_weight = line_chart(
        [
            Series("pomiary", "#8DC63F", weights, dots=True, width=1.5),
            Series("średnia 7 dni", "#1A4D3A", smoothed),
        ],
        start, today, y_fmt="{:.1f}",
    )
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
            "today": today.isoformat(),
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


@app.post("/profile-form")
def profile_form(
    birth_date: date = Form(...),
    sex: str = Form(...),
    height_cm: float = Form(...),
    target_deficit_kcal: int = Form(500),
    db: Session = Depends(db_session),
):
    put_profile(
        ProfileIn(birth_date=birth_date, sex=sex, height_cm=height_cm,
                  target_deficit_kcal=target_deficit_kcal),
        db,
    )
    return RedirectResponse("/", status_code=303)

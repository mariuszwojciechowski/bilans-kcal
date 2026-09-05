"""Ręczny wpis wagi/kroków, raport dnia (bilans kcal), ręczna aktywność fizyczna.

Sam raport dnia liczy `services.day.day_report` — router zajmuje się
telemetrią i zamianą braku danych wejściowych na 409.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..models import Activity, DailySummary, User, UserProfile, WeightLog
from ..services import day as day_service
from ..services import usage as usage_service
from ..services.clock import user_today
from ..services.energy import manual_activity_kcal, smoothed_weight

router = APIRouter()


# ── Ręczny wpis wagi i kroków (dla mobile, bez Garmina) ──────────────────

class WeightIn(BaseModel):
    date: date
    weight_kg: float


@router.post("/api/weight")
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
    usage_service.bump(db, user.id, "weight_manual")
    return {"ok": True}


class StepsIn(BaseModel):
    steps: int


@router.post("/api/day/{day}/steps")
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
    usage_service.bump(db, user.id, "steps_set")
    return {"ok": True}


# ── Raport dzienny ────────────────────────────────────────────────────────

@router.get("/api/day/{day}")
def get_day(day: date, db: Session = Depends(db_session),
            user: User = Depends(auth.current_user)):
    usage_service.bump(db, user.id, "day_view")
    try:
        return day_service.day_report(db, user.id, day)
    except day_service.DayReportUnavailable as exc:
        # Brak profilu albo pomiarów wagi to nie błąd serwera — klient ma
        # najpierw dokończyć konfigurację (ten sam kod i komunikat co wcześniej).
        raise HTTPException(409, str(exc)) from exc


# ── Aktywność fizyczna (ręczny wpis) ───────────────────────────────────────

class ActivityIn(BaseModel):
    type: str  # running, cycling, walking, swimming, strength_training
    intensity: str  # lekka, umiarkowana, intensywna
    duration_min: int  # zostaje dla kompatybilności — duration_s ma pierwszeństwo, gdy podane
    duration_s: int | None = None
    distance_km: float | None = None
    day: date | None = None


@router.post("/api/activities")
def add_manual_activity(data: ActivityIn, db: Session = Depends(db_session),
                        user: User = Depends(auth.current_user)):
    """Zapisz ręcznie logowaną aktywność."""
    day = data.day or user_today(db.get(UserProfile, user.id))
    duration_s = data.duration_s if data.duration_s is not None else data.duration_min * 60
    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user.id)).all()
    ]
    weight_kg = smoothed_weight(weights)
    if weight_kg is None:
        raise HTTPException(409, "Brak pomiarów wagi w bazie")

    kcal, explanation = manual_activity_kcal(
        data.type, data.intensity, duration_s,
        data.distance_km * 1000 if data.distance_km else None, weight_kg
    )

    activity = Activity(
        user_id=user.id,
        date=day,
        type=data.type,
        duration_s=duration_s,
        distance_m=data.distance_km * 1000 if data.distance_km else None,
        garmin_id="manual-" + uuid.uuid4().hex,
        kcal_garmin=round(kcal),
        source="manual"
    )
    db.add(activity)
    db.commit()
    usage_service.bump(db, user.id, "activity_add")
    return {
        "id": activity.id,
        "kcal": round(kcal),
        "explanation": explanation,
    }


@router.delete("/api/activities/{activity_id}")
def delete_manual_activity(activity_id: int, db: Session = Depends(db_session),
                          user: User = Depends(auth.current_user)):
    """Usuń ręcznie logowaną aktywność (tylko manualne)."""
    activity = db.get(Activity, activity_id)
    if activity is None or activity.user_id != user.id:
        raise HTTPException(404)
    if activity.source != "manual":
        raise HTTPException(404, "Można usuwać tylko ręcznie dodane aktywności")
    db.delete(activity)
    db.commit()
    usage_service.bump(db, user.id, "activity_delete")
    return {"ok": True}

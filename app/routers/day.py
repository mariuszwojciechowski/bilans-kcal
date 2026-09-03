"""Ręczny wpis wagi/kroków, raport dnia (bilans kcal), ręczna aktywność fizyczna."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..deps import humanize_ago
from ..models import Activity, DailySummary, Meal, PendingMeal, User, UserProfile, WeightLog
from ..providers import garmin as garmin_provider
from ..services import quips
from ..services import usage as usage_service
from ..services.balance import day_balance, deficit_warning, projected_weekly_change_kg
from ..services.energy import (DEFAULT_STEPS, age_from_year, manual_activity_kcal,
                               smoothed_weight, tdee_theoretical)
from ..services.macros import coverage, who_targets

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

    steps = summary.steps if summary and summary.steps else DEFAULT_STEPS
    activities_for_tdee = []
    for a in activities:
        act_dict = {"type": a.type, "duration_s": a.duration_s, "distance_m": a.distance_m}
        if a.source == "manual" and a.kcal_garmin:
            act_dict["kcal"] = a.kcal_garmin
        activities_for_tdee.append(act_dict)

    def _est_steps(a: Activity) -> int:
        """Szacunek kroków biegu/marszu z dystansu (~1400 kroków/km), jak w tdee_theoretical."""
        if a.distance_m and ("running" in a.type.lower() or "walking" in a.type.lower()):
            return round(a.distance_m / 1000.0 * 1400)
        return 0

    manual_kcal = sum(a.kcal_garmin or 0 for a in activities if a.source == "manual")
    activities_kcal = sum(a.kcal_garmin or 0 for a in activities)
    # Kroki Garmina z biegów/marszów już policzone przez zegarek — nie dublujemy; kroki
    # ręcznych biegów/marszów Garmin nie widział, więc dopisujemy je do wyświetlanej liczby.
    garmin_activity_steps = sum(_est_steps(a) for a in activities if a.source != "manual")
    manual_activity_steps = sum(_est_steps(a) for a in activities if a.source == "manual")
    steps_effective = max(steps - garmin_activity_steps, 0) + manual_activity_steps

    tdee = tdee_theoretical(
        weight_kg=weight,
        height_cm=profile.height_cm,
        age=age_from_year(profile.birth_year, day),
        sex=profile.sex,
        steps=steps,
        activities=activities_for_tdee,
        kcal_in=kcal_in,
    )
    bal = day_balance(
        kcal_in=kcal_in,
        garmin_total=(summary.kcal_total_garmin if summary else None),
        model_tdee=tdee.total,
        day_complete=bool(summary and summary.complete),
        manual_kcal=manual_kcal,
    )
    steps_kcal = max(bal.kcal_out - tdee.bmr - activities_kcal - tdee.tef, 0)
    out_breakdown = {
        "bmr": round(tdee.bmr),
        "steps_kcal": round(steps_kcal),
        "steps_count": steps_effective,
        "activities_kcal": round(activities_kcal),
        "tef": round(tdee.tef),
        "total": round(bal.kcal_out),
    }
    e_target = bal.kcal_out - profile.target_deficit_kcal
    targets = who_targets(e_target, weight, sex=profile.sex,
                          age=age_from_year(profile.birth_year, day),
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
        "out_breakdown": out_breakdown,
        "steps": steps,
        "steps_default": not (summary and summary.steps is not None),
        "garmin_connected": garmin_provider.tokens_present(db, user_id),
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
            {
                "id": a.id, "type": a.type, "duration_s": a.duration_s, "distance_m": a.distance_m,
                "kcal_garmin": a.kcal_garmin, "source": a.source,
                **({"est_steps": _est_steps(a)} if a.source == "manual" and _est_steps(a) else {}),
            }
            for a in activities
        ],
    }


@router.get("/api/day/{day}")
def get_day(day: date, db: Session = Depends(db_session),
            user: User = Depends(auth.current_user)):
    usage_service.bump(db, user.id, "day_view")
    return day_report(db, user.id, day)


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
    day = data.day or date.today()
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

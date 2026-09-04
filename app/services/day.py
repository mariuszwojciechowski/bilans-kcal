"""Raport dnia (M5): spożycie kontra wydatek, model teoretyczny, makro, posiłki.

Wyniesione z routera (`app/routers/day.py`), bo to jedyne miejsce, w które ma
wejść współczynnik kalibracji adaptacyjnej (WYMAGANIA.md 6.2 — patrz plan
w TODO.md). Router zostaje cienki: telemetria, mapowanie błędu na HTTP.

Warstwa serwisów jest wolna od FastAPI, dlatego brak danych wejściowych
zgłaszamy `DayReportUnavailable`, a nie `HTTPException` — router zamienia to
na 409 z tym samym komunikatem, jaki był wcześniej.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Activity, DailySummary, Meal, PendingMeal, UserProfile, WeightLog
from ..providers import garmin as garmin_provider
from . import quips
from .balance import day_balance, deficit_warning, projected_weekly_change_kg
from .energy import DEFAULT_STEPS, age_from_year, smoothed_weight, tdee_theoretical
from .macros import coverage, who_targets
from .timeago import humanize_ago

# Przybliżenie kroków w biegu/marszu — ta sama stała, z której korzysta
# `tdee_theoretical` (patrz punkt „Tabela MET jako dane" w TODO.md).
STEPS_PER_KM = 1400


class DayReportUnavailable(RuntimeError):
    """Raportu nie da się policzyć: brak profilu albo brak pomiarów wagi."""


def _est_steps(activity: Activity) -> int:
    """Szacunek kroków biegu/marszu z dystansu, jak w `tdee_theoretical`."""
    if activity.distance_m and (
        "running" in activity.type.lower() or "walking" in activity.type.lower()
    ):
        return round(activity.distance_m / 1000.0 * STEPS_PER_KM)
    return 0


def day_report(db: Session, user_id: int, day: date) -> dict:
    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise DayReportUnavailable("Najpierw skonfiguruj profil (PUT /api/profile)")

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user_id)).all()
    ]
    weight = smoothed_weight(weights)
    if weight is None:
        raise DayReportUnavailable(
            "Brak pomiarów wagi — zsynchronizuj Garmina (POST /api/sync)")
    weight_last_kg = round(max(weights, key=lambda w: w[0])[1], 1)

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
    to_goal_kg = (
        round(weight - profile.target_weight_kg, 1) if profile.target_weight_kg else None
    )
    return {
        "date": day.isoformat(),
        "weight_smoothed_kg": round(weight, 1),
        "weight_last_kg": weight_last_kg,
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
        "to_goal_kg": to_goal_kg,
        "quip": quips.pick(kcal_in, e_target, bal.balance, macros,
                           weight_to_goal_kg=to_goal_kg),
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

"""Synchronizacja danych z providera (Garmin) do lokalnej bazy — upsert idempotentny."""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, DailySummary, WeightLog
from ..providers import DataProvider


def sync_range(db: Session, provider: DataProvider, user_id: int, days: int = 7) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)

    synced_days = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        summary = provider.get_daily_summary(day)
        row = db.scalar(
            select(DailySummary).where(DailySummary.user_id == user_id, DailySummary.date == day)
        )
        if row is None:
            row = DailySummary(user_id=user_id, date=day)
            db.add(row)
        row.kcal_total_garmin = summary.kcal_total
        row.kcal_active_garmin = summary.kcal_active
        row.kcal_bmr_garmin = summary.kcal_bmr
        row.steps = summary.steps
        row.sync_ts = datetime.utcnow()
        # dzień zamknięty = pierwsza synchronizacja po jego zakończeniu
        row.complete = day < today
        synced_days += 1

    weights = provider.get_weights(start, today)
    for w in weights:
        row = db.scalar(
            select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.date == w.date)
        )
        if row is None:
            db.add(WeightLog(user_id=user_id, date=w.date, weight_kg=w.weight_kg))
        else:
            row.weight_kg = w.weight_kg

    activities = provider.get_activities(start, today)
    for a in activities:
        row = db.scalar(
            select(Activity).where(Activity.user_id == user_id, Activity.garmin_id == a.garmin_id)
        )
        if row is None:
            row = Activity(user_id=user_id, garmin_id=a.garmin_id, date=a.date, type=a.type,
                           duration_s=a.duration_s)
            db.add(row)
        row.date = a.date
        row.type = a.type
        row.duration_s = a.duration_s
        row.distance_m = a.distance_m
        row.kcal_garmin = a.kcal
        row.avg_hr = a.avg_hr

    db.commit()
    return {"days": synced_days, "weights": len(weights), "activities": len(activities)}

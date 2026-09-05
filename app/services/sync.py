"""Synchronizacja danych z providera (Garmin) do lokalnej bazy — upsert idempotentny.

`maybe_sync` — wariant z throttlem do automatycznych odświeżeń (refresh strony,
szacowanie/zapis posiłku): synchronizuje najwyżej raz na SYNC_MIN_INTERVAL_S,
żeby nie hammerować nieoficjalnego API Garmina (znane limity 429). Czas ostatniej
PRÓBY (także nieudanej) trzymany w pamięci procesu."""

import logging
import threading
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, DailySummary, WeightLog
from ..providers import DataProvider
from . import crypto

logger = logging.getLogger(__name__)

SYNC_MIN_INTERVAL_S = 600  # 10 minut

_last_attempt: dict[int, datetime] = {}
_lock = threading.Lock()


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

    # wagę pobieramy z szerszego okna — pomiary bywają rzadsze niż codzienne
    weights = provider.get_weights(today - timedelta(days=60), today)
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
        row.kcal_bmr_garmin = a.kcal_bmr
        row.steps = a.steps

    db.commit()
    return {"days": synced_days, "weights": len(weights), "activities": len(activities)}


def mark_attempt(user_id: int) -> None:
    _last_attempt[user_id] = datetime.utcnow()


def sync_is_due(user_id: int, min_interval_s: int = SYNC_MIN_INTERVAL_S) -> bool:
    last = _last_attempt.get(user_id)
    return last is None or (datetime.utcnow() - last).total_seconds() >= min_interval_s


def maybe_sync(user_id: int, days: int = 7, force: bool = False) -> None:
    """Synchronizacja z throttlem, do wywołań automatycznych (również w tle).
    Otwiera własną sesję DB. Błędy loguje zamiast rzucać — automatyczne
    odświeżenie nie może wywracać akcji użytkownika."""
    with _lock:
        if not force and not sync_is_due(user_id):
            return
        _last_attempt[user_id] = datetime.utcnow()  # liczy się próba, nie sukces

    from ..db import get_session
    from ..providers.garmin import GarminProvider

    db = get_session()
    try:
        result = sync_range(db, GarminProvider(user_id, db), user_id, days=days)
        logger.info("Auto-sync Garmin: %s", result)
    except Exception as exc:
        logger.warning("Auto-sync Garmin nieudany: %s", crypto.scrub(str(exc)))
    finally:
        db.close()

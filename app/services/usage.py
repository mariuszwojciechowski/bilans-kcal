"""Telemetria własnej aplikacji (plan „Statystyki użycia" w TODO.md).

Liczniki dzienne, nie log zdarzeń: jeden wiersz = (pseudonim, dzień,
zdarzenie, licznik). Bez znaczników czasu co do sekundy i bez kolejności
klików — z surowego logu dałoby się odtworzyć czyjś dzień, z liczników nie.
Pseudonim jest stabilnym skrótem z user_id (HMAC), nie da się z niego wprost
odtworzyć konta bez dostępu do bazy i soli."""

import hashlib
import hmac
import logging
import statistics
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import DEBUG, SECRET_KEY, USAGE_SALT
from ..models import User, UsageDaily

logger = logging.getLogger(__name__)

_HMAC_SALT_FALLBACK = b"fit-krasnal-usage-v1"

# Zamknięta lista nazw zdarzeń — nieznana nazwa jest odrzucana (422 na
# POST /api/usage). Nazwa nigdy nie niesie treści (opisów, wartości pól).
EVENTS: set[str] = {
    "meal_photo", "meal_text",
    "meal_save_photo", "meal_save_text", "meal_save_manual", "meal_save_saved",
    "meal_delete",
    "saved_meal_create", "saved_meal_use",
    "activity_add", "activity_delete",
    "steps_set", "weight_manual",
    "sync_manual",
    "queue_process", "queue_delete",
    "transfer_export", "transfer_import",
    "llm_key_save",
    "garmin_connect_ok", "garmin_mfa",
    "profile_save", "goal_save", "lifestyle_save",
    "trends_view", "trends_7", "trends_30", "trends_90", "trends_180",
    "login",
    "day_view",
    "tab_today", "tab_add", "tab_activities", "tab_trends", "tab_settings",
    "manual_open", "saved_meals_open", "photo_pick",
}

MEAL_SAVE_EVENTS = {"meal_save_photo", "meal_save_text", "meal_save_manual", "meal_save_saved"}


def _salt() -> bytes:
    if USAGE_SALT:
        return USAGE_SALT.encode() if isinstance(USAGE_SALT, str) else USAGE_SALT
    if DEBUG:
        return hashlib.sha256(SECRET_KEY.encode() + _HMAC_SALT_FALLBACK).digest()
    raise RuntimeError(
        "FIT_KRASNAL_USAGE_SALT nie jest ustawiony, a FIT_KRASNAL_DEBUG nie jest "
        "włączone — proces nie może bezpiecznie pseudonimizować statystyk. Ustaw "
        "FIT_KRASNAL_USAGE_SALT w /etc/fit-krasnal/env."
    )


def user_ref(user_id: int) -> str:
    """Stabilny pseudonim: HMAC-SHA256(sól, user_id), obcięty do 12 hex."""
    digest = hmac.new(_salt(), str(user_id).encode(), hashlib.sha256).hexdigest()
    return digest[:12]


def bump(db: Session, user_id: int, event: str, day: date | None = None) -> None:
    """Podbija licznik o 1. Nigdy nie może wywrócić requestu użytkownika —
    błąd (np. brak soli na produkcji przez zły deploy) trafia do logów, nie
    do klienta."""
    try:
        if event not in EVENTS:
            logger.warning("usage.bump: nieznane zdarzenie %r", event)
            return
        ref = user_ref(user_id)
        d = day or date.today()
        row = db.scalar(
            select(UsageDaily).where(
                UsageDaily.user_ref == ref, UsageDaily.date == d, UsageDaily.event == event
            )
        )
        if row is None:
            db.add(UsageDaily(user_ref=ref, date=d, event=event, count=1))
        else:
            row.count += 1
        db.commit()
    except Exception:
        logger.warning("usage.bump nie powiodło się (event=%s)", event, exc_info=True)


def purge_old(db: Session, keep_days: int = 180) -> int:
    """Kasuje liczniki starsze niż keep_days. Zwraca liczbę usuniętych wierszy."""
    cutoff = date.today() - timedelta(days=keep_days)
    result = db.execute(delete(UsageDaily).where(UsageDaily.date < cutoff))
    db.commit()
    return result.rowcount or 0


def dashboard_stats(db: Session, weeks: int = 12) -> dict:
    """Agregaty dla widoku /usage. Operuje wyłącznie na pseudonimach — konta
    (User) są dotykane tylko po to, żeby policzyć ich pseudonim i sprawdzić,
    czy dane zdarzenie dla niego wystąpiło (lejek wejścia); e-mail nigdy nie
    trafia do wyniku."""
    from .charts import bar_chart

    today = date.today()
    since_7 = today - timedelta(days=6)
    since_30 = today - timedelta(days=29)

    rows = db.execute(
        select(UsageDaily.user_ref, UsageDaily.date, UsageDaily.event, UsageDaily.count)
    ).all()

    by_ref: dict[str, list[tuple[date, str, int]]] = {}
    for ref, d, event, count in rows:
        by_ref.setdefault(ref, []).append((d, event, count))

    active_7 = sum(1 for items in by_ref.values() if any(d >= since_7 for d, _, _ in items))
    active_30 = sum(1 for items in by_ref.values() if any(d >= since_30 for d, _, _ in items))

    days_per_user = [len({d for d, _, _ in items}) for items in by_ref.values()]
    median_days = round(statistics.median(days_per_user), 1) if days_per_user else 0

    meal_days_per_user = [
        len({d for d, event, _ in items if event in MEAL_SAVE_EVENTS})
        for items in by_ref.values()
    ]
    adopted_7d = sum(1 for n in meal_days_per_user if n >= 7)

    total_accounts = db.scalar(select(func.count(User.id))) or 0

    funnel = {"accounts": total_accounts, "profile": 0, "llm_key": 0,
              "garmin": 0, "first_meal": 0, "returned_week2": 0}
    for u in db.scalars(select(User)).all():
        items = by_ref.get(user_ref(u.id), [])
        events = {event for _, event, _ in items}
        dates = sorted({d for d, _, _ in items})
        if "profile_save" in events:
            funnel["profile"] += 1
        if "llm_key_save" in events:
            funnel["llm_key"] += 1
        if "garmin_connect_ok" in events:
            funnel["garmin"] += 1
        if events & MEAL_SAVE_EVENTS:
            funnel["first_meal"] += 1
        if dates and (dates[-1] - dates[0]).days >= 7:
            funnel["returned_week2"] += 1

    totals: dict[str, dict] = {}
    for ref, _, event, count in rows:
        t = totals.setdefault(event, {"sum": 0, "users": set()})
        t["sum"] += count
        t["users"].add(ref)
    top_events = sorted(
        ({"event": e, "sum": v["sum"], "users": len(v["users"])} for e, v in totals.items()),
        key=lambda x: -x["sum"],
    )

    week_start = today - timedelta(days=today.weekday())  # poniedziałek bieżącego tygodnia
    chart_start = week_start - timedelta(weeks=weeks - 1)
    active_points, events_points = [], []
    for i in range(weeks - 1, -1, -1):
        w0 = week_start - timedelta(weeks=i)
        w1 = w0 + timedelta(days=6)
        active_refs = {ref for ref, d, _, _ in rows if w0 <= d <= w1}
        total_events = sum(count for _, d, _, count in rows if w0 <= d <= w1)
        active_points.append((w0, float(len(active_refs))))
        events_points.append((w0, float(total_events)))
    chart_weekly_active = bar_chart(active_points, chart_start, today,
                                    color_pos="#3A7A5C", color_neg="#3A7A5C")
    chart_weekly_events = bar_chart(events_points, chart_start, today,
                                    color_pos="#8DC63F", color_neg="#8DC63F")

    last_activity = sorted(
        (
            {"ref": ref, "last_date": max(d for d, _, _ in items),
             "days": len({d for d, _, _ in items})}
            for ref, items in by_ref.items()
        ),
        key=lambda x: x["last_date"], reverse=True,
    )

    return {
        "total_accounts": total_accounts,
        "active_7": active_7,
        "active_30": active_30,
        "median_days_active": median_days,
        "adopted_7d": adopted_7d,
        "funnel": funnel,
        "top_events": top_events,
        "chart_weekly_active": chart_weekly_active,
        "chart_weekly_events": chart_weekly_events,
        "last_activity": last_activity,
    }

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

from ..config import ADMIN_EMAIL, DEBUG, SECRET_KEY, USAGE_SALT
from ..models import (
    Activity, AppSetting, CalibrationLog, CalibrationState, DailySummary, Meal, User, UsageDaily,
    UserProfile,
)
from ..providers.garmin import GARMIN_TOKENS_KEY

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
    "calibration_step", "calibration_reset", "calibration_error",
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


def _allowed_ids_and_refs(db: Session, scope: str, admin: User | None) -> tuple[set[int], set[str]]:
    """Buduje jeden zbiór `user_id` i jeden zbiór pseudonimów dozwolonych w
    danym zakresie — jedyne miejsce, które zna semantykę `others`/`all`/`me`;
    wszystkie filtry niżej mają iść przez te dwa zbiory, nie przez osobne
    porównania z `ADMIN_EMAIL`."""
    if scope == "me":
        allowed_ids = {admin.id} if admin else set()
    else:
        all_ids = set(db.scalars(select(User.id)).all())
        if scope == "all":
            allowed_ids = all_ids
        else:  # "others" (domyślny)
            allowed_ids = all_ids - ({admin.id} if admin else set())
    allowed_refs = {user_ref(uid) for uid in allowed_ids}
    return allowed_ids, allowed_refs


def dashboard_stats(db: Session, weeks: int = 12, scope: str = "others") -> dict:
    """Agregaty dla widoku /usage. Operuje wyłącznie na pseudonimach — konta
    (User) są dotykane tylko po to, żeby policzyć ich pseudonim i sprawdzić,
    czy dane zdarzenie dla niego wystąpiło (lejek wejścia); e-mail nigdy nie
    trafia do wyniku. `scope` wybiera, kto wchodzi do agregatów — patrz
    TODO.md „Zakres statystyk /usage"."""
    from .charts import bar_chart

    today = date.today()
    since_7 = today - timedelta(days=6)
    since_30 = today - timedelta(days=29)

    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    admin_ref = user_ref(admin.id) if admin else None
    allowed_ids, allowed_refs = _allowed_ids_and_refs(db, scope, admin)

    rows = [
        r for r in db.execute(
            select(UsageDaily.user_ref, UsageDaily.date, UsageDaily.event, UsageDaily.count)
        ).all()
        if r[0] in allowed_refs
    ]

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

    total_accounts = len(allowed_ids)

    # Lejek liczony z realnych danych (profil/klucz LLM/Garmin/posiłki), nie z
    # telemetrii — telemetria działa tylko od dnia wdrożenia i zaniżałaby
    # konta założone wcześniej.
    with_profile = db.scalar(
        select(func.count()).select_from(UserProfile)
        .where(UserProfile.user_id.in_(allowed_ids))
    ) or 0
    with_llm_key = db.scalar(
        select(func.count(func.distinct(AppSetting.user_id)))
        .where(AppSetting.key.in_(("gemini_api_key", "anthropic_api_key")),
               AppSetting.user_id.in_(allowed_ids))
    ) or 0
    with_garmin = db.scalar(
        select(func.count(func.distinct(AppSetting.user_id)))
        .where(AppSetting.key == GARMIN_TOKENS_KEY,
               AppSetting.user_id.in_(allowed_ids))
    ) or 0
    with_meal = db.scalar(
        select(func.count(func.distinct(Meal.user_id)))
        .where(Meal.user_id.in_(allowed_ids))
    ) or 0
    meal_span = db.execute(
        select(Meal.user_id, func.min(Meal.date), func.max(Meal.date))
        .where(Meal.user_id.in_(allowed_ids))
        .group_by(Meal.user_id)
    ).all()
    returned_week2 = sum(1 for _, d0, d1 in meal_span if (d1 - d0).days >= 7)

    funnel = {"accounts": total_accounts, "profile": with_profile, "llm_key": with_llm_key,
              "garmin": with_garmin, "first_meal": with_meal, "returned_week2": returned_week2}

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

    # Posiłki dziennie — z tabeli Meal (dane realne, nie telemetria).
    meals_since = today - timedelta(days=29)
    meal_counts = db.execute(
        select(Meal.date, func.count(Meal.id))
        .where(Meal.date >= meals_since,
               Meal.user_id.in_(allowed_ids))
        .group_by(Meal.date)
    ).all()
    meal_by_day = dict(meal_counts)
    meals_points = [
        (meals_since + timedelta(days=i), float(meal_by_day.get(meals_since + timedelta(days=i), 0)))
        for i in range(30)
    ]
    chart_meals_per_day = bar_chart(meals_points, meals_since, today,
                                    color_pos="#1A4D3A", color_neg="#1A4D3A")

    last_activity = sorted(
        (
            {"ref": ref, "last_date": max(d for d, _, _ in items),
             "days": len({d for d, _, _ in items}),
             "is_admin": scope == "all" and ref == admin_ref}
            for ref, items in by_ref.items()
        ),
        key=lambda x: x["last_date"], reverse=True,
    )

    my_days = _my_days(db, admin.id) if scope == "me" and admin else []

    model_vs_measurement = _stats_model_vs_measurement(db, allowed_ids, today)
    calibration_stats = _stats_calibration(db, allowed_ids, allowed_refs, today, weeks, chart_start)
    conservative_balance = _stats_conservative_balance(db, allowed_ids, today)

    return {
        "scope": scope,
        "total_accounts": total_accounts,
        "active_7": active_7,
        "active_30": active_30,
        "median_days_active": median_days,
        "adopted_7d": adopted_7d,
        "funnel": funnel,
        "top_events": top_events,
        "chart_weekly_active": chart_weekly_active,
        "chart_weekly_events": chart_weekly_events,
        "chart_meals_per_day": chart_meals_per_day,
        "last_activity": last_activity,
        "my_days": my_days,
        "model_vs_measurement": model_vs_measurement,
        "calibration_stats": calibration_stats,
        "conservative_balance": conservative_balance,
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentyl metodą najbliższej rangi — wystarcza przy garstce testerów,
    nie potrzeba interpolacji."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _event_sum(db: Session, allowed_refs: set[str], event: str, since: date, today: date) -> int:
    return db.scalar(
        select(func.sum(UsageDaily.count)).where(
            UsageDaily.event == event, UsageDaily.date >= since, UsageDaily.date <= today,
            UsageDaily.user_ref.in_(allowed_refs),
        )
    ) or 0


def _stats_model_vs_measurement(db: Session, allowed_ids: set[int], today: date) -> dict:
    """Pytania 1-2 z TODO.md: czy `Activity.kcal_bmr_garmin`/`steps` w ogóle
    się wypełniają, i czy model teoretyczny trafia w pomiar Garmina. Ostatnie
    30 dni, jedno zapytanie per tabela."""
    since = today - timedelta(days=30)

    activities = db.execute(
        select(Activity.kcal_bmr_garmin, Activity.steps)
        .where(Activity.user_id.in_(allowed_ids), Activity.source == "garmin",
               Activity.date >= since)
    ).all()
    n_activities = len(activities)
    pct_with_bmr = (
        round(100 * sum(1 for kb, _ in activities if kb is not None) / n_activities, 1)
        if n_activities else None
    )
    pct_with_steps = (
        round(100 * sum(1 for _, st in activities if st is not None) / n_activities, 1)
        if n_activities else None
    )

    summaries = db.execute(
        select(DailySummary.user_id, DailySummary.date, DailySummary.kcal_total_garmin,
               DailySummary.model_total_kcal, DailySummary.complete)
        .where(DailySummary.user_id.in_(allowed_ids), DailySummary.date >= since)
    ).all()
    ratios = sorted(
        m / g for _, _, g, m, _ in summaries if g is not None and g > 0 and m is not None
    )
    model_ratio = {
        "n": len(ratios),
        "median": round(_percentile(ratios, 50), 3) if ratios else None,
        "p10": round(_percentile(ratios, 10), 3) if ratios else None,
        "p90": round(_percentile(ratios, 90), 3) if ratios else None,
        "outside_15pct": (
            round(100 * sum(1 for r in ratios if abs(r - 1) > 0.15) / len(ratios), 1)
            if ratios else None
        ),
    }

    meal_days = set(
        db.execute(
            select(Meal.user_id, Meal.date)
            .where(Meal.user_id.in_(allowed_ids), Meal.date >= since)
        ).all()
    )
    closed_with_meal = [
        (uid, g) for uid, d, g, _, complete in summaries if complete and (uid, d) in meal_days
    ]
    without_garmin = sum(1 for _, g in closed_with_meal if g is None)
    source_share = {
        "closed_with_meal": len(closed_with_meal),
        "without_garmin_pct": (
            round(100 * without_garmin / len(closed_with_meal), 1) if closed_with_meal else None
        ),
    }

    return {
        "activities_30d": n_activities, "pct_with_bmr": pct_with_bmr,
        "pct_with_steps": pct_with_steps, "model_ratio": model_ratio,
        "source_share": source_share,
    }


def _stats_calibration(db: Session, allowed_ids: set[int], allowed_refs: set[str], today: date,
                       weeks: int, chart_start: date) -> dict:
    """Pytania 3-4 z TODO.md: czy kalibracja się uczy i czy jest zdrowa."""
    from .calibration import CLAMP_HIGH, CLAMP_LOW, PRIOR_FACTOR
    from .charts import bar_chart

    states = db.scalars(
        select(CalibrationState).where(CalibrationState.user_id.in_(allowed_ids))
    ).all()
    factors = [s.factor for s in states]
    factor_dist = {
        "min": round(min(factors), 4) if factors else None,
        "median": round(statistics.median(factors), 4) if factors else None,
        "max": round(max(factors), 4) if factors else None,
        "on_clamp": sum(1 for f in factors if f <= CLAMP_LOW + 0.001 or f >= CLAMP_HIGH - 0.001),
    }
    adoption = {
        "with_state": len(states),
        "days_used_1": sum(1 for s in states if s.days_used >= 1),
        "days_used_10": sum(1 for s in states if s.days_used >= 10),
        "factor_changed": sum(1 for s in states if s.factor != PRIOR_FACTOR),
    }

    since_30 = today - timedelta(days=30)
    valid_days = set(
        db.execute(
            select(DailySummary.user_id, DailySummary.date)
            .where(DailySummary.user_id.in_(allowed_ids), DailySummary.date >= since_30,
                   DailySummary.complete.is_(True), DailySummary.kcal_total_garmin.is_not(None))
        ).all()
    )
    meal_days = set(
        db.execute(
            select(Meal.user_id, Meal.date)
            .where(Meal.user_id.in_(allowed_ids), Meal.date >= since_30)
        ).all()
    )
    eligible_days = valid_days & meal_days
    entered_days = set(
        db.execute(
            select(CalibrationLog.user_id, CalibrationLog.day)
            .where(CalibrationLog.user_id.in_(allowed_ids), CalibrationLog.day >= since_30)
        ).all()
    )
    learning = {
        "eligible_days": len(eligible_days),
        "entered_days": len(entered_days & eligible_days) if eligible_days else 0,
        "pct_entered": (
            round(100 * len(entered_days & eligible_days) / len(eligible_days), 1)
            if eligible_days else None
        ),
    }

    logs = db.execute(
        select(CalibrationLog.day, CalibrationLog.innov_kg)
        .where(CalibrationLog.user_id.in_(allowed_ids), CalibrationLog.day >= chart_start)
    ).all()
    week_start = today - timedelta(days=today.weekday())
    innov_points = []
    for i in range(weeks - 1, -1, -1):
        w0 = week_start - timedelta(weeks=i)
        w1 = w0 + timedelta(days=6)
        week_vals = [abs(innov) for d, innov in logs if w0 <= d <= w1]
        innov_points.append((w0, round(statistics.median(week_vals), 3) if week_vals else 0.0))
    chart_innov = bar_chart(innov_points, chart_start, today,
                            color_pos="#3A7A5C", color_neg="#3A7A5C")

    return {
        "adoption": adoption,
        "factor_dist": factor_dist,
        "learning": learning,
        "chart_innov": chart_innov,
        "reset_7": _event_sum(db, allowed_refs, "calibration_reset", today - timedelta(days=6), today),
        "reset_30": _event_sum(db, allowed_refs, "calibration_reset", today - timedelta(days=29), today),
        "error_7": _event_sum(db, allowed_refs, "calibration_error", today - timedelta(days=6), today),
        "error_30": _event_sum(db, allowed_refs, "calibration_error", today - timedelta(days=29), today),
    }


def _stats_conservative_balance(db: Session, allowed_ids: set[int], today: date) -> dict:
    """Pytanie 5 z TODO.md: czy bilans „konserwatywny" produktowo działa —
    jak często domknięty dzień z posiłkami kończy się nad celem."""
    from .calibration import PRIOR_FACTOR

    since = today - timedelta(days=30)
    summaries = db.execute(
        select(DailySummary.user_id, DailySummary.date, DailySummary.kcal_total_garmin)
        .where(DailySummary.user_id.in_(allowed_ids), DailySummary.date >= since,
               DailySummary.complete.is_(True))
    ).all()

    meal_kcal_by_day: dict[tuple[int, date], float] = {}
    for uid, d, kcal in db.execute(
        select(Meal.user_id, Meal.date, Meal.kcal)
        .where(Meal.user_id.in_(allowed_ids), Meal.date >= since)
    ).all():
        meal_kcal_by_day[(uid, d)] = meal_kcal_by_day.get((uid, d), 0) + kcal

    deficits = {
        p.user_id: p.target_deficit_kcal
        for p in db.scalars(select(UserProfile).where(UserProfile.user_id.in_(allowed_ids))).all()
    }
    factors = {
        s.user_id: s.factor
        for s in db.scalars(select(CalibrationState).where(CalibrationState.user_id.in_(allowed_ids))).all()
    }

    diffs = []
    for uid, d, kcal_total_garmin in summaries:
        kcal_in = meal_kcal_by_day.get((uid, d))
        deficit = deficits.get(uid)
        if kcal_in is None or kcal_total_garmin is None or deficit is None:
            continue
        factor = factors.get(uid, PRIOR_FACTOR)
        e_target = kcal_total_garmin * factor - deficit
        diffs.append(kcal_in - e_target)

    over_target = sum(1 for x in diffs if x > 0)
    return {
        "n_days": len(diffs),
        "over_target_pct": round(100 * over_target / len(diffs), 1) if diffs else None,
        "median_diff": round(statistics.median(diffs)) if diffs else None,
    }


def _my_days(db: Session, admin_id: int, limit: int = 14) -> list[dict]:
    """Sekcja „Moje dni: model vs pomiar" (tylko `scope == 'me'`) — dane
    właściciela samemu właścicielowi, per dzień; dla innych zakresów ta
    funkcja nigdy nie jest wołana."""
    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == admin_id)
        .order_by(DailySummary.date.desc()).limit(limit)
    ).all()
    if not summaries:
        return []
    dates = [s.date for s in summaries]
    activities = db.execute(
        select(Activity.date, Activity.kcal_bmr_garmin)
        .where(Activity.user_id == admin_id, Activity.source == "garmin",
               Activity.date.in_(dates))
    ).all()
    acts_by_day: dict = {}
    for d, kcal_bmr in activities:
        entry = acts_by_day.setdefault(d, {"count": 0, "with_bmr": 0})
        entry["count"] += 1
        if kcal_bmr is not None:
            entry["with_bmr"] += 1
    return [
        {
            "date": s.date,
            "kcal_total_garmin": s.kcal_total_garmin,
            "kcal_active_garmin": s.kcal_active_garmin,
            "kcal_bmr_garmin": s.kcal_bmr_garmin,
            "model_total_kcal": s.model_total_kcal,
            "activities": acts_by_day.get(s.date, {}).get("count", 0),
            "activities_with_bmr": acts_by_day.get(s.date, {}).get("with_bmr", 0),
        }
        for s in summaries
    ]

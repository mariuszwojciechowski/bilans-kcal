"""Kalibracja adaptacyjna — WYMAGANIA.md 6.2.

Model uczy się na danych użytkownika (jak MacroFactor): `day.day_report()`
mnoży zmierzony wydatek (`kcal_out`) przez współczynnik `factor` zanim odejmie
cel deficytu — patrz `current_factor()`. Mechanizm to filtr dzienny
(uproszczony Kalman, `step_day`/`catch_up`), nie wsadowa kalibracja z pierwszej
wersji planu — decyzja właściciela 2026-09-05 (TODO.md „Kalibracja adaptacyjna",
Warstwa 2): 10-14 dni czekania na pierwszy wynik było gorsze niż liczba, która
koryguje się codziennie i wolno dochodzi do prawdy. Wsadowe `compute()` zostaje
wyłącznie do karty w tygodniówce (6.4) i jako strażnik przed rozjazdem filtru.

Wszystkie stałe filtru w jednym miejscu (jak w opisie w TODO.md) — nie
rozpraszać ich po kodzie, żeby dało się je zmienić jednym commitem.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Calibration, CalibrationLog, CalibrationState, DailySummary, Meal, WeightLog
from .balance import KCAL_PER_KG_FAT
from .energy import smoothed_weight

# Dzień wdrożenia wspólnej sesji „Poprawa wyliczania kcal na dzień w toku" +
# „Kalibracja adaptacyjna" (21.5.0 → 22.0.0) — dni sprzed tej daty były liczone
# starym modelem wydatku i nie wchodzą do kalibracji (ani wsadowej, ani filtru).
CALIBRATION_EPOCH = date(2026, 9, 5)

PRIOR_FACTOR = 0.97          # start filtru — jawny konserwatyzm (zasada w TODO.md)
EMA_ALPHA = 0.1              # wygładzenie wagi (konwencja Hacker's Diet)
CLAMP_LOW = 0.85             # w dół bez ograniczeń (realnie spalasz mniej)
CLAMP_HIGH = 1.05            # w górę tylko +5% (błąd wagi 14 dni ~0.5-1 kg)
MAX_DAILY_STEP = 0.01        # krok dnia ograniczony do ±1%
G_MAX = 0.05                 # gain po ustabilizowaniu (~15 dni)
GAIN_OFFSET = 5              # gain dnia 1 = 1/(0+5) ≈ 0.17
GAP_RESET_DAYS = 21          # przerwa bez ważnego dnia > tyle → days_used = 0
MIN_VALID_DAYS_BATCH = 10    # próg wsadu (`compute`), też warunek pierwszego wpisu
GUARD_DIVERGENCE = 0.10      # filtr vs wsad różnią się > 10% → reset filtru do wsadu


def _clamp_factor(factor: float) -> float:
    return max(CLAMP_LOW, min(CLAMP_HIGH, factor))


@dataclass
class FilterState:
    factor: float
    trend_kg: float | None
    days_used: int
    last_valid_day: date | None
    updated_on: date | None


@dataclass
class StepResult:
    state: FilterState
    log_entry: tuple[float, float, float] | None  # (innov_kg, gain, factor_after)


def step_day(state: FilterState, day: date, kcal_in: float, kcal_out: float,
            weight_kg: float) -> StepResult:
    """Jeden krok filtru dla ważnego dnia `day` (walidację dnia robi wołający,
    `catch_up`). `weight_kg` to surowy pomiar wagi z dnia `day` albo `day+1`."""
    if state.trend_kg is None:
        # Pierwszy pomiar w ogóle — inicjalizacja trendu, bez korekty factora
        # (nie ma jeszcze punktu odniesienia do policzenia innowacji).
        new_state = FilterState(
            factor=state.factor, trend_kg=weight_kg, days_used=state.days_used,
            last_valid_day=day, updated_on=day,
        )
        return StepResult(state=new_state, log_entry=None)

    pred_kg = (kcal_in - state.factor * kcal_out) / KCAL_PER_KG_FAT
    trend_new = state.trend_kg + EMA_ALPHA * (weight_kg - state.trend_kg)
    obs_kg = trend_new - state.trend_kg
    innov = obs_kg - pred_kg
    gain = min(G_MAX, 1 / (state.days_used + GAIN_OFFSET))
    delta = gain * innov * KCAL_PER_KG_FAT / kcal_out
    delta = max(-MAX_DAILY_STEP, min(MAX_DAILY_STEP, delta))
    factor_after = _clamp_factor(state.factor - delta)

    new_state = FilterState(
        factor=factor_after, trend_kg=trend_new, days_used=state.days_used + 1,
        last_valid_day=day, updated_on=day,
    )
    return StepResult(state=new_state, log_entry=(innov, gain, factor_after))


def _day_kcal_out(summary: DailySummary, activities: list[Activity]) -> float:
    manual_kcal = sum(a.kcal_garmin or 0 for a in activities if a.source == "manual")
    return summary.kcal_total_garmin + manual_kcal


def _is_valid_day(summary: DailySummary | None, meals: list[Meal]) -> bool:
    return bool(summary and summary.complete and summary.kcal_total_garmin is not None and meals)


def current_factor(db: Session, user_id: int) -> float:
    state = db.get(CalibrationState, user_id)
    return state.factor if state else PRIOR_FACTOR


def state_view(db: Session, user_id: int) -> dict:
    """Do UI: `days_used`/`updated_on` obok `current_factor()` (patrz day.py)."""
    state = db.get(CalibrationState, user_id)
    if state is None:
        return {"factor": PRIOR_FACTOR, "days_used": 0, "updated_on": None}
    return {"factor": state.factor, "days_used": state.days_used,
            "updated_on": state.updated_on.isoformat() if state.updated_on else None}


def compute(db: Session, user_id: int, period_days: int = 14) -> Calibration | None:
    """Migawka wsadowa dla karty 6.4 i strażnika — NIE mechanizm kalibracji
    na co dzień (to robi `step_day`/`catch_up`). Okres kończy się wczoraj."""
    period_end = date.today() - timedelta(days=1)
    period_start = max(period_end - timedelta(days=period_days - 1), CALIBRATION_EPOCH)
    if period_start > period_end:
        return None

    summaries = {
        s.date: s for s in db.scalars(
            select(DailySummary).where(
                DailySummary.user_id == user_id,
                DailySummary.date >= period_start,
                DailySummary.date <= period_end,
            )
        ).all()
    }
    meals_by_day: dict[date, list[Meal]] = {}
    for m in db.scalars(
        select(Meal).where(Meal.user_id == user_id, Meal.date >= period_start,
                           Meal.date <= period_end)
    ).all():
        meals_by_day.setdefault(m.date, []).append(m)
    activities_by_day: dict[date, list[Activity]] = {}
    for a in db.scalars(
        select(Activity).where(Activity.user_id == user_id, Activity.date >= period_start,
                               Activity.date <= period_end)
    ).all():
        activities_by_day.setdefault(a.date, []).append(a)

    sum_balance = 0.0
    sum_kcal_in = 0.0
    sum_kcal_out = 0.0
    valid_days = 0
    d = period_start
    while d <= period_end:
        summary = summaries.get(d)
        meals = meals_by_day.get(d, [])
        if _is_valid_day(summary, meals):
            kcal_in = sum(m.kcal for m in meals)
            kcal_out = _day_kcal_out(summary, activities_by_day.get(d, []))
            sum_balance += kcal_in - kcal_out
            sum_kcal_in += kcal_in
            sum_kcal_out += kcal_out
            valid_days += 1
        d += timedelta(days=1)

    if valid_days < MIN_VALID_DAYS_BATCH or sum_kcal_out <= 0:
        return None

    all_weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user_id)).all()
    ]
    weight_end = smoothed_weight([(d, kg) for d, kg in all_weights if d <= period_end])
    weight_start = smoothed_weight([(d, kg) for d, kg in all_weights if d <= period_start])
    if weight_end is None or weight_start is None:
        return None

    expected_delta_kg = sum_balance / KCAL_PER_KG_FAT
    actual_delta_kg = weight_end - weight_start
    factor_new = (sum_kcal_in - actual_delta_kg * KCAL_PER_KG_FAT) / sum_kcal_out
    factor_new = _clamp_factor(factor_new)

    previous = db.scalar(
        select(Calibration).where(Calibration.user_id == user_id)
        .order_by(Calibration.period_end.desc())
    )
    factor = factor_new if previous is None else 0.5 * previous.factor + 0.5 * factor_new

    row = Calibration(
        user_id=user_id, period_start=period_start, period_end=period_end,
        expected_delta_kg=round(expected_delta_kg, 3), actual_delta_kg=round(actual_delta_kg, 3),
        factor=round(factor, 4),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def catch_up(db: Session, user_id: int) -> CalibrationState:
    """Przetwarza dni od ostatniego przetworzonego (`updated_on + 1`, pierwszy
    raz od `CALIBRATION_EPOCH`) do wczoraj; idempotentne. Kończy strażnikiem
    względem wsadu (`compute`), gdy rozjazd > `GUARD_DIVERGENCE`."""
    row = db.get(CalibrationState, user_id)
    if row is None:
        row = CalibrationState(user_id=user_id, factor=PRIOR_FACTOR, days_used=0)
        db.add(row)

    start_day = max(
        (row.updated_on + timedelta(days=1)) if row.updated_on else CALIBRATION_EPOCH,
        CALIBRATION_EPOCH,
    )
    end_day = date.today() - timedelta(days=1)
    if start_day > end_day:
        db.commit()
        return row

    summaries = {
        s.date: s for s in db.scalars(
            select(DailySummary).where(
                DailySummary.user_id == user_id,
                DailySummary.date >= start_day,
                DailySummary.date <= end_day,
            )
        ).all()
    }
    meals_by_day: dict[date, list[Meal]] = {}
    for m in db.scalars(
        select(Meal).where(Meal.user_id == user_id, Meal.date >= start_day,
                           Meal.date <= end_day)
    ).all():
        meals_by_day.setdefault(m.date, []).append(m)
    activities_by_day: dict[date, list[Activity]] = {}
    for a in db.scalars(
        select(Activity).where(Activity.user_id == user_id, Activity.date >= start_day,
                               Activity.date <= end_day)
    ).all():
        activities_by_day.setdefault(a.date, []).append(a)
    # okno d oraz d+1 dla pomiaru wagi — pobierz z marginesem
    weights_by_day = {
        w.date: w.weight_kg for w in db.scalars(
            select(WeightLog).where(
                WeightLog.user_id == user_id,
                WeightLog.date >= start_day,
                WeightLog.date <= end_day + timedelta(days=1),
            )
        ).all()
    }

    state = FilterState(
        factor=row.factor, trend_kg=row.trend_kg, days_used=row.days_used,
        last_valid_day=row.last_valid_day, updated_on=row.updated_on,
    )

    d = start_day
    while d <= end_day:
        if state.last_valid_day is not None and (d - state.last_valid_day).days > GAP_RESET_DAYS:
            state.days_used = 0
        summary = summaries.get(d)
        meals = meals_by_day.get(d, [])
        weight_kg = weights_by_day.get(d, weights_by_day.get(d + timedelta(days=1)))
        kcal_out = _day_kcal_out(summary, activities_by_day.get(d, [])) if summary else 0
        if _is_valid_day(summary, meals) and weight_kg is not None and kcal_out > 0:
            kcal_in = sum(m.kcal for m in meals)
            result = step_day(state, d, kcal_in, kcal_out, weight_kg)
            state = result.state
            if result.log_entry is not None:
                innov, gain, factor_after = result.log_entry
                db.add(CalibrationLog(user_id=user_id, day=d, innov_kg=round(innov, 4),
                                      gain=round(gain, 4), factor_after=round(factor_after, 4)))
        else:
            state.updated_on = d
        d += timedelta(days=1)

    row.factor = state.factor
    row.trend_kg = state.trend_kg
    row.days_used = state.days_used
    row.last_valid_day = state.last_valid_day
    row.updated_on = state.updated_on
    db.commit()

    _guard_against_batch_divergence(db, user_id, row)
    db.commit()
    return row


def latest_snapshot(db: Session, user_id: int) -> Calibration | None:
    """Ostatnia migawka wsadowa — do karty 6.4. Odczyt bez efektów ubocznych;
    nowe migawki powstają w `maybe_snapshot` (throttlowane, wołane z `catch_up`)."""
    return db.scalar(
        select(Calibration).where(Calibration.user_id == user_id)
        .order_by(Calibration.period_end.desc())
    )


def maybe_snapshot(db: Session, user_id: int, min_age_days: int = 7) -> Calibration | None:
    """Nowa migawka wsadowa, jeśli ostatnia jest starsza niż `min_age_days`
    (albo nie istnieje) — throttle, żeby nie pisać nowego wiersza przy każdym
    wywołaniu `catch_up` (raz dziennie z dashboardu)."""
    latest = latest_snapshot(db, user_id)
    if latest is not None and (date.today() - latest.period_end).days < min_age_days:
        return latest
    fresh = compute(db, user_id)
    return fresh if fresh is not None else latest


def _guard_against_batch_divergence(db: Session, user_id: int, row: CalibrationState) -> None:
    """Filtr i wsad różnią się > 10% (błąd w filtrze albo w danych) → reset
    filtru do wsadu, wpis w logu (patrz TODO.md „Warstwa 2")."""
    batch = maybe_snapshot(db, user_id)
    if batch is None or batch.factor <= 0:
        return
    divergence = abs(row.factor - batch.factor) / batch.factor
    if divergence > GUARD_DIVERGENCE:
        db.add(CalibrationLog(user_id=user_id, day=batch.period_end, innov_kg=0.0, gain=0.0,
                              factor_after=batch.factor))
        row.factor = batch.factor


def run_catch_up(user_id: int) -> None:
    """Wariant z własną sesją DB — do `background.add_task` przy wejściu na
    dashboard, obok `maybe_sync` (wzorzec: `app/services/sync.py:maybe_sync`)."""
    import logging

    from ..db import get_session

    logger = logging.getLogger(__name__)
    db = get_session()
    try:
        catch_up(db, user_id)
    except Exception:
        logger.exception("Kalibracja: catch_up nieudany dla user_id=%s", user_id)
    finally:
        db.close()


def maybe_recalibrate(db: Session, user_id: int) -> None:
    """Po imporcie transferu: `catch_up` przelicza filtr od zera z historii
    (kilkaset kroków, milisekundy) — stan filtru nie jest częścią eksportu."""
    catch_up(db, user_id)

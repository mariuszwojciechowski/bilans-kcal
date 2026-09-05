"""Kalibracja adaptacyjna — filtr dzienny (TODO.md „Kalibracja adaptacyjna",
Warstwa 2). Syntetyczny użytkownik: prawdziwy wydatek = 0.9 × to, co pokazuje
Garmin (czyli poprawny `factor` to 0.9), szum wagi ±0.5 kg (seed stały)."""
import random
from datetime import date, time, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CalibrationLog, CalibrationState, DailySummary, Meal, User
from app.models import WeightLog
from app.services import calibration

TRUE_FACTOR = 0.9
KCAL_IN = 2000
GARMIN_KCAL_OUT = 2500          # to, co pokazuje zegarek (raportowane w DailySummary)
TRUE_KCAL_OUT = TRUE_FACTOR * GARMIN_KCAL_OUT   # 2250 — realny wydatek
DAILY_BALANCE = KCAL_IN - TRUE_KCAL_OUT          # -250 kcal/dzień
START_WEIGHT = 90.0


class _FrozenToday:
    """Podmienia `calibration.date` tak, by `.today()` zwracało ustaloną datę —
    dane syntetyczne w testach są zakotwiczone w `CALIBRATION_EPOCH`, nie w
    zegarze maszyny uruchamiającej testy."""

    def __init__(self, fixed: date):
        self._fixed = fixed

    def today(self) -> date:
        return self._fixed


def _freeze_today(monkeypatch, fixed: date) -> None:
    monkeypatch.setattr(calibration, "date", _FrozenToday(fixed))


def _make_db(tmp_path, name="calib"):
    engine = create_engine(f"sqlite:///{tmp_path / f'{name}.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(User(id=1, email="t@example.com"))
    db.commit()
    return db


def _true_weight(day_index: int) -> float:
    return START_WEIGHT + day_index * DAILY_BALANCE / calibration.KCAL_PER_KG_FAT


def _seed_history(db, start_day: date, n_days: int, seed: int = 42, start_index: int = 0) -> None:
    rng = random.Random(seed)
    for i in range(n_days):
        day = start_day + timedelta(days=i)
        noise = rng.uniform(-0.5, 0.5)
        weight = round(_true_weight(start_index + i) + noise, 2)
        db.add(DailySummary(user_id=1, date=day, kcal_total_garmin=GARMIN_KCAL_OUT,
                            steps=9000, complete=True))
        db.add(Meal(user_id=1, date=day, time=time(12, 0), kcal=KCAL_IN, description="posilek"))
        db.add(WeightLog(user_id=1, date=day, weight_kg=weight))
    db.commit()


def test_single_day_does_not_move_factor_from_prior(tmp_path, monkeypatch):
    """(a) po 1 dniu filtr nie reaguje na jeden pomiar — factor blisko priora
    (pierwszy dzień tylko inicjuje trend wagi, bez korekty)."""
    db = _make_db(tmp_path)
    _seed_history(db, calibration.CALIBRATION_EPOCH, 1)
    _freeze_today(monkeypatch, calibration.CALIBRATION_EPOCH + timedelta(days=2))

    calibration.catch_up(db, 1)
    factor = calibration.current_factor(db, 1)
    assert 0.96 <= factor <= 0.98


def test_21_days_converges_near_true_factor(tmp_path, monkeypatch):
    """(b) po 21 dniach factor blisko prawdy (0.9)."""
    db = _make_db(tmp_path, "calib21")
    n_days = 21
    _seed_history(db, calibration.CALIBRATION_EPOCH, n_days)
    _freeze_today(monkeypatch, calibration.CALIBRATION_EPOCH + timedelta(days=n_days + 1))

    calibration.catch_up(db, 1)
    factor = calibration.current_factor(db, 1)
    assert 0.87 <= factor <= 0.93


def test_daily_step_never_exceeds_one_percent(tmp_path, monkeypatch):
    """(c) krok dnia nigdy > 1% — pilnujemy różnic kolejnych wpisów w logu."""
    db = _make_db(tmp_path, "calib_step")
    n_days = 21
    _seed_history(db, calibration.CALIBRATION_EPOCH, n_days)
    _freeze_today(monkeypatch, calibration.CALIBRATION_EPOCH + timedelta(days=n_days + 1))

    calibration.catch_up(db, 1)
    logs = db.scalars(
        select(CalibrationLog).where(CalibrationLog.user_id == 1).order_by(CalibrationLog.day)
    ).all()
    assert len(logs) >= 2
    prev = None
    for entry in logs:
        if entry.gain == 0.0 and entry.innov_kg == 0.0:
            continue  # wpis strażnika (reset), nie krok filtru
        if prev is not None:
            assert abs(entry.factor_after - prev) <= 0.01 + 1e-9
        prev = entry.factor_after


def test_clamp_upper_bound_at_105_percent():
    """(d) waga spadająca dwa razy szybciej niż bilans obiecuje -> factor rośnie,
    ale nie ponad 1.05 (clamp asymetryczny)."""
    state = calibration.FilterState(factor=1.0, trend_kg=90.0, days_used=0,
                                    last_valid_day=None, updated_on=None)
    day = calibration.CALIBRATION_EPOCH
    true_weight = 90.0
    # bilans obiecuje spadek 0.05 kg/dzień (2000 kcal in, 2385 kcal out -> -385/7700),
    # waga faktycznie spada 0.5 kg/dzień (niezależny od `trend_kg` szereg) —
    # ogromna innowacja, wielokrotny krok aż osiągnie sufit
    for _ in range(80):
        true_weight -= 0.5
        result = calibration.step_day(
            state, day, kcal_in=2000, kcal_out=2385, weight_kg=true_weight,
        )
        state = result.state
        day += timedelta(days=1)
    assert state.factor == 1.05


def test_day_without_weight_does_not_change_state(tmp_path, monkeypatch):
    """(e) dzień bez pomiaru wagi (ani d, ani d+1) jest pomijany — stan bez zmian."""
    db = _make_db(tmp_path, "calib_noweight")
    day0 = calibration.CALIBRATION_EPOCH
    db.add(DailySummary(user_id=1, date=day0, kcal_total_garmin=GARMIN_KCAL_OUT,
                        steps=9000, complete=True))
    db.add(Meal(user_id=1, date=day0, time=time(12, 0), kcal=KCAL_IN, description="posilek"))
    db.commit()   # brak WeightLog dla day0 i day0+1

    _freeze_today(monkeypatch, day0 + timedelta(days=2))
    calibration.catch_up(db, 1)

    row = db.get(CalibrationState, 1)
    assert row.days_used == 0
    assert row.trend_kg is None
    assert db.scalars(select(CalibrationLog)).first() is None


def test_catch_up_is_idempotent(tmp_path, monkeypatch):
    """(f) dwa wywołania catch_up() pod rząd dają ten sam stan."""
    db = _make_db(tmp_path, "calib_idempotent")
    n_days = 10
    _seed_history(db, calibration.CALIBRATION_EPOCH, n_days)
    _freeze_today(monkeypatch, calibration.CALIBRATION_EPOCH + timedelta(days=n_days + 1))

    calibration.catch_up(db, 1)
    row1 = db.get(CalibrationState, 1)
    snapshot1 = (row1.factor, row1.trend_kg, row1.days_used, row1.updated_on)

    calibration.catch_up(db, 1)
    row2 = db.get(CalibrationState, 1)
    snapshot2 = (row2.factor, row2.trend_kg, row2.days_used, row2.updated_on)

    assert snapshot1 == snapshot2


def test_guard_resets_filter_to_batch_on_divergence(tmp_path, monkeypatch):
    """(g) filtr rozjechany (1.05) vs wsad (~0.9, z 14 dni historii) -> reset
    filtru do wartości wsadu."""
    db = _make_db(tmp_path, "calib_guard")
    n_days = 14
    history_start = calibration.CALIBRATION_EPOCH
    _seed_history(db, history_start, n_days)
    yesterday = history_start + timedelta(days=n_days)   # jeden nowy, pusty dzień
    _freeze_today(monkeypatch, yesterday + timedelta(days=1))

    db.add(CalibrationState(user_id=1, factor=1.05, trend_kg=START_WEIGHT, days_used=20,
                            updated_on=yesterday - timedelta(days=1)))
    db.commit()

    calibration.catch_up(db, 1)

    batch = calibration.latest_snapshot(db, 1)
    assert batch is not None
    factor = calibration.current_factor(db, 1)
    assert abs(factor - batch.factor) < 1e-6
    assert factor < 1.0          # rozjechał się w dół, nie zostaje na 1.05

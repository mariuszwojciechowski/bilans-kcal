from datetime import date, timedelta

from app.services.forecast import goal_eta


def _weekly_series(start: date, weeks: int, start_kg: float, rate_kg_per_week: float):
    return [(start + timedelta(days=7 * i), start_kg + rate_kg_per_week * i)
            for i in range(weeks)]


def test_eta_from_steady_weight_loss():
    start = date(2026, 1, 1)
    series = _weekly_series(start, 8, 90.0, -0.5)  # 8 tygodni, -0.5 kg/tydz.
    today = series[-1][0]
    current = series[-1][1]
    target = current - 4  # 4 kg niżej od bieżącej

    result = goal_eta(series, target, today)
    assert result["status"] == "eta"
    assert result["basis"] == "weight"
    assert abs(result["weeks"] - 8) < 0.5
    eta_date = date.fromisoformat(result["eta_date"])
    expected = today + timedelta(weeks=8)
    assert abs((eta_date - expected).days) <= 3


def test_flat_series_gives_flat_status():
    start = date(2026, 1, 1)
    # praktycznie bez zmiany wagi (szum w obie strony, zerowy trend)
    weights = [80.0, 80.2, 79.8, 80.1, 79.9, 80.0, 80.2, 79.8]
    series = [(start + timedelta(days=3 * i), w) for i, w in enumerate(weights)]
    today = series[-1][0]

    result = goal_eta(series, 75.0, today)
    assert result["status"] == "flat"
    assert result["basis"] == "weight"


def test_weight_already_below_target_is_reached():
    start = date(2026, 1, 1)
    series = _weekly_series(start, 6, 74.0, -0.1)
    today = series[-1][0]
    result = goal_eta(series, 80.0, today)  # cel wyżej niż obecna waga
    assert result["status"] == "reached"


def test_too_few_points_falls_back_to_balance():
    start = date(2026, 1, 1)
    series = [(start, 90.0), (start + timedelta(days=1), 89.9), (start + timedelta(days=2), 89.8)]
    today = series[-1][0]
    result = goal_eta(series, 80.0, today, avg_balance_kcal=-500)
    assert result is not None
    assert result["basis"] == "balance"


def test_very_slow_rate_is_far():
    """Tempo poniżej progu 'flat' (-0.05 kg/tydz.), ale przy odległym celu
    prognoza wychodzi > 104 tygodnie (2 lata) → 'far', nie konkretna data."""
    start = date(2026, 1, 1)
    series = [(start, 90.0), (start + timedelta(days=1), 89.99)]
    today = series[-1][0]
    # rate = avg_balance * 7 / 7700 = -0.06 kg/tydz. dla avg_balance = -66
    result = goal_eta(series, 80.0, today, avg_balance_kcal=-66)
    assert result["status"] == "far"
    assert abs(result["rate_kg_per_week"] - (-0.06)) < 0.005


def test_no_target_returns_none():
    start = date(2026, 1, 1)
    series = _weekly_series(start, 8, 90.0, -0.5)
    assert goal_eta(series, None, series[-1][0]) is None


def test_no_weight_data_returns_none():
    assert goal_eta([], 80.0, date(2026, 1, 1), avg_balance_kcal=-500) is None

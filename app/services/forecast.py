"""Prognoza osiągnięcia celu wagi — WYMAGANIA.md 6.4.

Tempo liczone z FAKTYCZNEGO tempa zmiany wygładzonej wagi (regresja liniowa
najmniejszych kwadratów), nie z obietnicy bilansu — bilans kłamie o tyle, o
ile kłamie szacowanie posiłków. Bilans jest fallbackiem, gdy pomiarów wagi
jest za mało."""

from datetime import date, timedelta

from .balance import KCAL_PER_KG_FAT

MIN_POINTS = 6
MIN_SPAN_DAYS = 14
FLAT_THRESHOLD_KG_PER_WEEK = -0.05
FAR_WEEKS = 104


def _regression_rate_kg_per_week(smoothed: list[tuple[date, float]]) -> float | None:
    """Tempo zmiany wagi [kg/tydzień] z regresji liniowej po `smoothed`.
    None, gdy punktów jest mniej niż MIN_POINTS albo rozpiętość dat mniejsza
    niż MIN_SPAN_DAYS — wtedy wołający ma sięgnąć po fallback bilansowy."""
    if len(smoothed) < MIN_POINTS:
        return None
    pts = sorted(smoothed, key=lambda p: p[0])
    span_days = (pts[-1][0] - pts[0][0]).days
    if span_days < MIN_SPAN_DAYS:
        return None

    xs = [(d - pts[0][0]).days for d, _ in pts]
    ys = [w for _, w in pts]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope_per_day = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return slope_per_day * 7


def goal_eta(
    smoothed: list[tuple[date, float]],
    target_kg: float | None,
    today: date,
    avg_balance_kcal: float | None = None,
) -> dict | None:
    """Prognoza dotarcia do `target_kg`. `smoothed` — punkty (data, wygładzona
    waga), niesortowane. Zwraca None, gdy brak celu albo brak jakichkolwiek
    pomiarów wagi — nie da się wtedy powiedzieć nawet, czy cel jest osiągnięty."""
    if target_kg is None or not smoothed:
        return None

    current = sorted(smoothed, key=lambda p: p[0])[-1][1]

    rate = _regression_rate_kg_per_week(smoothed)
    basis = "weight"
    if rate is None:
        if avg_balance_kcal is None:
            return None
        rate = avg_balance_kcal * 7 / KCAL_PER_KG_FAT
        basis = "balance"

    if current <= target_kg:
        return {"status": "reached", "basis": basis}

    if rate >= FLAT_THRESHOLD_KG_PER_WEEK:
        return {"status": "flat", "rate_kg_per_week": round(rate, 2), "basis": basis}

    weeks = (current - target_kg) / abs(rate)
    if weeks > FAR_WEEKS:
        return {"status": "far", "rate_kg_per_week": round(rate, 2), "basis": basis}

    eta_date = today + timedelta(days=round(weeks * 7))
    return {
        "status": "eta",
        "rate_kg_per_week": round(rate, 2),
        "weeks": round(weeks, 1),
        "eta_date": eta_date.isoformat(),
        "basis": basis,
    }

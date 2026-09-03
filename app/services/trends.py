"""Dane widoku trendów (M9): ciężar, energia, bilans w zadanym zakresie dni.

Jedno źródło dla strony HTML (`GET /trends`) i JSON API (`GET /api/trends`).
Wcześniej ta sama logika — te same zapytania, to samo wygładzanie ciężaru, te
same serie wykresów — leżała w dwóch niemal identycznych kopiach w routerze;
poprawka w jednej nie trafiała do drugiej.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DailySummary, Meal, UserProfile, WeightLog
from .charts import Series, bar_chart, line_chart
from .forecast import goal_eta

TREND_RANGES = [(7, "Tydzień"), (30, "Miesiąc"), (90, "Kwartał"), (180, "Pół roku")]

MIN_DAYS = 2
MAX_DAYS = 366
SMOOTHING_WINDOW_DAYS = 7      # jak `energy.smoothed_weight` — patrz WYMAGANIA.md 3.2

# Kolory z palety marki (WYMAGANIA.md 9.2)
COLOR_MEASURED = "#8DC63F"     # brand_green_light — pomiary / spożyte
COLOR_SMOOTHED = "#1A4D3A"     # brand_green_dark — średnia 7 dni
COLOR_BURNED = "#3A7A5C"       # brand_green_medium — spalone
COLOR_GOAL = "#DC3545"         # danger — linia celu


def clamp_days(days: int) -> int:
    """Zakres z URL-a jest sterowany przez użytkownika — przycinamy do sensownego."""
    return max(MIN_DAYS, min(days, MAX_DAYS))


def nearest_range(days: int) -> int:
    """Najbliższy zdefiniowany zakres — do nazwy zdarzenia telemetrii
    (`trends_7|30|90|180`); przycisk może wysłać dowolną liczbę dni."""
    return min((d for d, _ in TREND_RANGES), key=lambda d: abs(d - days))


def payload(db: Session, user_id: int, days: int, today: date | None = None) -> dict:
    """Wspólna treść obu widoków trendów.

    Klucz `today` jest obiektem `date` i **nie wchodzi do odpowiedzi API** —
    router HTML formatuje go dla szablonu, router JSON go zdejmuje (kształt
    odpowiedzi `/api/trends` zostaje bez zmian). Zwracamy go, żeby oba widoki
    liczyły „dziś" raz: przy dwóch osobnych `date.today()` widok i dane mogłyby
    trafić na różne dni o północy.

    `today` jako parametr ułatwi wejście punktowi „Strefa czasowa użytkownika
    jako granica dnia" z TODO.md — wtedy zamiast `date.today()` poda się tu
    dzień w strefie profilu.
    """
    days = clamp_days(days)
    today = today or date.today()
    start = today - timedelta(days=days - 1)

    profile = db.get(UserProfile, user_id)
    target_weight = profile.target_weight_kg if profile else None

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.date >= start)
        ).all()
    ]
    # Wygładzenie liczymy z PEŁNEJ historii, nie tylko z okna: pierwszy dzień
    # zakresu ma wtedy średnią z poprzedzających go pomiarów, a nie z samego siebie.
    all_weights = sorted(
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user_id)).all()
    )
    smoothed = []
    for d, _ in weights:
        window = [kg for wd, kg in all_weights if 0 <= (d - wd).days < SMOOTHING_WINDOW_DAYS]
        if window:
            smoothed.append((d, sum(window) / len(window)))

    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == user_id, DailySummary.date >= start)
    ).all()
    kcal_out = [(s.date, float(s.kcal_total_garmin)) for s in summaries if s.kcal_total_garmin]

    meals = db.scalars(
        select(Meal).where(Meal.user_id == user_id, Meal.date >= start)
    ).all()
    kcal_in_by_day: dict[date, float] = {}
    for m in meals:
        kcal_in_by_day[m.date] = kcal_in_by_day.get(m.date, 0) + m.kcal
    kcal_in = sorted(kcal_in_by_day.items())

    # Bilans tylko dla dni, w których znamy OBIE strony równania.
    out_by_day = dict(kcal_out)
    balance = [(d, kcal - out_by_day[d]) for d, kcal in kcal_in if d in out_by_day]

    weight_series = [
        Series("pomiary", COLOR_MEASURED, weights, dots=True, width=1.5),
        Series("średnia 7 dni", COLOR_SMOOTHED, smoothed),
    ]
    if target_weight and weights:
        weight_series.append(
            Series("cel", COLOR_GOAL, [(start, target_weight), (today, target_weight)],
                   dash=True, width=1.5)
        )

    period_change = None
    if len(smoothed) >= 2:
        period_change = round(smoothed[-1][1] - smoothed[0][1], 1)
    avg_balance = round(sum(v for _, v in balance) / len(balance)) if balance else None

    return {
        "days": days,
        "today": today,
        "chart_weight": line_chart(weight_series, start, today, y_fmt="{:.1f}"),
        "chart_energy": line_chart(
            [Series("spożyte", COLOR_MEASURED, kcal_in, dots=True),
             Series("spalone (Garmin)", COLOR_BURNED, kcal_out, dots=True)],
            start, today,
        ),
        "chart_balance": bar_chart(balance, start, today),
        "period_change": period_change,
        "avg_balance": avg_balance,
        "balance_days": len(balance),
        "to_goal_kg": (round(smoothed[-1][1] - target_weight, 1)
                       if target_weight and smoothed else None),
        "goal_eta": goal_eta(smoothed, target_weight, today, avg_balance),
    }

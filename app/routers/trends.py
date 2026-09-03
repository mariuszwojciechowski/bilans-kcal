"""Trendy: strona HTML (wykresy SVG) i JSON API dla mobilnego SPA."""
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..db import db_session
from ..deps import STATIC_DIR, templates
from ..models import DailySummary, Meal, User, UserProfile, WeightLog
from ..services import usage as usage_service
from ..services.charts import Series, bar_chart, line_chart
from ..services.forecast import goal_eta
from ..services.sync import maybe_sync

router = APIRouter()

TREND_RANGES = [(7, "Tydzień"), (30, "Miesiąc"), (90, "Kwartał"), (180, "Pół roku")]


def _bump_trends_range(db: Session, user_id: int, days: int) -> None:
    """trends_7|30|90|180 — najbliższy zdefiniowany zakres (przycisk może
    nadal wysłać dowolną liczbę dni)."""
    nearest = min((d for d, _ in TREND_RANGES), key=lambda d: abs(d - days))
    usage_service.bump(db, user_id, f"trends_{nearest}")


@router.get("/trends", response_class=HTMLResponse)
def trends(
    request: Request,
    background: BackgroundTasks,
    days: int = 30,
    db: Session = Depends(db_session),
    user: User = Depends(auth.current_user),
):
    background.add_task(maybe_sync, user.id)
    days = max(2, min(days, 366))
    usage_service.bump(db, user.id, "trends_view")
    _bump_trends_range(db, user.id, days)
    today = date.today()
    start = today - timedelta(days=days - 1)
    profile = db.get(UserProfile, user.id)
    target_weight = profile.target_weight_kg if profile else None

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date >= start)
        ).all()
    ]
    smoothed = []
    all_weights = sorted(
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user.id)).all()
    )
    for d, _ in weights:
        window = [kg for wd, kg in all_weights if 0 <= (d - wd).days < 7]
        if window:
            smoothed.append((d, sum(window) / len(window)))

    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == user.id, DailySummary.date >= start)
    ).all()
    kcal_out = [(s.date, float(s.kcal_total_garmin)) for s in summaries if s.kcal_total_garmin]

    meals = db.scalars(
        select(Meal).where(Meal.user_id == user.id, Meal.date >= start)
    ).all()
    kcal_in_by_day: dict[date, float] = {}
    for m in meals:
        kcal_in_by_day[m.date] = kcal_in_by_day.get(m.date, 0) + m.kcal
    kcal_in = sorted(kcal_in_by_day.items())

    out_by_day = dict(kcal_out)
    balance = [
        (d, kcal - out_by_day[d]) for d, kcal in kcal_in if d in out_by_day
    ]

    weight_series = [
        Series("pomiary", "#8DC63F", weights, dots=True, width=1.5),
        Series("średnia 7 dni", "#1A4D3A", smoothed),
    ]
    if target_weight and weights:
        weight_series.append(
            Series("cel", "#DC3545", [(start, target_weight), (today, target_weight)],
                   dash=True, width=1.5)
        )
    chart_weight = line_chart(weight_series, start, today, y_fmt="{:.1f}")
    chart_energy = line_chart(
        [
            Series("spożyte", "#8DC63F", kcal_in, dots=True),
            Series("spalone (Garmin)", "#3A7A5C", kcal_out, dots=True),
        ],
        start, today,
    )
    chart_balance = bar_chart(balance, start, today)

    period_change = None
    if len(smoothed) >= 2:
        period_change = round(smoothed[-1][1] - smoothed[0][1], 1)
    avg_balance = round(sum(v for _, v in balance) / len(balance)) if balance else None

    return templates.TemplateResponse(
        request,
        "trends.html",
        {
            "days": days,
            "ranges": TREND_RANGES,
            "chart_weight": chart_weight,
            "chart_energy": chart_energy,
            "chart_balance": chart_balance,
            "period_change": period_change,
            "avg_balance": avg_balance,
            "balance_days": len(balance),
            "to_goal_kg": (round(smoothed[-1][1] - target_weight, 1)
                           if target_weight and smoothed else None),
            "goal_eta": goal_eta(smoothed, target_weight, today, avg_balance),
            "today": today.isoformat(),
            "has_logo": (STATIC_DIR / "logo.png").exists(),
        },
    )


# ── Trendy API (JSON + SVG) — dla mobilnego SPA ───────────────────────────

@router.get("/api/trends")
def api_trends_data(days: int = 30, db: Session = Depends(db_session),
                    user: User = Depends(auth.current_user)):
    days = max(2, min(days, 366))
    usage_service.bump(db, user.id, "trends_view")
    _bump_trends_range(db, user.id, days)
    today = date.today()
    start = today - timedelta(days=days - 1)
    profile = db.get(UserProfile, user.id)
    target_weight = profile.target_weight_kg if profile else None

    weights = [
        (w.date, w.weight_kg)
        for w in db.scalars(
            select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date >= start)
        ).all()
    ]
    all_weights = sorted(
        (w.date, w.weight_kg)
        for w in db.scalars(select(WeightLog).where(WeightLog.user_id == user.id)).all()
    )
    smoothed = []
    for d, _ in weights:
        window = [kg for wd, kg in all_weights if 0 <= (d - wd).days < 7]
        if window:
            smoothed.append((d, sum(window) / len(window)))

    summaries = db.scalars(
        select(DailySummary).where(DailySummary.user_id == user.id, DailySummary.date >= start)
    ).all()
    kcal_out = [(s.date, float(s.kcal_total_garmin)) for s in summaries if s.kcal_total_garmin]

    meals = db.scalars(
        select(Meal).where(Meal.user_id == user.id, Meal.date >= start)
    ).all()
    kcal_in_by_day: dict[date, float] = {}
    for m in meals:
        kcal_in_by_day[m.date] = kcal_in_by_day.get(m.date, 0) + m.kcal
    kcal_in = sorted(kcal_in_by_day.items())

    out_by_day = dict(kcal_out)
    balance = [(d, kcal - out_by_day[d]) for d, kcal in kcal_in if d in out_by_day]

    weight_series = [
        Series("pomiary", "#8DC63F", weights, dots=True, width=1.5),
        Series("średnia 7 dni", "#1A4D3A", smoothed),
    ]
    if target_weight and weights:
        weight_series.append(
            Series("cel", "#DC3545", [(start, target_weight), (today, target_weight)],
                   dash=True, width=1.5)
        )

    period_change = None
    if len(smoothed) >= 2:
        period_change = round(smoothed[-1][1] - smoothed[0][1], 1)
    avg_balance = round(sum(v for _, v in balance) / len(balance)) if balance else None

    return {
        "days": days,
        "ranges": [{"days": d, "label": l} for d, l in TREND_RANGES],
        "chart_weight": line_chart(weight_series, start, today, y_fmt="{:.1f}"),
        "chart_energy": line_chart(
            [Series("spożyte", "#8DC63F", kcal_in, dots=True),
             Series("spalone (Garmin)", "#3A7A5C", kcal_out, dots=True)],
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

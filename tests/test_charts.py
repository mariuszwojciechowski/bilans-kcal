"""Znaczniki „szacowany" na wykresach SVG (`Series.hollow`, `bar_chart(estimated=...)`)
— patrz plan „Trendy liczą kcal inaczej niż «Dziś»" w TODO.md.

Bez tych parametrów SVG ma zostać identyczny jak przed ich dodaniem — inaczej
istniejące wykresy (waga, spożyte) zmieniłyby wygląd bez powodu."""

from datetime import date, timedelta

from app.services.charts import Series, bar_chart, line_chart

D0 = date(2026, 8, 1)
POINTS = [(D0, 100.0), (D0 + timedelta(days=1), 150.0), (D0 + timedelta(days=2), 90.0)]
D1 = D0 + timedelta(days=2)


def test_line_chart_without_hollow_is_unchanged():
    plain = line_chart([Series("s", "#000", POINTS, dots=True)], D0, D1)
    same = line_chart([Series("s", "#000", POINTS, dots=True, hollow=frozenset())], D0, D1)
    assert plain == same
    assert 'fill="white"' not in plain


def test_line_chart_hollow_marks_only_that_point():
    hollow_day = D0 + timedelta(days=1)
    svg = line_chart([Series("s", "#000", POINTS, dots=True, hollow=frozenset({hollow_day}))],
                     D0, D1)
    assert svg.count('fill="white"') == 1
    # pozostałe dwa punkty nadal pełne + prostokąt legendy = trzy fill="#000"
    assert svg.count('fill="#000"') == 3


def test_bar_chart_without_estimated_is_unchanged():
    plain = bar_chart(POINTS, D0, D1)
    same = bar_chart(POINTS, D0, D1, estimated=frozenset())
    assert plain == same
    assert "fill-opacity" not in plain


def test_bar_chart_estimated_marks_only_that_bar():
    estimated_day = D0 + timedelta(days=1)
    svg = bar_chart(POINTS, D0, D1, estimated=frozenset({estimated_day}))
    # jeden słupek szacowany + legenda = dwa wystąpienia przerywanego obrysu
    assert svg.count('stroke-dasharray="3,2"') == 2
    assert svg.count('fill-opacity=".45"') == 2

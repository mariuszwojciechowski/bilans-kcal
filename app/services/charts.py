"""Proste wykresy SVG rysowane po stronie serwera (bez zewnętrznych bibliotek).

Wejście: serie punktów (data, wartość). Wyjście: string <svg> osadzany w szablonie.
Kolory zgodne z paletą v2 (WYMAGANIA 9.2)."""

from dataclasses import dataclass, field
from datetime import date

INK_MUTED = "#6C757D"
GRID = "rgba(108,117,125,.25)"


@dataclass
class Series:
    label: str
    color: str
    points: list[tuple[date, float]]
    dash: bool = False
    dots: bool = False
    width: float = 2.5
    extra: dict = field(default_factory=dict)
    hollow: frozenset = field(default_factory=frozenset)


def _x(d: date, d0: date, d1: date, w: int, pad: int) -> float:
    span = max((d1 - d0).days, 1)
    return pad + (d - d0).days / span * (w - 2 * pad)


def _y(v: float, vmin: float, vmax: float, h: int, pad: int) -> float:
    span = (vmax - vmin) or 1.0
    return h - pad - (v - vmin) / span * (h - 2 * pad)


def _frame(w: int, h: int, pad: int, d0: date, d1: date,
           vmin: float, vmax: float, fmt: str = "{:.0f}") -> list[str]:
    parts = []
    for frac in (0.0, 0.5, 1.0):
        v = vmin + (vmax - vmin) * frac
        y = _y(v, vmin, vmax, h, pad)
        parts.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{w - pad}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{pad - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="{INK_MUTED}">{fmt.format(v)}</text>')
    parts.append(f'<text x="{pad}" y="{h - 4}" font-size="11" fill="{INK_MUTED}">{d0.strftime("%d.%m")}</text>')
    parts.append(f'<text x="{w - pad}" y="{h - 4}" text-anchor="end" font-size="11" fill="{INK_MUTED}">{d1.strftime("%d.%m")}</text>')
    return parts


def _empty(w: int, h: int, msg: str) -> str:
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<text x="{w/2}" y="{h/2}" text-anchor="middle" font-size="13" fill="{INK_MUTED}">{msg}</text></svg>')


def line_chart(series: list[Series], d0: date, d1: date,
               width: int = 780, height: int = 230, pad: int = 42,
               y_fmt: str = "{:.0f}") -> str:
    values = [v for s in series for _, v in s.points]
    if not values:
        return _empty(width, height, "Brak danych w tym okresie")
    vmin, vmax = min(values), max(values)
    margin = (vmax - vmin) * 0.1 or max(abs(vmax) * 0.05, 1)
    vmin, vmax = vmin - margin, vmax + margin

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="max-width:100%;height:auto">']
    parts += _frame(width, height, pad, d0, d1, vmin, vmax, y_fmt)

    legend_x = pad
    for s in series:
        pts = sorted(s.points)
        coords = " ".join(
            f"{_x(d, d0, d1, width, pad):.1f},{_y(v, vmin, vmax, height, pad):.1f}" for d, v in pts
        )
        dash = ' stroke-dasharray="5,4"' if s.dash else ""
        if len(pts) > 1:
            parts.append(f'<polyline points="{coords}" fill="none" stroke="{s.color}" '
                         f'stroke-width="{s.width}" stroke-linejoin="round"{dash}/>')
        if s.dots or len(pts) == 1:
            for d, v in pts:
                if d in s.hollow:
                    continue
                parts.append(f'<circle cx="{_x(d, d0, d1, width, pad):.1f}" '
                             f'cy="{_y(v, vmin, vmax, height, pad):.1f}" r="3" fill="{s.color}"/>')
        for d, v in pts:
            if d in s.hollow:
                parts.append(f'<circle cx="{_x(d, d0, d1, width, pad):.1f}" '
                             f'cy="{_y(v, vmin, vmax, height, pad):.1f}" r="3" '
                             f'fill="white" stroke="{s.color}" stroke-width="1.5"/>')
        parts.append(f'<rect x="{legend_x}" y="8" width="12" height="4" fill="{s.color}"/>')
        parts.append(f'<text x="{legend_x + 16}" y="14" font-size="11" fill="{INK_MUTED}">{s.label}</text>')
        legend_x += 16 + 7 * len(s.label) + 24
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(points: list[tuple[date, float]], d0: date, d1: date,
              width: int = 780, height: int = 230, pad: int = 42,
              color_pos: str = "#DC3545", color_neg: str = "#28A745",
              estimated: frozenset = frozenset()) -> str:
    """Słupki wokół zera — dla bilansu: deficyt (ujemny) zielony, nadwyżka czerwona.

    `estimated`: daty, dla których wydatek jest szacowany (dzień w toku albo
    brak pomiaru Garmina) — rysowane jaśniej i z przerywanym obrysem, żeby
    różnica była widoczna nawet bez rozróżniania nasycenia koloru."""
    if not points:
        return _empty(width, height, "Brak danych w tym okresie")
    values = [v for _, v in points]
    vmax = max(max(values), 0)
    vmin = min(min(values), 0)
    margin = (vmax - vmin) * 0.1 or 50
    vmin, vmax = vmin - margin, vmax + margin

    span_days = max((d1 - d0).days, 1)
    bar_w = max(min((width - 2 * pad) / (span_days + 1) * 0.7, 26.0), 2.0)

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="max-width:100%;height:auto">']
    parts += _frame(width, height, pad, d0, d1, vmin, vmax)
    if estimated:
        parts.append(f'<rect x="{pad}" y="6" width="12" height="8" fill="{color_neg}" rx="2"/>')
        parts.append(f'<text x="{pad + 16}" y="14" font-size="11" fill="{INK_MUTED}">dzień domknięty</text>')
        legend2_x = pad + 16 + 7 * len("dzień domknięty") + 24
        parts.append(f'<rect x="{legend2_x}" y="6" width="12" height="8" fill="{color_neg}" '
                     f'fill-opacity=".45" stroke="{color_neg}" stroke-width="1" '
                     f'stroke-dasharray="3,2" rx="2"/>')
        parts.append(f'<text x="{legend2_x + 16}" y="14" font-size="11" fill="{INK_MUTED}">'
                     f'szacowany (dzień w toku lub brak pomiaru)</text>')
    y0 = _y(0, vmin, vmax, height, pad)
    parts.append(f'<line x1="{pad}" y1="{y0:.1f}" x2="{width - pad}" y2="{y0:.1f}" '
                 f'stroke="{INK_MUTED}" stroke-width="1.5"/>')
    for d, v in sorted(points):
        x = _x(d, d0, d1, width, pad) - bar_w / 2
        y = _y(v, vmin, vmax, height, pad)
        top, hgt = (y, y0 - y) if v >= 0 else (y0, y - y0)
        color = color_pos if v > 0 else color_neg
        style = (f'fill="{color}" fill-opacity=".45" stroke="{color}" stroke-width="1" '
                 f'stroke-dasharray="3,2"') if d in estimated else f'fill="{color}"'
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
                     f'height="{max(hgt, 1):.1f}" {style} rx="2"/>')
    parts.append("</svg>")
    return "".join(parts)

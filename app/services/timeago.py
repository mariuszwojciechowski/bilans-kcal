"""Formatowanie „jak dawno" — wspólne dla raportu dnia i strony ustawień.

Leży w serwisach, a nie w `app/deps.py`, bo `services/day.py` tego potrzebuje,
a warstwa serwisów jest świadomie wolna od FastAPI (deps.py go importuje).
"""

from datetime import datetime


def humanize_ago(dt: datetime | None) -> str | None:
    """'1d 21h 12m temu' — z dokładnością do minut."""
    if dt is None:
        return None
    seconds = max(int((datetime.utcnow() - dt).total_seconds()), 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts) + " temu"

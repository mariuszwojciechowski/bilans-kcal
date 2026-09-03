"""Sprząta liczniki statystyk użycia (UsageDaily) starsze niż retencja.

Plan „Statystyki użycia" (TODO.md) mówi o dopisaniu tego do
scripts/purge_deleted.py — ten skrypt jeszcze nie istnieje (plan kasowania
konta nie jest zaimplementowany), więc na razie jest to samodzielny skrypt.
Gdy purge_deleted.py powstanie, to wywołanie powinno się tam przenieść i ten
plik skasować.

Użycie (cron / systemd timer, raz dziennie):
    .venv/bin/python scripts/purge_usage.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from app.db import get_session, init_db  # noqa: E402
from app.services import usage  # noqa: E402


def main() -> int:
    init_db()
    db = get_session()
    try:
        deleted = usage.purge_old(db)
    finally:
        db.close()
    print(f"Usunięto {deleted} wierszy statystyk starszych niż 180 dni.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

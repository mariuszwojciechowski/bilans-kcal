"""Przetwarza kolejkę posiłków offline (PendingMeal) dla wszystkich użytkowników.

Kolejka dotąd przetwarzała się tylko „przy okazji" innej akcji użytkownika
(BackgroundTasks po zapisie klucza LLM, imporcie transferu, ręcznym „spróbuj
ponownie"). Ten skrypt woła to samoistnie, do uruchamiania co minutę.

Użycie (cron / systemd timer, co minutę):
    .venv/bin/python scripts/process_meal_queue.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.db import get_session, init_db  # noqa: E402
from app.models import User  # noqa: E402
from app.services import meal_queue  # noqa: E402


def main() -> int:
    init_db()
    db = get_session()
    try:
        user_ids = db.scalars(select(User.id)).all()
    finally:
        db.close()

    total_processed = total_failed = 0
    for user_id in user_ids:
        result = meal_queue.process_queue(user_id)
        total_processed += result["processed"]
        total_failed += result["failed"]

    print(f"Kolejka: przetworzono {total_processed}, nieudanych {total_failed} "
          f"(użytkowników: {len(user_ids)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

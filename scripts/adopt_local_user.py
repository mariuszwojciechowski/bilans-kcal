"""Jednorazowa migracja z single-user na multi-user.

Do wersji z auth (sesja + hasło) dane siedziały w tabelach pod `user_id`
zahardkodowanego usera `local@fit-krasnal` — ten skrypt ustawia mu
prawdziwy e-mail i hasło, żeby dało się do niego zalogować normalnie.

Wszystkie relacje (profil, posiłki, wagi, kolejka, ustawienia) zostają
nienaruszone — nic się nie przenosi między rekordami, zmienia się tylko
sam wiersz `user`.

Użycie:
    .venv/bin/python scripts/adopt_local_user.py <email> <hasło>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from sqlalchemy import select

from app import auth
from app.db import get_session, init_db
from app.models import User

OLD_EMAIL = "local@fit-krasnal"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    new_email, password = sys.argv[1].strip().lower(), sys.argv[2]

    if auth.password_problem(password, password) is not None:
        print(f"Hasło niepoprawne (min. {auth.MIN_PASSWORD_LEN} znaków, max 72 bajty).")
        return 1

    init_db()
    db = get_session()
    try:
        old = db.scalar(select(User).where(User.email == OLD_EMAIL))
        if old is None:
            print(f"Brak użytkownika `{OLD_EMAIL}` — nic do migracji.")
            print("Jeśli już wcześniej uruchomiłeś ten skrypt: sprawdź e-mail w bazie.")
            return 1
        conflict = db.scalar(select(User).where(User.email == new_email))
        if conflict is not None and conflict.id != old.id:
            print(f"Konto `{new_email}` już istnieje (id={conflict.id}). Wybierz inny e-mail.")
            return 1

        old.email = new_email
        old.password_hash = auth.hash_password(password)
        db.commit()
        print(f"OK — konto id={old.id} ma teraz e-mail `{new_email}` i ustawione hasło.")
        print("Zaloguj się lokalnie i wyeksportuj dane: /api/transfer/export")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

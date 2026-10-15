"""Reset hasła użytkownika z terminala (na VM, uruchamiane przez admina).

Dla testera, który zapomniał hasła — dopóki nie ma samodzielnego resetu
mailem (patrz TODO.md). Hasło pyta przez `getpass`, żeby nie trafiło ani
do historii basha, ani do argumentów procesu (widocznych w `ps`).

Użycie:
    .venv/bin/python scripts/reset_password.py <email>
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from sqlalchemy import select

from app import auth
from app.db import get_session, init_db
from app.models import User


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    email = sys.argv[1].strip().lower()

    password = getpass.getpass("Nowe hasło: ")
    password2 = getpass.getpass("Powtórz nowe hasło: ")
    problem = auth.password_problem(password, password2)
    if problem:
        reasons = {
            "mismatch": "hasła się nie zgadzają",
            "short": f"za krótkie (min. {auth.MIN_PASSWORD_LEN} znaków)",
            "long": f"za długie (max {auth.MAX_PASSWORD_BYTES} bajtów)",
        }
        print(f"Hasło odrzucone: {reasons[problem]}. Spróbuj ponownie.")
        return 1

    init_db()
    db = get_session()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"Brak konta `{email}`.")
            return 1
        user.password_hash = auth.hash_password(password)
        db.commit()
        print(f"OK — hasło konta `{email}` zmienione. Przekaż je testerowi "
              "bezpiecznym kanałem (najlepiej nie mailem).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

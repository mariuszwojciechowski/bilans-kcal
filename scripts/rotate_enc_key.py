"""Rotacja klucza szyfrującego sekretów użytkownika (FIT_KRASNAL_ENC_KEY).

Odszyfrowuje wszystkie sekrety (klucze LLM, tokeny Garmina) OBECNYM kluczem
(ten, co jest już w środowisku procesu) i zaszyfrowuje je NOWYM, w jednej
transakcji — więc nic nie zostaje w niekonsystentnym stanie przy błędzie.

Użycie (na serwerze, z aktywnym starym FIT_KRASNAL_ENC_KEY w środowisku):
    .venv/bin/python scripts/rotate_enc_key.py <nowy-klucz>

Nowy klucz wygenerujesz:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Po sukcesie: wpisz nowy klucz jako FIT_KRASNAL_ENC_KEY w /etc/fit-krasnal/env
i `systemctl restart fit-krasnal` — dopóki tego nie zrobisz, proces nadal
używa starego klucza (ten skrypt niczego w środowisku nie zmienia)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.db import get_session, init_db  # noqa: E402
from app.models import AppSetting  # noqa: E402
from app.services import crypto, settings as settings_service  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    new_key = sys.argv[1].strip().encode()

    init_db()
    db = get_session()
    rows = db.scalars(
        select(AppSetting).where(AppSetting.key.in_(settings_service.SECRET_SETTING_KEYS))
    ).all()
    print(f"Rotacja {len(rows)} sekretów...")
    for row in rows:
        plaintext = crypto.decrypt(row.value)  # obecny klucz z FIT_KRASNAL_ENC_KEY
        row.value = crypto.encrypt_with_key(plaintext, new_key)
    db.commit()
    print(
        "Gotowe. Wpisz nowy klucz jako FIT_KRASNAL_ENC_KEY w /etc/fit-krasnal/env "
        "i zrestartuj usługę: systemctl restart fit-krasnal"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

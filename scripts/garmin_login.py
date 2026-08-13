"""Jednorazowe, interaktywne logowanie do Garmin Connect.

Uruchom samodzielnie w terminalu:  .venv/bin/python scripts/garmin_login.py
Poprosi o e-mail, hasło i (jeśli włączone) kod MFA. Tokeny sesji (ważne ~rok)
zapisze w ~/.fit-krasnal/garth — POZA repozytorium. Hasło nie jest nigdzie
zapisywane."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garminconnect import Garmin  # noqa: E402

from app.config import GARMIN_TOKENS_DIR  # noqa: E402


def main() -> None:
    tokens = str(GARMIN_TOKENS_DIR)

    # najpierw spróbuj wznowić istniejącą sesję
    try:
        api = Garmin()
        api.login(tokens)
        name = api.get_full_name()
        print(f"Sesja aktywna — zalogowano jako: {name}. Nic do zrobienia.")
        return
    except Exception:
        pass

    print("Logowanie do Garmin Connect (dane nie są nigdzie zapisywane poza tokenami sesji).")
    email = input("E-mail: ").strip()
    password = getpass.getpass("Hasło: ")

    api = Garmin(email=email, password=password, return_on_mfa=True)
    result, state = api.login()
    if result == "needs_mfa":
        code = input("Kod MFA: ").strip()
        api.resume_login(state, code)

    GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    api.garth.dump(tokens)
    print(f"Zalogowano jako: {api.get_full_name()}")
    print(f"Tokeny zapisane w: {tokens}")


if __name__ == "__main__":
    main()

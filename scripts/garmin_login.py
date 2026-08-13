"""Jednorazowe, interaktywne logowanie do Garmin Connect.

Uruchom samodzielnie w terminalu:  .venv/bin/python scripts/garmin_login.py
Poprosi o e-mail, hasło i (jeśli włączone) kod MFA. Tokeny sesji (ważne ~rok)
zapisze w ~/.fit-krasnal/garth — POZA repozytorium. Hasło nie jest nigdzie
zapisywane.

Uwaga: Garmin limituje próby logowania nieoficjalnymi metodami (błędy 429).
Biblioteka próbuje kilku strategii po kolei — pojedyncze komunikaty 429 po
drodze są normalne, dopóki całość kończy się sukcesem. Po kilku nieudanych
próbach odczekaj kilkanaście minut."""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garminconnect import Garmin  # noqa: E402

from app.config import GARMIN_TOKENS_DIR  # noqa: E402


def main() -> None:
    GARMIN_TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    tokens = str(GARMIN_TOKENS_DIR)

    # najpierw spróbuj wznowić istniejącą sesję
    try:
        api = Garmin()
        api.login(tokens)
        print(f"Sesja aktywna — zalogowano jako: {api.get_full_name()}. Nic do zrobienia.")
        return
    except Exception:
        pass

    print("Logowanie do Garmin Connect (dane nie są nigdzie zapisywane poza tokenami sesji).")
    email = input("E-mail: ").strip()
    password = getpass.getpass("Hasło: ")

    # prompt_mfa: biblioteka sama zapyta o kod, dokończy logowanie
    # i zapisze tokeny do tokenstore.
    api = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Kod MFA: ").strip(),
    )
    api.login(tokens)

    print(f"Zalogowano jako: {api.get_full_name()}")
    print(f"Tokeny zapisane w: {tokens}")


if __name__ == "__main__":
    main()

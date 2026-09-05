"""Konfiguracja testów — ładuje się przed importem `app.main`.

Ustawia `FIT_KRASNAL_DEBUG=1`, żeby SessionMiddleware nie wymagał HTTPS
(bez tego TestClient po HTTP nie odsyłałby ciasteczka Secure — co maskuje
się jako 401 przy każdym kolejnym requeście po zalogowaniu).
"""
import os
from datetime import date

os.environ.setdefault("FIT_KRASNAL_DEBUG", "1")

from app.services import clock  # noqa: E402  (po ustawieniu env, jak reszta importów app)


def app_today() -> date:
    """„Dziś" tak, jak liczy je serwer dla użytkownika bez strefy w profilu
    (`clock.user_today(None)` → Europe/Warsaw).

    NIE `date.today()`: to strefa PROCESU, czyli UTC na runnerze GitHuba.
    Między 22:00 a 24:00 UTC obie daty się różnią i testy, które seedują dane
    albo pytają `/api/day/{dzień}` „na dziś", rozjeżdżają się z serwerem
    (czerwony CI 2026-09-05 22:11 UTC, 4 failed). Testy ustawiające własną
    strefę w profilu (`test_timezone.py`) mają własne zamrażanie czasu i tego
    pomocnika nie używają.
    """
    return clock.user_today(None)

"""Konfiguracja testów — ładuje się przed importem `app.main`.

Ustawia `FIT_KRASNAL_DEBUG=1`, żeby SessionMiddleware nie wymagał HTTPS
(bez tego TestClient po HTTP nie odsyłałby ciasteczka Secure — co maskuje
się jako 401 przy każdym kolejnym requeście po zalogowaniu).
"""
import os

os.environ.setdefault("FIT_KRASNAL_DEBUG", "1")

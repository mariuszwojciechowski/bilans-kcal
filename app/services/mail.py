"""Mailing transakcyjny przez Resend (https://resend.com) — dziś tylko
reset hasła. Jeden mail = jeden POST na API (httpx, bez SDK).

Bez `FIT_KRASNAL_RESEND_KEY` nic nie wychodzi na świat: link resetu
ląduje w logu, żeby dało się przetestować przepływ lokalnie i na VM.
Konfiguracja konta/DNS: deploy/README.md, sekcja „Resend".
"""
import logging

import httpx

from ..config import MAIL_FROM, RESEND_API_KEY

logger = logging.getLogger(__name__)

_RESEND_API = "https://api.resend.com/emails"
_TIMEOUT_S = 10


def _send(to: str, subject: str, text: str) -> bool:
    """Niskopoziomowa wysyłka. Zwraca False zamiast wyjątku — mail to nigdy
    nie może wywrócić żądania, a różnice „wysłano/nie" rozmywa
    anti-enumeracja na poziomie routera."""
    if not RESEND_API_KEY:
        # dev/test: link trafia do logów (root-only na VM), nie na świat
        logger.info("mail: brak klucza Resend, nie wysyłam (to=%s subject=%r)",
                    to, subject)
        return False
    try:
        resp = httpx.post(
            _RESEND_API,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": MAIL_FROM, "to": [to], "subject": subject, "text": text},
            timeout=_TIMEOUT_S,
        )
    except httpx.HTTPError:
        logger.exception("mail: Resend nie odpowiada (to=%s)", to)
        return False
    if resp.status_code >= 400:
        logger.error("mail: Resend odrzucił wysyłkę (to=%s status=%s body=%s)",
                     to, resp.status_code, resp.text[:300])
        return False
    return True


def send_password_reset(to: str, url: str) -> bool:
    """Mail z jednorazowym linkiem resetu hasła."""
    text = (
        "Cześć!\n"
        "\n"
        "Ktoś poprosił o reset hasła do Fit Krasnal. Jeśli to nie Ty — "
        "zignoruj tego maila, nic się nie stanie.\n"
        "\n"
        "Link ustawia nowy hasło (ważny 60 minut, działa raz):\n"
        f"{url}\n"
        "\n"
        "— Krasnal\n"
    )
    return _send(to, "Fit Krasnal — reset hasła", text)

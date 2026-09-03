import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import DEBUG, DEV_SECRET_KEY, ENC_KEY, SECRET_KEY, USAGE_SALT, ensure_dirs
from .db import get_session, init_db
from .deps import STATIC_DIR
from .providers import garmin as garmin_provider
from .routers import (auth as auth_router, dashboard, day, meals, profile, pwa,
                      settings, transfer, trends, usage)
from .services import crypto, meal_queue

app = FastAPI(title="Fit Krasnal")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=not DEBUG,   # lokalny dev po http potrzebuje https_only=False
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router.router)
app.include_router(profile.router)
app.include_router(day.router)
app.include_router(meals.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(transfer.router)
app.include_router(trends.router)
app.include_router(usage.router)
app.include_router(pwa.router)


@app.on_event("startup")
def startup() -> None:
    # Lepiej, żeby proces nie wstał, niż żeby cicho szyfrował kluczem
    # deweloperskim albo sesję podpisywał domyślnym sekretem na produkcji.
    if not DEBUG and (SECRET_KEY == DEV_SECRET_KEY or not ENC_KEY):
        raise RuntimeError(
            "Produkcja wymaga FIT_KRASNAL_SECRET_KEY (nie domyślnego) i "
            "FIT_KRASNAL_ENC_KEY ustawionych w /etc/fit-krasnal/env."
        )
    # Brak soli nie blokuje startu (telemetria nie jest funkcją krytyczną), ale
    # NIE może być cichy: `usage.bump` zjada wyjątek do logu, więc bez tego
    # ostrzeżenia /usage po prostu stoi puste i nikt nie wie dlaczego.
    if not DEBUG and not USAGE_SALT:
        logging.getLogger(__name__).warning(
            "FIT_KRASNAL_USAGE_SALT nie jest ustawiony — statystyki użycia nie "
            "będą się zapisywać (/usage zostanie puste). Dopisz go do "
            "/etc/fit-krasnal/env i zrestartuj usługę."
        )
    ensure_dirs()
    init_db()
    # Klucze LLM aplikują się per-użytkownika w /settings/llm — przy multi-user
    # nie ma "tego jednego" usera do zasilenia na starcie. Kolejka posiłków jest
    # globalna (retencja 21 dni), więc jej sprzątanie zostawiamy.
    db = get_session()
    try:
        crypto.migrate_plaintext_settings(db)
        garmin_provider.migrate_tokens_dirs_to_db(db)
        meal_queue.purge_expired(db)
    finally:
        db.close()


# 401 z current_user na stronie HTML → redirect na /login (przeglądarka).
# Endpointy JSON /api/* zostawiamy jako 401 (dla klientów, np. mobile).
@app.exception_handler(HTTPException)
async def _redirect_html_on_401(request: Request, exc: HTTPException):
    from fastapi.exception_handlers import http_exception_handler
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login", status_code=303)
    return await http_exception_handler(request, exc)

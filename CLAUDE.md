# Kontekst dla nowej sesji

Ten plik ma pomóc nowej sesji Claude Code szybko wejść w projekt bez
kilkuset requestów rekonesansu. Nie jest publiczną dokumentacją —
o produkcie mówi [README.md](README.md), o wymaganiach [WYMAGANIA.md](WYMAGANIA.md),
o rzeczach do zrobienia [TODO.md](TODO.md), o wdrożeniu [deploy/README.md](deploy/README.md).

## Stan bieżący (stan na sierpień 2026)

- Produkcja: **https://fit.krasnal.cc** (multi-user, pilot, ~10 testerów).
- Landing: https://krasnal.cc.
- Backend: Python 3.13 + FastAPI + SQLite + Jinja2, jeden proces uvicorn
  (single-worker) na maszynie e2-micro w GCP.
- Auth: sesja w podpisanym ciasteczku (Starlette `SessionMiddleware`),
  hasła w bcrypt. Kod zaproszenia `FIT_KRASNAL_INVITE_CODE` gatuje rejestrację.
- Konto admin: **krasnal@krasnal.cc** (twarda referencja w kilku miejscach
  planowana — patrz TODO "Statystyki użycia"). Kontakt do testerów: ten sam alias.
- Deploy: `git push` na `main` → GitHub Actions → SSH na VM (`deploy/deploy.sh`)
  → restart systemd. Sekret SSH w GitHub Secrets. Testy przechodzą przed
  deployem — czerwony pytest = brak deploya.

## Struktura repo

- `app/main.py` — wszystkie route'y (auth, dashboard, API, mobile view).
- `app/auth.py` — hash/verify hasła, sesja, `current_user` dependency, throttle
  nieudanych logowań.
- `app/config.py` — env vars, ścieżki, `garmin_tokens_dir(user_id)`.
- `app/db.py` — silnik SQLite, `_migrate()` z addytywnymi migracjami.
- `app/models.py` — SQLAlchemy: `User`, `UserProfile`, `WeightLog`, `Meal`,
  `PendingMeal`, `AppSetting`, `DailySummary`, `Activity`. Model **od początku
  multi-user** (każda tabela domenowa ma `user_id`).
- `app/providers/garmin.py` — nieoficjalne API Garmin (`garminconnect`).
  Tokeny per user w `GARMIN_TOKENS_DIR/<user_id>/`, `_mfa_state: dict[int, ...]`.
- `app/services/` — `energy` (BMR, TDEE, kroki), `macros` (WHO + `bar_pct`),
  `meal_vision` (Gemini/Claude vision), `meal_queue` (kolejka offline),
  `balance`, `charts`, `quips`, `settings` (`get_llm_keys` per user),
  `sync` (throttled Garmin sync), `transfer` (export/import JSON).
- `app/templates/` — Jinja2. Server-rendered: `dashboard.html`, `settings.html`,
  `trends.html`, `login.html`, `register.html`. SPA-lite dla telefonu:
  `mobile.html` (fetch do `/api/*`, ta sama sesja).
- `app/resources/` — normy WHO (`who_norms.json`), teksty krasnala (`quips.json`).
- `deploy/` — `fit-krasnal.service` (systemd), `setup-vm.sh` (bootstrap),
  `deploy.sh` (uruchamiany z Actions), `landing/index.html` (strona `krasnal.cc`),
  `README.md` (procedura + onboarding testera).
- `scripts/` — `garmin_login.py` (CLI, legacy desktop), `adopt_local_user.py`
  (migracja starego `local@fit-krasnal` na prawdziwe konto), `start_backend.sh`,
  `stop_backend.sh`.
- `tests/` — pytest, `conftest.py` ustawia `FIT_KRASNAL_DEBUG=1` (bez tego
  TestClient traci ciasteczka Secure).

## Kluczowe konwencje

**Auth per request:** wszystkie route'y biorące dane usera mają
`user: User = Depends(auth.current_user)`. Bez sesji: 401 dla `/api/*`,
redirect 303 na `/login` dla stron HTML (globalny exception handler w
`main.py`). Nigdy nie używaj `local_user()` — została usunięta.

**Klucze LLM per user:** `settings.get_llm_keys(db, user_id) → LlmKeys(gemini, anthropic)`.
Przekazuj jako parametry do `meal_vision.pick_backend / llm_configured /
estimate_from_photo / estimate_from_text`. NIE mutuj `os.environ`
(`apply_llm_env` jest legacy, dla starych testów). Ten sam wzorzec w
`meal_queue.process_queue`.

**Garmin per user:** `GarminProvider(user_id)`, `tokens_present(user_id)`,
`interactive_login_start(email, password, user_id)`,
`interactive_login_mfa(code, user_id)`. Tokeny w podkatalogu `<user_id>/`.

**Migracje:** addytywne, w `app/db.py:_migrate()`. Wzorzec: `PRAGMA table_info`
+ `ALTER TABLE ADD COLUMN`. Bez Alembic. Migracja nowej kolumny musi umieć
backfill'ować istniejące wiersze (patrz `external_id` w `Meal`).

**Testy:** `.venv/bin/python -m pytest` — wszystko musi być zielone,
inaczej deploy się nie zbuduje.

**Deployment jest bezpośredni:** commit → push → produkcja. Nie ma
staging'u. Regresja w main = regresja u testerów. Testy muszą chronić.

## Rzeczy do NIE odtworzenia / uważaj

- **`docs/` została świadomie usunięta** (commit `091844d`). Był to
  równoległy klient PWA na GitHub Pages, duplikował logikę backendu (13
  commitów podwójnego utrzymania). Zamiast tego jest `app/templates/mobile.html`
  serwowany z tego samego backendu pod `GET /mobile`. GitHub Pages nadal
  serwuje ostatnią wersję, ale build jest czerwony — patrz [TODO.md](TODO.md).
- **WYMAGANIA.md jest sprzed multi-user** (sierpień 2026-08-13). Fakty
  produktowe są aktualne, ale odniesienia do "single-user" i "docs/index.html
  jako kolejka offline" są nieaktualne w kodzie. Nie aktualizuj bez potrzeby
  — dokument opisuje pierwotny kontrakt, historię decyzji, nie stan kodu.
- **Nie ustaw uvicorn workers > 1** bez zmiany kilku rzeczy (throttle
  `_last_attempt` w `sync.py`, throttle `_failed` w `auth.py`, `_mfa_state`
  w `garmin.py` — dziś to dict-y w pamięci procesu, przy wielu workerach
  będą się rozjeżdżać).

## Historia decyzji

Plan wdrożenia multi-user (kroki 1-9): [deploy/multi-user-plan.md](deploy/multi-user-plan.md).
Zapisany chronologicznie z uzasadnieniem każdej decyzji — patrz sekcje A-F
plus aktualizacja z 2026-08-27 o usunięciu `docs/`.

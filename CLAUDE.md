# Kontekst dla nowej sesji

## Mapa dokumentów — co czytać, czego nie

| Plik | Kiedy czytać |
|---|---|
| ten plik | zawsze (jest wstrzykiwany automatycznie) |
| [TODO.md](TODO.md) | gdy szukasz zadania — sam indeks, ~90 linii |
| `plans/<slug>.md` | gdy realizujesz konkretny punkt z TODO |
| [DONE.md](DONE.md) | indeks zrobionych; **nie czytaj `archive/` całego** — wyciągnij sekcję: `awk '/^## <fragment>/,/^## /' archive/<plik>.md`, szukaj przez `grep -rn "<fraza>" archive/` |
| [README.md](README.md) | co to za produkt (dla człowieka) |
| [VERSIONING.md](VERSIONING.md) | jak podnieść `VERSION` (X/Y/Z) |
| [deploy/README.md](deploy/README.md) | wdrożenie, VM, onboarding testera |
| [WYMAGANIA.md](WYMAGANIA.md) | **dokument historyczny** (sprzed multi-user) — tylko gdy szukasz pierwotnego kontraktu; nie aktualizuj |

**Każda zmiana w kodzie podnosi `VERSION`** wg [VERSIONING.md](VERSIONING.md) —
to część „done", nie opcjonalny krok.

## Stan bieżący

- Produkcja **https://fit.krasnal.cc** (multi-user, pilot ~10 testerów),
  landing https://krasnal.cc. Konto admin i kontakt: **krasnal@krasnal.cc**.
- Python 3.13 + FastAPI + SQLite + Jinja2, jeden proces uvicorn (single-worker)
  na e2-micro w GCP. Sesja w podpisanym ciasteczku (`SessionMiddleware`),
  hasła bcrypt, rejestracja za kodem `FIT_KRASNAL_INVITE_CODE`.
- Deploy: `git push` na `main` → GitHub Actions → SSH na VM (`deploy/deploy.sh`)
  → restart systemd. **Czerwony pytest = brak deploya. Nie ma staging'u:
  regresja w main = regresja u testerów.**

## Struktura repo (tylko rzeczy nieoczywiste)

- `app/main.py` — `FastAPI()`, sesja, `/static`, startup (migracje, kolejka),
  globalny handler 401 → `/login`, `include_router` dla `app/routers/*`.
- `app/routers/` — tematycznie: `auth` (+`/prywatnosc`), `profile` (+`/api/sync`),
  `day`, `meals` (+kolejka offline, zapisane posiłki), `dashboard` (`/` i
  `/mobile`), `settings`, `transfer`, `trends`, `usage` (admin), `pwa`.
- `app/deps.py` — `templates`, `STATIC_DIR`, `require_llm_consent`,
  `require_admin`. **Importuje FastAPI**, więc serwisy nie mogą z niego brać nic
  (dlatego `humanize_ago` mieszka w `services/timeago.py`).
- `app/services/` — **warstwa wolna od FastAPI**: brak danych zgłasza wyjątkiem
  domenowym (`day.DayReportUnavailable` → router mapuje na 409), nigdy
  `HTTPException`. Pilnuje tego `tests/test_day_trends_services.py`.
  Jedno źródło prawdy per temat: `day.day_report`, `trends.payload`.
- `app/templates/` — `mobile.html` to **jedyny widok aplikacji** (responsive,
  SPA-lite na `/api/*`); osobno server-rendered `settings.html`, `trends.html`,
  `login/register`, `privacy.html`, `usage.html`.
- `app/models.py` — od początku multi-user: każda tabela domenowa ma `user_id`.
- `app/resources/` — normy WHO, tabela MET, teksty krasnala (dane, nie kod).
- `scripts/` — `garmin_login.py` (CLI, legacy single-user),
  `adopt_local_user.py`, `start_backend.sh`, `stop_backend.sh`.
- `tests/conftest.py` ustawia `FIT_KRASNAL_DEBUG=1` (bez tego `TestClient`
  gubi ciasteczka `Secure`).

## Konwencje

**Auth per request:** każdy route z danymi usera ma
`user: User = Depends(auth.current_user)`. Bez sesji: 401 dla `/api/*`,
303 na `/login` dla stron. `local_user()` została usunięta — nie wracaj do niej.

**Klucze LLM per user:** `settings.get_llm_keys(db, user_id) → LlmKeys`,
przekazywane parametrem do `meal_vision.*`. **Nie mutuj `os.environ`**
(`apply_llm_env` jest legacy). Ten sam wzorzec w `meal_queue.process_queue`.

**Providery per user:** `GarminProvider(user_id, db)` / `StravaProvider(...)`,
wybór przez `providers.get_provider_for_user` (Garmin > Strava > None). Tokeny
leżą zaszyfrowane w `AppSetting`, nie jako pliki; materializują się do katalogu
tymczasowego tylko na czas logowania do Garmina.

**Sekrety użytkownika (klucze LLM, tokeny) TYLKO przez
`settings_service.get_setting/set_setting/all_settings`** — nigdy wprost
w `AppSetting.value`. Co jest szyfrowane, decyduje `SECRET_SETTING_KEYS`
(`services/crypto.py`, Fernet, `FIT_KRASNAL_ENC_KEY`). Nowy sekret = dopisanie
klucza do tego zbioru, nie osobna ścieżka szyfrowania.

**Migracje:** addytywne, w `db.py:_migrate()` (`PRAGMA table_info` +
`ALTER TABLE ADD COLUMN`), bez Alembic. Nowa kolumna musi umieć backfillować
istniejące wiersze (wzór: `external_id` w `Meal`).

**Rok urodzenia, nie data:** profil trzyma `birth_year`, wiek liczy
`energy.age_from_year` (1 lipca). `birth_date` zostaje w schemacie jako
pochodna, nic jej nie czyta; `ProfileIn` przyjmuje ją tylko dla starych
klientów i plików transferu.

**Nota `/prywatnosc` musi być zgodna z kodem.** Zmiana tego, co zbieramy,
przetwarzamy, wysyłamy albo jak długo trzymamy → aktualizacja
`app/templates/privacy.html` w tym samym zadaniu + zdanie o tym we wpisie
DONE.md. Nowy odbiorca danych = bump `PRIVACY_VERSION` (= ponowna zgoda
testerów). To publiczne zobowiązanie, nie dokumentacja wewnętrzna.

**Kierunek błędu w bilansie** (decyzja właściciela 2026-09-05): przy
niepewności pokazuj **mniej** pozostałych kcal, nigdy więcej. Skala rzędu
3–5% wydatku (~100–150 kcal), **jawnie i w jednym miejscu** (zaokrąglenie
budżetu w dół, asymetryczny clamp kalibracji) — nigdy ukryta w stałych MET
czy wzorze BMR, bo ukrytego przesunięcia nie da się skalibrować.

**Krok „Statystyki" w każdym planie** (decyzja właściciela 2026-09-05): co
zliczać i jak pokazać na `/usage`, żeby po wdrożeniu było widać **adopcję**
funkcji i jej **funkcjonowanie**.

## Rzeczy do NIE odtworzenia

- **`docs/` została świadomie usunięta** (`091844d`) — był tam równoległy klient
  PWA na GitHub Pages, duplikat logiki backendu. Zostały **dwa pliki-nagrobki**
  (`index.html` + kill switch `sw.js`), które sprzątają po tamtej wersji
  (`localStorage` z kluczem API, IndexedDB, cache) i przekierowują na `/mobile`.
  **Nie dopisuj tam logiki aplikacji.**
- **Nie ustawiaj uvicorn `workers > 1`** bez przebudowy throttli trzymanych
  w pamięci procesu: `_last_attempt` (`sync.py`), `_failed` (`auth.py`),
  `_mfa_state` (`garmin.py`).
- Historia decyzji multi-user (kroki 1–9, sekcje A–F):
  [deploy/multi-user-plan.md](deploy/multi-user-plan.md).

## Preferencje współpracy (obowiązkowe)

- **Przed kodowaniem zawsze pytaj** — opisz zamiar i poczekaj na potwierdzenie.
- **Commituj często** (każda istotna zmiana, łatwiejszy `git revert`),
  **nie pushuj** — push robi właściciel.
- **Pełną suitę `pytest` puszczaj dopiero za zgodą właściciela.** Testy
  zmienianego pliku (`pytest tests/test_x.py`) — na bieżąco.
- **Zrealizowany punkt:** usuń go z [TODO.md](TODO.md) (razem z
  `plans/<slug>.md`, jeśli był) i dopisz wpis na początek właściwej listy
  w [DONE.md](DONE.md) + pełną treść na początek pliku w `archive/`.
  Wpis archiwalny: tytuł + **max 5 punktów**; szczegóły zostają w commicie.
- **Nowy plan dłuższy niż ~60 linii** ląduje w `plans/<slug>.md`, a w TODO.md
  zostaje tytuł, złożoność i 2–3 zdania.

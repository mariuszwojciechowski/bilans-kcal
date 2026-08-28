# Multi-user pilot dla Fit Krasnal (bilans-kcal)

## Context

Chcesz wystawić Fit Krasnal publicznie pod domeną na GCP, żeby przetestowała
je grupa <10 osób. Appka jest dziś **strictly single-user**: `local_user(db)`
(`app/main.py:75`) zawsze zwraca ten sam, zahardkodowany wiersz `User` — bez
względu na to, kto wysyła request. Wystawienie tego dziś dla kilku testerów
oznaczałoby, że wszyscy dzielą jeden profil, jeden dziennik posiłków, jedną
wagę i jedno konto Garmina — realną kolizję danych, nie tylko "brak logowania".

Model danych jest multi-user od początku (decyzja D2 w WYMAGANIA.md — każda
domenowa tabela ma `user_id`), więc to nie jest przebudowa schematu — to
dopisanie warstwy auth i naprawienie dwóch miejsc z globalnym stanem procesu
(Garmin tokens + stan MFA), które dziś zakładają jednego użytkownika na cały
proces.

Ustalone z Tobą decyzje:
1. **Logowanie**: sesja w ciasteczku (email + hasło), nie Basic Auth.
2. **Konta**: samodzielna rejestracja z jednym, wspólnym kodem zaproszenia.
3. **Klucze LLM**: każdy tester wkleja własny darmowy klucz Gemini — istniejący
   mechanizm `AppSetting` (już kluczowany po `user_id`) obsługuje to bez
   żadnych zmian w kodzie.

**Mobile web (`docs/index.html`) JEST w zakresie** — na tym etapie testerzy
łączą się z backendem przez przeglądarkę (desktop dashboard i/lub mobile),
nie przez dedykowaną natywną appkę (to dopiero w planach, D7). Zgodnie z
Twoją decyzją: mobile ma stać się **cienkim klientem backendu** — bez
IndexedDB, wszystkie dane (posiłki, waga, makra) przez to samo API co
desktop, pod tą samą sesją logowania. Szczegóły w sekcji E.

---

## A) Zmiany schematu

Jedno nowe pole, żadnych zmian w istniejących tabelach domenowych:

- `app/models.py` — `User`: dodać `password_hash: Mapped[str] = mapped_column(String)`.
- Brak nowej tabeli sesji — sesja to podpisane ciasteczko Starlette
  `SessionMiddleware` (`itsdangerous`) z samym `{"user_id": <int>}`. Wylogowanie
  = wyczyszczenie ciasteczka, bez sprzątania w bazie.
- `app/db.py` `_migrate()` — dopisać addytywną migrację wg istniejącego wzorca
  (`PRAGMA table_info` + `ALTER TABLE ... ADD COLUMN`), tak jak dla
  `target_weight_kg`/`lifestyle`/`external_id`.
- Nowe zależności w `pyproject.toml`: `itsdangerous`, `passlib[bcrypt]`.
  `python-multipart` już jest (potrzebne do istniejących `Form(...)`).
- Nowe zmienne env w `app/config.py`/`.env.example`:
  - `FIT_KRASNAL_SECRET_KEY` — klucz podpisujący sesję; wymagany w produkcji,
    z jawnie-niebezpiecznym fallbackiem dev (`"dev-insecure-secret-change-me"`),
    żeby nie dało się przypadkiem użyć go w produkcji.
  - `FIT_KRASNAL_INVITE_CODE` — wspólny kod zaproszenia; jeśli nieustawiony,
    `/register` zwraca 503 "rejestracja wyłączona" (nigdy nie wpuszcza domyślnie).

---

## B) Moduł auth

Nowy plik `app/auth.py`: hashowanie hasła (`passlib` + bcrypt), helpery sesji
(`login_user`, `logout_user`) i `current_user` jako **FastAPI dependency**
zastępująca `local_user`.

Kluczowa decyzja projektowa: `current_user` musi widzieć `Request` (do sesji)
i `db`, więc zamiana wszystkich 18 miejsc wywołania `local_user(db)` (17 route'ów
+ inline w `queue_process`, `app/main.py:571`) jest mechaniczna, ale nie jest
1-linijkową zmianą treści — to zmiana z lokalnej zmiennej na drugi parametr
dependency:

```python
# przed
def some_route(db: Session = Depends(db_session)):
    user = local_user(db)

# po
def some_route(db: Session = Depends(db_session), user: User = Depends(current_user)):
```

`current_user` zawsze rzuca `HTTPException(401)` gdy nie ma sesji/user nie
istnieje (proste, jednoznaczne dla endpointów `/api/*`). Dla stron HTML
(`/`, `/settings`, `/trends`) dopisujemy jeden globalny exception handler w
`main.py`, który przy 401 + `Accept: text/html` robi `RedirectResponse("/login")`
— zamiast dwóch wariantów dependency.

Handler startupowy (`app/main.py:37-47`) dziś robi `local_user(db)` żeby
zasilić `apply_llm_env` i wywołać `purge_expired`. Po zmianie: usuwamy
per-user priming z startupu (klucze LLM są już aplikowane per-user w
`settings_llm`), zostaje tylko globalny `meal_queue.purge_expired(db)`
(sprawdzone: sygnatura nie bierze `user_id`, to globalny sweep kolejki).

Po zamianie wszystkich miejsc: usunąć `local_user()` i `LOCAL_USER_EMAIL`
z `main.py`, żeby nie zostały jako martwy/mylący kod.

---

## C) Strony logowania / rejestracji

Nowe szablony `app/templates/login.html` i `register.html` — powtórnie
wykorzystujące inline `<style>` z `settings.html` (`--green`, `--lime`, `--bg`,
`--card`, `.banner.ok/.err`, `.card`, `input`, `button.primary`), bez nagłówka
z nawigacją (Dashboard/Ustawienia) — użytkownik nie jest jeszcze zalogowany.

Nowe route'y w `main.py`: `GET/POST /login`, `GET/POST /register`,
`POST /logout`. Rejestracja: sprawdza kod zaproszenia
(`FIT_KRASNAL_INVITE_CODE`), unikalność emaila, minimalną długość hasła (8
znaków), haszuje hasło, loguje od razu po utworzeniu konta. Logowanie:
`verify_password` przez `passlib`. Błędy wracają jako redirect z
`?error=...` (ten sam wzorzec co istniejący `settings.html?error=` dla
błędów logowania Garmina).

`SessionMiddleware` rejestrowany w `main.py` przy tworzeniu `app`, z
`https_only=True` w produkcji (przez `FIT_KRASNAL_DEBUG` flag, żeby lokalny
dev na `http://localhost:8321` wciąż dostawał działające ciasteczko).

Dopisać przycisk/link "Wyloguj" (`<form method=post action=/logout>`) do
istniejącego `<header>` w `dashboard.html:79`, `settings.html:52`,
`trends.html:50` — te trzy miejsca mają identyczny wzorzec `<header><a
class="brand" ...>`.

**Krok 3.5 — limit prób logowania (must-have, nie było w oryginalnym
zapytaniu, ale rekomendowane):** appka będzie na publicznym internecie z
logowaniem hasłem, bez weryfikacji email. Nawet dla ~10 kont, endpoint
`/login` bez throttlingu jest trywialnie brute-forceable. Minimalny koszt,
ten sam wzorzec co istniejący throttle w `app/services/sync.py` (dict + lock
w procesie): licznik nieudanych prób per email, blokada np. 5 prób → 15 min
lockout, reset po sukcesie. Kilka linii, zero nowej infrastruktury — polecam
to jako obowiązkowy, mały dodatek do kroku logowania, nie coś do odłożenia
"na później".

---

## D) Naprawa Garmina pod wielu użytkowników

To jest funkcjonalny blocker dla realnego użycia przez kilka osób naraz —
dwa miejsca z globalnym stanem procesu:

1. **`GARMIN_TOKENS_DIR`** (`app/config.py:30-32`) — dziś jedna ścieżka dla
   całego procesu. Zostaje jako katalog bazowy; dopisać helper
   `garmin_tokens_dir(user_id: int) -> Path` (`GARMIN_TOKENS_DIR / str(user_id)`).
   Zmienić w `app/providers/garmin.py`:
   - `tokens_present()` → bierze `user_id`, sprawdza per-user katalog. Call
     site: `main.py:456`.
   - `interactive_login_start(email, password)` → dodać `user_id`, użyć
     per-user katalogu (linie 36-37). Call site: `main.py:520`.
   - `interactive_login_mfa(code)` → dodać `user_id` (linia 47), potrzebny
     też do odczytu `_mfa_state[user_id]`. Call site: `main.py:531`.
   - `GarminProvider.__init__` → dodać `user_id`, `_client()` używa
     `garmin_tokens_dir(self._user_id)` (linia 61).
   - Każde `GarminProvider()` musi dostać `user_id`: `main.py:136` (`sync()`)
     i `app/services/sync.py:103` (w `maybe_sync`, już ma `user_id` jako
     parametr — tylko przełożyć dalej).

2. **`_mfa_state`** (`app/providers/garmin.py:19-20`) — z pojedynczego
   globalnego dict/None na `dict[int, dict]` keyowany `user_id`. Wiadomy,
   akceptowalny dla pilota <10 osób skrót: jeśli ktoś zacznie MFA i nie
   dokończy, wpis zostaje w pamięci (brak sprzątania) — bez znaczenia przy tej
   skali.

3. `main.py`: `/settings/garmin` (516-525) i `/settings/garmin/mfa` (528-534)
   dostają `user: User = Depends(current_user)` i przekazują `user.id`.

4. `scripts/garmin_login.py` — **bez zmian**. To osobny, desktopowy skrypt
   CLI, niepowiązany z web-pilotem; testerzy łączą Garmina przez
   `/settings/garmin` w przeglądarce.

---

## E) Mobile web — cienki klient backendu (zamiast IndexedDB)

Dobra wiadomość: prawie całe potrzebne API **już istnieje** w `app/main.py` —
`GET/PUT /api/profile`, `GET /api/day/{day}` (liczy makra/bilans/TDEE
server-side, dokładnie to, co dziś `whoTargets`/`tdee`/`renderMacros` w
`docs/index.html` liczą lokalnie jako "lustrzaną kopię"), `POST /api/meals`,
`DELETE /api/meals/{id}`, `POST /api/meals/photo`/`text` (LLM po stronie
serwera, z kluczem tego usera z `AppSetting` — mobile **nie musi już mieć
własnego pola na klucz Gemini**), `GET /api/transfer/export`,
`POST /api/transfer/import`.

Trzy realne decyzje/zmiany, które to wymusza:

1. **Ten sam origin, żeby sesja działała bez CORS.** Dziś `docs/` jest na
   GitHub Pages (`mariuszwojciechowski.github.io`) — inny origin niż backend
   na GCP. Rekomendacja: mobile widok wersji-pilotowej serwować **z tego
   samego FastAPI/domeny** co dashboard (nowy route, np. `GET /mobile`,
   renderujący zaadaptowaną wersję `docs/index.html` jako
   `app/templates/mobile.html`, chroniony tym samym `current_user`). Ten sam
   podpisany cookie sesji działa wtedy dla obu widoków bez dodatkowej
   konfiguracji CORS/`SameSite=None`. Istniejący GitHub Pages `docs/` **zostaje
   nietknięty** jako Twoje osobiste, w pełni offline'owe narzędzie — pilot
   dostaje własną, serwowaną-z-backendu wersję.
2. **Brakujący kawałek API: ręczny wpis wagi/kroków.** Desktop (D3) bierze
   wagę wyłącznie z Garmina — nie ma endpointu do ręcznego wpisu. Mobile dziś
   pozwala wpisać wagę/kroki ręcznie (`saveWeighIn()`, `saveDaySteps()` w
   `docs/index.html`) — to realna wartość dla testera bez zegarka Garmin przy
   sobie. Rekomendacja: dopisać dwa małe endpointy, `POST /api/weight`
   (`WeightLog(source="manual", ...)` — pole `source` już istnieje i przyjmuje
   dowolny string, zero migracji) i `POST /api/day/{day}/steps`
   (`DailySummary.steps` już istnieje). Świadome, oznaczone odstępstwo od D3
   tylko dla mobile — desktop się nie zmienia.
3. **Kolejka offline (M8) wypada z tej wersji.** Cienki klient bez
   IndexedDB nie ma gdzie trzymać "posiłku bez internetu" do późniejszego
   przetworzenia — to wymaga sieci przy każdej operacji, tak jak desktop.
   To świadoma regresja względem dzisiejszego GitHub Pages `docs/`
   (który zostaje nietknięty i dalej ją ma) — pilot na GCP jej nie dostaje.
   Flaguję to wprost, żebyś potwierdził, że to akceptowalne dla testu.

Zakres zmian w kodzie: skopiować/zaadaptować `docs/index.html` do
`app/templates/mobile.html` — zamienić wszystkie `all/put/ups/del` na
`fetch()` do istniejących endpointów (i dwóch nowych z pkt. 2), usunąć
`callGemini`/`SYSTEM`/`SCHEMA`/pole klucza Gemini (serwer już to robi),
usunąć `queueOnly`/`processQueue`/UI kolejki (pkt. 3), zamienić `whoTargets`/
`tdee`/`renderMacros`/`barPct`/`currentWeight`/`ageYears` na jedno wywołanie
`GET /api/day/{day}` (serwer zwraca to samo, co te funkcje dziś liczą
lokalnie). Nowa route `GET /mobile` w `main.py`, chroniona `current_user`,
z linkiem "Zaloguj" wskazującym `/login?next=/mobile` (żeby po zalogowaniu
tester wracał na mobile, nie na desktop dashboard).

---

## F) Kolejność wdrożenia (każdy krok osobno testowalny)

1. **Zależności + schema**: `itsdangerous`, `passlib[bcrypt]` w
   `pyproject.toml`; kolumna `password_hash` + migracja. Test: appka wciąż
   startuje, istniejący single-user flow niezmieniony (auth jeszcze nie
   podłączone).
2. **Moduł auth + middleware, bez zmian w route'ach**: `app/auth.py`,
   `SessionMiddleware`, `FIT_KRASNAL_SECRET_KEY`/`FIT_KRASNAL_INVITE_CODE`.
   Test: appka startuje, `request.session` dostępne.
3. **Strony login/register + limit prób logowania (3.5)**: 5 nowych route'ów,
   w pełnej izolacji od reszty appki (stary `local_user` flow nadal działa
   równolegle). Test: pełny cykl rejestracja → login → logout przez
   curl/przeglądarkę; złe dane (kod, hasło, duplikat emaila) → redirect z
   `?error=`.
4. **Zamiana `local_user` → `current_user` we wszystkich 18 miejscach** +
   exception handler + usunięcie `local_user()`/`LOCAL_USER_EMAIL`. To
   jedyny krok zmieniający zachowanie istniejących route'ów — testować
   najuważniej: dwie sesje przeglądarki (np. normalna + incognito), dwa
   konta testowe, każde widzi tylko swoje dane; `/` bez sesji → redirect na
   `/login`; `/api/*` bez sesji → 401.
5. **Naprawa Garmina per-user** (sekcja D). Test: konto A łączy Garmina,
   `data/.../<A.id>/` się tworzy, dashboard A synchronizuje; konto B nie
   widzi się jako połączone, po podłączeniu B dane/tokeny A nietknięte.
6. **Przycisk "Wyloguj"** w trzech nagłówkach. Test: klik → redirect na
   `/login`, ponowna wizyta `/` też redirectuje (cookie wyczyszczone).
7. **Dwa nowe endpointy**: `POST /api/weight` (manual), `POST /api/day/{day}/steps`.
8. **`app/templates/mobile.html` + `GET /mobile`**: adaptacja `docs/index.html`
   na fetch do API (sekcja E) — bez Gemini-w-kliencie, bez kolejki offline,
   bez IndexedDB. `docs/` (GitHub Pages) zostaje nietknięty.
9. **Onboarding dla testerów** (README/notatka): rejestracja z kodem →
   `/settings` wklejenie własnego klucza Gemini → `/settings/garmin`
   połączenie własnego konta Garmin → `/mobile` albo `/` do codziennego użytku.

Poza zakresem tego planu (świadomie): reset hasła, weryfikacja email,
role/uprawnienia, sam deployment na GCP (Dockerfile/Cloud Run/sekrety —
osobny etap po tym, jak appka jest bezpieczna do wielu użytkowników),
rate limiting na `/api/meals/photo`/`/text` (każdy tester ma własny klucz,
więc nadużycie zżera tylko jego quotę, nie Twoją), kolejka offline na
mobile (świadomie wypada — patrz sekcja E, pkt 3).

---

## Krytyczne pliki

- `app/main.py` — 18 call sites `local_user`, nowe route'y (`/login`,
  `/register`, `/logout`, `/mobile`, `/api/weight`, `/api/day/{day}/steps`),
  middleware, exception handler
- `app/auth.py` (nowy) — hashowanie, sesja, `current_user`, limit prób logowania
- `app/models.py` — `User.password_hash`
- `app/db.py` — migracja
- `app/config.py` — `garmin_tokens_dir()`, nowe env vars
- `app/providers/garmin.py` — `_mfa_state` per-user, `GarminProvider(user_id)`
- `app/services/sync.py` — przekazanie `user_id` do `GarminProvider`
- `app/templates/login.html`, `register.html`, `mobile.html` (nowe)
- `app/templates/dashboard.html:79`, `settings.html:52`, `trends.html:50` — przycisk wyloguj
- `pyproject.toml`, `.env.example`
- `docs/index.html` — **nietknięty** (osobne, offline'owe narzędzie na GitHub Pages)

## Weryfikacja (minimum)

1. `.venv/bin/python -m pytest` — zielono (dopisać tylko testy hash/verify
   hasła + `current_user` bez sesji → 401).
2. Lokalnie: dwa konta testowe przez przeglądarkę (desktop `/` i mobile
   `/mobile`) — każde widzi tylko swoje dane; wylogowany → redirect na `/login`.
3. GCP/domena to osobny, następny etap — nie część tego planu.

---

## AKTUALIZACJA 2026-08-27: docs/ usunięte z repo

`docs/` (osobna PWA na GitHub Pages) została **usunięta z repo** po
zamknięciu pilota multi-user — koszt podwójnego utrzymania (13 commitów w
historii dotknęło jednocześnie `docs/` i backendu) przewyższył wartość
offline queue / add-to-home-screen. GitHub Pages nadal serwuje ostatnią
wypchniętą wersję (`mariuszwojciechowski.github.io/bilans-kcal/`) — user
świadomie zdecydował się jej nie wyłączać, żeby nie zerwać istniejących
zakładek testerów. Landing `krasnal.cc` linkuje ją jako "stara wersja" z
notą, że dane wprowadzone tam nie synchronizują się z `fit.krasnal.cc` i
wymagają eksportu → importu.

**Konsekwencja dla przyszłych sesji:** nie szukajcie `docs/` w drzewie
repo, nie próbujcie tam wprowadzać zmian synchronizowanych z backendem.
Cały mobile-web to `app/templates/mobile.html` serwowany przez `GET /mobile`.

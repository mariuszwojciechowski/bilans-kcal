# TODO — do zrobienia po pilocie

Notatnik na luźne punkty, których nie robię teraz, ale nie chcę ich zgubić.
Każdy punkt jest przyszłym samodzielnym zadaniem — nie planem wdrożenia.

Przy każdym punkcie **szacowanie złożoności w skali 1-10**:

- **1** — wpisanie tej linijki tutaj zajmuje tyle samo co samo zrobienie.
- **3** — kilka godzin roboty, znane rozwiązanie.
- **5** — wieczór do dnia pracy, jakieś decyzje po drodze.
- **7** — kilka dni, sensowny plan przed startem.
- **10** — tygodnie, wymaga zewnętrznych rzeczy (usługa mailowa, nowa infrastruktura).

Zrealizowane punkty przenosimy do [DONE.md](DONE.md) — tutaj zostają wyłącznie
rzeczy do zrobienia.

---

## GitHub Pages — czerwony pipeline po skasowaniu docs/ (1/10)

Po usunięciu katalogu `docs/` (commit `091844d`) workflow *pages build and
deployment* w GitHub Actions faluje: repo miało w Settings → Pages → Source
ustawione na `docs/` folder, którego już nie ma. Stary content nadal
serwuje się z ostatniego udanego deploya, ale każdy push wywala nowego
builda. Do wyboru: (a) wyłączyć Pages w Settings → *None* (przerywa też
serwowanie starej wersji), (b) zostawić w Source folder `/` i wrzucić
minimalny `index.html` który redirectuje na `fit.krasnal.cc` (zabija starą
wersję po naszej stronie), (c) ignorować pipeline — nic to nie psuje,
tylko brzydko wygląda w Actions.

## Skrypt na serwerze do resetu hasła (1/10)

Analogiczny do `scripts/adopt_local_user.py`, tyle że dla dowolnego użytkownika:
`scripts/reset_password.py <email>` — pyta o nowe hasło w terminalu (żeby nie
lądowało w historii bash), haszuje i zapisuje w bazie. Do użycia, gdy tester
zapomni hasła i napisze do Ciebie.

## Zmiana hasła z poziomu Ustawień (2/10)

Dodatkowa karta w `/settings`: pola *stare hasło*, *nowe hasło*, *powtórz*.
Endpoint `POST /settings/password` używa `auth.verify_password` na starym,
`auth.hash_password` na nowym, sprawdza kryteria minimalnej długości. Ten
sam wzorzec błędów co formularze rejestracji.

## Statystyki użycia — adopcja i najczęściej klikane opcje (5/10)

Rozpisane 2026-09-03 (zastępuje wcześniejszy szkic tego punktu). Cel: właściciel
ma wiedzieć, **ilu testerów naprawdę używa aplikacji, jak głęboko weszli
i które funkcje są klikane** — bez zaglądania komukolwiek w dziennik posiłków.

**Uczciwie o anonimowości:** przy jednej bazie i ~10 kontach pełna anonimowość
jest nieosiągalna — administrator z dostępem do serwera zawsze może połączyć
statystyki z kontem. Osiągalne i wiążące dla tego planu jest to: w tabeli
statystyk NIE ma e-maili, treści posiłków, zdjęć, wag ani kalorii; jest
**pseudonim** (stabilny skrót z `user_id`), dzień, nazwa zdarzenia i licznik.
Widok `/usage` operuje wyłącznie na pseudonimach i agregatach. To trzeba opisać
jednym zdaniem w nocie `/prywatnosc` (plan „RODO" niżej) — telemetria własnej
aplikacji jest w porządku, ukrywanie jej nie.

**Decyzje (wiążące):**

- **Liczniki dzienne, nie log zdarzeń.** Jeden wiersz = (pseudonim, dzień,
  zdarzenie, licznik). Bez znaczników czasu co do sekundy i bez kolejności
  klików — z surowego logu dałoby się odtworzyć czyjś dzień, z liczników nie.
- **Zamknięta lista nazw zdarzeń** po stronie serwera. Nieznana nazwa → 422.
  Nazwa zdarzenia nigdy nie niesie treści (żadnych opisów posiłków, nazw
  aktywności, wartości pól).
- **Źródło prawdy to serwer.** Zdarzenia, które i tak trafiają na endpoint,
  liczymy w route'cie (nie da się ich zgubić przy blokadzie JS). Klient zgłasza
  tylko to, co nie ma odpowiednika po stronie serwera — przełączanie zakładek
  i otwarcie wpisu ręcznego.
- **Retencja 180 dni**, sprzątane tym samym timerem co kasowanie kont.

**Kroki dla implementującego LLM:**

1. **Model.** W `app/models.py` tabela `UsageDaily(id, user_ref: str, date: Date,
   event: str, count: int)` z `UniqueConstraint("user_ref", "date", "event")`
   i indeksem po `date`. Nowa tabela — `create_all` wystarczy, bez migracji.
   Uwaga: **bez** `ForeignKey("user.id")` — statystyki mają przeżyć skasowanie
   konta jako czysty agregat (i nie blokować kasacji wiersza `user`).
2. **Serwis `app/services/usage.py`:**
   - `user_ref(user_id: int) -> str` — `hmac_sha256(USAGE_SALT, str(user_id))`
     obcięte do 12 znaków hex; `USAGE_SALT` z `app/config.py`
     (`FIT_KRASNAL_USAGE_SALT`, w dev pochodna `SECRET_KEY` — wzorzec jak
     w planie szyfrowania). Sól stała: zmiana = zerwana ciągłość statystyk.
   - `EVENTS: set[str]` — zamknięta lista (patrz punkt 3).
   - `bump(db, user_id, event, day=None)` — UPSERT `count = count + 1`
     (`INSERT ... ON CONFLICT DO UPDATE`, SQLite to umie). Dzień z
     `clock.user_today(profile)`, gdy plan strefy czasowej już wszedł; do tego
     czasu `date.today()`. **Nigdy nie może wywrócić requestu użytkownika** —
     całość w try/except z `logger.warning`.
   - `purge_old(db, keep_days=180)`.
3. **Instrumentacja serwera** (`app/main.py`, jedna linia `usage.bump(...)`
   na route): `meal_photo` (`/api/meals/photo`), `meal_text` (`/api/meals/text`),
   `meal_save` (`/api/meals`, rozbite po `source`: `meal_save_photo|text|manual|saved`),
   `meal_delete`, `saved_meal_create`, `saved_meal_use`, `activity_add`,
   `activity_delete`, `steps_set`, `weight_manual`, `sync_manual` (`/api/sync`),
   `queue_process`, `queue_delete`, `transfer_export`, `transfer_import`,
   `llm_key_save`, `garmin_connect_ok`, `garmin_mfa`, `profile_save`,
   `goal_save`, `lifestyle_save`, `trends_view` (z parametrem zakresu jako
   osobne zdarzenia: `trends_7|30|90|180`), `login`. Plus `day_view` w
   `day_report` — to jest miara „wszedł i patrzy".
4. **Zdarzenia czysto klienckie.** `POST /api/usage` — body `{event}`,
   `Depends(auth.current_user)`, walidacja po `EVENTS`, odpowiedź 204.
   W `app/templates/mobile.html` funkcja `track(event)` (fire-and-forget,
   `fetch(..., {keepalive:true}).catch(()=>{})` — nigdy nie blokuje UI) wołana
   w: `show(page)` → `tab_today|add|activities|trends|settings`, `showManual()`
   → `manual_open`, `toggleSavedMeals()` → `saved_meals_open`, wybór zdjęcia →
   `photo_pick`. Nie instrumentuj każdego kliknięcia — te cztery odpowiadają na
   pytanie „które opcje są używane", reszta to szum.
5. **Widok `/usage`** — `app/templates/usage.html`, route z zależnością
   `require_admin` (`ADMIN_EMAIL` w `app/config.py`, domyślnie
   `krasnal@krasnal.cc`, nadpisywalne przez env; nie-admin → 404, nie 403 —
   nie ma po co ogłaszać, że taki widok istnieje). Sekcje:
   - **Adopcja:** liczba kont, aktywni w 7 / 30 dniach (pseudonimy z ≥1
     zdarzeniem), mediana dni z aktywnością na użytkownika, ilu ma ≥7 dni
     z posiłkiem (to jest realna adopcja, nie rejestracja).
   - **Lejek wejścia:** ilu założyło konto → uzupełniło profil → zapisało klucz
     LLM → podłączyło Garmina → zapisało pierwszy posiłek → wróciło w kolejnym
     tygodniu. Liczby bezwzględne, przy 10 osobach procenty są śmieszne.
   - **Najczęściej klikane:** tabela zdarzeń posortowana po sumie, z drugą
     kolumną „ilu różnych użytkowników" (jedna osoba klikająca 200 razy nie ma
     wyglądać na sukces funkcji).
   - **Tygodniowo:** aktywni użytkownicy i suma zdarzeń per tydzień — wykres
     przez istniejące `app/services/charts.py` (`bar_chart`), bez nowych
     zależności.
   - **Ostatnia aktywność per pseudonim:** dzień ostatniego zdarzenia + liczba
     dni z aktywnością. Do wyłapania „kto odpadł po tygodniu".
   Link do `/usage` widoczny w Ustawieniach tylko dla admina.
6. **Sprzątanie.** `usage.purge_old` dopisany do `scripts/purge_deleted.py`
   (timer z planu kasowania konta). Przy kasowaniu konta wierszy `UsageDaily`
   **nie** usuwamy — to już tylko pseudonim i licznik; napisz to w komentarzu
   przy `erasure.delete_account`, żeby ktoś tego nie „naprawił" w drugą stronę
   bez zastanowienia. (Jeśli właściciel zdecyduje inaczej, kasowanie po
   `user_ref` to jedna linia — ale wtedy statystyki adopcji tracą historię
   tych, którzy odeszli, czyli najciekawszą część.)
7. **Testy `tests/test_usage.py`:** `bump` tworzy wiersz i inkrementuje przy
   drugim wywołaniu tego samego dnia; ten sam `user_id` daje stabilny
   `user_ref`, różni użytkownicy — różny; `POST /api/usage` z nazwą spoza
   `EVENTS` → 422 i brak wiersza; `/usage` dla nie-admina → 404, dla admina →
   200 z pseudonimem, ale **bez** e-maila w treści odpowiedzi (asercja wprost:
   e-mail testowego użytkownika nie występuje w HTML); wywołanie
   `/api/meals/text` podbija licznik `meal_text`; awaria zapisu statystyk
   (monkeypatch rzucający wyjątek w `bump`) nie psuje odpowiedzi endpointu —
   to najważniejszy test w tym pliku.

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja —
właściciel.

## Kasowanie konta z 7-dniowym oknem odzyskania (6/10)

→ **Objęte planem „Usuń moje dane i konto w Ustawieniach" na końcu tego pliku**
(2026-09-03) — nie implementuj osobno, poniższy opis został tam wchłonięty wraz
z decyzją o oknie 7 dni.

Użytkownik kasuje konto. W bazie flagi `deleted_at` + soft-delete relacji,
konto znika z widoku. Przez 7 dni skrypt na serwerze potrafi je przywrócić —
warunek: nowe konto zarejestrowane na ten sam e-mail (świadoma podatność
zaakceptowana na pilota). Po założeniu nowego konta tester **nie widzi**
starych danych — musi być przekonany, że są nie do odzyskania. Twarda
kasacja po 7 dniach (skrypt uruchamiany z cron / systemd timer).

## Kasowanie danych z konta — czyszczenie historii (6/10)

→ **Objęte planem „Usuń moje dane i konto w Ustawieniach" na końcu tego pliku**
(2026-09-03) — nie implementuj osobno; okno 3 dni zostało tam utrzymane.

Analogicznie do wyżej: użytkownik z poziomu ustawień czyści posiłki/wagi/kolejkę.
Widocznie znikają natychmiast. Twarda kasacja finalizuje się po **3 dniach**.
Do tego czasu skrypt na serwerze potrafi przywrócić. Użytkownik ma być
przekonany, że skasował — tak samo jak przy kasowaniu konta.

## Prawdziwe „zapomniałem hasła" (mailem) (8/10)

Przycisk *"nie pamiętam hasła"* → formularz z e-mailem → link resetu
wysyłany na skrzynkę → tester klika, ustawia nowe hasło. Wymaga:
tabeli tokenów resetu w bazie, szablonu maila, konfiguracji wysyłki
(przez Gmail SMTP relay albo zewnętrzną usługę), ustawienia SPF/DKIM na
`krasnal.cc`, testowania że maile nie lądują w spamie. Kilka dni pracy,
w większości spoza samego kodu appki.


## Kalibracja adaptacyjna — WYMAGANIA.md 6.2 (6/10)

Jedyny duży brak z pierwotnego kontraktu ("przewaga produktu": model uczy się
na danych użytkownika jak MacroFactor). Kroki dla implementującego LLM:

1. **Model danych.** W `app/models.py` dodaj tabelę `Calibration` wg szkicu
   z WYMAGANIA.md 8.4: `id`, `user_id` (FK + index), `period_start`,
   `period_end` (Date), `expected_delta_kg`, `actual_delta_kg` (Float),
   `factor` (Float), `created_at`. Nowa tabela nie wymaga migracji w
   `app/db.py:_migrate()` — `create_all` ją utworzy.
2. **Serwis.** Nowy plik `app/services/calibration.py`:
   - `compute(db, user_id, period_days=14) -> Calibration | None` — dla okresu
     kończącego się wczoraj: skumulowany bilans z dni **ważnych** (dzień ma
     ≥1 posiłek w `Meal` i `DailySummary.complete == True` z
     `kcal_total_garmin` — dni bez wpisów posiłków wykluczone wg reguły 6.3);
     `expected_delta_kg = suma_bilansów / 7700` (stała `KCAL_PER_KG_FAT`
     z `app/services/balance.py`); `actual_delta_kg` = różnica wygładzonej
     wagi 7d (`energy.smoothed_weight` na oknie kończącym się na końcu i na
     początku okresu). Współczynnik korekty wydatku:
     `factor = (suma_kcal_in − actual_delta_kg·7700) / suma_kcal_out`,
     przycięty do [0.85, 1.15]. Zwróć `None`, gdy < 10 dni ważnych albo brak
     pomiarów wagi na obu końcach okresu.
   - `current_factor(db, user_id) -> float` — `factor` z najnowszego wpisu
     `Calibration` albo `1.0`.
   - `maybe_recalibrate(db, user_id)` — liczy i zapisuje nowy wpis, jeśli
     ostatni jest starszy niż 7 dni (albo nie istnieje); wołane w tle przy
     wejściu na dashboard (wzorzec: `background.add_task`, jak `maybe_sync`
     w `app/main.py`).
3. **Zastosowanie.** W `app/main.py:day_report()`: pobierz
   `factor = calibration.current_factor(db, user_id)` i licz
   `e_target = bal.kcal_out * factor − profile.target_deficit_kcal`
   (dziś: bez factora). Do odpowiedzi dodaj pola `calibration_factor`
   i `calibration_updated` (data ostatniego wpisu) — UI ma pokazywać
   "zapotrzebowanie skorygowane o ±X% względem pomiaru".
4. **UI.** W `app/templates/mobile.html` (jedyny widok dzienny) pokaż korektę
   przy zapotrzebowaniu; w `/trends` (`app/main.py:trends` +
   `app/templates/trends.html`) dodaj do tygodniówki kartę "kalibracja":
   oczekiwana vs rzeczywista zmiana ciężaru i factor (wymóg 6.4).
5. **Transfer.** Kalibracji nie eksportuj w `app/services/transfer.py` —
   po imporcie danych przelicza się z historii (dopisz `maybe_recalibrate`
   po udanym imporcie).
6. **Testy.** `tests/test_calibration.py`: syntetyczne 14 dni (posiłki +
   `DailySummary` complete + `WeightLog`) o znanym bilansie; przypadki:
   zgodność wag → factor ≈ 1.0, waga spada wolniej niż bilans obiecuje →
   factor < 1.0, za mało dni → `None`, clamp na 0.85/1.15. Wszystko musi
   być zielone — czerwony pytest blokuje deploy.

## Integracja z innym zrodlami w zakresie spalanych kcal (??/10)

Apple Watch, Fitbit, Whoop, Oura, Health Connect

## Strefa czasowa użytkownika jako granica dnia — WYMAGANIA.md 8.3 (4/10)

`user_profile.tz` jest zapisywane (`app/main.py:205`) i eksportowane, ale nigdzie
nie używane: wszystkie granice dnia biorą się z `date.today()` procesu, czyli ze
strefy serwera (VM w GCP). Tester w innej strefie widzi „dzisiaj" serwera, a dzień
zamyka mu się (`DailySummary.complete`) w środku jego doby.

**Decyzje (wiążące):** znaczniki czasu w bazie zostają w UTC (`sync_ts`,
`created_at`, `last_used_at`) — zmienia się WYŁĄCZNIE wyliczanie DATY dnia. Strefa
pusta lub nieznana → `Europe/Warsaw` (dotychczasowy default). Nie wprowadzamy
migracji istniejących dat — dane sprzed zmiany zostają, jak są.

**Kroki dla implementującego LLM:**

1. **Nowy `app/services/clock.py`**: `user_tz(profile) -> ZoneInfo` (łap
   `ZoneInfoNotFoundError` → Europe/Warsaw), `user_now(profile) -> datetime`
   (aware), `user_today(profile) -> date`, `user_time(profile) -> time`. Każda
   funkcja przyjmuje `UserProfile | None` — profil może jeszcze nie istnieć
   (rejestracja przed konfiguracją) i wtedy działa fallback.
2. **`app/main.py` — zamień wszystkie zegary procesu** na wersje z profilu:
   linia 449 (`_queue_meal`, godzina wpisu), 479 i 507 (domyślny dzień szacowania
   ze zdjęcia i z tekstu), 547 (`save_meal`, godzina), 717 (data w nazwie pliku
   eksportu), 760 (`trends`), 996 (`add_manual_activity`), 1050
   (`api_trends_data`). Każdy z tych route'ów ma już `user`; profil pobierz przez
   `db.get(UserProfile, user.id)`. `day_report` profil już ma — użyj go zamiast
   dokładać drugie zapytanie.
3. **`app/services/sync.py`** — `sync_range(db, provider, user_id, days=7,
   today: date | None = None)`; `None` zostawia `date.today()` (skrypty CLI),
   a `main.py` i `maybe_sync` przekazują `user_today(profile)`. To `today`
   decyduje o `row.complete = day < today` (linia 46) i o oknie synchronizacji.
   `maybe_sync` otwiera własną sesję — profil dociąga w niej sam.
4. **Walidacja w `put_profile`** (`app/main.py:188`): `ZoneInfo(data.tz)`
   w try/except → 422 przy nieznanej strefie, zamiast cichego zapisu śmiecia.
5. **UI.** `dashboard()` (`app/main.py:593`) przekazuje do szablonu `today =
   user_today(profile)`, a `mobile.html` (linie ~409 i ~413, dziś `new Date()`)
   czyta datę z osadzonej stałej zamiast z zegara przeglądarki — inaczej telefon
   w podróży pokaże inny dzień niż backend liczy. W zakładce Ustawienia
   (`#page-settings`, sekcja Profil) dodaj pole „Strefa czasowa": `<select>`
   z kilkunastoma popularnymi strefami, prefill z
   `Intl.DateTimeFormat().resolvedOptions().timeZone` gdy profil jeszcze nie ma
   ustawionej; zapis istniejącym `PUT /api/profile` (pole `tz` już przyjmuje).
6. **Testy `tests/test_timezone.py`** (bez freezegun — wstrzykuj czas parametrem
   albo monkeypatchem na `clock.user_now`): profil `Pacific/Auckland` o 23:30 UTC
   → `user_today` o dzień dalej niż `date.today()`; `POST /api/meals` bez daty
   ląduje w dniu użytkownika; `sync_range(today=<jutro>)` nie zamyka dnia
   bieżącego; `PUT /api/profile` z `tz: "Mars/Olympus"` → 422; brak profilu →
   Europe/Warsaw.

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja — właściciel.

## Prognoza osiągnięcia celu ciężaru — WYMAGANIA.md 6.4 (3/10)

Trendy pokazują linię celu i „do celu [kg]", ale nie mówią KIEDY. Wymóg 6.4 mówi
o „prognozie osiągnięcia celu" obok wykresu trendu wagi.

**Decyzje (wiążące):** prognoza liczona z FAKTYCZNEGO tempa zmiany wygładzonej
wagi (regresja liniowa po punktach `smoothed` z wybranego okresu), nie z obietnicy
bilansu — bilans kłamie o tyle, o ile kłamie szacowanie posiłków. Bilans jest
fallbackiem, gdy pomiarów wagi jest za mało, i wtedy jawnie opisany w UI jako
„wg bilansu". Prognoza dalsza niż 2 lata nie pokazuje daty.

**Kroki dla implementującego LLM:**

1. **Nowy `app/services/forecast.py`** — `goal_eta(smoothed: list[tuple[date,
   float]], target_kg: float | None, today: date, avg_balance_kcal: float | None
   = None) -> dict | None`:
   - `None`, gdy brak celu albo brak jakichkolwiek danych;
   - tempo z regresji najmniejszych kwadratów po `smoothed` (wymagaj ≥ 6 punktów
     rozłożonych na ≥ 14 dni), w kg/tydzień; `basis="weight"`;
   - fallback `basis="balance"`: `avg_balance_kcal * 7 / KCAL_PER_KG_FAT`
     (stała z `app/services/balance.py`);
   - cel osiągnięty (`current <= target`) → `{"status": "reached"}`;
   - tempo ≥ −0.05 kg/tydz. (stoi albo rośnie) → `{"status": "flat", "rate_kg_per_week"}`
     bez daty;
   - inaczej `{"status": "eta", "rate_kg_per_week", "weeks", "eta_date"}`,
     `weeks = (current − target) / |rate|`, `eta_date = today + weeks·7 dni`;
     `weeks > 104` → `{"status": "far", "rate_kg_per_week"}`.
2. **Podłączenie.** `trends()` (`app/main.py:750`) i `api_trends_data`
   (`app/main.py:1046`) liczą już `smoothed`, `target_weight` i `avg_balance` —
   dołóż `goal_eta(...)` do kontekstu szablonu i do JSON-a (klucz `goal_eta`).
   Nie licz tego drugi raz w `day_report` — prognoza żyje w Trendach.
3. **UI.** `app/templates/trends.html`: czwarty kafelek w `.stats` — data
   (`%d.%m.%Y`) jako duża liczba, pod spodem „prognoza celu · tempo −0.42 kg/tydz.".
   `app/templates/mobile.html` w `renderTrends()`: ten sam kafelek obok
   `#tr-goal-stat`. Teksty stanów, w tonie z sekcji 9.1 (rzeczowo, bez
   wykrzykników): `reached` → „cel osiągnięty", `flat` → „ciężar nie spada —
   prognozy brak", `far` → „przy tym tempie ponad 2 lata", `basis="balance"` →
   dopisek „(wg bilansu, za mało pomiarów ciężaru)".
4. **Testy `tests/test_forecast.py`** (czysto jednostkowe, bez HTTP): seria
   spadająca 0.5 kg/tydz. przez 8 tygodni i cel 4 kg niżej → `weeks ≈ 8`,
   `eta_date` w oknie ±3 dni; seria płaska → `flat`; waga poniżej celu →
   `reached`; 3 punkty → fallback na `avg_balance`, `basis="balance"`; tempo
   −0.01 kg/tydz. przy celu 10 kg niżej → `far`; brak celu → `None`.

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja — właściciel.

## Szyfrowanie sekretów użytkownika: klucze LLM i tokeny Garmina (5/10)

Dziś klucz Gemini/Claude leży w `app_setting.value` PLAINTEXTEM, a tokeny sesji
Garmina jako jawne pliki JSON w `GARMINTOKENS/<user_id>/`. Kopia bazy albo backup
katalogu danych = cudze klucze API i cudza sesja Garmina do wzięcia. Hasło Garmina
nie jest zapisywane (`app/providers/garmin.py:32`) — to zostaje bez zmian.

**Decyzje (wiążące, wybór właściciela 2026-09-03):** szyfrowanie symetryczne
Fernet (`cryptography`), klucz szyfrujący w `/etc/fit-krasnal/env` obok
`FIT_KRASNAL_SECRET_KEY`, ładowany przez systemd `EnvironmentFile`. Świadomie
przyjęty zakres ochrony: chroni kopię bazy, backup i eksport katalogu danych;
NIE chroni przed kimś, kto ma roota na żywej VM. Osobna zmienna, nie pochodna
`SECRET_KEY` — rotacja klucza sesji nie może unieważniać cudzych kluczy API.

**Kroki dla implementującego LLM (w tej kolejności — A jest samodzielne i można
je wypuścić bez B):**

1. **Zależność i konfiguracja.** `cryptography>=42` w `pyproject.toml`.
   W `app/config.py`: `ENC_KEY = os.getenv("FIT_KRASNAL_ENC_KEY")`. Generowanie:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. **`app/services/crypto.py`**: `encrypt(value: str) -> str` zwraca
   `"enc:v1:" + token`; `decrypt(value: str) -> str` przepuszcza bez zmian
   wartość BEZ prefiksu (stary plaintext — to jest ścieżka migracyjna, nie błąd);
   `is_encrypted(value)`. Klucz: `FIT_KRASNAL_ENC_KEY`, a gdy go nie ma i `DEBUG`
   jest włączone — wyprowadź deterministycznie z `SECRET_KEY` (HKDF-SHA256,
   stały salt) żeby lokalny dev i testy działały bez konfiguracji. Gdy nie ma
   klucza i NIE ma `DEBUG` → `RuntimeError` przy starcie (punkt 6).
3. **A: klucze LLM.** `app/services/settings.py` — stała
   `SECRET_SETTING_KEYS = {"gemini_api_key", "anthropic_api_key"}`; `set_setting`
   szyfruje wartość, gdy klucz jest w zbiorze; `get_setting` i `all_settings`
   deszyfrują. `get_llm_keys` i `masked()` działają wtedy bez zmian (dostają już
   jawną wartość). Migracja: `crypto.migrate_plaintext_settings(db)` — bierze
   wiersze z `SECRET_SETTING_KEYS` bez prefiksu i przepisuje zaszyfrowane;
   wywołana w `startup()` (`app/main.py:46`), idempotentna.
4. **B: tokeny Garmina do bazy.** Pliki znikają z dysku — token jedzie jako
   zaszyfrowany blob w `AppSetting` pod kluczem `garmin_tokens` (dopisz go do
   `SECRET_SETTING_KEYS`), a przy każdym użyciu materializuje się do katalogu
   tymczasowego (`tempfile.mkdtemp()`, `chmod 700`, kasowany w `finally`;
   systemd ma `PrivateTmp=true`, więc to jest prywatny tmpfs procesu).
   W `app/providers/garmin.py`: `interactive_login_start` / `interactive_login_mfa`
   po `api.client.dump(tmpdir)` czytają pliki, pakują do jednego JSON-a
   `{nazwa_pliku: treść}` i zapisują przez `settings_service.set_setting`;
   `GarminProvider._client()` odwrotnie — rozpakowuje blob do tmpdir i woła
   `api.login(tmpdir)`; `tokens_present(user_id)` sprawdza wpis w bazie
   (potrzebuje sesji DB — przekaż ją z route'ów, wszystkie trzy miejsca wywołania
   mają `db`). Migracja: przy starcie, jeśli istnieje `garmin_tokens_dir(user_id)`
   z plikami — wciągnij do bazy i skasuj katalog. `garmin_tokens_dir` zostaje
   w `config.py` wyłącznie na potrzeby tej migracji i `scripts/garmin_login.py`.
   Efekt uboczny, o który i tak by trzeba było zadbać: kasowanie konta
   (patrz plan „Usuń moje dane i konto") zabiera tokeny razem z wierszami bazy.
5. **Higiena plików.** `config.ensure_dirs()` — `DATA_DIR` i `PHOTOS_DIR` na
   `chmod 700`, plik bazy po utworzeniu `chmod 600`.
6. **Twarde warunki startowe.** W `startup()`: gdy `not DEBUG` i
   (`SECRET_KEY == DEV_SECRET_KEY` albo brak `FIT_KRASNAL_ENC_KEY`) → `RuntimeError`
   z jasnym komunikatem. Lepiej, żeby proces nie wstał, niż żeby cicho szyfrował
   kluczem deweloperskim.
7. **Sekrety nie mogą wyciec do logów ani do eksportu.** `logger.warning`
   w `app/services/sync.py:99` i `meal_queue.py:139` drukują treść wyjątku —
   biblioteki HTTP potrafią wsadzić w URL klucz API. Dodaj
   `crypto.scrub(text) -> str` (maskuje `AIza[\w-]+`, `sk-ant-[\w-]+`) i przepuść
   przez nią te dwa logi. `transfer.export_payload` sekretów nie eksportuje —
   dopisz test-strażnik, żeby nikt tego nie zmienił przez przypadek.
8. **Wdrożenie i dokumentacja.** `deploy/setup-vm.sh` generuje
   `FIT_KRASNAL_ENC_KEY` obok `FIT_KRASNAL_SECRET_KEY` (linia ~45);
   `deploy/README.md` — akapit „rotacja klucza szyfrującego" (skrypt
   `scripts/rotate_enc_key.py`: odszyfruj starym, zaszyfruj nowym, w jednej
   transakcji); `.env.example` — nowa zmienna z instrukcją generowania;
   `CLAUDE.md` — konwencja „sekrety użytkownika trzymamy tylko przez
   `settings_service`, nigdy wprost w `AppSetting`". **Uwaga przy wdrożeniu
   punktu 4:** istniejący testerzy mają aktywne sesje Garmina — migracja musi
   przejść, zanim skasujesz katalogi; jak nie przejdzie, ludzie muszą logować
   się do Garmina od nowa (z MFA).
9. **Testy `tests/test_crypto.py`**: round-trip `encrypt`/`decrypt`;
   `decrypt` na plaintekście zwraca go bez zmian; wartość w bazie po
   `set_setting` NIE zawiera jawnego klucza (czytaj wiersz surowym SQL-em);
   `migrate_plaintext_settings` przepisuje stary wiersz i jest idempotentna;
   `scrub` maskuje oba formaty kluczy; eksport transferu nie zawiera ciągu
   `gemini_api_key` ani wartości klucza. Do B: `tokens_present` po zapisie bloba
   → `True`, katalog na dysku nie powstaje.

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja — właściciel
(pamiętaj: bez `FIT_KRASNAL_ENC_KEY` w `/etc/fit-krasnal/env` proces po deployu
NIE wstanie — to celowe, ale trzeba ustawić zmienną PRZED pushem).

## „Usuń moje dane i konto" w Ustawieniach (6/10)

Zastępuje i konsoliduje dwa wcześniejsze punkty tej listy („Kasowanie konta
z 7-dniowym oknem odzyskania" i „Kasowanie danych z konta — czyszczenie
historii"). Wymóg wprost z WYMAGANIA.md 8.3 (prawo do usunięcia) i warunek
wyjścia pilota poza grono znajomych.

**Decyzje (wiążące, wybór właściciela 2026-09-03):** soft-delete z oknem
odzyskania — konto **7 dni**, sama historia **3 dni**. Dane znikają z aplikacji
NATYCHMIAST; przez okno odzyskania administrator potrafi je przywrócić na prośbę
użytkownika; potem kasacja jest bezpowrotna. Użytkownikowi mówimy o tym wprost
(nie udajemy, że dane wyparowały w tej samej sekundzie — to byłoby kłamstwo
wobec RODO i wobec niego).

**Mechanika (wiążąca):** nie filtrujemy zapytań po `deleted_at` w kilkudziesięciu
miejscach. Zamiast tego kasujemy wiersze naprawdę, a przed kasacją zrzucamy je do
pliku kopii w formacie transferu — czyli tym samym, który już umiemy wczytać.
Odzysk = `transfer.import_payload` z tego pliku.

**Kroki dla implementującego LLM:**

1. **Model.** W `app/models.py`: `User.deleted_at: Mapped[datetime | None]`
   (migracja addytywna w `app/db.py:_migrate()`, wzorzec `password_hash`) oraz
   tabela `DeletionRequest(id, user_id, kind, requested_at, purge_after,
   snapshot_path, original_email, done_at)`, `kind` ∈ `{"data", "account"}`
   (nowa tabela — `create_all` ją utworzy, migracja niepotrzebna).
2. **Serwis `app/services/erasure.py`**:
   - `wipe_data(db, user_id) -> DeletionRequest` — zrzuca
     `transfer.export_payload(db, user_id)` do
     `DATA_DIR/trash/<user_id>-<ts>.json` (`chmod 600`, katalog `700`), potem
     kasuje wiersze użytkownika: `Meal`, `PendingMeal` (+ pliki zdjęć przez
     `meal_queue._delete_photo`), `SavedMeal`, `WeightLog`, `DailySummary`,
     `Activity`. Profil i konto ZOSTAJĄ. `purge_after = teraz + 3 dni`.
   - `delete_account(db, user_id)` — to samo, plus: kasuje `UserProfile`,
     `AppSetting` (czyli i klucze LLM, i tokeny Garmina po wdrożeniu planu
     szyfrowania; do tego czasu skasuj też katalog `garmin_tokens_dir(user_id)`),
     ustawia `User.deleted_at`, zapisuje `original_email` w `DeletionRequest`
     i podmienia `user.email` na `deleted+<id>+<oryginał>` — dzięki temu adres
     jest natychmiast wolny (unikat na `user.email`), a tester może założyć konto
     od nowa. `purge_after = teraz + 7 dni`.
   - `purge_due(db, now)` — kasuje pliki kopii, których `purge_after` minął,
     i twardo usuwa wiersze `user` dla `kind="account"`; stempluje `done_at`.
3. **API w `app/main.py`** (obok pozostałych route'ów konta):
   - `POST /api/account/wipe-data` — body `{password, confirm}`; `confirm` musi
     być dokładnie `"USUWAM"`, hasło sprawdzane `auth.verify_password` (403 przy
     złym — to jedyna bariera przed kliknięciem z cudzej, niezablokowanej
     przeglądarki); zwraca liczniki skasowanych wierszy.
   - `POST /api/account/delete` — jak wyżej + `auth.logout_user(request)`.
   - `auth.current_user` (`app/auth.py:83`) i `login_submit` odrzucają konto
     z `deleted_at` (401 / komunikat „konto zostało skasowane").
4. **UI.** Karta „Twoje dane" w `app/templates/settings.html` (przed kartą
   „Kontakt") i w zakładce Ustawienia `app/templates/mobile.html` (sekcja
   „Konto"): dwa przyciski w kolorze `danger` — „Usuń historię (posiłki, ciężar,
   aktywności)" i „Usuń konto i wszystkie dane". Każdy otwiera potwierdzenie
   z polem hasła i polem, w które trzeba wpisać `USUWAM`. Pod przyciskami zdanie
   bez upiększeń: „Dane znikają z aplikacji natychmiast. Przez 3 dni (historia)
   / 7 dni (konto) administrator może je odtworzyć na Twoją prośbę — potem są
   kasowane bezpowrotnie." Obok link do eksportu (`/api/transfer/export`) —
   „pobierz swoje dane, zanim je skasujesz".
5. **Skrypty i timer.** `scripts/purge_deleted.py` (woła `purge_due`, loguje co
   skasował) + `deploy/fit-krasnal-purge.service` i `.timer` (codziennie 03:00,
   `OnCalendar=*-*-* 03:00:00`, `Persistent=true`), instalowane w
   `deploy/setup-vm.sh` i opisane w `deploy/README.md`.
   `scripts/restore_deleted.py <email|user_id>` — znajduje kopię, tworzy konto,
   jeśli trzeba, i wczytuje przez `transfer.import_payload`.
6. **Testy `tests/test_erasure.py`** (wzorzec `clients` z
   `tests/test_saved_meals_api.py`): pełny cykl — posiłki i wagi → `wipe-data`
   → `/api/day` bez posiłków, plik kopii istnieje → `restore` przez
   `import_payload` wraca do stanu sprzed; `delete` → logowanie odbite,
   e-mail wolny (rejestracja tym samym adresem przechodzi); złe hasło → 403,
   nic nie skasowane; brak `confirm` → 422; kasowanie usera A nie tyka danych
   usera B; `purge_due` po `purge_after` kasuje plik i wiersz `user`, przed
   terminem nie rusza nic.

Weryfikacja: pełny pytest zielony → commit + push. Po deployu właściciel
sprawdza, że timer jest aktywny (`systemctl list-timers | grep purge`).

## RODO: informacja, zgoda na wysyłkę zdjęć do LLM, retencja (4/10)

Aplikacja przetwarza dane o zdrowiu (art. 9 RODO) dla ~10 osób i wysyła zdjęcia
posiłków do Google/Anthropic — dziś bez jednego zdania informacji i bez zgody.
WYMAGANIA.md 8.3 stawiały to jako warunek przed wersją multi-user; pilot ruszył
wcześniej, więc to jest dług do spłacenia, nie nowa funkcja.

**Decyzje (wiążące, wybór właściciela 2026-09-03):** zakres proporcjonalny do
pilota — nota informacyjna („co zbieramy, gdzie to leci, jak skasować"), JEDNA
wyraźna zgoda na wysyłanie zdjęć i opisów posiłków do zewnętrznego modelu, jawne
okresy retencji i działające kasowanie (osobny plan wyżej). BEZ rejestru
czynności przetwarzania, BEZ DPIA, BEZ analizy umów powierzenia. Istniejący
testerzy: **baner z terminem 14 dni**, po terminie twarda bramka.

**Kroki dla implementującego LLM:**

1. **Nota informacyjna.** `app/templates/privacy.html` + route
   `GET /prywatnosc` BEZ auth (jest linkowana z logowania i rejestracji).
   Treść, konkretnie i po ludzku: jakie dane zbieramy (profil, ciężar/kroki/kcal
   z Garmina, posiłki, zdjęcia); dokąd trafiają zdjęcia i opisy (Google Gemini
   albo Anthropic, poza EOG, wyłącznie na czas analizy — sprawdź i przytocz
   aktualny zapis regulaminów API o nietrenowaniu na danych z płatnego/AI Studio
   API, z datą sprawdzenia); gdzie leżą dane (VM w GCP, region z
   `deploy/README.md`); kto ma dostęp (właściciel jako administrator); okresy
   retencji (kolejka 21 dni — `meal_queue.RETENTION_DAYS`; zdjęcia kasowane
   zaraz po analizie; kopia po skasowaniu 3/7 dni; logi 30 dni); prawa
   (eksport i kasowanie — przyciskami w Ustawieniach, bez pisania maili);
   kontakt `krasnal@krasnal.cc`. Link w stopce `login.html`, `register.html`,
   `settings.html` i zakładki Ustawienia w `mobile.html`.
2. **Wersjonowanie i model.** `PRIVACY_VERSION = "2026-09-03"` w
   `app/config.py`; tabela `Consent(id, user_id, kind, version, granted_at,
   withdrawn_at)` w `app/models.py`, `kind` na dziś jedno: `"llm_photos"`
   (`create_all` wystarczy). Helper `app/services/consent.py`:
   `has_consent(db, user_id, kind) -> bool` (jest wpis w bieżącej wersji i nie
   jest wycofany), `grant`, `withdraw`.
3. **Rejestracja.** W `register.html` checkbox (NIEzaznaczony domyślnie):
   „Zgadzam się, żeby zdjęcia i opisy moich posiłków były wysyłane do
   zewnętrznego modelu (Google Gemini albo Anthropic) w celu oszacowania
   kalorii" + link do `/prywatnosc`. Zgoda jest DOBROWOLNA: bez niej konto
   działa, tylko bez szacowania z LLM (ręczny wpis posiłku i „moje posiłki"
   zostają). `register_submit` (`app/main.py:141`) zapisuje `Consent` gdy
   zaznaczony.
4. **Egzekwowanie.** Zależność `require_consent("llm_photos")` na
   `POST /api/meals/photo` i `POST /api/meals/text` → 409 z komunikatem
   „Brak zgody na wysyłanie zdjęć do zewnętrznego modelu — włącz ją
   w Ustawieniach"; `meal_queue.process_queue` przerywa dla użytkownika bez
   zgody (jak przy braku klucza). W `mobile.html` bez zgody chowaj ścieżkę
   zdjęcia i opisu, zostaw „wpisz wartości ręcznie" i „moje posiłki",
   z jednym zdaniem dlaczego i linkiem do Ustawień.
5. **Przełącznik w Ustawieniach.** Karta „Prywatność": stan zgody, data,
   wersja, przycisk włącz/wycofaj oraz link do noty. Wycofanie: `withdrawn_at`,
   wyłączenie ścieżek LLM i skasowanie oczekujących wpisów kolejki wraz ze
   zdjęciami (`meal_queue.delete_pending` dla wszystkich `PendingMeal` usera) —
   inaczej zostawiamy w kolejce zdjęcia, których nie wolno już wysłać.
6. **Istniejący testerzy — baner, potem bramka.** `CONSENT_DEADLINE` w
   `app/config.py` (data wdrożenia + 14 dni). Kto nie ma zgody w bieżącej
   wersji, widzi na górze `mobile.html` baner: „Doprecyzowaliśmy, co dzieje się
   z Twoimi danymi. Zapoznaj się i zdecyduj do <data>" + link do `/prywatnosc`
   i do karty Prywatność. Po `CONSENT_DEADLINE` ścieżki LLM są zablokowane
   niezależnie od decyzji (punkt 4 działa od razu — przed terminem też, bo
   zgody po prostu nie ma; baner jest po to, żeby człowiek wiedział, dlaczego
   przestało działać szacowanie).
7. **Retencja w kodzie, nie tylko w tekście.** Sprawdź, że `purge_expired`
   faktycznie leci przy starcie (`app/main.py:54`) i przy każdym przetwarzaniu
   kolejki — jeśli nikt nie wejdzie do aplikacji przez miesiąc, wpisy przeterminowane
   wiszą; dorzuć wywołanie do timera z planu kasowania konta
   (`scripts/purge_deleted.py` woła też `meal_queue.purge_expired`). Logi:
   ustaw `MaxRetentionSec=30day` dla journald usługi w
   `deploy/fit-krasnal.service` (albo logrotate) i opisz to w nocie.
8. **Testy `tests/test_consent.py`**: `/prywatnosc` odpowiada 200 bez
   logowania; rejestracja bez checkboxa → konto jest, zgody nie ma;
   `POST /api/meals/photo` bez zgody → 409, po `grant` → normalna ścieżka
   (LLM zamockowany jak w `tests/test_meal_vision.py`); wycofanie zgody kasuje
   `PendingMeal` i pliki zdjęć; zgoda zapisana w starszej wersji niż
   `PRIVACY_VERSION` liczy się jak brak zgody; `process_queue` bez zgody nie
   przetwarza nic.

Weryfikacja: pełny pytest zielony → commit + push. Treść noty przed wdrożeniem
czyta właściciel — to jedyny punkt, którego LLM nie powinien wypuścić na
produkcję bez przeczytania przez człowieka.

## Rok urodzenia zamiast pełnej daty — minimalizacja danych (3/10)

**Ustalenie faktów (sprawdzone w kodzie 2026-09-03, nie zgaduj inaczej):**
`user_profile.birth_date` jest czytane w DOKŁADNIE dwóch miejscach —
`app/main.py:329` i `app/main.py:353` — i oba wołają `energy.age_years`, którego
wynik idzie do:

- `bmr_mifflin` (`app/services/energy.py:14`), człon `− 5 · wiek` → **jeden rok
  wieku to 5 kcal BMR**, przy ~2400 kcal wydatku to 0.2%, przy błędzie
  szacowania posiłków ±25–40% (setki kcal) — szum;
- `macros.resolve_norms` → grupa wiekowa `adult 18–64` / `senior 65+`
  (podbite minimum białka wg PROT-AGE).

Nic więcej. Żadnego pola, wykresu ani reguły opartej o dzień czy miesiąc
urodzenia. **Rok wystarcza; miesiąc nie wnosi nic mierzalnego.** Odwrotnie niż
przy większości pól: pełna data urodzenia to silny identyfikator (w połączeniu
z e-mailem i danymi o zdrowiu), rok jest znacznie słabszy — trzymanie jej bez
zastosowania to gromadzenie danych na zapas. To jest argument główny, dokładność
jest tylko przy okazji.

**Decyzje (wiążące):**

- Profil trzyma `birth_year: int`. Pełna data znika z formularzy, z API
  i z eksportu.
- Wiek liczony konwencją **środka roku** (tak, jakby każdy rodził się 1 lipca):
  błąd ≤ 1 rok, bez systematycznego przesunięcia w żadną stronę. Prostsze
  `day.year − birth_year` też by wystarczyło, ale zawyża wiek średnio o pół roku
  u wszystkich urodzonych po lipcu — przy progu 65+ wolimy błąd symetryczny.
- Kolumna `birth_date` w SQLite ZOSTAJE (konwencja repo: migracje wyłącznie
  addytywne, `app/db.py:_migrate()`), ale przestaje cokolwiek znaczyć — zapisujemy
  w niej `date(birth_year, 7, 1)` jako wartość pochodną, z komentarzem przy
  modelu. Faktyczne usunięcie kolumny to osobne zadanie na kiedyś, po przebudowie
  tabeli; nie robimy go przy okazji.

**Kroki dla implementującego LLM:**

1. **Model i migracja.** W `app/models.py` do `UserProfile` dodaj
   `birth_year: Mapped[int | None] = mapped_column(Integer)`; przy `birth_date`
   dopisz komentarz „legacy: pochodna `birth_year` (1 lipca), nieczytana przez
   kod". W `app/db.py:_migrate()` addytywnie, wzorzec jak `target_weight_kg`:
   `PRAGMA table_info(user_profile)` → `ALTER TABLE user_profile ADD COLUMN
   birth_year INTEGER` → backfill
   `UPDATE user_profile SET birth_year = CAST(strftime('%Y', birth_date) AS INTEGER)
   WHERE birth_year IS NULL`. Istniejący testerzy nie muszą nic klikać.
2. **`app/services/energy.py`** — nowa `age_from_year(birth_year: int,
   on_date: date) -> int`: `on_date.year − birth_year − (0 if (on_date.month,
   on_date.day) >= (7, 1) else 1)`. `age_years` zostaje (używa jej
   `tests/test_energy.py` i mogą skrypty), ale w aplikacji nie ma już wywołań —
   dopisz w docstringu, że to funkcja pomocnicza, a profil operuje na roku.
3. **`app/main.py`** — `ProfileIn`: `birth_year: int`, `birth_date: date | None
   = None` zostawione WYŁĄCZNIE jako wejście zgodnościowe (stary klient
   z cache'a, stary plik transferu): gdy `birth_year` nie podano, a jest
   `birth_date`, weź z niej rok; gdy nie ma żadnego → 422. Walidacja zakresu:
   `date.today().year − 120 <= birth_year <= date.today().year − 13`
   (dolna granica to zdrowy rozsądek, nie regulamin). W `put_profile`
   (linia 188) zapisuj `profile.birth_year` oraz `profile.birth_date =
   date(birth_year, 7, 1)`. Linie 329 i 353 → `age_from_year(profile.birth_year,
   day)`. Route `/profile-form` (linia 1122): `birth_year: int = Form(...)`.
4. **`GET /api/profile`** zwraca dziś surowy obiekt ORM, więc po migracji
   wystawiłby oba pola. Dodaj model odpowiedzi (albo ręczny dict) zwracający
   `birth_year`, `sex`, `height_cm`, `target_deficit_kcal`, `target_weight_kg`,
   `lifestyle`, `tz` — bez `birth_date`. Minimalizacja dotyczy też tego, co
   aplikacja o sobie opowiada.
5. **UI** (`app/templates/mobile.html`): linia 319 — `<input type="date"
   id="s-birth">` na `<input type="number" id="s-birth-year" min="1900"
   max="…" step="1" inputmode="numeric" placeholder="np. 1985">` z etykietą
   „Rok urodzenia"; linia 865 (prefill) → `profile.birth_year`; linia 890
   (zapis) → `birth_year: Number(...)`. Pod polem jedno zdanie, w tonie sekcji
   9.1: „Wiek wpływa tylko na przemianę spoczynkową (5 kcal na rok) i na próg
   65+ w normach — dokładna data nie jest nam potrzebna". To jest tani sygnał
   zaufania i warto go pokazać.
6. **Transfer** (`app/services/transfer.py:53` i `:116`): eksport zapisuje
   `birth_year` i PRZESTAJE zapisywać `birth_date`; import bierze `birth_year`,
   a gdy go nie ma (stary plik) — rok z `birth_date`. `FORMAT`/`VERSION` bez
   zmian: to rozszerzenie zgodne wstecz, nie nowy format.
7. **Powiązania.** Nota `/prywatnosc` z planu RODO wymienia „rok urodzenia",
   nie datę — jeśli ten punkt robisz po tamtym, popraw treść noty. Decyzję
   dopisz do `CLAUDE.md` (sekcja „Kluczowe konwencje"), NIE do `WYMAGANIA.md`
   — ten plik jest zapisem pierwotnego kontraktu (3.1 mówi o dacie urodzenia)
   i zgodnie z własną adnotacją nie jest aktualizowany do stanu kodu.
8. **Testy.** `tests/test_energy.py`: `age_from_year` przed i po 1 lipca
   (1985 → 40 w czerwcu 2026, 41 w lipcu 2026); różnica BMR między wiekiem
   z roku a wiekiem z pełnej daty ≤ 5 kcal dla tego samego człowieka.
   `tests/test_macros.py` albo nowy: rocznik dający 65 lat wpada w grupę
   `senior`, rocznik o rok młodszy w `adult`. Nowy test migracji w duchu
   strażnika z `tests/test_activities_api.py`: zbuduj `user_profile` STARYM
   DDL-em (bez `birth_year`, z `birth_date`), wywołaj `app.db._migrate(engine)`,
   sprawdź, że `birth_year` jest wypełniony rokiem z daty i że ORM-owy
   `select(UserProfile)` działa. API: `PUT /api/profile` z samym `birth_year`
   → 200 i poprawny wiek w `/api/day`; ze starym `birth_date` → też 200
   (zgodność); `birth_year: 1850` i `birth_year: <rok+1>` → 422; round-trip
   transferu w obie strony (nowy plik i stary plik z `birth_date`).

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja —
właściciel.

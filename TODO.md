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

Weryfikacja: pełny pytest zielony → commit + push. Deploy i produkcja — właściciel.

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

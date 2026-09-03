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

**Zasada dla implementującego LLM (dowolny punkt z tej listy):** jeśli
realizowana zmiana wpływa na to, co i jak aplikacja zbiera, przetwarza,
wysyła albo przechowuje (nowe dane, nowe miejsce ich wysyłki, zmiana okresu
retencji, zmiana zakresu zgody) — zaktualizuj `app/templates/privacy.html`
w tym samym zadaniu i odnotuj to wprost we wpisie w [DONE.md](DONE.md)
(„nota `/prywatnosc` zaktualizowana — co się zmieniło"). Nota ma zostać
zgodna ze stanem kodu, nie z pamięcią z dnia jej napisania.

**Zasada dla implementującego LLM (uruchamianie testów):** pełną suitę
testów (`pytest` bez filtra na konkretny plik) puszczaj dopiero po zgodzie
właściciela — nie automatycznie po skończeniu implementacji. Testy nowego/
zmienianego pliku (np. `pytest tests/test_usage.py`) można odpalać na
bieżąco w trakcie pracy.

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

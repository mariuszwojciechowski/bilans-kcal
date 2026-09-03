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

## Mapa braków względem WYMAGANIA.md (audyt 2026-09-03)

Przegląd całego kontraktu z [WYMAGANIA.md](WYMAGANIA.md) przeciw stanowi kodu.
Moduły M1-M11 są zrobione (patrz [DONE.md](DONE.md)); poniżej wyłącznie to,
czego nie ma. Kolumna „gdzie plan" wskazuje punkt tej listy — **jeśli punkt
istnieje, nie dopisuj drugiego planu na to samo**, bo się rozjadą.

| Wymóg | Stan | Gdzie plan |
|---|---|---|
| 6.2 Kalibracja adaptacyjna | brak tabeli `Calibration`; `day_report` liczy `e_target = kcal_out − deficyt` bez współczynnika (`app/routers/day.py:day_report()`) | „Kalibracja adaptacyjna" (6/10) |
| 6.4 Karta kalibracji w tygodniówce | pochodna 6.2 — średni bilans i ETA celu w `/trends` są | krok 4 planu kalibracji |
| 8.3 Strefa czasowa jako granica dnia | `user_profile.tz` zapisywane i eksportowane, nieczytane — wszędzie `date.today()` procesu | „Strefa czasowa użytkownika…" (4/10) |
| 8.3 Prawo do usunięcia (samoobsługowe) | realizowane mailem; nota `/prywatnosc` mówi o tym wprost, więc nie jest to kłamstwo — tylko brak | „«Usuń moje dane i konto»…" (6/10) |
| §4 Tabela MET konfigurowalna | MET to stałe w `app/services/energy.py` (43-45, 131-137), w przeciwieństwie do norm WHO wyniesionych do JSON | „Tabela MET jako dane…" (3/10) |
| §10.2 Cel redukcyjny białka | `protein_cut_g_per_kg` leży w `who_norms.json`, ale nic go nie czyta | „Cel redukcyjny białka…" (2/10) |
| §10.3 Nazwa pakietu / domena mobilna | nie zarezerwowane | „Nazwa pakietu i domena…" (1/10) |
| Etap 2 — aplikacja mobilna | poza MVP, nie rozpoczęta | „Aplikacja mobilna (Etap 2)…" (10/10) |

§10.1 (retencja zdjęć posiłków) jest **rozstrzygnięte**: zdjęcie po udanym
oszacowaniu kasowane od razu, w kolejce leży maks. 21 dni
(`app/services/meal_queue.py`) — zapisane w nocie `/prywatnosc`.

Odstępstwa świadome, nie braki: rok urodzenia zamiast pełnej daty (3.1 jest
w tym miejscu nieaktualne — patrz [CLAUDE.md](CLAUDE.md)), ręczny wpis wagi
i kroków w widoku mobilnym (odstępstwo od D3), wycofana paczka PWA (M10).

---

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


## Tabela MET jako dane, nie kod — WYMAGANIA.md §4 (3/10)

§4 wymaga: „Tabela MET konfigurowalna (Compendium of Physical Activities)".
Dziś każdy współczynnik jest stałą w `app/services/energy.py` i jego zmiana
wymaga commita: `KCAL_PER_STEP_PER_KG` (40), `MET_STRENGTH` (43),
`MET_CYCLING_BY_SPEED_KMH` (44), `MET_DEFAULT` (45), 1400 kroków/km (118),
`DEFAULT_STEPS` (128), `MANUAL_MET` (131-137), `INTENSITY_MAP` (139),
mnożnik marszu 0.53 (162). Normy WHO są już wyniesione do
`app/resources/who_norms.json` — ten punkt robi z MET to samo.

**Decyzje (wiążące):** wartości liczbowe zostają **identyczne** — to
refaktoryzacja bez zmiany wyników, więc `tests/test_energy.py` musi przejść
**bez modyfikacji** (jeśli któryś test padnie, znaczy że wartość się zmieniła
przy przenoszeniu — cofnij, nie poprawiaj testu). Plik jest jedynym źródłem
prawdy: nie zostawiamy „awaryjnych" wartości w kodzie, brak pliku = błąd, tak
samo jak przy `who_norms.json`.

**Kroki dla implementującego LLM:**

1. **Nowy `app/resources/met_table.json`** wg wzorca `who_norms.json`: blok
   `meta` (`fetched`, `sources` — Compendium of Physical Activities /
   Ainsworth i in. — oraz jawna nota, które wartości są uproszczeniem
   właściciela, a nie cytatem z Compendium) i sekcje:
   - `steps`: `kcal_per_step_per_kg: 0.00057`, `steps_per_km: 1400`,
     `default_steps: 5000`,
   - `distance`: `running_kcal_per_kg_per_km: 1.0`,
     `walking_kcal_per_kg_per_km: 0.53`,
   - `cycling`: `met_by_speed_kmh: [[16.0, 6.0], [20.0, 8.0], [null, 10.0]]`
     (`null` = brak górnej granicy, loader zamienia na `inf`),
   - `garmin_types`: mapa fragmentu `typeKey` → MET dla `activity_kcal_model`
     (`strength`/`training` → 4.0) plus `default_met: 5.0`,
   - `manual`: per typ (`running`, `cycling`, `walking`, `swimming`,
     `strength_training`) trójka `[lekka, umiarkowana, intensywna]` plus
     `intensity_order: ["lekka", "umiarkowana", "intensywna"]`.
2. **Loader w `app/services/energy.py`**: `MET_PATH` + `@lru_cache(maxsize=1)
   def _met() -> dict` — dokładnie wzorzec `macros._norms()`
   (`app/services/macros.py:18-23`). `neat_from_steps`, `running_kcal`,
   `cycling_met`, `activity_kcal_model`, `manual_activity_kcal`,
   `tdee_theoretical` czytają `_met()` zamiast stałych.
3. **Zachowaj publiczne nazwy.** `DEFAULT_STEPS` jest importowany w trzech
   miejscach (`app/routers/day.py`, `tests/test_activities_api.py:17`,
   `tests/test_queue_settings.py:147`) — zostaw jako stałą modułu
   inicjalizowaną z pliku (`DEFAULT_STEPS = _met()["steps"]["default_steps"]`),
   nie kasuj. Sygnatury funkcji bez zmian — `manual_activity_kcal` woła
   `app/routers/day.py:add_manual_activity()` i cztery pliki testów.
4. **Testy `tests/test_met_table.py`**: plik wczytuje się i ma `meta.sources`;
   każdy typ w `manual` ma trzy intensywności; progi `cycling` są rosnące,
   a ostatni to `null`; monkeypatch `MET_PATH` na plik z innym `default_met`
   + `_met.cache_clear()` zmienia wynik `activity_kcal_model` dla nieznanego
   typu (dowód, że wartości naprawdę idą z pliku, a nie z kodu).

Weryfikacja: pełny pytest zielony → commit + push. Nota `/prywatnosc` bez
zmian — liczymy to samo, z tych samych danych.

## Cel redukcyjny białka — domyślnie czy opt-in? — WYMAGANIA.md §10.2 (2/10)

Pytanie otwarte §10.2: czy „cel redukcyjny" białka 1.2-1.6 g/kg pokazywać
domyślnie obok normy WHO, czy jako opcję. Stan faktyczny: `who_norms.json` ma
per grupę pole `protein_cut_g_per_kg: [1.2, 1.6]`, ale **nic go nie czyta** —
`app/services/macros.py` bierze zakres białka wyłącznie ze stylu życia
(`protein_range_g_per_kg`), a `protein_who_min_g` pokazuje obok jako punkt
odniesienia. Dla stylu „rekreacyjnie trenujący" zakres 1.2-1.6 i tak wychodzi,
tylko z innego powodu — a pole w JSON jest martwe.

**Do decyzji właściciela (bez tego nie implementuj) — jeden z dwóch:**

- **(a) zamknąć przez styl życia**: usunąć martwe `protein_cut_g_per_kg`
  z `app/resources/who_norms.json` (dwie grupy) i z fixture
  `tests/test_macros.py:62`. Pół godziny, mniej martwego kodu.
- **(b) trzeci znacznik na pasku białka**: `who_targets` zwraca dodatkowo
  `protein_cut_g` z tego pola, `coverage()["protein"]` dostaje klucz
  `cut_range_g`, a `app/templates/mobile.html` (pasek białka, ~595) rysuje go
  inną kreską niż zakres normy. Sens ma tylko, jeśli uznasz, że zakres ze
  stylu życia jest przy deficycie mylący.

Nota `/prywatnosc` niezmieniona w obu wariantach.

## Nazwa pakietu i domena pod wydanie mobilne — WYMAGANIA.md §10.3 (1/10)

Pytanie otwarte §10.3, do rezerwacji **zanim** cokolwiek pójdzie do sklepów:
identyfikator aplikacji (np. `pl.fitkrasnal.app` albo `cc.krasnal.fit` —
zgodny z posiadaną domeną) plus decyzja, czy backend zostaje na
`fit.krasnal.cc`. Identyfikatora pakietu w Google Play **nie da się później
zmienić**: zmiana = nowa aplikacja i utrata wszystkich instalacji. Zadanie
administracyjne, bez kodu — sprawdzić dostępność w Play Console (i App Store
Connect, jeśli iOS w planie), zarezerwować, zapisać wybór tutaj oraz
w [deploy/README.md](deploy/README.md).

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
     w `app/routers/dashboard.py`).
3. **Zastosowanie.** W `app/routers/day.py:day_report()`: pobierz
   `factor = calibration.current_factor(db, user_id)` i licz
   `e_target = bal.kcal_out * factor − profile.target_deficit_kcal`
   (dziś: bez factora). Do odpowiedzi dodaj pola `calibration_factor`
   i `calibration_updated` (data ostatniego wpisu) — UI ma pokazywać
   "zapotrzebowanie skorygowane o ±X% względem pomiaru".
4. **UI.** W `app/templates/mobile.html` (jedyny widok dzienny) pokaż korektę
   przy zapotrzebowaniu; w `/trends` (`app/routers/trends.py:trends()` +
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

`user_profile.tz` jest zapisywane (`app/routers/profile.py:ProfileIn`) i eksportowane, ale nigdzie
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
2. **Routery — zamień wszystkie zegary procesu** na wersje z profilu:
   `app/routers/meals.py` (`_queue_meal` — godzina wpisu; `estimate_meal_photo`
   i `estimate_meal_text` — domyślny dzień szacowania; `save_meal` — godzina),
   `app/routers/transfer.py` (`transfer_export` — data w nazwie pliku eksportu),
   `app/routers/trends.py` (`trends`, `api_trends_data`), `app/routers/day.py`
   (`add_manual_activity`). Każdy z tych route'ów ma już `user`; profil pobierz
   przez `db.get(UserProfile, user.id)`. `day_report` profil już ma — użyj go
   zamiast dokładać drugie zapytanie.
3. **`app/services/sync.py`** — `sync_range(db, provider, user_id, days=7,
   today: date | None = None)`; `None` zostawia `date.today()` (skrypty CLI),
   a `app/routers/profile.py:sync()` i `maybe_sync` przekazują
   `user_today(profile)`. To `today` decyduje o `row.complete = day < today`
   (linia 46) i o oknie synchronizacji. `maybe_sync` otwiera własną sesję —
   profil dociąga w niej sam.
4. **Walidacja w `put_profile`** (`app/routers/profile.py`): `ZoneInfo(data.tz)`
   w try/except → 422 przy nieznanej strefie, zamiast cichego zapisu śmiecia.
5. **UI.** `dashboard()` (`app/routers/dashboard.py`) przekazuje do szablonu `today =
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
3. **API w `app/routers/auth.py`** (obok pozostałych route'ów konta —
   login/register/logout):
   - `POST /api/account/wipe-data` — body `{password, confirm}`; `confirm` musi
     być dokładnie `"USUWAM"`, hasło sprawdzane `auth.verify_password` (403 przy
     złym — to jedyna bariera przed kliknięciem z cudzej, niezablokowanej
     przeglądarki); zwraca liczniki skasowanych wierszy.
   - `POST /api/account/delete` — jak wyżej + `auth.logout_user(request)`.
   - `auth.current_user` (`app/auth.py`) i `login_submit`
     (`app/routers/auth.py`) odrzucają konto
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

## Aplikacja mobilna (Etap 2) — Flutter — WYMAGANIA.md 8.2 / D7 (10/10)

Etap 2 z wymagań: jeden kod na Android + iOS, backend zostaje źródłem prawdy
(sync, kalibracja, LLM), a apka dostarcza dane zdrowotne z urządzenia zamiast
nieoficjalnego API Garmina. Ten punkt świadomie **nie jest** planem
implementacji — przed startem trzeba osobnego planu, bo połowa pracy leży poza
kodem apki. Istnieje, żeby nie zgubić warunków wejścia.

**Warunki wstępne po stronie backendu (dziś niespełnione):**

1. **Uwierzytelnianie inne niż ciasteczko.** `app/auth.py` trzyma sesję
   w podpisanym ciasteczku (`SessionMiddleware`) — klient mobilny potrzebuje
   tokenu urządzenia (tabela tokenów + nagłówek `Authorization`, unieważnianie
   per urządzenie). To przebudowa `current_user`, nie dopisek.
2. **Strefa czasowa użytkownika** — telefon jeździ po strefach, a dziś dzień
   liczy się ze strefy serwera. Bez tego apka pokaże inny dzień, niż backend
   policzy. Patrz punkt „Strefa czasowa użytkownika…".
3. **Kasowanie konta i danych z poziomu aplikacji** — wymóg regulaminowy
   Google Play (ścieżka usunięcia konta w apce **i** przez stronę). Patrz
   punkt „«Usuń moje dane i konto»…".
4. **Health Connect / HealthKit zamiast `garminconnect`.** Interfejs
   `app/providers/DataProvider` jest już na to przygotowany
   (`get_daily_summary`, `get_weight`, `get_activities`) — D4 był świadomym
   długiem MVP, formalnie poza ToS Garmina. Pakiet `health` po stronie Fluttera.
5. **Nazwa pakietu** — nieodwracalna, patrz punkt „Nazwa pakietu i domena…".
6. **Formularze sklepowe.** `/prywatnosc` już jest publiczną notą, ale sklepy
   wymagają osobno *Data safety* (Play) / *App Privacy* (App Store) spójnych
   z jej treścią. Dane zdrowotne to kategoria wrażliwa — dodatkowe
   oświadczenia i zwykle dłuższa weryfikacja.

**Kolejność wg wartości:** punkty 2 i 3 są potrzebne również w webie i mają
już plany — rób je niezależnie od decyzji o mobile. 1 i 4 to dopiero start
Etapu 2. Dopóki pilot działa na widoku `/mobile` (ten sam backend, PWA
instalowalna na ekranie głównym), apka mobilna nie jest na ścieżce krytycznej.

# Archiwum DONE — v21.4.0 – v23.0.0

Pełne wpisy przeniesione z [DONE.md](../DONE.md), gdzie został indeks.
**Nie czytaj całego pliku** — wyciągnij jedną sekcję:
`awk '/^## <fragment tytułu>/,/^## /' archive/done-v21-v23.md`

---

## ~~Strefa czasowa użytkownika jako granica dnia~~ ✓ zrobione (23.0.0) — WYMAGANIA.md 8.3

`user_profile.tz` było zapisywane i eksportowane, ale nigdzie nieczytane —
wszystkie granice dnia brały się z `date.today()` procesu (strefa serwera,
GCP). Tester w innej strefie widział „dzisiaj" serwera, a dzień zamykał mu
się (`DailySummary.complete`) w środku jego doby.

**Nowy `app/services/clock.py`**: `user_tz`/`user_now`/`user_today`/`user_time`,
każda przyjmuje `UserProfile | None` (profil może jeszcze nie istnieć).
Nieznana/pusta strefa → `Europe/Warsaw` (dotychczasowy efektywny default).
Znaczniki czasu w bazie zostają w UTC (`sync_ts`, `created_at`,
`last_used_at`) — zmienia się wyłącznie wyliczanie daty/godziny dnia; brak
migracji istniejących dat.

**Wpięcie:** `app/routers/meals.py` (`_queue_meal`, `estimate_meal_photo`/
`estimate_meal_text` — domyślny dzień, `save_meal` — domyślna godzina),
`app/routers/transfer.py` (nazwa pliku eksportu), `app/routers/day.py`
(`add_manual_activity` — domyślny dzień), `app/services/day.py:day_report`
(dzień „dziś" dla `day_energy`, profil już ma), `app/routers/trends.py` (oba
route'y podają `today=user_today(profile)` do `trends.payload`, który już
przyjmował ten parametr), `app/services/sync.py:sync_range` (nowy parametr
`today: date | None`, `None` zostawia zegar serwera — do skryptów CLI;
`maybe_sync` i `POST /api/sync` dociągają profil i podają swój `user_today`),
`app/routers/dashboard.py` (embeduje `today` do szablonu), `mobile.html`
(`todayIso()` czyta `SERVER_TODAY` osadzone z backendu zamiast `new Date()` —
telefon w podróży ma pokazywać ten sam dzień, co liczy backend), nowe pole
„Strefa czasowa" w karcie Profil (`#page-settings`, prefill z
`Intl.DateTimeFormat().resolvedOptions().timeZone` gdy profil jeszcze nie ma
ustawionej strefy). `PUT /api/profile` waliduje `tz` przez `ZoneInfo(...)` →
422 przy nieznanej strefie zamiast cichego zapisu śmiecia.

Pułapka po drodze w `app/models.py:DailySummary` (dotyczy też kolumn dodanych
w poprzednim punkcie): kolumna nazywa się `date`, więc w ciele klasy adnotacja
`Mapped[date | None]` dla kolumny zdefiniowanej *po* niej odnosi się już do
kolumny `date`, nie do `datetime.date` — SQLAlchemy dostaje wtedy `nullable`
niewykryty z Optional. Rozwiązanie: forward-ref (`Mapped["date | None"]`) +
jawny `nullable=True`.

Nota `/prywatnosc`: bez zmian — to wyliczenie granicy dnia z danych już
zebranych (profil), bez nowej kategorii ani odbiorcy.

Testy `tests/test_timezone.py` (bez freezegun — `clock.datetime` podmieniane
monkeypatchem na wariant ze stałym `.now(tz)`): profil `Pacific/Auckland`
23:30 UTC → `user_today` dzień dalej niż UTC; brak profilu → Europe/Warsaw;
nieznana/pusta strefa → Europe/Warsaw; `POST /api/meals/text` bez daty ląduje
w dniu użytkownika (HTTP, ten sam mechanizm freeze); `sync_range(today=...)`
respektuje przekazany dzień niezależnie od zegara maszyny; `PUT /api/profile`
z nieznaną strefą → 422.

## ~~Statystyki: obserwowalność poprawki kcal (21.5.0) i kalibracji adaptacyjnej (22.0.0)~~ ✓ zrobione (22.2.0)

Oba wdrożenia z 2026-09-05 weszły bez kroku „Statystyki" — ten punkt go
nadrabia, na przełączniku `scope` z punktu wyżej (wszystkie nowe agregaty
honorują `allowed_ids`/`allowed_refs`, żadnych własnych filtrów).

**Trzy nowe zdarzenia telemetrii** w `usage.EVENTS`: `calibration_step`
(`app/services/calibration.py:catch_up`, bump per ważny dzień filtru, **po**
commicie stanu, nie w pętli), `calibration_reset` (`_guard_against_batch_divergence`
przy resecie strażnika), `calibration_error` (`run_catch_up`, w `except`, po
`db.rollback()`).

**Kolumny `DailySummary.model_total_kcal`/`model_checked_on`** (migracja
addytywna, bez backfillu) — `day.day_report()` zapisuje migawkę modelu
teoretycznego (`e.tdee.total`) raz na domknięty dzień, przy pierwszym wejściu
na ten dzień (`model_checked_on != day`). Pułapka po drodze: w `DailySummary`
kolumna nazywa się `date`, a nowa kolumna miała adnotację `Mapped[date | None]`
— w ciele klasy `date` odnosi się już do wcześniej zdefiniowanej kolumny
(przesłonięcie nazwy w namespace klasy), nie do `datetime.date`, co dawało
`NOT NULL` zamiast nullable. Naprawione forward-refem (`Mapped["date | None"]`)
+ jawnym `nullable=True` — pilnować tego wzorca przy każdej kolejnej kolumnie
typu `date`/`Optional` w tym modelu.

**Trzy nowe sekcje na `/usage`** (`app/services/usage.py:_stats_model_vs_measurement`/
`_stats_calibration`/`_stats_conservative_balance`, ostatnie 30 dni, jedno
zapytanie per tabela, bez `day_energy` w pętli): „Wydatek: model vs pomiar"
(% aktywności z `kcal_bmr_garmin`/`steps`, rozkład `model_total_kcal ÷
kcal_total_garmin` z % poza ±15%, % domkniętych dni z posiłkiem bez Garmina),
„Kalibracja" (adopcja filtru, rozkład `factor` i liczba na clampie z importowanych
stałych `CLAMP_LOW`/`CLAMP_HIGH`, współczynnik uczenia, wykres tygodniowy mediany
`|innov_kg|`, sumy `calibration_reset`/`calibration_error` w 7/30 dni — czerwono
gdy >0), „Bilans konserwatywny" (% domkniętych dni z posiłkiem, gdzie `kcal_in
> e_target`, `e_target` odtworzone z bieżącego `CalibrationState.factor`).
Wyłącznie agregaty — żadna nowa tabela per pseudonim z danymi zdrowotnymi.

Nota `/prywatnosc`: bez zmian — nowe sekcje to wyłącznie agregaty z danych już
zbieranych (Garmin, posiłki, kalibracja), bez nowej kategorii ani odbiorcy.

Testy: `tests/test_usage.py` (nowe sekcje renderują się, e-mail admina nadal
nigdzie w HTML, rozkład `model_ratio`/liczba na clampie liczone poprawnie),
`tests/test_calibration.py` (`calibration_step` bumpuje raz per ważny dzień,
`calibration_reset` bumpuje przy resecie strażnika), `tests/test_day_trends_services.py`
(`model_total_kcal` zapisuje się tylko dla dnia domkniętego i tylko raz).

## ~~Zakres statystyk `/usage`: testerzy / wszyscy / tylko ja~~ ✓ zrobione (22.1.0)

Problem: konto admina było wycięte ze wszystkich agregatów `/usage`, mimo że
jest jedynym kontem z realnym wolumenem danych do złapania problemów w
modelu (np. rozjazd 4213 vs 2889 kcal).

**Zmiana:** przełącznik `scope` (`others` domyślny / `all` / `me`) w
`app/services/usage.py:dashboard_stats` — jeden zbiór `allowed_ids`/
`allowed_refs` (`_allowed_ids_and_refs`) zastąpił rozsiane filtry
`r[0] != admin_ref` i podzapytanie `other_users`. `app/routers/usage.py`
waliduje `scope` przez `Literal["others", "all", "me"]` (nieznana wartość →
422 automatycznie z FastAPI/pydantic). Szablon `usage.html` dostał trzy
zakładki `testerzy · wszyscy · ja`, wiersz admina w tabeli „Ostatnia
aktywność" ma dopisek „(ja)" tylko przy `all`. Tylko `scope == "me"` renderuje
nową sekcję „Moje dni: model vs pomiar" (14 dni, `DailySummary` + liczba
aktywności zegarkowych z `kcal_bmr_garmin` — kolumna „Model" na razie zawsze
„—", bo `DailySummary.model_total_kcal` jeszcze nie istnieje — patrz punkt
„Statystyki: obserwowalność…" niżej).

Nota `/prywatnosc`: bez zmian — dane innych użytkowników nadal wyłącznie w
agregatach; sekcja „Moje dni" pokazuje dane właściciela wyłącznie jemu.

Testy `tests/test_usage.py`: `others`/`all`/`me` filtrują poprawnie pseudonim
admina, `all` ma „(ja)", `me` ma sekcję „Moje dni" i nadal nie ujawnia
e-maila, `scope=xyz` → 422. Uwaga zachowana dla przyszłych zmian: `usage.py`
importuje `ADMIN_EMAIL` bezpośrednio z `config`, osobno od `app.deps` — testy
scope'u muszą monkeypatchować `app.services.usage.ADMIN_EMAIL`, samo
`app.deps.ADMIN_EMAIL` (patch dla `require_admin`) nie wystarczy.

## ~~Kalibracja adaptacyjna~~ ✓ zrobione (22.0.0, commit 30d4e71)

WYMAGANIA.md 6.2 — model uczy się na danych użytkownika (jak MacroFactor).
Zaimplementowany mechanizm to **filtr dzienny** (uproszczony Kalman,
`app/services/calibration.py:step_day`/`catch_up`), nie wsadowa kalibracja
z pierwszej wersji planu w TODO.md: 10-14 dni czekania na pierwszy wynik było
gorsze niż liczba, która koryguje się co dzień i wolno dochodzi do prawdy
(decyzja właściciela 2026-09-05, „Warstwa 2" w TODO.md).

**Mechanizm:** `CalibrationState` (1 wiersz/użytkownika: `factor`, `trend_kg`
— EMA wagi α=0.1, `days_used`, `last_valid_day`, `updated_on`) i
`CalibrationLog` (append-only, po wierszu na ważny dzień) — nowe tabele,
`create_all` wystarczy, bez migracji. Start: `factor=0.97` (jawny
konserwatyzm), gain maleje z 1/6≈0.17 do 0.05 po ~15 dniach, krok dnia ≤±1%,
clamp asymetryczny **[0.85, 1.05]** (w dół bez ograniczeń, w górę tylko +5% —
błąd wagi 14-dniowej sięga 0.5-1 kg). Dni sprzed `CALIBRATION_EPOCH =
2026-09-05` (dzień tego wdrożenia, razem z poprawką wyliczania kcal na dzień
w toku) nie wchodzą — liczone starym modelem wydatku.

Wsadowe `compute()` (14-dniowe okno, `Calibration` — tabela ze szkicu
WYMAGANIA.md 8.4) zostaje wyłącznie do: (a) karty „kalibracja" w tygodniówce
(oczekiwana vs rzeczywista zmiana wagi, wymóg 6.4) i (b) strażnika — gdy filtr
i wsad różnią się >10%, `catch_up()` resetuje filtr do wartości wsadu
i zapisuje to w `CalibrationLog` (wpis z `gain=innov_kg=0.0` jako znacznik
resetu, nie krok filtru).

**Wpięcie:** `day.day_report()` mnoży `kcal_out` przez
`calibration.current_factor()` przed odjęciem celu deficytu; odpowiedź ma
nowe pola `calibration_factor`, `calibration_updated`, `calibration_days_used`.
Zaokrąglenie `remaining_kcal` w dół do 50 (z poprawki 21.5.0) stosowane jest
**po** przemnożeniu przez factor — jedno miejsce, dwa jawne przesunięcia obok
siebie w kodzie. `catch_up` wołane w tle przy wejściu na dashboard
(`background.add_task`, obok `maybe_sync`) i po imporcie transferu
(`transfer.import_payload` → `calibration.maybe_recalibrate` — stan filtru
nie wchodzi do eksportu, przelicza się od zera z historii). `/api/trends`
i `/trends` dostały nowy klucz `calibration` (karta 6.4) —
`API_TRENDS_KEYS` w testach zaktualizowane.

**Testy** `tests/test_calibration.py`: syntetyczny użytkownik z losowym szumem
wagi ±0.5 kg (seed 42) i prawdziwym wydatkiem 0.9×Garmin — filtr nie reaguje
na 1 dzień, po 21 dniach zbieżny w [0.87, 0.93], krok dnia nigdy >1%, clamp
1.05 przy wadze spadającej dwa razy szybciej niż bilans, dzień bez wagi nie
zmienia stanu, `catch_up()` idempotentne, strażnik resetuje filtr 1.05 do
wsadu ~0.9.

Nota `/prywatnosc`: bez zmian — filtr przetwarza dane już zbierane (posiłki,
Garmin, waga), bez nowej kategorii ani nowego odbiorcy.

---

## ~~Poprawa wyliczania kcal na dzień w toku~~ ✓ zrobione (21.5.0, commit 30d4e71)

Objaw z 2026-09-05 (konto właściciela): Krasnal pokazał wydatek 4213 kcal,
Garmin za ten sam dzień 2889 kcal — model teoretyczny (który dzień w toku
brał przez `max(pomiar, model)`) zawyżył marsz 4,5h licząc go MET 5.0 przez
cały czas trwania, mimo że zegarek dał realny pomiar aktywny/spoczynkowy.

**Weryfikacja założeń (krok 0 planu):** nie było możliwości zalogowania się na
żywe konto Garmina w tym środowisku (brak sesji/danych logowania) — pola
`bmrCalories` i `steps` w `get_activities_by_date` oraz narastanie
`bmrKilocalories` w `get_user_summary` **nie zostały zweryfikowane na żywych
danych**. Zaimplementowano od razu wg łańcucha fallbacków opisanego w planie
(per-aktywność `kcal_bmr_garmin` → proporcja z dobowego `kcal_bmr_garmin` →
`bmr_mifflin`), więc brak pola `bmrCalories` w realnej odpowiedzi Garmina nie
wywali się — po prostu zawsze wejdzie ten fallback. Właściciel: przy
najbliższym prawdziwym dniu z aktywnością zegarkową warto sprawdzić w logu/DB,
czy `Activity.kcal_bmr_garmin` faktycznie się wypełnia, czy zawsze jest NULL.

**Decyzje:** dzień w toku = pomiar Garmina (+ ręczne aktywności), bez `max` z
modelem — model teoretyczny jest wyłącznie fallbackiem, gdy brak
`kcal_total_garmin`. Model MET dla aktywności zegarkowych zastąpiony przez
`kcal_garmin` netto (brutto minus spoczynek za czas trwania); MET zostaje
tylko jako fallback, poprawiony: gałęzie `walking` (3.5) / `hiking` (6.0),
wzór **netto** `(MET−1)×kg×h` (wcześniej brutto — podwójnie liczyło spoczynek
razem z BMR), rower ≥20 km/h obniżony z MET 10 na 8. Rozbicie na ekranie dla
dnia z Garminem: spoczynek + aktywności netto + kroki poza aktywnościami +
ręczne (bez TEF, bo Garmin go nie wyodrębnia) — osobny kształt od modelu
teoretycznego (bmr+neat+aktywności+tef).

**Konserwatywne przesunięcie (zasada z nagłówka TODO):** `remaining_kcal`
zaokrąglany w dół do pełnych 50 kcal (`day.py:_floor_to_50`) — jedyne miejsce
z celowym przesunięciem w tym planie.

**Strażnik przed powrotem awarii:** nowy test
`test_day_in_progress_walk_reproduces_symptom_and_uses_garmin_net` odtwarza
dokładnie objaw z 2026-09-05 i pilnuje, że `tdee_model.total` (model
teoretyczny) mieści się w ±15% pomiaru Garmina dla tego samego dnia.

Nota `/prywatnosc`: bez zmian — nowe kolumny `Activity.kcal_bmr_garmin` i
`Activity.steps` to ta sama kategoria danych („aktywności z Garmina"), którą
nota już opisuje; nie wchodzą do `transfer.py` (eksport tylko ręcznych
aktywności, bez zmian).

---

## ~~Trendy liczą kcal inaczej niż „Dziś" — jedna logika wydatku w całej aplikacji~~ ✓ zrobione (21.4.0)

Bug zgłoszony 2026-09-04: dzień w toku miał zielony bilans na „Dziś", a
czerwony słupek w „Trendach" — bo „Trendy" brały surowe `kcal_total_garmin`
zamiast tej samej logiki (`day_balance`), której używa „Dziś".

| Sytuacja | „Dziś" (przed i po) | „Trendy" przed | „Trendy" po |
|---|---|---|---|
| dzień w toku | model/mixed, szacowane | surowy Garmin → fałszywa nadwyżka | jak „Dziś", oznaczony jako szacowany |
| dzień domknięty + aktywność ręczna | Garmin + ręczne | sam Garmin | Garmin + ręczne |
| dzień bez wpisu Garmina | model TDEE | dzień pominięty | model TDEE, oznaczony jako szacowany |

**Implementacja:** nowa czysta funkcja `day_energy()` w `app/services/day.py`
— jedyne miejsce liczące wydatek/bilans dnia, bez dostępu do bazy. `day_report`
woła ją i buduje z wyniku identyczną odpowiedź `/api/day/{day}` co wcześniej
(dowód: `test_api_day_returns_exactly_what_service_computes` przeszedł bez
zmian). `trends.payload` przeszedł na `day_energy` w pętli po zakresie dni,
z falbackiem na surowy Garmin, gdy brak profilu albo wagi (żeby wykres wagi
mógł się nadal wyświetlić). Dni szacowane (`estimated=True`) mają jaśniejszy,
przerywany słupek na wykresie bilansu (`charts.bar_chart(estimated=...)`) i
pusty okrąg na wykresie energii (`charts.line_chart` / `Series.hollow`) —
jedno pojęcie „szacowany" zgodne z flagą z `/api/day/{day}`. Średni bilans i
prognoza celu liczą się tylko z dni domkniętych (`estimated == False`) —
dzień w toku zmienia się co godzinę i zaburzałby średnią.

Kontrakt `/api/trends` bez zmian — informacja „szacowany" jedzie wyłącznie
w SVG (kolor/legenda/tekst), nie w JSON. Nota `/prywatnosc` bez zmian — te
same dane, inne zestawienie.

Testy: rozszerzony `tests/test_day_trends_services.py` (dzień w toku, dzień
domknięty z aktywnością ręczną, dzień bez Garmina, `avg_balance` z pominięciem
dni szacowanych) + nowy `tests/test_charts.py` (znaczniki `estimated`/`hollow`
nie zmieniają SVG, gdy nie podane; oznaczają wyłącznie właściwy punkt/słupek,
gdy podane).

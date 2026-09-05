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

**Zasada dla implementującego LLM (kierunek błędu w bilansie — decyzja
właściciela 2026-09-05):** bilans na ekranie „Dziś" ma być **lekko
konserwatywny**: przy niepewności pokazuj raczej **mniej** pozostałych kcal
do zjedzenia, nigdy więcej. Lekko zaniżony wydatek (mniejszy budżet) motywuje
do zakończenia jedzenia; zawyżony wydatek („zostało jeszcze 850 kcal") działa
odwrotnie. Dopuszczalna skala tego przesunięcia: **rząd 3-5% wydatku
(~100-150 kcal), nie więcej** — błąd 1300 kcal z 2026-09-05 to nie
„konserwatyzm", tylko awaria. Przesunięcie ma być **jawne i w jednym miejscu**
(zaokrąglenie budżetu w dół, asymetryczny clamp kalibracji — patrz punkty
„Poprawa wyliczania kcal na dzień w toku" i „Kalibracja adaptacyjna"), a nie
ukryte w stałych MET czy wzorze BMR, bo ukrytego przesunięcia nie da się potem
skalibrować.

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
| 6.2 Kalibracja adaptacyjna | brak tabeli `Calibration`; `day_report` liczy `e_target = kcal_out − deficyt` bez współczynnika (`app/services/day.py:day_report()`) | „Kalibracja adaptacyjna" (6/10) |
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

## Poprawa wyliczania kcal na dzień w toku (5/10)

### Objaw (2026-09-05, konto właściciela)

Krasnal pokazał wydatek **4213 kcal**, Garmin Connect za ten sam dzień
**2889 kcal** (1802 spoczynkowe + 1087 aktywne). Dwie aktywności z zegarka:
marsz ~4,5 h / 11 704 kroków (Garmin: 498 aktywnych + 341 spoczynkowych = 839)
i rower ~46 min (417 + 58 = 475). Kroki dnia 16 038 (zgodne).
Skutek dla użytkownika: „zostało ~850 kcal" zamiast „jesteś ~470 kcal nad celem".

### Diagnoza (zweryfikowana w kodzie, nie powtarzaj analizy)

Dzień w toku → `day_balance` bierze `max(pomiar Garmina, model)`
(`app/services/balance.py:37-39`). Model wygrał (4213 > 2889), bo:

1. **Marsz z zegarka liczony MET 5.0 przez cały czas trwania.**
   `activity_kcal_model` nie ma gałęzi `walking`/`hiking` → `MET_DEFAULT = 5.0`
   (`app/services/energy.py:84`). 4,5 h × 5 MET × ~78 kg ≈ 1750 kcal wobec 498
   aktywnych wg Garmina. To ~1200 kcal z 1300 kcal nadwyżki.
2. **Model dla aktywności z zegarka ignoruje `kcal_garmin`.** W `day_energy`
   `act_dict["kcal"]` podkładane jest tylko dla `source == "manual"`
   (`app/services/day.py:85-86`); Garminowe aktywności idą przez MET.
3. **Podwójne liczenie spoczynku.** MET jest brutto (1 MET = spoczynek), a
   model dodaje pełne 24 h BMR. Za 5 h aktywności ≈ 350 kcal policzone dwa razy.
   Ta sama wada dotyczy `kcal_garmin` z aktywności — Garmin podaje
   `calories` **brutto** (aktywne + spoczynkowe, patrz liczby w objawie).
4. **Rower > 20 km/h = MET 10** (`energy.py:44`); Garmin wyszedł na ~7-8 brutto.
5. **Rozbicie na ekranie jest fikcją dla dnia w toku.** `out_breakdown.steps_kcal`
   to reszta `total − BMR − aktywności(Garmin) − TEF` (`day.py:160`), więc
   „kroki 969 kcal" wchłonęły błąd modelu; prawdziwy NEAT poza aktywnościami
   to ~170 kcal (16 038 − 11 704 kroków). TEF pokazany obok totalu Garmina
   nie ma sensu — Garmin nie wyodrębnia TEF.

Kluczowy fakt do decyzji: Garminowe `bmrKilocalories` w podsumowaniu dnia to
**spoczynek za całą dobę już od rana** (1802 = prognoza doby, nie „dotąd").
Total Garmina w ciągu dnia nie jest więc zaniżony o BMR — brakuje mu tylko
aktywności, które jeszcze nie nastąpiły. Reguła `max(...)` chroniła przed
problemem, którego nie ma, a otwiera drogę modelowi, który chybia o 1300 kcal.

### Decyzje (podjęte przez właściciela 2026-09-05, nie otwieraj ponownie)

- **Dzień w toku: wydatek = pomiar Garmina + ręczne aktywności.** Bez `max`
  z modelem. Model teoretyczny zostaje wyłącznie jako fallback, gdy
  `kcal_total_garmin is None`. `estimated` dla dnia w toku zostaje `True`
  (Trendy nadal wykluczają go ze średnich), `out_source` zostaje `"mixed"`.
- **Model używa `kcal_garmin` netto dla aktywności z zegarka**, MET tylko dla
  ręcznych bez kcal i dla braku `kcal_garmin`. Netto = brutto − spoczynek za
  czas trwania.
- **MET jako fallback poprawiony:** gałęzie `walking` (3.5) i `hiking` (6.0),
  wzór netto `(MET − 1) × kg × h`, rower ≥ 20 km/h obniżony z 10 na 8.
- **BMR zostaje Mifflin.** Garmin liczy spoczynek ~8-10% wyżej — to systematyczne
  przesunięcie ma łapać „Kalibracja adaptacyjna" (punkt niżej), nie ten plan.
- **Rozbicie na ekranie z danych Garmina, gdy są.** Gdy `out_source` ∈
  {garmin, mixed}: spoczynek (`kcal_bmr_garmin`), aktywności netto, kroki poza
  aktywnościami (= `kcal_active_garmin` − suma netto aktywności, floor 0),
  ręczne, bez TEF. Gdy `model`: stare rozbicie BMR + NEAT + aktywności + TEF.
- **Kierunek błędu: konserwatywnie, w małej skali** (zasada z nagłówka TODO).
  W praktyce dla tego planu: (a) dzień w toku **nie** dostaje prognozy
  przyszłego NEAT ani „reszty dnia" — wydatek rośnie dopiero, gdy Garmin
  dośle dane; (b) `remaining_kcal` w `day_report` zaokrąglaj **w dół do
  pełnych 50 kcal** (jedyne miejsce z celowym przesunięciem — komentarz w
  kodzie ma odsyłać do tej zasady); (c) fallbacki modelu (MET netto, walking
  3.5) mają być realistyczne, nie „na zapas" — model ma trafiać, przesuwa
  tylko punkt (b); (d) nowy test w `tests/test_activities_api.py`
  (odtworzenie objawu, krok 7) ma dodatkowo asertować, że **model
  teoretyczny** dla tego samego dnia (`tdee_model.total`) mieści się w
  **±15%** pomiaru Garmina — to strażnik przed powrotem awarii rzędu 1300 kcal.

### Instrukcja dla implementującego LLM — co czytać (budżet tokenów)

Czytaj **tylko** wskazane zakresy; reszta plików nie ma znaczenia dla zadania.

| Plik | Zakres | Po co |
|---|---|---|
| `app/services/balance.py` | całość (54 linie) | `day_balance` — zmieniasz gałąź dnia w toku |
| `app/services/energy.py` | 39-125 | stałe MET, `activity_kcal_model`, `tdee_theoretical` |
| `app/services/day.py` | 26-123 (`_est_steps`, `DayEnergy`, `day_energy`) i 160-168 (`out_breakdown`) | jedyne miejsce liczenia wydatku i rozbicia |
| `app/providers/__init__.py` | 26-34 (`ActivityData`) | nowe pola z zegarka |
| `app/providers/garmin.py` | 168-188 (`get_activities`) | mapowanie JSON Garmina |
| `app/services/sync.py` | 61-75 | upsert aktywności — dopisz nowe kolumny |
| `app/models.py` | 81-95 (`Activity`) | nowe kolumny |
| `app/db.py` | 114-117 | wzorzec migracji `ALTER TABLE activity ADD COLUMN` — skopiuj |
| `app/templates/mobile.html` | 592-603 (`renderEnergyBreakdown`) | jedyne miejsce renderujące rozbicie |
| `tests/test_balance.py` | 19-24 | test `takes_max` do przepisania |
| `tests/test_day_trends_services.py` | 170-203 | test dnia w toku — asercja `balance < 0` przestanie być prawdziwa |
| `tests/test_activities_api.py` | 174-217 | testy `out_breakdown` — sprawdź, które asercje trzymają nowy kontrakt |
| `tests/test_energy.py` | 73-95 | testy MET/TDEE do aktualizacji |

**Nie czytaj:** `app/routers/*` (router tylko woła `day_report`), `trends.py`
(woła `day_energy`, nic nie zmieniasz), `transfer.py` (eksportuje tylko ręczne
aktywności; nowe kolumny zegarkowe **nie** wchodzą do eksportu), `privacy.html`
(nota już mówi „aktywności" z Garmina — nowe pola to ta sama kategoria danych,
zmiana noty **nie** jest potrzebna, odnotuj to w DONE.md), `WYMAGANIA.md`,
`deploy/`, `DONE.md` poza dopisaniem wpisu na końcu.

### Kroki

0. **Weryfikacja dwu założeń (10 min, zanim ruszysz kod).** Na koncie z
   podłączonym Garminem (lokalnie: `scripts/garmin_login.py`, albo poproś
   właściciela o surowy JSON) sprawdź w odpowiedzi `get_activities_by_date`
   obecność pól `bmrCalories` i `steps`, a w `get_user_summary` z godzin
   przedpołudniowych — czy `bmrKilocalories` już jest wartością całodobową.
   Fallbacki, jeśli założenia nie trzymają: brak `bmrCalories` → spoczynek
   aktywności licz `kcal_bmr_garmin / 86400 × duration_s` (a gdy i to `None`:
   `bmr_mifflin / 86400 × duration_s`); `bmrKilocalories` narastające →
   dzień w toku liczy `kcal_active_garmin + max(kcal_bmr_garmin, bmr_mifflin)`.
   Wynik weryfikacji zapisz jednym zdaniem w DONE.md.
1. **Dane z zegarka.** `ActivityData` + `Activity` + migracja + `sync.py` +
   `garmin.py`: dwie nowe kolumny `kcal_bmr_garmin: int | None`
   (z `bmrCalories`) i `steps: int | None` (z `steps`). Migracja jak
   `source` w `db.py:114-117`, bez backfillu (stare wiersze zostają `NULL`,
   fallbacki z kroku 0 je obsługują). Test migracji: wzorzec
   `test_migration_backfills_garmin_source` w `tests/test_activities_api.py:238`.
2. **`energy.py`.** (a) `activity_kcal_model` zwraca **netto**:
   `(met − 1) × kg × h`; dodaj gałąź `"walking"` → 3.5 i `"hiking"` → 6.0
   (sprawdzaj `hiking` przed `walking`); `MET_CYCLING_BY_SPEED_KMH` ostatni
   próg 10.0 → 8.0. (b) `running_kcal` zostaje (1.0 kcal/kg/km to już wartość
   ~netto). (c) `tdee_theoretical`: `activities` przyjmuje opcjonalne
   `kcal_net` i `steps` w słowniku; gdy `kcal_net` jest — użyj go zamiast
   modelu; do `activity_steps` bierz `a["steps"]`, gdy jest, inaczej dotychczasowe
   `distance × 1400`. Docstring: „kcal aktywności są netto, BMR liczone osobno".
3. **`day.py:day_energy`.** Dla każdej aktywności zbuduj `act_dict` z
   `kcal_net` = `kcal_garmin − spoczynek` (spoczynek wg kroku 0/1) dla
   `source != "manual"`; dla ręcznych `kcal_net = kcal_garmin` (ręczne MET są
   liczone w `manual_activity_kcal` brutto — **zostaw**, różnica dla
   30-60 min wpisów to <10%, a zmiana rozjechałaby zapisane wartości).
   `_est_steps` → najpierw `activity.steps`, potem dystans. Dodaj do `DayEnergy`
   pole `activities_net_kcal` (suma netto zegarkowych) i `activities_steps`.
4. **`balance.py:day_balance`.** Gałąź `not day_complete` przy
   `garmin_total is not None`: `DayBalance(kcal_in, measured, "mixed", True)`.
   Usuń parametr `model_tdee` z tej gałęzi tylko logicznie — sygnatura
   zostaje (fallback `garmin_total is None` dalej go używa). Zaktualizuj
   docstring modułu (linie 3-4) i komentarz w 37-38.
5. **`day.py:day_report` — `out_breakdown`.** Dwa kształty, wybierane po
   `e.out_source`:
   - garmin/mixed: `{"kind": "garmin", "resting": kcal_bmr_garmin,
     "activities_kcal": suma netto zegarkowych, "steps_kcal": max(kcal_active_garmin
     − activities_kcal, 0), "steps_count": e.steps_effective, "manual_kcal":
     e.manual_kcal, "total": kcal_out}`. Gdy `kcal_bmr_garmin is None`
     (stare wiersze) — `resting = kcal_total − kcal_active` gdy oba są, inaczej
     `round(e.tdee.bmr)`.
   - model: `{"kind": "model", "bmr", "steps_kcal": neat, "steps_count",
     "activities_kcal", "tef", "total"}` — jak dziś, ale `steps_kcal` z
     `e.tdee.neat`, nie z reszty.
   Klucz `total` musi się zgadzać z `kcal_out` w obu kształtach (pilnuje
   `test_closed_garmin_day_plus_manual_activity_sums_to_kcal_out`).
6. **`mobile.html:renderEnergyBreakdown`.** Rozgałęzienie po `b.kind`:
   garmin → „spoczynek **1802** + aktywności **915** + kroki **172** [+ ręczne
   **X**] = **2889 kcal**"; model → dotychczasowa linia. Pod spodem dla dnia
   w toku dopisz szarym: „Garmin dosyła dane co kilka godzin — wydatek
   urośnie do końca dnia". Nic więcej w UI.
7. **Testy.** `test_balance.py`: `test_day_in_progress_takes_max` →
   `test_day_in_progress_uses_measurement` (kcal_out == garmin_total +
   manual, `mixed`, `estimated True`); dodaj test, że fallback bez Garmina
   nadal daje model. `test_energy.py`: netto dla MET, gałąź walking/hiking,
   rower 8.0 przy 25 km/h, `kcal_net` wygrywa nad modelem, `steps` z aktywności
   wygrywa nad dystansem. `test_day_trends_services.py:170-203`: seed
   `kcal_total_garmin=1300` przy `kcal_in=1600` → `balance > 0` teraz;
   zmień asercję i komentarz (nadal `estimated is True`, marker na wykresie
   bez zmian). `test_activities_api.py`: dopisz test odtwarzający objaw —
   dzień w toku, marsz 4,5 h `kcal_garmin=839`, `kcal_bmr_garmin=341`,
   `steps=11704`, summary 2889/1087/1802/16038 → `kcal_out == 2889`,
   `out_breakdown.activities_kcal == 498 + 417`, `steps_kcal == 172`,
   `tdee_model.total` w ±15% od 2889, `remaining_kcal` podzielne przez 50
   i nie większe od surowej różnicy.
   Uruchamiaj tylko te cztery pliki; pełną suitę po zgodzie właściciela
   (zasada z nagłówka TODO).
8. **Wersja i porządki.** `VERSION` 21.4.0 → **21.5.0** (zmiana zachowania
   istniejącej funkcjonalności = Y). Ten punkt przenieś do DONE.md z sha
   commitu, zapisz wynik weryfikacji z kroku 0 i zdanie o nocie prywatności.
   W punkcie „Tabela MET jako dane" (wyżej) popraw wzmiankę o `MET_DEFAULT`
   i progach roweru, jeśli po zmianie nie zgadzają się numery linii/wartości.

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
     przycięty **asymetrycznie do [0.85, 1.05]** (zasada „bilans konserwatywny"
     z nagłówka TODO — decyzja właściciela 2026-09-05, zastępuje wcześniejsze
     symetryczne [0.85, 1.15]): korekta **w dół** (realnie spalasz mniej →
     mniejszy budżet) wchodzi w pełni, korekta **w górę** (waga spada szybciej
     niż bilans obiecuje → większy budżet) tylko do +5%, bo większy budżet
     to zachęta do jedzenia, a błąd wagi w 14 dni (woda, glikogen) sięga
     0,5-1 kg = ±250-500 kcal/dzień pozornej różnicy. Nowy współczynnik
     **wygładzaj z poprzednim**: `factor = 0.5·poprzedni + 0.5·nowy` (pierwszy
     wpis bez wygładzania) — jeden dziwny tydzień nie ma skakać celem
     o 15%. Zwróć `None`, gdy < 10 dni ważnych albo brak pomiarów wagi
     na obu końcach okresu. **Warunek wstępny:** licz kalibrację wyłącznie
     z dni po wdrożeniu punktu „Poprawa wyliczania kcal na dzień w toku" —
     dni domknięte używają surowego `kcal_total_garmin`, więc historyczne
     `complete == True` są OK, ale sprawdź w DONE.md datę wdrożenia i wyklucz
     dni sprzed niej, jeśli w bazie są ręczne aktywności (te były liczone
     brutto MET).
   - `current_factor(db, user_id) -> float` — `factor` z najnowszego wpisu
     `Calibration` albo `1.0`.
   - `maybe_recalibrate(db, user_id)` — liczy i zapisuje nowy wpis, jeśli
     ostatni jest starszy niż 7 dni (albo nie istnieje); wołane w tle przy
     wejściu na dashboard (wzorzec: `background.add_task`, jak `maybe_sync`
     w `app/routers/dashboard.py`).
3. **Zastosowanie.** W `app/services/day.py:day_report()` (raport dnia jest
   w serwisie od 2026-09-03, router tylko go woła): pobierz
   `factor = calibration.current_factor(db, user_id)` i licz
   `e_target = bal.kcal_out * factor − profile.target_deficit_kcal`
   (dziś: bez factora). Do odpowiedzi dodaj pola `calibration_factor`
   i `calibration_updated` (data ostatniego wpisu) — UI ma pokazywać
   "zapotrzebowanie skorygowane o ±X% względem pomiaru". Zaokrąglenie
   `remaining_kcal` w dół do 50 (z planu „Poprawa wyliczania kcal…") stosuj
   **po** pomnożeniu przez factor — dwa jawne przesunięcia, oba w tym samym
   miejscu, oba widoczne w kodzie obok siebie. Nie dodawaj trzeciego. Uwaga: kształt tej
   odpowiedzi pilnuje `tests/test_day_trends_services.py` — dopisanie pól jest
   OK, ale test porównuje wyjście serwisu z wyjściem `/api/day`, więc oba
   muszą dostać je razem.
4. **UI.** W `app/templates/mobile.html` (jedyny widok dzienny) pokaż korektę
   przy zapotrzebowaniu; dla tygodniówki dolicz dane w
   `app/services/trends.py:payload()` (jedno źródło dla `/trends` i
   `/api/trends`) i dorysuj kartę "kalibracja" w `app/templates/trends.html`:
   oczekiwana vs rzeczywista zmiana ciężaru i factor (wymóg 6.4). Nowy klucz
   dopisz też do `API_TRENDS_KEYS` w `tests/test_day_trends_services.py` —
   ta lista jest świadomym kontraktem API, nie przypadkowym asertem.
5. **Transfer.** Kalibracji nie eksportuj w `app/services/transfer.py` —
   po imporcie danych przelicza się z historii (dopisz `maybe_recalibrate`
   po udanym imporcie).
6. **Testy.** `tests/test_calibration.py`: syntetyczne 14 dni (posiłki +
   `DailySummary` complete + `WeightLog`) o znanym bilansie; przypadki:
   zgodność wag → factor ≈ 1.0, waga spada wolniej niż bilans obiecuje →
   factor < 1.0, za mało dni → `None`, clamp asymetryczny 0.85/1.05
   (waga spadająca dwa razy szybciej niż bilans → factor dokładnie 1.05,
   nie więcej), wygładzanie z poprzednim wpisem (drugi wpis = średnia). Wszystko musi
   być zielone — czerwony pytest blokuje deploy.

## Integracja z innymi źródłami spalanych kcal (fundament 6/10 + osobno per producent)

Dziś jedynym źródłem wydatku energetycznego jest Garmin (nieoficjalne API, D4).
Ten punkt otwiera aplikację na inne zegarki/opaski. Plan jest rozbity na
**wspólny fundament (część 0)**, bez którego żaden producent nie ma sensu, oraz
**niezależne implementacje per producent (części A–G)** — każda jest osobnym
zadaniem z własnym bumpem `X` w `VERSION` (nowa funkcjonalność) i własnym wpisem
w DONE.md. Stan API producentów sprawdzony 2026-09-04 (linki w każdej części) —
**na starcie każdej części zweryfikuj ponownie**, te API zmieniają się co rok.

**Zanim cokolwiek zaczniesz — ankieta wśród testerów (0/10, właściciel):** jakie
urządzenie kto nosi. Implementuj wyłącznie producentów, których ktoś faktycznie
używa; reszta zostaje tu jako plan. Kolejność wg spodziewanej wartości:
0 → E (Apple) + F (Health Connect: Samsung/Xiaomi) razem, bo dzielą endpoint
ingest → A (Polar) → D (Oura) → C (Whoop) → B (Fitbit/Google Health, czeka
na dojrzałość API).

### Mapa możliwości (stan 2026-09-04)

| Źródło | Dostęp z serwera | Total kcal (z BMR) | Kroki | Waga | Aktywności | Auth |
|---|---|---|---|---|---|---|
| Garmin (dziś) | nieoficjalne `garminconnect`; oficjalne Health API tylko dla firm, nabór wstrzymany | tak | tak | tak | tak | login+MFA |
| Polar | **oficjalne** AccessLink v4, rejestracja klienta samoobsługowa | tak (`calories`; potwierdź, że zawiera BMR) | tak | do weryfikacji w v4 | tak | OAuth2 |
| Oura | **oficjalne** API v2 | tak (`total_calories`) | tak | nie | tak | OAuth2 |
| Whoop | **oficjalne** API v2 | tak (`kilojoule` cyklu) | **nie** (Whoop nie liczy kroków) | nie (statyczna) | tak | OAuth2 |
| Fitbit / Pixel Watch | Fitbit Web API **wyłączane IX 2026**; następca: Google Health API (OAuth Google + obowiązkowa weryfikacja aplikacji dla restricted scopes) | tak | tak | tak | tak | OAuth2 Google |
| Apple Watch | **brak web API** — dane tylko na telefonie (HealthKit) → push z telefonu | tak (`active + basal`) | tak | tak | tak | push z tokenem urządzenia |
| Samsung Health | **brak publicznego web API** (Platform API partnerski) → Health Connect na telefonie → push | tak (`TotalCaloriesBurned`) | tak | tak | tak | push z tokenem urządzenia |
| Xiaomi (Mi Fitness / Zepp) | brak API → Health Connect → push; Mi Fitness udostępnia **tylko kroki, sen, tętno, treningi — bez kcal** | **nie** → model z kroków | tak | nie | tak | push z tokenem urządzenia |
| Huawei | Health Kit REST wymaga zatwierdzenia dewelopera i aplikacji w AppGallery → nie dla nas; ścieżka: Health Sync → Health Connect → push | j.w. | tak | tak | tak | push |
| Google Fit | REST API **wyłączone** (2025) — bez alternatywy poza Health Connect | — | — | — | — | — |
| Strava | oficjalne, ale nowe aplikacje w „single player mode” (tylko konto autora) do czasu zatwierdzenia → nie da się podłączyć testerów | nie (tylko kcal treningów) | nie | nie | tak | OAuth2 |
| Withings | oficjalne API (OAuth2) — **tylko waga** (D3 dla nie-Garminowców) | — | — | tak | — | OAuth2 |

Wniosek architektoniczny: są **dwie klasy źródeł** — *pull* (serwer sam pyta
API producenta: Garmin, Polar, Oura, Whoop, Fitbit) i *push* (telefon wysyła
dane do nas: Apple, Health Connect = Samsung/Xiaomi/Huawei/Pixel). Fundament
musi obsłużyć obie.

### Decyzje (wiążące, do potwierdzenia przez właściciela przed częścią 0)

1. **Jedno aktywne źródło dziennych totali na użytkownika.** Kroki, total
   kcal i aktywności biorą się z jednego wybranego źródła (`activity_source`);
   ręczne aktywności doliczają się zawsze, jak dziś. Dwa źródła naraz = podwójne
   liczenie tego samego biegu — nie wchodzimy w to na pilocie.
2. **Kolumny `kcal_total_garmin` / `kcal_active_garmin` / `kcal_bmr_garmin` /
   `garmin_id` zostają** pod starą nazwą (rename w SQLite = przebudowa tabeli,
   a nazwy pilnują testy i eksport). Nowa kolumna `DailySummary.source` mówi,
   skąd dane. Sufiks „garmin" traktujemy jako historyczny — komentarz w
   `app/models.py`, nie migracja.
3. **Semantyka `kcal_total` = pełny dobowy wydatek łącznie z BMR** (tak liczy
   `balance.day_balance`). Provider, który daje tylko kcal aktywne (Apple:
   `active_energy` bez `basal`), **sumuje** oba pola po swojej stronie — jeśli
   nie ma czym, zwraca `None` i bilans idzie z modelu (`out_source = "model"`).
4. **Tokeny OAuth każdego providera to sekret** — klucz `<provider>_tokens`
   w `AppSetting`, szyfrowany przez `settings_service` (dopisać do
   `SECRET_SETTING_KEYS`; nie wymyślać osobnej ścieżki — patrz CLAUDE.md).
5. **Nota `/prywatnosc`:** każdy nowy producent to nowy podmiot, u którego
   użytkownik autoryzuje „Fit Krasnal" (producent widzi fakt połączenia), i nowy
   strumień danych DO aplikacji. Notę aktualizujemy w tej samej części, w której
   producent wchodzi. `PRIVACY_VERSION` bumpujemy **raz** — przy pierwszym nowym
   producencie (bump unieważnia zgodę na LLM i wymusza ponowną — nie robimy tego
   przy każdym z siedmiu producentów).

### Część 0 — fundament wielu źródeł (6/10)

**Kroki dla implementującego LLM:**

1. **Kontrakt providera** (`app/providers/__init__.py`):
   - `ActivityData.garmin_id` → `external_id` (poprawić `garmin.py`, `sync.py`;
     kolumna w bazie zostaje). Dla źródeł innych niż Garmin `sync` zapisuje
     `Activity.garmin_id = f"{source}:{external_id}"` (unikat
     `(user_id, garmin_id)` nie zderzy się między producentami); Garmin bez
     prefiksu — zgodność z istniejącymi wierszami.
   - `DailySummaryData` — wszystkie pola już opcjonalne; `get_daily_summary`
     może zwrócić `None` dla dnia bez danych (dziś Garmin zwraca dict z `None`).
   - Wspólny wyjątek `ProviderNotConnected(RuntimeError)`;
     `GarminNotLoggedIn` staje się jego podklasą. Routery mapują klasę bazową
     na 409 (dziś łapią tylko Garmina: `app/routers/profile.py:sync`).
   - `class DataProvider(Protocol)` dostaje `SOURCE: ClassVar[str]`.
2. **Rejestr źródeł** — nowy `app/providers/registry.py`: `ProviderSpec(id,
   label, kind: "pull"|"push", factory(user_id, db) -> DataProvider | None,
   connected(db, user_id) -> bool, disconnect(db, user_id))` i słownik
   `PROVIDERS`. `active_source(db, user_id) -> str | None`: ustawienie
   `activity_source` (AppSetting, **nie sekret**); brak ustawienia + tokeny
   Garmina obecne → `"garmin"` (zgodność dla obecnych testerów, bez migracji
   danych). `set_active_source(db, user_id, source)` — 422 dla nieznanego,
   409 gdy `connected()` fałszywe.
3. **`app/services/sync.py`** — rozbić `sync_range` na trzy idempotentne
   upserty używane zarówno przez pull, jak i push: `upsert_daily(db, user_id,
   summary, source, today)`, `upsert_weights(db, user_id, weights, source)`,
   `upsert_activities(db, user_id, activities, source)`. `sync_range`
   przyjmuje `source` (z `provider.SOURCE`), ustawia `DailySummary.source`,
   `WeightLog.source`, `Activity.source`. `maybe_sync` bierze providera z
   `registry.active_source` zamiast twardo `GarminProvider`; dla źródła `push`
   albo `None` wychodzi od razu (nic do pobrania). Log „Auto-sync Garmin" →
   „Auto-sync {source}".
4. **Model i migracja**: `DailySummary.source: Mapped[str] = "garmin"` — migracja
   addytywna w `app/db.py:_migrate()` (wzorzec `activity.source`), backfill
   istniejących wierszy na `'garmin'`. Nowy sekret `ingest_token` i klucze
   `<provider>_tokens` → `SECRET_SETTING_KEYS` (można regułą: każdy klucz z
   sufiksem `_tokens` jest sekretem — jedno miejsce, nie lista do pilnowania).
5. **Generyczny OAuth2** (dla A–D) — nowy `app/services/oauth.py` (bez
   FastAPI) + `app/routers/connect.py`:
   - konfiguracja per provider w rejestrze: `authorize_url`, `token_url`,
     `scopes`, `client_auth` (`basic` | `body`), `pkce: bool`;
   - `GET /connect/{provider}` — generuje `state` (`secrets.token_urlsafe`),
     zapisuje w sesji, redirect na `authorize_url`;
   - `GET /connect/{provider}/callback` — sprawdza `state`, wymienia `code`
     na tokeny (`httpx`, **przenieść z grupy dev do zależności runtime** w
     `pyproject.toml`), zapisuje JSON `{access_token, refresh_token,
     expires_at, scope, ...}` przez `set_setting(<provider>_tokens)`, ustawia
     `activity_source`, odpala `maybe_sync(force=True)` w tle, redirect
     `/settings?saved=1`;
   - `oauth.bearer(db, user_id, provider) -> str` — odświeża, gdy do wygaśnięcia
     < 5 min; nieudany refresh → kasuje tokeny i rzuca `ProviderNotConnected`
     (użytkownik widzi „połącz ponownie", nie 500);
   - `POST /settings/source/disconnect` — `registry.disconnect` + czyści
     `activity_source`;
   - env: `FIT_KRASNAL_PUBLIC_URL` (domyślnie `https://fit.krasnal.cc`, do
     budowy `redirect_uri`) i per provider `FIT_KRASNAL_<PROVIDER>_CLIENT_ID` /
     `_CLIENT_SECRET` w `app/config.py`, opisane w `.env.example` i
     `deploy/README.md`. Provider bez skonfigurowanego klienta **nie pojawia
     się** na liście w UI (nie ma po co pokazywać przycisku, który nie działa).
6. **Generyczny ingest** (dla E–F) — nowy `app/routers/ingest.py`:
   - `POST /api/ingest/{provider}` uwierzytelniany **tokenem urządzenia**, nie
     ciasteczkiem: nagłówek `X-API-Key`, wartość porównywana
     `secrets.compare_digest` z `get_setting(user_id, "ingest_token")`.
     Lookup po tokenie: token ma postać `<user_id>.<sekret>` — `user_id`
     jawnie, sekret sprawdzany po odszyfrowaniu ustawienia tego usera (bez
     skanowania całej tabeli);
   - `POST /api/settings/ingest-token` (sesja) generuje/rotuje token i zwraca
     go **raz**; UI pokazuje pełny adres do wklejenia w aplikacji na telefonie;
   - body: znormalizowany JSON `{days: [{date, kcal_total, kcal_active,
     kcal_bmr, steps}], weights: [{date, weight_kg}], activities:
     [{external_id, date, type, duration_s, distance_m, kcal, avg_hr}]}` —
     provider-specific parsery (Apple, Health Connect) tłumaczą surowy format
     na ten kształt **przed** wejściem do upsertów; nieznane pola ignorowane,
     brak wymaganych → 422 z nazwą pola; limit body 1 MB; wszystko traktowane
     jak dane niezaufane (to telefon usera, ale format narzuca cudza apka);
   - `complete` dla dnia = `day < today` (jak w pull); jutrzejsza paczka
     nadpisuje wczorajszy dzień pełnymi danymi — dlatego upsert, nie insert;
   - telemetria `ingest_ok` / `ingest_rejected` w `usage.EVENTS`.
7. **Raport dnia i UI**: `day_report` zwraca dodatkowo `activity_source`
   (id) i `source_label`; klucz `garmin_connected` **zostaje** (czyta go
   `mobile.html`), ale znaczy „aktywne źródło połączone". `balance.out_source`
   zostaje w wartościach `garmin|mixed|model` (kontrakt API, testy) — UI mapuje
   etykietę z `source_label`, a `mobile.html:596` przestaje mieć „Garmin" na
   twardo. Ostrzeżenie o podwójnym liczeniu ręcznych aktywności
   (`#a-garmin-warning`) też z etykiety. `settings.html`: karta „Konto Garmin"
   → karta **„Źródło danych o spalonych kcal"**: lista producentów z rejestru
   (status połączony / przycisk „Połącz" → `/connect/{p}` albo formularz Garmina
   albo instrukcja push z tokenem), radio aktywnego źródła, „Odłącz". W
   `mobile.html` (sekcja Ustawienia) analogicznie, przez `GET /api/settings`
   (dopisać `sources: [{id, label, connected}]`, `activity_source`).
8. **Nota `/prywatnosc`**: punkt „Dane z Garmina" → „Dane z urządzenia
   (opcjonalnie, jeśli połączysz źródło)" z listą producentów **faktycznie
   wdrożonych** (nie planowanych) i zdaniem, że przy OAuth producent widzi
   fakt autoryzacji aplikacji, a my nic do producenta nie wysyłamy. Bump
   `PRIVACY_VERSION` wg decyzji 5. W tej części (sam fundament) nota się nie
   zmienia — zmienia ją pierwszy producent.
9. **Powiązania z innymi planami** (dopisz tam odsyłacze, nie dubluj):
   „Usuń moje dane i konto" — `delete_account` kasuje **wszystkie**
   `*_tokens` i `ingest_token`, nie tylko Garmina; „Strefa czasowa" —
   `today` do `complete` w ingest i sync ma iść z `clock.user_today`;
   `usage.py:funnel` — `with_garmin` → `with_source` (ktokolwiek z
   `activity_source` ustawionym); `transfer.py` — eksport aktywności dopisuje
   `source`, klucz `garmin_id` zostaje.
10. **Testy**: `tests/test_provider_registry.py` (rejestr, fallback na
    Garmina, 422/409 przy zmianie źródła), `tests/test_oauth_connect.py`
    (fałszywy provider w rejestrze; `state` nieprawidłowy → 400; wymiana kodu z
    monkeypatchem `httpx.Client.post`; refresh po wygaśnięciu; nieudany refresh
    kasuje tokeny i daje 409 na `/api/sync`), `tests/test_ingest.py` (zły token
    → 401; token usera A nie zapisuje do usera B; upsert nadpisuje; 422 przy
    brakującym polu; body > 1 MB → 413), `tests/test_sync_sources.py`
    (`sync_range` z fałszywym providerem `SOURCE="x"` ustawia `source`
    wszędzie; `maybe_sync` bez aktywnego źródła nic nie robi). Istniejące
    `test_garmin_multiuser.py` i `test_day_trends_services.py` **muszą przejść
    bez zmian** oprócz dopisania nowych kluczy do listy kontraktu.

Weryfikacja: pełny pytest zielony → commit + push. Bump `X` w `VERSION`
(zmiana logiki syncu). Nota bez zmian.

### Część A — Polar (AccessLink v4) (5/10)

Jedyny producent z tabeli, u którego oficjalne API jest samoobsługowe i za
darmo: rejestracja klienta na https://admin.polaraccesslink.com kontem Polar
Flow (właściciel, raz; `redirect_uri` = `https://fit.krasnal.cc/connect/polar/callback`).
Dokumentacja: https://www.polar.com/polar-api-v4/ .

1. **Rejestr**: `authorize_url = https://auth.polar.com/oauth/authorize`,
   `token_url = https://auth.polar.com/oauth/token` (client credentials w
   nagłówku Basic), scopes `activity:read training_sessions:read profile:read`.
   Access token ważny **12 h** → refresh w `oauth.bearer` jest tu codziennością,
   nie wyjątkiem.
2. **`app/providers/polar.py`** — `PolarProvider(user_id, db)`, `SOURCE="polar"`:
   `get_daily_summary(day)` z listy dziennej aktywności (endpoint v4 z zakresem
   dat; dane dostępne **90 dni wstecz** — `sync_range(days=30)` mieści się),
   `kcal_total = calories`, `kcal_active = active_calories` (jeśli v4 zwraca),
   `kcal_bmr = calories − active_calories`, `steps`; `get_activities` z
   sesji treningowych (`sport`, `duration` ISO 8601 → sekundy, `distance`,
   `calories`, `heart_rate.average`); `get_weights` — **do weryfikacji na
   starcie**, czy v4 daje historię wagi z Polar Flow (w v3 była w „physical
   information" jako transakcja); jeśli nie — zwraca `[]`, waga ręcznie.
3. **Pułapki do sprawdzenia w dokumentacji przed kodem**: (a) czy `calories`
   zawiera BMR (w v3 tak — „total daily calories including BMR"; jeśli v4 daje
   tylko aktywne → suma z BMR wg Polara albo `None`), (b) czy v4 wymaga
   jeszcze osobnego „register user" po autoryzacji (v3 wymagało `POST /users`
   — bez tego dane były puste), (c) limity 3000/15 min są bez znaczenia przy
   10 testerach, ale 429 → log i wyjście, jak w Garminie.
4. **Typy aktywności**: mapa `sport` Polara → słownik `energy.activity_kcal_model`
   (`RUNNING` → `running`, `CYCLING`/`ROAD_BIKING` → `cycling`,
   `STRENGTH_TRAINING` → `strength_training`, `WALKING` → `walking`, reszta →
   `other`) — jedno miejsce w providerze, nie rozsiane po `energy.py`. Gdy
   wejdzie plan „Tabela MET jako dane", mapa idzie do `met_table.json`.
5. **Testy** `tests/test_provider_polar.py`: provider pod zmockowanym `httpx`
   (nagrane przykładowe odpowiedzi w `tests/fixtures/polar/*.json`), mapowanie
   pól, ISO-duration, brak wagi → `[]`, 401 z API → `ProviderNotConnected`.
6. Nota `/prywatnosc` + `PRIVACY_VERSION` (jeśli to pierwszy nowy producent),
   `.env.example` i `deploy/README.md` (jak zarejestrować klienta), telemetria
   `polar_connect_ok`.

### Część B — Fitbit / Pixel Watch przez Google Health API (7/10, nie zaczynać przed X 2026)

Fitbit Web API jest **wyłączane we wrześniu 2026** (nowe integracje
niemożliwe, tokeny nie przenoszą się). Następca — **Google Health API**
(https://developers.google.com/health/about ): OAuth Google, 31 typów danych,
metody `list` / `reconcile` / `rollUp` / `dailyRollUp`. Obejmuje wszystkie
Fitbity i Pixel Watch. Haczyk: **wszystkie scope'y są „restricted"** →
obowiązkowa weryfikacja aplikacji (privacy & security review) przed produkcją.

1. **Warunki wstępne (właściciel, poza kodem)**: projekt w Google Cloud,
   ekran zgody OAuth, włączony Health API. Do sprawdzenia: czy tryb
   *Testing* ekranu zgody (do 100 testerów wpisanych ręcznie) pozwala używać
   restricted scopes bez weryfikacji — jeśli tak, pilot działa bez review; jeśli
   nie, ta część czeka na review (tygodnie) i ocenę, czy warto.
2. **Rejestr**: standardowe endpointy Google (`accounts.google.com/o/oauth2/v2/auth`,
   `oauth2.googleapis.com/token`), `access_type=offline`, `prompt=consent`.
3. **`app/providers/google_health.py`** — `SOURCE="google_health"` (etykieta
   „Fitbit / Pixel Watch"): `dailyRollUp` dla kcal i kroków (kcal total z BMR
   — potwierdź nazwę typu), `list` dla treningów i wagi.
4. Testy, nota, telemetria — jak w A. Dodatkowo `deploy/README.md`: procedura
   dodania testera do listy testowej projektu Google (bez tego dostanie
   „app not verified").

### Część C — Whoop (API v2) (4/10)

Dokumentacja: https://developer.whoop.com/api/ (aplikację rejestruje właściciel
w Developer Dashboard). Whoop **nie liczy kroków** i nie ma dziennej historii
wagi — użytkownik Whoopa wpisuje kroki (już jest `POST /api/day/{day}/steps`)
albo model bierze `DEFAULT_STEPS`; wagę wpisuje ręcznie.

1. **Rejestr**: `authorize_url = https://api.prod.whoop.com/oauth/oauth2/auth`,
   `token_url = https://api.prod.whoop.com/oauth/oauth2/token`, scopes
   `read:cycles read:workout offline` (`offline` jest **warunkiem** refresh
   tokena; access token żyje ~1 h).
2. **`app/providers/whoop.py`**, `SOURCE="whoop"`: cykle
   `GET /developer/v2/cycle?start&end` → `score.kilojoule / 4.184` = kcal total
   **z BMR** (tak Whoop pokazuje „Calories"). **Decyzja mapowania**: cykl
   Whoopa to nie doba kalendarzowa (od snu do snu) — przypisujemy cykl do daty
   jego `start` w strefie usera; cykl bez `end` (trwa) = dzień w toku,
   `complete=False`; `score_state != "SCORED"` → `kcal_total=None`. Treningi
   `GET /developer/v2/activity/workout` → `score.kilojoule`, `sport_name`,
   `start/end` → `duration_s`, `distance_meter`, `average_heart_rate`;
   `external_id` = UUID treningu. `get_weights` → `[]`.
3. **UI**: gdy aktywne źródło nie dostarcza kroków (`ProviderSpec.provides_steps
   = False`), pole ręcznych kroków w `mobile.html` przestaje pokazywać
   „Synchronizacja z Garminem nadpisze tę wartość" (linia ~258) — bo nie nadpisze.
4. Webhooki Whoopa pomijamy (pull z throttlem `maybe_sync` wystarcza na pilota).
5. Testy (`tests/test_provider_whoop.py`: kJ→kcal, cykl w toku, brak `SCORED`),
   nota, telemetria — jak w A.

### Część D — Oura (API v2) (4/10)

Dokumentacja: https://cloud.ouraring.com/docs/ . Pierścień, nie zegarek —
liczy kroki i total kcal, nie ma wagi. Do działania API potrzebne aktywne
członkostwo Oura po stronie usera (sprawdź przy ankiecie).

1. **Rejestr**: `authorize_url = https://cloud.ouraring.com/oauth/authorize`,
   `token_url = https://api.ouraring.com/oauth/token`, scopes `daily workout`.
   Refresh token jest **jednorazowy** — po odświeżeniu zapisz nową parę w tej
   samej transakcji, inaczej równoległy `maybe_sync` i `/api/sync` mogą się
   wzajemnie wylogować (`sync._lock` już to mityguje w jednym procesie; nie
   ustawiaj workers > 1 — patrz CLAUDE.md).
2. **`app/providers/oura.py`**, `SOURCE="oura"`:
   `GET /v2/usercollection/daily_activity?start_date&end_date` → `day`,
   `total_calories` (z BMR), `active_calories`, `steps`;
   `GET /v2/usercollection/workout` → `calories`, `activity`,
   `start_datetime/end_datetime`, `distance`; brak tętna w podsumowaniu
   treningu → `avg_hr=None`. `get_weights` → `[]`.
3. Uwaga na `total_calories` dnia bieżącego — rośnie w ciągu dnia, więc
   `complete=False` do jutra działa tu identycznie jak z Garminem
   (`out_source="mixed"`).
4. Testy, nota, telemetria — jak w A.

### Część E — Apple Watch / Apple Health (5/10 serwer + instrukcja dla testera)

Apple **nie ma web API** — dane HealthKit żyją na iPhonie. Trzy drogi:

- **(E1, pilot — zalecane)** aplikacja **Health Auto Export** (App Store,
  płatna; automatyzacja „REST API" wysyła JSON POST-em na dowolny adres z
  własnym nagłówkiem, np. `X-API-Key`; dokumentacja formatu:
  https://github.com/Lybron/health-auto-export ). Tester ustawia URL
  `https://fit.krasnal.cc/api/ingest/apple`, nagłówek z tokenem z Ustawień,
  agregację dzienną, zakres „od ostatniej synchronizacji", harmonogram co
  godzinę. Ograniczenie Apple: eksport działa tylko przy odblokowanym telefonie
  → dane przychodzą z opóźnieniem; dlatego dzień bieżący jest `complete=False`,
  a domknięcie przychodzi w kolejnych paczkach (upsert).
- **(E2, za darmo, kruche)** Skrót iOS (Shortcuts: „Find Health Samples" →
  suma → „Get Contents of URL") wysyłający nasz znormalizowany JSON z części 0
  pkt 6. Szablon skrótu do pobrania w `deploy/README.md`; nie robimy dla niego
  osobnego parsera — celuje wprost w format znormalizowany.
- **(E3, docelowo)** natywna aplikacja / Flutter `health` → punkt „Aplikacja
  mobilna (Etap 2)". Poza zakresem tego planu.

1. **`app/providers/apple.py`** — nie `DataProvider` (nic nie pobiera), tylko
   parser `parse_health_auto_export(payload: dict) -> NormalizedIngest`:
   `data.metrics[]` po `name`: `active_energy` + `basal_energy_burned` →
   `kcal_total` (suma; brak `basal` → `None`, decyzja 3), `step_count` →
   `steps`, `weight_body_mass` → wagi; `data.workouts[]` → aktywności
   (`name` → typ przez tę samą mapę co w A, `start/end`, `activeEnergyBurned`
   → kcal, `distance`, `avgHeartRate`; `external_id` = `id` treningu albo hash
   `start+name`). Jednostki: sprawdź `units` każdej metryki (`kcal` vs `kJ`,
   `kg` vs `lb`) — Health Auto Export eksportuje w jednostkach ustawionych
   przez usera. Daty w formacie `YYYY-MM-DD HH:MM:SS ±HHMM` → data lokalna
   telefonu (nie konwertować do UTC — doba usera to doba telefonu).
   **Zweryfikuj nazwy pól na realnej paczce** przed napisaniem testów —
   fixture `tests/fixtures/apple/hae_daily.json` ma pochodzić z prawdziwego
   eksportu (zanonimizowanego), nie z pamięci.
2. **Rejestr**: `ProviderSpec(id="apple", kind="push", provides_steps=True)`;
   `connected()` = `ingest_token` istnieje **i** jest ≥1 `DailySummary` ze
   `source="apple"` (token sam w sobie nie znaczy, że telefon coś wysłał).
   Status w UI: „ostatnia paczka X min temu" z `max(sync_ts)`.
3. **Instrukcja dla testera** w `deploy/README.md` (sekcja onboarding) i skrót
   w karcie Ustawień: zrzuty kroków konfiguracji Health Auto Export, co
   zaznaczyć (Active Energy, Basal Energy, Steps, Weight, Workouts), agregacja
   dzienna. Bez tej instrukcji funkcja praktycznie nie istnieje.
4. **Nota `/prywatnosc`**: nowy podpunkt — dane wysyła aplikacja na telefonie
   usera, bezpośrednio do nas, po HTTPS, z tokenem urządzenia; token można
   unieważnić w Ustawieniach. Bez OAuth — Apple nic nie widzi.
5. Testy `tests/test_ingest_apple.py`: fixture → oczekiwane `DailySummary`
   (suma active+basal), kJ→kcal gdy `units="kJ"`, brak basal → `kcal_total is
   None` + `steps` zapisane, paczka „since last sync" z dwoma dniami nadpisuje
   wczorajszy `complete=True`.

### Część F — Health Connect (Android): Samsung, Xiaomi, Huawei, Pixel (5/10 + osobno per producent instrukcja)

Health Connect to **API na telefonie**, bez chmury — z serwera nic nie
pobierzemy. Do czasu Etapu 2 (własna apka Flutter z pakietem `health`) jedyna
droga to aplikacja-most na telefonie, która czyta Health Connect i POST-uje do
`POST /api/ingest/health_connect` (część 0 pkt 6). Kandydaci: open-source
**health-connect-webhook** (https://github.com/mcnaveen/health-connect-webhook —
webhook z własnym nagłówkiem) — sprawdź na starcie, czy nadal utrzymywany i
jakie typy rekordów wysyła; **Health Sync** (płatny) synchronizuje między
platformami i eksportuje CSV na Google Drive, ale nie ma webhooka — odpada
jako most, przydaje się jako *dostawca* do Health Connect (Huawei Health →
Health Connect).

1. **`app/providers/health_connect.py`** — parser rekordów HC → format
   znormalizowany: `TotalCaloriesBurnedRecord` → `kcal_total` (z BMR),
   `ActiveCaloriesBurnedRecord` → `kcal_active`, `StepsRecord` → `steps`
   (suma w dobie), `WeightRecord` → wagi, `ExerciseSessionRecord` →
   aktywności (`exerciseType` int → typ przez mapę HC; `external_id` =
   `metadata.id`). Rekordy mają `startTime/endTime` UTC + `startZoneOffset` —
   dobę licz w offsetcie rekordu, nie w UTC.
2. **Kluczowy problem HC — wielu autorów tego samego typu**: `TotalCaloriesBurned`
   mogą pisać jednocześnie Samsung Health i Garmin Connect (ten sam bieg dwa
   razy). Zasada: **nigdy nie sumujemy między `metadata.dataOrigin`**. Parser
   grupuje po `dataOrigin` (nazwa pakietu), a wybór autora robi ustawienie
   `hc_origin` (AppSetting, nie sekret) — domyślnie autor z największą liczbą
   rekordów w paczce; UI pokazuje listę wykrytych autorów z radiem. Kroki i
   kcal muszą iść od **tego samego** autora (inaczej kroki Xiaomi + kcal
   Samsunga = dwie różne doby).
3. **Per producent — co realnie dostaniemy** (do instrukcji dla testera i do
   etykiety w UI):
   - **Samsung Health** (Galaxy Watch): pisze do HC kroki, `TotalCaloriesBurned`,
     wagę, BMR, sesje treningowe (źródło: blog Samsung Developer „Accessing
     Samsung Health Data through Health Connect"). Pełna parytetowość z
     Garminem. Samsung Health Platform API (serwerowe) jest partnerskie — nie
     dla nas, nie próbować.
   - **Xiaomi (Mi Fitness, Mi Band / Watch)**: Mi Fitness udostępnia do HC
     **tylko kroki, sen, tętno, treningi — bez kcal dobowych**. Dla Xiaomi
     `kcal_total=None` zawsze → bilans z modelu (`tdee_theoretical` z
     prawdziwymi krokami i treningami). To trzeba **powiedzieć testerowi
     wprost** w UI („Xiaomi nie podaje spalonych kcal — liczymy je z kroków i
     treningów"). Zepp (Amazfit) — analogicznie, sprawdź na starcie, czy ma
     już eksport kcal do HC.
   - **Huawei**: Huawei Health nie pisze natywnie do HC; ścieżka: Health Sync
     (Huawei Health → Health Connect) → most → my. Dwa pośredniki, pilot tylko
     jeśli ktoś naprawdę ma Huawei.
   - **Pixel Watch / Fitbit na Androidzie**: Fitbit pisze do HC — alternatywa
     dla części B bez Google OAuth review.
   - **Garmin na Androidzie**: Garmin Connect też pisze do HC — awaryjna
     ścieżka, gdyby `garminconnect` (D4) przestał działać.
4. **Rejestr**: `ProviderSpec(id="health_connect", kind="push")`, etykieta
   w UI z nazwą wykrytego autora („Health Connect · Samsung Health"). `connected()`
   jak w E. `provides_steps=True`; `provides_kcal` zależy od autora → w
   `day_report` `source_label` dostaje dopisek „(kcal z modelu)", gdy
   `kcal_total_garmin is None` mimo aktywnego źródła.
5. **Instrukcje w `deploy/README.md`**: osobne akapity Samsung / Xiaomi /
   Huawei — jak włączyć udostępnianie do Health Connect w danej apce producenta,
   jak skonfigurować most (URL, nagłówek, typy rekordów), co wybrać jako autora.
6. Testy `tests/test_ingest_health_connect.py`: fixture z dwoma autorami →
   brak sumowania, wybór autora; rekord Xiaomi bez kcal → `kcal_total None`,
   kroki zapisane; offset strefy → właściwa doba; `ExerciseSession` → `Activity`
   z prefiksem `health_connect:`.
7. Nota `/prywatnosc` — jak w E (push z telefonu, bez OAuth).

### Część G — opcjonalne dodatki (poza kcal, tu tylko żeby nie zgubić)

- **Withings (waga)** (3/10): oficjalne OAuth2 (`account.withings.com/oauth2_user/authorize2`,
  `wbsapi.withings.net/v2/oauth2`), token 3 h + refresh 12 mies. Dla
  użytkowników Oura/Whoop/Polar bez wagi w API — automatyczna waga ze smart
  wagi zamiast ręcznego wpisu (D3). Wchodzi w rejestr jako źródło **tylko
  wagi** (`kind="pull"`, `provides_kcal=False`) — wymaga rozluźnienia decyzji 1
  na „jedno źródło totali + opcjonalne osobne źródło wagi".
- **Strava** — nie: nowe aplikacje działają wyłącznie na koncie autora do czasu
  zatwierdzenia przez Stravę, kcal tylko z treningów (bez totali).
- **Garmin Health API (oficjalne)** — nie: program tylko dla firm z osobowością
  prawną, opłata wdrożeniowa, nabór wstrzymany (2026). Zostajemy na D4.
- **Suunto / Coros** — API partnerskie; ścieżka: ich apki → Health Connect → F.

Weryfikacja każdej części: pełny pytest zielony → commit + push (bump `X`).
Deploy i rejestracje klientów OAuth u producentów — właściciel.

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
2. **Routery i serwisy — zamień wszystkie zegary procesu** na wersje z profilu:
   `app/routers/meals.py` (`_queue_meal` — godzina wpisu; `estimate_meal_photo`
   i `estimate_meal_text` — domyślny dzień szacowania; `save_meal` — godzina),
   `app/routers/transfer.py` (`transfer_export` — data w nazwie pliku eksportu),
   `app/routers/day.py` (`add_manual_activity`). Każdy z tych route'ów ma już
   `user`; profil pobierz przez `db.get(UserProfile, user.id)`.
   `app/services/day.py:day_report` profil już ma — użyj go zamiast dokładać
   drugie zapytanie. **Trendy są już gotowe na tę zmianę:**
   `app/services/trends.py:payload(db, user_id, days, today=None)` przyjmuje
   dzień parametrem — wystarczy, że oba route'y w `app/routers/trends.py`
   podadzą `today=user_today(profile)` zamiast zdawać się na domyślne
   `date.today()`.
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

# Archiwum DONE — v24.0.0 – v25.0.0

Pełne wpisy przeniesione z [DONE.md](../DONE.md), gdzie został indeks.
**Nie czytaj całego pliku** — wyciągnij jedną sekcję:
`awk '/^## <fragment tytułu>/,/^## /' archive/done-v24-v25.md`

---

## Integracja ze Strava — dla użytkowników bez Garmina (25.0.0, e102d2f)

**Implementacja:** Nowy provider Strava (`app/providers/strava.py`) z OAuth v3
(access + refresh token). Priorytet Garmin > Strava (uniknięcie duplikatów
— Garmin zwykle eksportuje tam automatycznie). Activity.source zawiera
"strava" + prefiks garmin_id: "strava-{activity.id}".

**RODO — nowa zgoda:** `Consent(kind="strava")` niezależna od `llm_photos`.
Migracja w `app/db.py`: backfill starej zgody `llm_photos` na nową
`PRIVACY_VERSION` (żeby nie tracić zgód obecnych userów — sekcja o LLM się
nie zmienia, zmienia się sekcja o Strawie). `PRIVACY_VERSION: 2026-09-03 → 2026-09-11`.

**Routing OAuth:** POST `/settings/strava/connect` (formularz z checkboxem
zgody), GET `/settings/strava/callback` (token exchange), POST
`/settings/strava/disconnect` (deauthorize + cleanup).

**Funkcjonalność:** `get_provider_for_user()` w `app/providers/__init__.py`
wybiera providera (Garmin > Strava > None). `sync.py: maybe_sync()` i
`profile.py: sync()` używają tego zamiast GarminProvider na sztywno.
Strava pobiera aktywności — typ, czas, dystans, kalorie, tętno (bez wagi,
bez dziennego podsumowania, bo tam ich nie ma).

**Statystyki:** Nowe eventy w `usage.EVENTS`: `strava_connect_ok`,
`strava_disconnect`, `strava_sync_ok`, `strava_sync_error`.

**Nota `/prywatnosc`:** Nowa sekcja `#strava` z wyjaśnieniem co się synchronizuje,
że OAuth (nie login), że token szyfrowany, że Garmin ma priorytet, że zgodę
można wycofać.

**Testy:** `tests/test_strava.py` (7 testów) — tokeny, provider selection,
consent independence, daily summary (None), weights (empty), missing tokens.

**Co nie wchodzi:** UI w templates (commit 2), stats na `/usage` (commit 2),
inne producenci (Polar, Oura, Whoop, Apple Health, Health Connect — na liście
w TODO).

**Co robi właściciel:** Rejestracja w https://www.strava.com/settings/api,
wklejenie client_id/secret do .env, potwierdzenie zgody userów.

**Bez pushu, bez pełnej suity testów** (per plan TODO.md).

## ~~Prognoza doby: spoczynek z historii Garmina zamiast Mifflina~~ ✓ zrobione (24.9.2)

**Objaw (2026-09-10, `/usage?scope=me`):** prognoza poranna 1755–1896 kcal,
a dni bez treningu kończyły się na 2088–2236 — ~350 kcal za nisko.
**Przyczyna:** spoczynek do prognozy brał `max(kcal_bmr_garmin z dziś, Mifflin)`;
Garmin podaje spoczynek narastająco (rano ~680), więc zawsze wygrywał Mifflin
(~1644), a pełnodobowy spoczynek Garmina to ~2000. **Decyzja:** `bmr_full` =
mediana `kcal_bmr_garmin` z ostatnich 7 domkniętych dni (ta sama lista, którą
pobiera bazowy NEAT — `day.py:_history_baselines`, zero nowych zapytań),
fallback Mifflin przy < 3 dniach; odpowiedź `/api/day` ma `forecast.bmr_source`
(`garmin`/`mifflin`). Treningi nadal poza bazą — cel rośnie po ich synchronizacji
(decyzja właściciela). Testy w `test_activities_api.py`. Nota `/prywatnosc`
bez zmian. **Właściciel:** po tygodniu sprawdź na `/usage` rozkład „prognoza
poranna ÷ pomiar końcowy" — dni bez treningu powinny być ~1,0.

## ~~Cel dnia z prognozy pełnej doby + roszady na „Dziś"~~ ✓ zrobione (24.4.0 f0f7080, 24.5.0 1f4d59d, 24.6.0 — statystyki)

**Zgłoszenie właściciela 2026-09-06, poranek:** „cel dnia 737 — to nie jest cel
dnia; realistyczny cel powinien zakładać zwyczajny dzień, a przy aktywnościach
rosnąć; zostało dziś 150 powinno liczyć się od nowego celu." Spalone 811 kcal,
spożyte 550, bilans −261 — te trzy były OK.

**Odkrycie:** Garmin w podsumowaniu dnia podaje wydatek (i spoczynek)
**narastająco**, nie za całą dobę. Poprawka 21.5.0 zakładała odwrotnie (nie
dało się wtedy sprawdzić na żywym koncie, patrz jej wpis niżej). Skutek:
cel dnia = pomiar „dotąd" × kalibracja − deficyt, rano absurdalnie niski.
Komentarz w `balance.py` o „spoczynku za całą dobę od rana" był błędny —
mechanizm dnia w toku (pomiar bez `max` z modelem) zostaje, zmienia się
wyłącznie to, z czego liczy się **cel**.

**Decyzja (24.4.0, `app/services/energy.py:full_day_forecast`,
`app/services/day.py:_baseline_neat/_sync_hour_local`):** dla dnia w toku cel
dnia liczy się z **prognozy pełnej doby** = zmierzone do ostatniej
synchronizacji + spoczynek do północy (BMR/h × godziny do końca doby) +
zwyczajny ruch do końca okna czuwania 6–23 (bazowy NEAT × ułamek okna, który
został). Bazowy NEAT = **mediana** z ostatnich 7 domkniętych dni z
`kcal_active_garmin − netto aktywności zegarkowych` (mediana, żeby dzień
z marszem 4,5 h nie zawyżał bazy); poniżej 3 dni historii — fallback
`DEFAULT_STEPS` jak w modelu. BMR do prognozy = `max(kcal_bmr_garmin,
Mifflin)` — narastające BMR Garmina przegrywa z Mifflinem, całodobowe (gdyby
jednak) wygrywa. Godzina odniesienia = `sync_ts` w strefie użytkownika, nie
„teraz" (pomiar jest aktualny na moment synchronizacji). Własność: prognoza
**monotoniczna względem czasu**, o północy równa pomiarowi — dzień leniwszy
niż baza sam zjeżdża w dół w ciągu dnia; każda zsynchronizowana aktywność
podnosi prognozę od razu (siedzi w „zmierzone"). `kcal_out` i bilans
**zostają pomiarem** (fakty), prognoza dotyczy celu i „zostało dziś".
Bez trzeciego przesunięcia: konserwatyzm nadal tylko w 0.97 i floor-50.
Nowe pola `/api/day`: `forecast_kcal`, `forecast{measured, resting_left,
neat_left, hours_left, baseline_neat, baseline_days, bmr_full}` (`null` dla
dni domkniętych / bez Garmina). `deficit_warning` liczony z prognozy.
Pierwsza prognoza dnia zapisywana raz w `DailySummary.forecast_total_kcal`
(migracja addytywna, bez backfillu). Dla dnia domkniętego `forecast_kcal ==
kcal_out`, nic się nie zmienia; Trendy bez zmian.

**Roszady UI (24.5.0, `mobile.html`):** kcal spalone w miejscu „zostało dziś";
„zostało dziś" pod bilansem (siatka: spożyte | spalone / cel dnia | bilans /
puste | zostało dziś / waga | do celu). Przycisk „Aktywności/Kroki" i pole
„pomiar wagi" przeniesione na górę zakładki **Dodaj** (nowa karta „Aktywność
i waga" nad „Dodaj posiłek"); waga zapisuje się pod datę z pola daty posiłku
(domyślnie dziś). Z „Dziś" znikła linia „zapotrzebowanie skorygowane o −x%";
równanie celu dnia (teraz z rozbiciem prognozy: zmierzone + spoczynek +
zwyczajny ruch, baza i liczba dni) **oraz** stan kalibracji są na samym dole
zakładki **Trendy** (`renderTargetFormula`, z ostatniego raportu „dziś" albo
jednego zapytania `/api/day`).

**Statystyki (24.6.0, `/usage`):** w sekcji „Wydatek: model vs pomiar" nowy
rozkład **prognoza poranna ÷ pomiar końcowy** dla dni domkniętych (mediana,
p10, p90, % poza ±15%) — mówi, czy cel pokazywany rano trafia; w „Moje dni"
(`scope=me`) kolumna „Prognoza poranna". Honoruje `scope`, agregaty.

**Testy:** `test_energy.py` (prognoza: składniki o 9:00, monotoniczność,
o północy == pomiar, przed 6:00 pełny NEAT), `test_activities_api.py`
(dzień w toku z 7 dniami historii → baza 400 = mediana, prognoza > 2000
przy pomiarze 811, zapis pierwszej prognozy; dzień domknięty bez prognozy;
fallback bazy przy 1 dniu historii; test objawu 4213 przepięty na
`forecast_kcal`), `test_usage.py` (rozkład prognozy liczy tylko dni
domknięte). Uruchamiane tylko dotknięte pliki; pełna suita po zgodzie.

**Nota `/prywatnosc`:** bez zmian — prognoza liczy się z danych już
zbieranych, nowa kolumna to pochodna tych danych, bez nowego odbiorcy.

**Dla właściciela:** komentarz o całodobowym BMR w `balance.py` poprawiony
(24.6.1, sam komentarz — zachowanie `day_balance` bez zmian); wpis „Poprawa
wyliczania kcal na dzień w toku" niżej ma niezweryfikowane założenie —
**to jest jego weryfikacja: Garmin podaje narastająco**.

## ~~Podmiana ikony krasnala z prawdziwej grafiki 24×24~~ ✓ zrobione (24.3.5, CSS/HTML wjechało wcześniej przypadkiem w 82492c4)

„Ikona krasnala przy komunikatach" (24.3.0, patrz niżej) trzymała fallback na
`icon-192.png` (ikona PWA z rowerem). Zastąpiona głową krasnala wyciętą z
`data/krasnal-icon-source.png` (plik poza repo, `.gitignore`).

**Decyzje:**
- Bitmapa **72×72 px**, mimo że w CSS ikona ma 20/24 px — na Retinie (DPR 2–3)
  24 px fizyczne rozmywałyby cienką kreskę brody w szarą plamę; przeglądarka
  skaluje 72→20/24 sama i lepiej.
- Plik to **czysta maska alfa** (RGB czarne, informacja tylko w kanale A),
  kolorowana przez CSS (`background: currentColor` + `mask-image` /
  `-webkit-mask-image`) — jeden plik zamiast osobnych wersji jasny/ciemny,
  bo komunikaty siedzą w `.muted` (`var(--stone)`) i w obu motywach mają być
  tego samego szarego co tekst.
- Grubość kreski (`MaxFilter`) dobrana wizualnie na `--stroke 11` (skala
  źródło→72px ~17×; przy tej wartości czapka z pomponem i broda są czytelne
  jako zwarte kształty, oczy jako plamy — cieńsze kreski brody i tak są
  nie do zachowania przy 20 px).
- `scripts/make_krasnal_icon.py` (wzorzec: `scripts/extract_logo.py`) jest
  jedynym zapisem, jak `app/static/krasnal-24.png` powstał z pliku źródłowego.

Rozszerzony `tests/test_krasnal_icon.py`: serwowanie 200/`image/png`, rozmiar
72×72 z alfą, przezroczyste narożniki + tusz w środkowej kolumnie, oraz
sprawdzenie, że każda ścieżka `/static/krasnal-*.png` znaleziona w
`mobile.html` faktycznie odpowiada 200 (zamiast sztywnej ścieżki na
`icon-192.png` jak wcześniej).

Statystyki: świadomie brak (zmiana czysto wizualna, bez opt-in; sygnał
funkcjonowania to brak 404 na `/static/krasnal-24.png` w logach uvicorn po
deployu — sprawdza właściciel ręcznie).

`/prywatnosc` bez zmian (nic nowego nie zbieramy). Weryfikacja ręczna na
dev serwerze (jasny/ciemny motyw) **pominięta na tym etapie** na wyraźną
prośbę właściciela — do zrobienia przy najbliższym wejściu na dev serwer.

Uwaga do historii: CSS/HTML tej zmiany (`.krasnal-ico` z maską,
`krasnalSays()` bez `<img>`) trafiło do repo wcześniej, przypadkiem, w
commicie 82492c4 (o zakresie białka) — równoległa sesja pracowała na tym
samym pliku wg tego samego planu z TODO.md i oba zestawy edycji się scaliły
na dysku przed jej commitem. Ten wpis domyka resztę (skrypt, wygenerowany
plik, test, VERSION, TODO→DONE).

## ~~Testy: „dziś" ze strefy użytkownika, nie zegara runnera — naprawa czerwonego CI~~ ✓ zrobione (24.3.1)

**Objaw:** push b70803e/4189a74 o 00:11–00:23 CEST 2026-09-06 (= 22:11–22:23
UTC 2026-09-05) → GitHub Actions 4 failed / 188 passed, deploy zablokowany:
trzy testy w `tests/test_activities_api.py` (aktywność dodana przez API
„znika" z `/api/day/{today}`, `kcal_out` bez ręcznego biegu, `StopIteration`)
i `test_html_and_json_trends_come_from_one_source` (oś wykresu 05.09 vs 06.09).

**Przyczyna (potwierdzona reprodukcją, nie hipoteza):** od 23.0.0 routery
liczą „dziś" przez `clock.user_today(profile)` — bez `tz` w profilu to
**Europe/Warsaw**. Testy brały `date.today()` = strefa **procesu**, czyli UTC
na runnerze. Między 22:00 a 24:00 UTC (lato) obie daty się różnią:
`POST /api/activities` bez daty ląduje na dniu warszawskim, test czyta dzień
UTC; `trends_service.payload(db, 1, 30)` bez `today` bierze `date.today()`
(`app/services/trends.py:59`), router podaje `user_today`. Na Macu właściciela
(strefa warszawska) obie wartości są równe, więc lokalnie suita była zielona
o każdej porze — błąd widoczny tylko w CI i tylko w 2-godzinnym oknie przed
północą UTC. Kod aplikacji zachował się poprawnie; stare były testy.

**Naprawa:** pomocnik `app_today()` w `tests/conftest.py`
(`clock.user_today(None)`, z docstringiem „dlaczego nie `date.today()`"),
użyty zamiast `date.today()` w `test_activities_api.py` (13 miejsc),
`test_birth_year.py` (`/api/weight` + `/api/day`) i jako `TODAY` w
`test_day_trends_services.py`; tam też wszystkie cztery wywołania
`trends_service.payload(...)` dostały jawne `today=TODAY` — test ma dowodzić,
że HTML i JSON liczą z jednego źródła, a nie że serwis zgaduje „dziś" tak samo
jak router. Import przez `from tests.conftest import app_today` (`tests/` jest
pakietem). Nietknięte celowo: `test_usage.py` (dzień serwera po obu
stronach), `test_consent.py`, `test_queue_settings.py` (podają datę do
serwisu, nie porównują z API), `test_timezone.py` (własne zamrażanie).

**Decyzje:** naprawa w testach, nie `TZ=Europe/Warsaw` w workflow — to by
zamaskowało klasę błędu, a suita ma być zielona w dowolnej strefie procesu.
Bez globalnego zamrażania czasu (`sync/calibration/usage` wołają
`date.today()` poza `clock` — osobny punkt w TODO.md „Pochodne naprawy…").

**Weryfikacja:** cztery zmienione/powiązane pliki
(`test_activities_api`, `test_day_trends_services`, `test_birth_year`,
`test_timezone`) — 41 passed pod `TZ=Etc/GMT+12`, `TZ=UTC`
(reprodukcja awarii z CI: przed naprawą 4 failed), `TZ=Pacific/Kiritimati`
(data „z przodu") i bez `TZ`; cała suita kolekcjonuje się (199 testów).
Pełna suita nie była uruchamiana lokalnie (zasada z TODO.md) — sprawdzi ją
CI po pushu właściciela.

Bez statystyk (zmiana w testach). Nota `/prywatnosc` bez zmian.

---

## ~~Ikona krasnala przy komunikatach~~ ✓ zrobione (b70803e, 24.3.0)

**Zgłoszenie właściciela 2026-09-05:** zniknęła ikonka krasnala przed
tekstem motywacyjnym; miała wrócić i pojawiać się przed różnymi komunikatami
stanu.

**Rozwiązanie:** jedna funkcja `krasnalSays(el, text)` w `mobile.html`
(`innerHTML` z `<img class="krasnal-ico">` + `esc(text)` — escape
obowiązkowy, quipy i błędy to tekst, nie HTML) i słownik `KRASNAL_STATUS`
w jednym miejscu (sync/synced/estimating/queue/nodata) — podmienił
rozrzucone dotąd komunikaty stanu w `doSync`, `playPending`, `estimate`
i fallback `renderToday`. Quip motywacyjny (`rep.quip`) przez tę samą
funkcję.

Grafika `app/static/krasnal-24.png` (24×24, wycięta z
`data/krasnal-icon-source.png`) jeszcze nie istnieje — użyto fallbacku
`icon-192.png` (`width:20px`) do czasu, aż właściciel dostarczy plik —
patrz TODO.md „Podmiana ikony krasnala z prawdziwej grafiki 24×24".

Zweryfikowane ręcznie w przeglądarce (lokalne konto testowe, usunięte po
sprawdzeniu): ikonka renderuje się przy quipie i przy „Krasnal nie ma
danych…", żadnych błędów JS w konsoli. Test `tests/test_krasnal_icon.py`
pilnuje, żeby `/static/icon-192.png` (ścieżka użyta w JS) było serwowane.

Bez statystyk (zmiana czysto wizualna, świadomie bez kroku „Statystyki").
Nota `/prywatnosc` bez zmian.

---

## ~~Cel białka zależny od bilansu (redukcja / masa)~~ ✓ zrobione (572314c, 24.2.0) — WYMAGANIA.md §10.2

`who_norms.json` miał per grupę martwe pole `protein_cut_g_per_kg: [1.2, 1.6]`
— nic go nie czytało; pasek białka brał zakres wyłącznie ze stylu życia.

**Rozwiązanie:** `who_targets(..., target_balance_kcal=0)` wybiera cel po
znaku bilansu docelowego z profilu — deficyt → „redukcyjny" (1.2-1.6 g/kg),
nadwyżka → „budowy masy" (1.6-2.2 g/kg, nowe pole `protein_bulk_g_per_kg`),
utrzymanie → brak celu. `MacroTargets.protein_goal`/`protein_goal_kind` są
`None`, gdy zakres celu pokrywa się z zakresem ze stylu życia (próg 0.05 g/kg
na obu granicach) — nie dublujemy informacji. `coverage()["protein"]` dostaje
`goal_range_g`/`goal_kind`/`goal_pct` liczone tą samą `bar_pct(...)`, którą
liczy się wypełnienie paska.

`mobile.html`: dwie pionowe kreski (`.goal-mark`) na pasku białka + wyjaśnienie
pod paskiem na „Dziś" (tylko gdy znacznik widoczny), i na żywo w Ustawieniach
pod polem bilansu — jeden słownik `PROTEIN_GOAL_TEXT` (g/kg zwierciadlą
`who_norms.json`, więc nie jest to źródło prawdy, tylko tekst — jeśli
`who_norms.json` się zmieni, słownik trzeba zaktualizować ręcznie).

Statystyki na `/usage` (`_stats_protein_goal`): `n_visible` = ilu profilom
znacznik się pokazuje (adopcja), `in_goal_pct` = % domkniętych dni z posiłkiem
w ostatnich 30 dniach, gdzie spożycie białka trafiło w dolną granicę celu
(funkcjonowanie), liczone tylko wśród profili z widocznym znacznikiem.

Testy: `tests/test_macros.py` (cut dla „mało aktywny" na deficycie, `None`
gdy pokrywa się ze stylem — „rekreacyjny", bulk dla „siłowy" na nadwyżce,
`None` przy bilansie 0).

Nota `/prywatnosc` bez zmian (nic nowego nie zbieramy).

---

## ~~Bilans zamiast deficytu w Ustawieniach + jawny „cel dnia"~~ ✓ zrobione (6096340, 24.1.0)

**Zgłoszenie właściciela 2026-09-05:** „Ustawienie deficytu na 0 wydaje się
nie działać; nie rozumiem wartości «zostało do celu dnia» — co jest celem
dnia? ani spalone, ani spożyte."

**Diagnoza:** cel dnia to `e_target = kcal_out × factor_kalibracji −
target_deficit_kcal`, a „zostało" to `floor50(e_target − kcal_in)` — sama
liczba `e_target` nie była nigdzie pokazana. Dodatkowo pole w Ustawieniach
miało `min="0"` — nadwyżka (budowa masy) była niemożliwa do ustawienia.

**Rozwiązanie:** UI mówi „bilans" (`s-balance`, `min=-1500/max=+1000/step=50`,
podpis na żywo deficyt/utrzymanie/nadwyżka), backend zostaje przy
`target_deficit_kcal` (konwersja znaku tylko w `mobile.html` i w
`/profile-form`) — rename kolumny byłby przebudową tabeli SQLite i plików
transferu, za drogo za jedno słowo. Nowy kafelek „cel dnia" na ekranie Dziś
(`target_kcal` z `/api/day`), etykieta „zostało dziś", jawna linia z formułą
pod kafelkami, `renderCalibrationLine` pokazuje też „kalibracja: 0%" zamiast
znikać. `deficit_warning` dostał lustrzaną gałąź dla nadwyżki (>20% wydatku).
Kolor kafelka bilansu rozgałęziony po znaku `target_deficit_kcal`, żeby
klasy pos/mid/neg znaczyły „dobrze/średnio/źle" także przy nadwyżce.

Statystyki na `/usage`: rozkład znaku bilansu docelowego wśród profili
(deficyt/utrzymanie/nadwyżka) + mediana wartości bezwzględnej
(`_stats_balance_goal`).

Testy: `test_balance.py` (gałąź nadwyżki), `test_activities_api.py`
(`target_kcal`), `test_birth_year.py` (konwersja znaku w `/profile-form`).

Nota `/prywatnosc` bez zmian (to samo pole, inna prezentacja).

---

## ~~Tabela MET jako dane, nie kod~~ ✓ zrobione (24.0.0) — WYMAGANIA.md §4

§4 wymaga „Tabela MET konfigurowalna (Compendium of Physical Activities)".
Współczynniki (`KCAL_PER_STEP_PER_KG`, `MET_STRENGTH`/`MET_WALKING`/
`MET_HIKING`/`MET_DEFAULT`, progi roweru, mnożniki biegu/marszu, MET ręcznych
aktywności, `DEFAULT_STEPS`) były stałymi w `app/services/energy.py` — zmiana
którejkolwiek wymagała commita. Refaktoryzacja **bez zmiany wyników**:
`tests/test_energy.py` przeszedł bez modyfikacji.

**Nowy `app/resources/met_table.json`** — wzorzec `who_norms.json`: blok
`meta.sources` (Compendium of Physical Activities / Ainsworth i in., plus
jawna nota, które wartości są uproszczeniem właściciela — próg roweru ≥20 km/h
obniżony do MET 8 zamiast ~10 z Compendium, mnożniki biegu/marszu, kcal/krok),
sekcje `steps`/`distance`/`cycling`/`garmin_activities`/`manual`. Loader
`_met()` w `energy.py` (`@lru_cache`, wzorzec `macros._norms()`) — plik jest
jedynym źródłem prawdy, brak pliku wywala import modułu (nie cichy fallback).

**Ważna różnica względem `who_norms.json`:** tylko `DEFAULT_STEPS` jest
stałą modułu inicjalizowaną raz przy imporcie (bo importują go po nazwie
`app/routers/day.py`, `tests/test_activities_api.py`, `tests/test_queue_settings.py`
— zmiana na coś dynamicznego złamałaby te importy). Wszystkie pozostałe
wartości (`neat_from_steps`, `running_kcal`, `cycling_met`,
`activity_kcal_model`, `manual_activity_kcal`, `tdee_theoretical`) czytają
`_met()` **przy każdym wywołaniu**, nie z eager module-level stałych — inaczej
`test_met_table.py`'owy dowód „wartości naprawdę idą z pliku" (podmiana
`MET_PATH` + `_met.cache_clear()` między wywołaniami) by nie zadziałał.

Testy `tests/test_met_table.py`: plik ładuje się i ma `meta.sources`, każdy
typ w `manual` ma trzy intensywności, progi `cycling` rosnące z `null` na
końcu, podmiana `MET_PATH` na plik z innym `default_met` + `_met.cache_clear()`
zmienia wynik `activity_kcal_model` dla nieznanego typu. `tests/test_energy.py`
(18 testów) i `tests/test_activities_api.py`/`test_queue_settings.py`
(importują `DEFAULT_STEPS`/`manual_activity_kcal`) przeszły bez zmian.

Nota `/prywatnosc`: bez zmian — liczymy to samo, z tych samych danych, inny
tylko sposób trzymania współczynników w kodzie.

# Zrobione — archiwum TODO

Punkty przeniesione z [TODO.md](TODO.md), gdy zostały zrealizowane. Trzymamy je
zamiast kasować: każdy wpis mówi, CO było problemem i JAKĄ decyzję podjęto,
a to bywa potrzebne, gdy ten sam temat wraca albo gdy trzeba odtworzyć powód
zmiany bez czytania diffów. Numer commita przy tytule prowadzi do implementacji.

Kolejność jak w TODO.md — najnowsze u góry. Nowe wpisy dopisuj na początku
listy, po tym akapicie.

---

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

## ~~Cztery poprawki UX w widoku mobilnym: zapis wagi, czyszczenie i odświeżanie formularza „Dodaj"~~ ✓ zrobione

Zgłoszone przez właściciela po ręcznym testowaniu `/mobile` (nie wykryte wcześniej
testami/API — to błędy interakcji w przeglądarce, niewidoczne przy testach na
poziomie serwisu/endpointu).

**1. Waga w widoku dziennym nie zapisywała się przy zmianie zakładki.** Pole
`#t-newweight` polegało wyłącznie na natywnym `onchange` (blur). W SPA
z chowaniem stron (`show()`) i klawiaturą numeryczną telefonu to zdarzenie bywa
gubione — działał tylko jawny „Zapisz profil". Fix: `flushPendingWeight()`
wywoływane na starcie `show(page)`, niezależnie od tego, czy natywny `change`
się odpalił.

**2. `#f-photo`/`#f-desc`/`#f-note` nie czyściły się po udanym „Szacuj".** Dane
trafiały już do draftu albo kolejki, ale pola wejściowe formularza stały
wypełnione aż do finalnego „Zapisz posiłek". Fix: nowa `resetAddForm()`,
wołana w obu gałęziach sukcesu `estimate()` (kolejka i draft) — `saveDraft()`
też przepisany na to samo wywołanie zamiast trzech powtórzonych linii.

**3. Godzina w „Dodaj posiłek" nie odświeżała się.** `#f-time` ustawiane raz,
przy starcie strony — kolejne posiłki w tej samej, długo otwartej sesji
dziedziczyły starą godzinę (przykład właściciela: wpis o 7:00, dodanie
kolejnego 3h później nadal brało 7:00).

**4. To samo dla daty — z uwagi na przejścia przez północ.** Właściciel zwrócił
uwagę, że przy sesji trwającej po północy stara data też by się utrzymywała.

**Wspólny fix (3+4):** nowa `refreshMealWhen()` (`#f-date` + `#f-time` :=
teraz), wołana w: `show(page)` gdy `page` to `"today"` lub `"add"` (pokrywa oba
warianty przycisków „Dziś"/„Dodaj" — mobilny dolny pasek i górną nawigację
desktopową, `goToday()`/`goAdd()` i tak przechodzą przez `show()`), na starcie
`estimate()` („Szacuj"), `showManual()` („Wpisz ręcznie") i przy otwieraniu
panelu w `toggleSavedMeals()` („Moje posiłki"). Init na końcu pliku uproszczony
— `show("today")` i tak to teraz robi, więc zniknęło duplikujące ręczne
ustawienie `f-date`/`f-time` przy starcie.

**5. Rozróżnienie „ręcznie zmienione vs domyślne" dla daty/godziny.** Pierwsza
wersja `refreshMealWhen()` (punkt 3+4) nadpisywała też datę/godzinę ręcznie
poprawioną przez użytkownika (np. celowe wsteczne wpisanie zapomnianego
posiłku), jeśli zdążył potem kliknąć „Szacuj"/„Wpisz ręcznie"/„Moje posiłki".
Dopisane po zgłoszeniu tego jako realnego ryzyka, nie tylko teoretycznego.
Fix: flaga `_mealWhenAuto` (`true` = pola stoją na domyślnym "teraz", wolno je
nadpisywać; `false` = użytkownik dotknął `#f-date`/`#f-time` ręcznie —
`oninput="_mealWhenAuto = false"` na obu polach). `refreshMealWhen()` nic nie
robi, gdy flaga jest `false`. Flaga wraca do `true` w `resetAddForm()` — czyli
przy każdym zakończonym (zakolejkowanym albo zapisanym) posiłku, więc kolejny,
nowy wpis znów startuje od "teraz", a ręczna korekta chroni tylko bieżącą,
niedokończoną próbę.

**Zweryfikowane ręcznie** (dev serwer na osobnym `FIT_KRASNAL_DATA`, klucz
Gemini celowo nieprawidłowy): (1) wartość ustawiona programowo w polu wagi
bez natywnego `change` i tak trafia do `/api/weight` po przejściu na inną
zakładkę (`weight_smoothed_kg` w `/api/day` się zgadza); (2)+(3)+(4) spreparowane
"stare" `f-date`/`f-time`/`f-desc` (2000-01-01, 01:23, opis) zostają
poprawnie zresetowane do bieżącej daty/godziny i wyczyszczone po `estimate()`,
`showManual()` i `toggleSavedMeals()`; (5) ręczna zmiana obu pól przez
`dispatchEvent(input)` przed „Szacuj" przeżywa wywołanie (data/godzina
zostają nietknięte), a kolejny, nieedytowany wpis zaraz potem znów dostaje
świeże „teraz" — potwierdza, że ochrona jest per-wpis, nie trwała. Testów
pytest **nie uruchamiano po tej zmianie** na wyraźną prośbę właściciela
(zmiana czysto frontendowa, backend
niedotknięty).

Nota `/prywatnosc` bez zmian — żadna z czterech poprawek nie zmienia zakresu
zbieranych/przetwarzanych danych.

---

## ~~Implementacja zgubionej funkcjonalności~~ ✓ zrobione

Backend miał od dawna gotowy endpoint `POST /api/queue/process`
(`app/routers/meals.py:172-176`, woła `meal_queue.process_queue` w tle) do
ręcznego wymuszenia przetworzenia kolejki offline — ale żaden element UI go
nie wywoływał. Widok mobilny (`/mobile`) pozwalał tylko usunąć wpis z kolejki
(✕), nie dawał sposobu, żeby kazać aplikacji spróbować ponownie od razu,
zamiast czekać na kolejny zapis klucza LLM czy import transferu.

**Co jest:**

1. `app/templates/mobile.html`, `renderMeals()` — przy każdym wpisie kolejki
   nowy przycisk „▶" (`playPending(id)`) obok istniejącego „✕"
   (`delPending(id)`); `id` na razie tylko dekoracyjnie, bo `process_queue`
   i tak przetwarza całą kolejkę usera naraz (`order_by(created_at)`), nie
   pojedynczy wpis — to świadome uproszczenie, zgodne z tym, co endpoint już
   robił.
2. Nowa funkcja JS `playPending(id)` woła istniejący `POST /api/queue/process`
   i odświeża widok (`renderToday()`); komunikat stanu w nowym,
   stałym elemencie `#queue-status` (nad `#t-pending`, poza obszarem, który
   `renderMeals` nadpisuje przy każdym odświeżeniu, więc komunikat przeżywa
   `renderToday()`).
3. **Uwaga UX doprecyzowana przy weryfikacji:** przetwarzanie idzie w tle
   (`background.add_task`), więc `renderToday()` wywołane zaraz po odpowiedzi
   `{"ok": true}` prawie zawsze pokaże wpis nadal w kolejce — to nie błąd,
   LLM jeszcze nie zdążył odpowiedzieć. Bez pollingu; jeśli po chwili
   ręcznego odświeżenia wpis nadal wisi, to sygnał realnego niepowodzenia
   (brak/zły klucz LLM), tak jak dziś.
4. Przy okazji: sekcja „W kolejce" przeniesiona nad listę posiłków w karcie
   „Posiłki" (`#t-pending` przed `#t-meals`) — na prośbę właściciela, żeby
   wpisy czekające na LLM rzucały się w oczy pierwsze.

**Zweryfikowane ręcznie** (dev serwer na osobnym `FIT_KRASNAL_DATA`, żeby nie
tykać danych produkcyjnych/lokalnych, `GEMINI_API_KEY` celowo podmieniony na
nieprawidłowy na czas testu): posiłek tekstowy bez skonfigurowanego klucza
trafia do kolejki, przycisk ▶ woła endpoint, `#queue-status` pokazuje
komunikat, kolejka po przetworzeniu z błędnym kluczem zostaje (zgodnie z
oczekiwaniem — brak regresji w istniejącej logice `process_queue`).
`pytest tests/test_queue_settings.py` zielony (12 passed) — backend
niezmieniony.

Nota `/prywatnosc` bez zmian — nie zmienia się nic w zbieraniu/przetwarzaniu
danych, tylko dodano ręczny spust dla istniejącego mechanizmu.

---

## ~~Duplikat trendów i `day_report` w routerze — wyniesienie do serwisów~~ ✓ zrobione (commit a4aa213), pytest zielony (150 passed)

Największy dług architektoniczny wskazany w audycie 2026-09-03, spłacony zaraz
po podziale `main.py` na routery — tamten podział **przeniósł** duplikat do
`app/routers/trends.py`, ale go nie usunął.

**Co było:** `trends()` i `api_trends_data()` to były dwie niemal identyczne
kopie ~70 linii (te same zapytania o wagi/summary/posiłki, to samo wygładzanie
7-dniowe, te same serie wykresów). Poprawka w jednej nie trafiała do drugiej.
`day_report()` (165 linii) siedział w routerze — a to jedyne miejsce, w które
ma wejść współczynnik kalibracji (6.2).

**Co jest:**

1. `app/services/trends.py` — `payload(db, user_id, days, today=None)` jako
   jedno źródło dla obu widoków; router (`app/routers/trends.py`, 202 → 66
   linii) robi już tylko telemetrię i kształt odpowiedzi: HTML dokłada
   `ranges`/`today`/`has_logo`, JSON zdejmuje `today`. Kolory serii dostały
   nazwy (`COLOR_MEASURED` itd.) zamiast hexów wklejonych dwa razy.
2. `app/services/day.py` — `day_report()` plus `_est_steps` i stała
   `STEPS_PER_KM`; router (311 → 148 linii) woła serwis i mapuje błąd.
3. `app/services/timeago.py` — `humanize_ago` **musiała** wyjść z `app/deps.py`,
   bo `services/day.py` jej potrzebuje, a `deps.py` importuje FastAPI.
4. **Serwisy zostają wolne od FastAPI:** brak profilu/wagi to
   `day.DayReportUnavailable`, które router zamienia na 409 z tym samym
   komunikatem co wcześniej. Nie `HTTPException` w serwisie.

**Parametr `today` w `payload()`** jest z rozmysłem: punkt „Strefa czasowa
użytkownika jako granica dnia" dostaje gotowe wejście — wystarczy podać
`user_today(profile)` zamiast domyślnego `date.today()`.

**Dowód, że nic się nie zmieniło dla klienta:** złoty zrzut `/api/day`,
`/api/trends` (6 zakresów: 2, 7, 30, 90, 366, 1000 — łapie też przycinanie)
i strony `/trends` na syntetycznych danych, wykonany **przed** i **po** zmianie
— wyjście identyczne bajt w bajt, razem z SHA-256 treści HTML. Poza
porównaniem tylko `quip` (losowany) i `last_sync_ago` (zależy od minuty).

**Strażnicy na przyszłość** (`tests/test_day_trends_services.py`, 6 testów):
kształt odpowiedzi `/api/trends` jako jawny kontrakt (`API_TRENDS_KEYS` — łapie
np. wyciek `today` do API), zgodność HTML z JSON (te same SVG w treści strony),
przycinanie zakresu dni, równość `/api/day` z wyjściem serwisu, 409 zamiast 500
przy braku profilu i wagi, oraz test architektoniczny: żaden plik w
`app/services/` nie może zawierać słowa `fastapi`.

Nota `/prywatnosc`: bez zmian — przeniesienie kodu, żadnych nowych danych
ani odbiorców.

## ~~Stara wersja na GitHub Pages — wyłączenie i sprzątanie po niej~~ ✓ zrobione (commit d8833e3)

Zastępuje punkt „GitHub Pages — czerwony pipeline po skasowaniu `docs/`".
Audyt publicznego repo (2026-09-03) pokazał, że problem był większy niż
czerwony pipeline:

- Pages nadal serwowały ostatni udany deploy starego klienta PWA, a link do
  niego siedział **w Ustawieniach aplikacji** (`settings.html`) i **na
  landingu** — czyli aktywnie wysyłaliśmy testerów do wersji, której nikt
  nie utrzymuje od 2026-08-31.
- Ten klient trzymał **klucz API Gemini użytkownika w `localStorage`** na
  originie `mariuszwojciechowski.github.io`. To origin **wspólny dla
  wszystkich** GitHub Pages tego konta — dowolna inna strona opublikowana
  z tego konta mogła ten klucz odczytać.
- Wysyłał też dzienne liczniki użycia do zewnętrznego serwisu
  (`abacus.jasoncameron.dev`) z identyfikatorem przestrzeni opublikowanym
  w repo — każdy mógł je czytać i podbijać. Przeczyło to zdaniu z noty
  `/prywatnosc`: „To jedyne miejsce, gdzie Twoje dane wychodzą poza tę
  aplikację" (chodziło o LLM).

**Decyzja:** nie da się „odpublikować" tego, co już jest w cache przeglądarek
testerów, więc zamiast tylko wyłączać Pages **nadpisujemy** tamtą wersję
nagrobkiem, który po sobie sprząta.

**Co zrobione:**

1. `docs/index.html` — strona-nagrobek: kasuje z przeglądarki `gemini_key`
   i `profile` z `localStorage`, bazę IndexedDB `fitkrasnal`, wszystkie cache
   i rejestracje service workera, potem przekierowuje na
   `fit.krasnal.cc/mobile`. Całość z limitem 2 s, żeby przekierowanie
   wykonało się nawet przy odmowie któregoś API przeglądarki.
2. `docs/sw.js` — kill switch: `skipWaiting`, kasuje cache, **wyrejestrowuje
   się** i przenawiguje otwarte okna. Stary `sw.js` robił dla nawigacji
   network-first, więc podmiana dociera do każdego, kto ma starą wersję
   zainstalowaną na ekranie głównym.
3. Usunięty link ze `app/templates/settings.html` (karta „Przenoszenie danych")
   — zastąpiony wskazaniem na `/mobile` z tego samego backendu; usunięta cała
   kafla „stara wersja" z `deploy/landing/index.html` wraz z martwym CSS
   `.app.legacy`.
4. Efekt ubocznie pożądany: build Pages przestaje być czerwony, bo katalog
   `docs/` (ustawiony jako Source) znowu istnieje.

**Zostaje właścicielowi (poza repo):** po potwierdzeniu, że Pages wystawiły
nagrobek, można dodatkowo ustawić *Settings → Pages → Source: None*. Nie jest
to konieczne — nagrobek jest bezpieczny sam z siebie — ale zamyka temat na
dobre. Nie odtwarzaj w `docs/` niczego poza tymi dwoma plikami (patrz
[CLAUDE.md](CLAUDE.md), „Rzeczy do NIE odtworzenia").

## ~~Statystyki użycia — dopracowanie po zgłoszeniach~~ ✓ zrobione (commity ae065c8, eb1f1a7, f300e98), pytest zielony (141 passed)

Nie z TODO.md — poprawki wprost z bieżących zgłoszeń właściciela po wdrożeniu
poprzedniego punktu. (1) 500 na `/usage`: `FIT_KRASNAL_USAGE_SALT` nie był
ustawiony na produkcji — celowy `RuntimeError` w `_salt()` (bez tego pseudonimizacja
byłaby niebezpieczna), naprawa to dodanie zmiennej w `/etc/fit-krasnal/env`, nie
zmiana kodu. (2) Mobilny widok ustawień (`mobile.html`) miał tylko jeden link do
pełnych ustawień desktopowych — „Zarządzaj połączeniem z Garminem” — przez co
dostęp do `/usage` szedł tą samą, nielogiczną drogą; dodany osobny link „Statystyki
użycia →” w sekcji Administracja (`is_admin` teraz też w kontekście `dashboard()`).
(3) Lejek wejścia liczył się z telemetrii (`UsageDaily`), która działa tylko od
dnia wdrożenia — zaniżał konta założone wcześniej. Przepisany na realne tabele:
`UserProfile` (profil), `AppSetting` (klucz LLM, tokeny Garmina), `Meal` (pierwszy
posiłek, rozpiętość dat ≥7 dni = „wrócił w tygodniu 2”). (4) Dodany wykres „Posiłki
dziennie (30 dni)” liczony z `Meal`, nie z eventów klienckich. (5) Admin (`ADMIN_EMAIL`)
wykluczony z wszystkich agregatów `/usage` — własna aktywność testowa nie miesza się
ze statystykami userów. (6) Nowy widok `/admin/consents` (`require_admin`) — kto i na
co wyraził zgodę RODO, z e-mailem (w przeciwieństwie do celowo zanonimizowanego
`/usage`): tabela email/rodzaj zgody/status (aktualna/wycofana/nieaktualna
wersja/brak zgody)/wersja noty/daty, `consent.admin_overview()`. Link z sekcji
Administracja w `/settings` i `mobile.html`, wzajemny link z `/usage`.

## ~~Statystyki użycia — adopcja i najczęściej klikane opcje~~ ✓ zrobione (commit be997a0), pytest zielony (139 passed)

Liczniki dzienne po pseudonimie (`app/models.py:UsageDaily`, HMAC z `user_id`,
sól `FIT_KRASNAL_USAGE_SALT`) — bez e-maili, treści posiłków, zdjęć, wag ani
kalorii. Instrumentacja serwera w ~25 miejscach `app/main.py` (posiłki,
aktywności, waga/kroki, sync, kolejka, transfer, klucz LLM, Garmin,
profil/cel/styl życia, login, trendy, wejście w dzień) + `POST /api/usage`
i `track()` w `mobile.html` dla zdarzeń czysto klienckich (zakładki, wpis
ręczny, moje posiłki, wybór zdjęcia). Panel `/usage` (`require_admin` po
`ADMIN_EMAIL`, nie-admin → 404): adopcja, lejek wejścia, top zdarzenia,
wykres tygodniowy (`charts.bar_chart`), ostatnia aktywność per pseudonim;
link w Ustawieniach tylko dla admina. Retencja 180 dni — `scripts/purge_usage.py`
(samodzielny skrypt, bo `purge_deleted.py` z planu kasowania konta jeszcze
nie istnieje; do scalenia, gdy ten plan powstanie). Nota `/prywatnosc`
zaktualizowana — nowa sekcja o telemetrii w „Jakie dane zbieramy" i wpis
retencji 180 dni w „Ile czasu trzymamy dane".

## ~~Prognoza osiągnięcia celu ciężaru — WYMAGANIA.md 6.4~~ ✓ zrobione (commit ed1cb9d), pytest zielony (131 passed), zweryfikowane w przeglądarce (desktop /trends i mobile SPA — data ETA i tempo widoczne na kafelku)

`app/services/forecast.py:goal_eta` — tempo z regresji najmniejszych kwadratów
po wygładzonej wadze z wybranego okresu Trendów (≥6 punktów na ≥14 dniach),
fallback na bilans (`avg_balance_kcal * 7 / KCAL_PER_KG_FAT`) gdy pomiarów za
mało. Stany: `reached` (cel osiągnięty), `flat` (tempo ≥ −0.05 kg/tydz., bez
daty), `eta` (data + tempo), `far` (prognoza > 104 tygodni, bez konkretnej
daty). Podłączone do `trends()` i `api_trends_data` — czwarty kafelek w
`.stats` (desktop `trends.html`, mobile SPA `#tr-eta-stat`), z dopiskiem „(wg
bilansu, za mało pomiarów ciężaru)” gdy `basis="balance"`.

---

## ~~Szyfrowanie sekretów użytkownika: klucze LLM i tokeny Garmina~~ ✓ zrobione (commity c1e1c9b, 7b4a88d), pytest zielony (124 passed), FIT_KRASNAL_ENC_KEY już ustawiony na produkcji przed wdrożeniem

Zakres pełny: A (klucze LLM) + B (tokeny Garmina). Szyfrowanie Fernet
(`app/services/crypto.py`), klucz `FIT_KRASNAL_ENC_KEY` — w dev/testach
wyprowadzany deterministycznie z `SECRET_KEY` (HKDF), na produkcji wymagany
(hard-fail w `startup()`, razem z odrzuceniem domyślnego `SECRET_KEY`).
`settings_service.SECRET_SETTING_KEYS` (`gemini_api_key`, `anthropic_api_key`,
`garmin_tokens`) — jedyna droga do sekretów, nigdy wprost przez `AppSetting`.

Tokeny Garmina nie leżą już jako pliki na dysku — `GarminProvider` materializuje
je do katalogu tymczasowego tylko na czas logowania/synchronizacji i kasuje
natychmiast po. Migracja istniejących katalogów tokenów i plaintextowych
kluczy LLM leci automatycznie przy starcie (`crypto.migrate_plaintext_settings`,
`garmin_provider.migrate_tokens_dirs_to_db`) — idempotentna, bez ręcznej
interwencji przy deployu. `scripts/rotate_enc_key.py` do rotacji klucza.

**Kolejność z użytkownikiem (2026-09-03):** przed napisaniem kodu przeszliśmy
razem przez wygenerowanie i ręczne dopisanie `FIT_KRASNAL_ENC_KEY` do
`/etc/fit-krasnal/env` na VM `krasnal-first1` — wartość nie trafiła do
pamięci/repo (sekret). Restart usługi (`systemctl restart fit-krasnal`)
zostaje na koniec, przy realnym deployu tego kodu.

---

## ~~RODO: informacja, zgoda na wysyłkę zdjęć do LLM, retencja~~ ✓ zrobione (commit 96fb708), pytest zielony (116 passed), zweryfikowane w przeglądarce (baner, karta Prywatność, chowanie/pokazywanie pól LLM po grant/withdraw)

Nota `/prywatnosc` (bez auth), zgoda `Consent(kind="llm_photos")` wersjonowana
przez `PRIVACY_VERSION`, bramka `require_llm_consent` na `POST /api/meals/photo`
i `/api/meals/text` (409 bez zgody) oraz w `meal_queue.process_queue` (przerywa
bez zgody, jak przy braku klucza). Checkbox w rejestracji (opcjonalny), karta
„Prywatność" w Ustawieniach (desktop `settings.html` i mobile SPA) z
przełącznikiem grant/withdraw — wycofanie kasuje oczekującą kolejkę wraz ze
zdjęciami. Baner dla istniejących testerów bez zgody, z terminem
`CONSENT_DEADLINE` (17.09.2026) — sama bramka 409 działa od razu, baner to
tylko komunikat "dlaczego". Treść noty sprawdzona pod względem faktów o
polityce Gemini/Anthropic API (WebSearch + WebFetch na ai.google.dev i
anthropic.com/legal, 2026-09-03) — ważne rozróżnienie: darmowy klucz Gemini
(ten, do którego onboarding kieruje testerów) trenuje/jest recenzowany przez
ludzi WYŁĄCZNIE poza UE/EOG/Szwajcarią/UK; dla Polski obowiązują warunki
płatnego poziomu nawet na darmowym kluczu.

**Świadome odstępstwo od litery planu w TODO.md:** plan zakładał "eksport i
kasowanie — przyciskami w Ustawieniach, bez pisania maili", ale przycisk
samoobsługowego usuwania danych/konta nie istnieje (to osobny, jeszcze
niezrealizowany punkt „Usuń moje dane i konto w Ustawieniach"). Nota mówi o
tym uczciwie: eksport działa przyciskiem, usunięcie na razie wymaga maila do
administratora — do poprawienia, kiedy tamten punkt zostanie zrealizowany.
`MaxRetentionSec=30day` dla journald dodany do `deploy/setup-vm.sh` (wymaga
ponownego uruchomienia skryptu na VM, żeby zadziałać na produkcji).

---

## ~~Rok urodzenia zamiast pełnej daty — minimalizacja danych~~ ✓ zrobione (commit aba6c7f), pytest zielony (107 passed)

Profil `UserProfile` trzyma teraz `birth_year: int` — pełna data urodzenia
(silny identyfikator w połączeniu z e-mailem i danymi o zdrowiu) nie jest
nigdzie w kodzie czytana: idzie tylko do BMR (5 kcal/rok) i do progu senior
65+ w normach makro. Wiek liczony konwencją „środka roku"
(`energy.age_from_year`, 1 lipca) — błąd ≤ 1 rok, symetryczny.

`UserProfile.birth_date` zostaje w schemacie jako pochodna
(`date(birth_year, 7, 1)`), migracja addytywna z backfillem z istniejącej
`birth_date` (`app/db.py:_migrate()`). `ProfileIn` przyjmuje `birth_date`
wyłącznie jako wejście zgodnościowe (stary klient/plik transferu) —
`GET /api/profile` i eksport transferu wystawiają tylko `birth_year`.
UI (`mobile.html`, `#page-settings`) ma teraz pole liczbowe „Rok urodzenia"
z jednym zdaniem wyjaśnienia, zamiast `<input type="date">`.

---

## ~~Ujednolicenie nawigacji desktop ↔ mobile~~ ✓ zrobione (SHA po commicie), pytest zielony (95 passed), zweryfikowane w przeglądarce (375px: 5 zakładek bez zmian; 1200px: hdr-nav przełącza w miejscu, Dodaj scrolluje+focusuje bez showManual(), aktywny link podświetlony, etykieta widoku w headerze) — deploy nie zweryfikowany, zostawione właścicielowi

Feedback właściciela 2026-09-01. MOBILE JEST WZORCEM — dolny navbar
(Dziś / Dodaj / Aktywności / Trendy / Ustawienia jako zakładki SPA
w `mobile.html`) zachowuje się dobrze i MA ZOSTAĆ DOKŁADNIE JAK JEST.
Problem jest na desktopie: Dziś/Aktywności przełączają widok w miejscu
(nagłówek i nawigacja zostają — dobrze), ale Trendy i Ustawienia linkują
do OSOBNYCH stron serwerowych `/trends` i `/settings`, które zabierają
nawigację (źle), a „Dodaj" woła `show('add')+showManual()`, co na
desktopie (gdzie formularz Dodaj i tak jest widoczny obok Dziś) tylko
otwiera draft ręczny i duplikuje przycisk „Wpisz wartości ręcznie".

**Docelowy model (decyzje):**

- Desktop dostaje TE SAME zakładki co mobile i wszystkie przełączają widok
  w miejscu — nagłówek + `hdr-nav` zawsze zostają.
- Trendy i Ustawienia na desktopie używają SPA-owych stron, które mobile
  już ma (`page-trends` + `renderTrends()`, `page-settings` +
  `renderSettings()`) — koniec z uciekaniem na `/trends` i `/settings`
  z nawigacji. Strony serwerowe zostają jako deep-linki (m.in. link
  „Zarządzaj połączeniem z Garminem" → `/settings#garmin` zostaje).
- „Dodaj" na desktopie: widok Dziś nadal pokazuje formularz Dodaj obok
  (dwie kolumny — najlepsze użycie szerokiego ekranu, zostaje). Klik
  „Dodaj" w `hdr-nav` = przełącz na widok Dziś (jeśli jesteś gdzie
  indziej) + `scrollIntoView` + focus na formularzu — BEZ `showManual()`
  (to usuwa duplikację przycisku). Na mobile „Dodaj" bez zmian.

**Kroki implementacji (`app/templates/mobile.html`):**

1. Uogólnij mechanizm `main.act` na atrybut: `show(page)` ustawia
   `document.querySelector("main").dataset.view = page` (klasę `act`
   usuń). Desktopowy CSS (`@media min-width:800px`) steruje widokami po
   `main[data-view=...]`: `today` (i brak atrybutu) → `page-today` +
   `page-add` obok siebie jak dziś; `activities` → `page-activities`
   (dwie kolumny, już jest); `trends` → `page-trends`; `settings` →
   `page-settings`; pozostałe strony w danym widoku ukryte. Usuń
   `#page-settings, #page-trends { display:none !important }` (linie ~89-90).
2. `hdr-nav`: Trendy → `onclick="show('trends');return false"`,
   Ustawienia → `show('settings')` (zamiast href na strony serwerowe);
   „Dodaj" → `goAdd()`: na desktopie `show('today')` + scroll/focus do
   karty Dodaj, na mobile dotychczasowe `show('add')` (rozpoznaj po
   `matchMedia('(min-width:800px)')`); bez `showManual()` na desktopie.
3. `renderTrends()`/`renderSettings()` na szerokim viewporcie: sprawdź,
   że wykresy SVG i formularz nie rozjeżdżają się na 1020 px (max-width
   main) — ewentualnie ogranicz szerokość kart tych widoków.
4. Wskaźnik aktywnego widoku obok loga: `show()` ustawia tekst w headerze
   (np. w `#hdr-date` obok daty albo osobny span) — na wzór tego, co
   strony serwerowe robiły tytułem; aktywny link w `hdr-nav` podświetlaj
   (klasa active jak w dolnym nav).
5. Weryfikacja w przeglądarce: 375 px (mobile navbar bez zmian zachowania,
   wszystkie 5 zakładek) i 1200 px (5 zakładek w hdr-nav, żadna nie gubi
   nawigacji, „Dodaj" focusuje formularz bez otwierania draftu ręcznego).
   Pytest zielony. Deploy i prod — właściciel.

## ~~Przemeblowanie: równanie do Bilansu, karta GARMIN w zakładce, dwie kolumny~~ ✓ zrobione (commit 02cc6f2), pytest zielony (95 passed), zweryfikowane w przeglądarce (mobile 375px + desktop 1200px) — deploy nie zweryfikowany, zostawione właścicielowi

Feedback właściciela 2026-09-01, cztery punkty. Wszystko w
`app/templates/mobile.html`. Po pushu stop — deploy i prod robi właściciel.

1. **Dziś: równanie wynosi się do Bilansu.** `#tdee-breakdown` (linia ~150,
   dziś w karcie `#sync-card`) przenieś do karty Bilans — bezpośrednio POD
   wiersz z przyciskiem „Aktywności/Kroki" i polem ciężaru (linia ~136-140).
   Render bez zmian (`renderEnergyBreakdown(rep, "tdee-breakdown")` —
   id zostaje, zmienia się tylko miejsce w markupie).
2. **Karta GARMIN przenosi się na zakładkę Aktywności.** Sekcja „Rozbicie
   wydatku energetycznego" (linia ~236-238) staje się kartą „Garmin" —
   dokładnie taką, jaka była na Dziś: nagłówek, przycisk „Synchronizuj
   z Garminem" (`doSync()`), `<p id="sync-status">`, a pod nimi równanie
   `#a-tdee-breakdown`. Karta `#sync-card` znika z Dziś w całości.
   Uwaga: `doSync()` pisze do `#sync-status` — element jedzie razem
   z przyciskiem; id `tdee-breakdown` i `a-tdee-breakdown` zostają, więc
   `renderEnergyBreakdown` działa bez zmian.
3. **Desktop: zakładka Aktywności w dwóch kolumnach.** W `@media
   (min-width: 800px)`: `main.act #page-activities { grid-template-columns:
   1fr 1fr; }` + przypisanie kolumn: sekcja „Dodaj aktywność" do PRAWEJ
   (`grid-column: 2`), reszta (Kroki, Garmin z rozbiciem, „Aktywności
   dzisiaj") do LEWEJ (`grid-column: 1`). Sekcje lewej kolumny mają się
   układać jedna pod drugą (np. `grid-auto-flow: dense` albo dwa wrappery
   kolumnowe — wybierz co prostsze; uważaj, że `.page` na desktopie już
   jest gridem, linia ~88). Mobile bez zmian — jedna kolumna.
4. **Ostrzeżenie do prawej kolumny.** `#a-garmin-warning` (linia ~287)
   ląduje w prawej kolumnie, pod formularzem „Dodaj aktywność".
5. **Klik w „Dziś" i „Aktywności" na navbarze odpala synchronizację —
   w OBU wersjach nav** (dolny mobile `<nav>` i desktopowy `hdr-nav`).
   Stan: „Dziś" już to robi (`goToday()` woła `doSync()` — oba navbary
   używają `goToday`), ale `show('activities')` nie synchronizuje ani nie
   odświeża danych. Zrób analogicznie do `goToday`: funkcja
   `goActivities()` = `show('activities')` + `renderToday()` + `doSync()`,
   podpięta pod oba przyciski „Aktywności" (mobile `#nav-activities`
   i link w `hdr-nav`) ORAZ pod przycisk „Aktywności/Kroki" w Bilansie.
   `doSync` po sukcesie już odświeża widok — nie zdubluj renderów.
6. **Weryfikacja:** pytest zielony + przeglądarka (375 px i desktop):
   równanie widoczne w Bilansie na Dziś, karta Garmin z przyciskiem
   i równaniem w zakładce, dwie kolumny tylko na desktopie, ostrzeżenie
   po prawej, klik w Dziś/Aktywności widocznie odpala sync (status
   „Synchronizuję…"). Deployu i produkcji nie ruszaj.

## ~~Przycisk „Aktywności/Kroki" — wyrównanie, podejście trzecie~~ ✓ zrobione (commit 02cc6f2) — zweryfikowane getBoundingClientRect() w przeglądarce: bottom i height przycisku i inputa równe co do piksela na 375px i 1200px

Dwa poprzednie fixy (pusty label, potem `align-items:flex-end`) nie
wyrównały — screenshot właściciela z 2026-09-01 pokazuje przycisk wciąż
niżej i o innej wysokości niż input ciężaru. PRZYCZYNA (z CSS, nie zgaduj
innej): bazowa reguła (`mobile.html` ~linia 39) daje inputom
`margin: 4px 0` i `border: 1px solid`, a przycisk w tym wierszu ma inline
`margin:0`, zaś `button.ghost` zeruje border — przy `align-items:flex-end`
dolna krawędź przycisku wypada 4 px NIŻEJ (brak dolnego marginesu),
a pudełko jest 2 px niższe (brak obramowania). FIX: przyciskowi w tym
wierszu (~linia 137) daj `margin:4px 0` (jak input, zamiast `margin:0`)
i `border:1px solid transparent` — wtedy box przycisku jest identyczny
z boxem inputa i `flex-end` domyka resztę. WERYFIKACJA OBOWIĄZKOWA w
przeglądarce (preview + javascript_tool), nie na oko: porównaj
`getBoundingClientRect()` przycisku i inputa — `.bottom` i `.height` mają
być RÓWNE co do piksela, w szerokości mobilnej (375px) i desktopowej;
dopiero równość = zrobione.

## ~~Skala intensywności w nowej linii~~ ✓ zrobione (commit 02cc6f2), zweryfikowane w przeglądarce

W przyciskach intensywności (radio w formularzu aktywności,
`app/templates/mobile.html`) liczbowe wskazanie ma być w NOWEJ LINII pod
nazwą, nie w jednym ciągu: zamiast „Lekka · 1–3/10" →
„Lekka<br><small>1–3/10</small>" (analogicznie umiarkowana 4–7/10,
intensywna 8–10/10). Etykiety siłowni bez zmian (opisowe, bez skali).
Uwaga: etykiety są podmieniane JS-em przy zmianie typu
(`INTENSITY_LABELS_DEFAULT`, ~linia 895) — zmiana i w markupie startowym,
i w mapie; wstawiaj przez innerHTML, nie textContent.

## ~~Szlif zakładki Aktywności — runda 2 po testach właściciela~~ ✓ zrobione (commit 443cb0b), pytest zielony (95 passed) — deploy nie zweryfikowany, zostawione właścicielowi

Feedback z 2026-09-01. Backend rozbicia (commit `db4f6cf`: `out_breakdown`,
kroki jako reszta, `manual_kcal` w bilansie) jest DOBRY — nie ruszaj go poza
punktem 5. Wszystko poniżej to `app/templates/mobile.html`, chyba że napisano
inaczej. Higiena tokenów: czytaj fragmentami po wskazanych liniach, pełny
pytest raz na koniec. Po pushu ZATRZYMAJ SIĘ — deploy i weryfikację na
produkcji wykonuje właściciel osobiście.

1. **Widok Dziś dalej pokazuje stare rozbicie z modelu** (`renderTdee`,
   linia ~481, cel `#tdee-breakdown` linia ~151): równanie liczone z
   `rep.tdee_model` plus inline lista aktywności z kcal Garmina
   („cycling 50 min, 206 kcal · swimming…"). Ma pokazywać TO SAMO co
   zakładka: wydziel wspólną funkcję renderującą równanie z
   `rep.out_breakdown` i użyj jej dla `#tdee-breakdown` i
   `#a-tdee-breakdown`; inline'ową listę aktywności z Dziś usuń (lista
   żyje w zakładce Aktywności). Czysty model zostaje w API
   (`tdee_model`) — z UI znika.
2. **Usunięcie ręcznej aktywności nie odświeża obliczeń**: callback
   `deleteActivity` (linia ~1008) woła tylko `loadActivityList(day)` —
   lista znika, ale równanie, SPALONE i bilans zostają stare. Zamień
   callback na `renderToday()` (odświeża dzień, rozbicie i listę razem).
3. **Równanie bez liczby kroków**: w `renderActivityBreakdown`
   (linia ~917) usuń ` (${b.steps_count} kroków…)` — składnik ma brzmieć
   „kroki <b>319</b> kcal"; liczba kroków jest już w polu Kroki na górze
   zakładki (dopisek „domyślne" przenieś tam, np. pod input `#a-steps`).
4. **Polskie nazwy ręcznych aktywności**: lista wpisów (`loadActivityList`,
   linia ~996+) drukuje surowe `a.type` („swimming", „walking"). Dodaj
   mapę `TYPE_LABELS = {running: "bieg", walking: "marsz (z kijkami)",
   swimming: "pływanie", cycling: "rower", strength_training: "siłownia"}`
   i używaj jej dla wpisów ręcznych w liście ORAZ w `<option>` selecta
   `#a-type` (wartości `value` zostają angielskie — backend i Garmin nimi
   mówią). Wpisy z Garmina drukuj po staremu (surowy typeKey, np.
   cycling — one mogą być „obce").
5. **Czas trwania jako [h:]mm[:ss]**: zamień `#a-duration-min`
   (linia ~262, type=number) na input tekstowy z parserem: „29:58" →
   29 min 58 s, „1:05:00" → 65 min, samo „33" → potraktuj jako minuty
   i na blur znormalizuj do „33:00". Backend: do `ActivityIn`
   (`app/main.py`) dodaj opcjonalne `duration_s: int | None` — gdy podane,
   ma pierwszeństwo nad `duration_min` (które zostaje dla kompatybilności);
   endpoint już liczy wszystko z sekund. Test: POST z `duration_s=1798`
   daje te same kcal co 29.97 min.
6. **Dystans z przecinkiem**: `#a-distance-km` (linia ~266) na input
   tekstowy `inputmode="decimal"`, przed parsowaniem `value.replace(",",
   ".")` — „5,3" i „5.3" równoważne.
7. **Skala 1–10 w intensywności**: standardowe etykiety radio
   (`INTENSITY_LABELS_DEFAULT`, linia ~938) rozszerz o skalę:
   „Lekka · 1–3/10", „Umiarkowana · 4–7/10", „Intensywna · 8–10/10".
   Etykiety siłowni (`INTENSITY_LABELS_STRENGTH`) zostają opisowe, bez
   skali.
8. **Przycisk „Aktywności/Kroki" — wyrównanie do DOLNEJ krawędzi inputa
   ciężaru** (linia ~137): obecny hack z pustym `<label>&nbsp;</label>`
   nie wyrównuje, bo button i input mają różne wysokości. Daj na tym
   `.row2` `align-items:flex-end` (albo `align-self:flex-end` na spanie
   przycisku), usuń pusty label i zrównaj wysokość przycisku z inputem
   (wspólna reguła height/padding). Sprawdź wizualnie mobile i desktop.
9. **Martwy kod**: linie ~758 i ~769 odwołują się do `#a-duration`
   i `#a-activity` — pól, których nie ma w markupie (pozostałość
   pierwszego formularza). Zweryfikuj, czy funkcja wokół nich jest w ogóle
   osiągalna, i usuń ją wraz z odwołaniami.
10. **Weryfikacja**: pełny `pytest` zielony → commit + push. NIE weryfikuj
    produkcji i NIE sprawdzaj deployu — właściciel robi to sam.

## ~~Rozbicie wydatku: pomiar Garmina jako suma, kroki jako reszta~~ ✓ zrobione (commit db4f6cf), pytest zielony (94 passed) — deploy nie zweryfikowany, zostawione właścicielowi

Decyzja właściciela 2026-08-31 (wiążąca). Dziś równanie w zakładce Aktywności
pokazuje CZYSTY model (aktywności z MET ~399), a lista pod nim pomiar Garmina
(206) — dwie liczby dla tej samej aktywności. Nowa semantyka: **równanie ma
sumować się do SPALONE (tej samej liczby co na Dziś), a „kroki" są RESZTĄ.**

**Definicje (wiążące):**

- `SPALONE (kcal_out)`: dzień zamknięty z Garminem → `total Garmina + Σ kcal
  wpisów ręcznych` (zakładamy, że Garmin ręcznych nie widział); dzień w toku →
  `max(total Garmina + ręczne, model TDEE)`; brak Garmina → model TDEE.
  UWAGA: to zmiana bilansu (M5) — ręczne wpisy u garminowca dotąd NIE
  wchodziły do SPALONE, teraz wchodzą.
- Rozbicie: `BMR (model Mifflin) + kroki (RESZTA) + aktywności (pomiar) +
  TEF (model) = SPALONE`, gdzie `aktywności = Σ kcal_garmin wpisów
  garminowych + Σ kcal wpisów ręcznych`, a `kroki = max(SPALONE − BMR −
  aktywności − TEF, 0)` (podłoga na zerze — krótko noszony zegarek / wczesna
  pora może dać ujemną resztę). Własność: bez Garmina reszta == modelowy
  NEAT, więc jeden wzór obsługuje wszystkie przypadki.
- Liczba kroków przy „kroki": efektywna — wpisane/zsynchronizowane MINUS
  szacowane kroki aktywności biegowych/marszowych z Garmina (jak dziś,
  ~1400/km w `tdee_theoretical`), PLUS dla garminowca kroki ręcznych
  biegów/marszów NIE są odejmowane (Garmin ich nie zliczył) — przeciwnie,
  szacunek kroków wpisu ręcznego DODAJEMY do wyświetlanej liczby kroków.

**Kroki dla implementującego LLM:**

1. **`app/services/balance.py`** — `day_balance(...)` dostaje parametr
   `manual_kcal: float = 0`; pomiar = `garmin_total + manual_kcal`;
   dzień zamknięty → pomiar, w toku → `max(pomiar, model_tdee)`, brak
   Garmina → model (jak dziś). Zaktualizuj docstring.
2. **`app/main.py:day_report`** — podziel `activities` na garminowe
   i ręczne (`a.source`); `manual_kcal = Σ kcal_garmin ręcznych`;
   `activities_kcal = Σ kcal_garmin garminowych + manual_kcal`; wołaj
   `day_balance(..., manual_kcal=manual_kcal)`. Nowe pole odpowiedzi
   `out_breakdown = {bmr, steps_kcal, activities_kcal, tef, total}` wg
   definicji wyżej (`steps_kcal` = reszta z podłogą 0, `total ==
   round(bal.kcal_out)`). Model `tdee_model` zostaje bez zmian (prognoza
   na Dziś). Do pola `steps` dodaj szacowane kroki RĘCZNYCH biegów/marszów
   (dystans × 1400), a per wpis ręczny w `activities` dodaj
   `est_steps` (bieg/marsz z dystansem) do adnotacji w UI.
3. **`app/templates/mobile.html`** — `renderActivityBreakdown` przechodzi
   na `out_breakdown` (równanie = SPALONE z Dziś); linia kroków:
   „kroki X kcal (N kroków)" — jawnie jednostka. Lista dzieli się na
   „Z Garmina" i „Wprowadzone ręcznie — zakładamy, że Garmin o nich nie
   wie" (✕ do kasowania już jest); przy ręcznym biegu/marszu dopisek
   „(~N kroków)". Ostrzeżenie dla garminowca zmienia treść: ręczne wpisy
   SĄ doliczane do pomiaru — „jeśli zegarek zarejestrował ten trening,
   skasuj wpis ręczny, inaczej policzy się podwójnie".
4. **Testy** (`tests/test_activities_api.py`, wzorzec `clients` już jest):
   dzień zamknięty z Garminem + wpis ręczny → `kcal_out == total + ręczne`
   i `out_breakdown.total == kcal_out`; reszta kroków floor na 0 (total
   Garmina mniejszy niż BMR+TEF); bez Garmina → `steps_kcal` == modelowy
   NEAT po odjęciu kroków aktywności; `est_steps` obecne dla ręcznego
   biegu z dystansem, nieobecne dla siłowni.
5. **Weryfikacja:** pełny `pytest` zielony → commit + push → w Actions
   „Deploy na GCP" = `success` (sprawdź, nie zakładaj) → na prodzie
   równanie w Aktywnościach sumuje się do SPALONE z Dziś.

## ~~Poprawki zakładki Aktywności po testach na produkcji~~ ✓ zrobione (commit aa623ca), pytest zielony (90 passed)

Feedback właściciela z 2026-08-31 po używaniu na telefonie (działa) i desktopie
(nie działa). Kroki dla implementującego LLM — wszystko w
`app/templates/mobile.html`, chyba że napisano inaczej; czytaj plik
fragmentami po wskazanych liniach, pełny pytest raz na koniec.

1. **Desktop: zakładka Aktywności w ogóle niedostępna.** Mechanika: przy
   `min-width: 800px` dolny `<nav>` jest ukryty, `.page { display: grid
   !important }` (linia ~88) pokazuje WSZYSTKIE strony naraz (Ustawienia
   i Trendy chowane po id), a `show()` (linia ~418) przełącza klasę
   `visible`, którą `!important` nadpisuje — stąd „klik nic nie robi".
   Naprawa w konwencji desktopu:
   - w `@media (min-width: 800px)` dodaj `#page-activities { display: none
     !important; }` oraz reguły sterowane klasą na `<main>`:
     `main.act #page-activities { display: grid !important; }`,
     `main.act #page-today, main.act #page-add { display: none !important; }`;
   - w `show(page)` dodaj `document.querySelector("main").classList
     .toggle("act", page === "activities")` (a `goToday()`/inne wywołania
     `show` naturalnie ją zdejmą);
   - do `hdr-nav` (linia ~102) dodaj link `Aktywności` między „Dodaj"
     a „Trendy": `onclick="show('activities');return false"`.
   Efekt: na desktopie przycisk „Aktywności/Kroki" i link w headerze
   przełączają widok, jak na telefonie.
2. **Aktywności (też garminowe) widoczne pod rozbiciem wydatku.** W
   `page-activities` (linia ~218) kolejność sekcji to: Kroki → Rozbicie
   wydatku → Dodaj aktywność → Aktywności dzisiaj. Przenieś sekcję
   „Aktywności dzisiaj" (`#a-list`, linia ~276) bezpośrednio POD kartę
   „Rozbicie wydatku energetycznego" — składniki równania (kroki,
   aktywności — w tym garminowy np. cycling) mają być widoczne razem,
   nad formularzem.
3. **Siłownia: etykiety intensywności opisujące charakter treningu.**
   Radio (linia ~258) ma stałe „Lekka/Umiarkowana/Intensywna". Gdy
   `#a-type == "strength_training"`, podmieniaj JS-em TEKSTY etykiet
   (wartości `lekka/umiarkowana/intensywna` zostają — backend mapuje je
   w `INTENSITY_MAP`): `lekka` → „Ciężko, długie przerwy (maxy)",
   `umiarkowana` → „Klasycznie, umiarkowane przerwy", `intensywna` →
   „Obwodowo, krótkie przerwy". Uwaga na odwróconą semantykę: maxy =
   najniższy MET 3.5 (indeks 0), obwodowy = 6.0 (indeks 2) — mapowanie
   w `energy.MANUAL_MET["strength_training"]` już jest poprawne, zmienia
   się tylko UI. Przy zmianie typu na inny przywróć standardowe etykiety.
4. **Nowa aktywność: pływanie.** Jak rower (MET z intensywności, dystans
   informacyjny): w `app/services/energy.py` dodaj
   `MANUAL_MET["swimming"] = [6.0, 8.0, 10.0]` i gałąź w
   `manual_activity_kcal` (MET × masa × h); w select `#a-type` opcja
   `<option value="swimming">Pływanie</option>` z polami czas + dystans +
   intensywność. Test w `tests/test_activities_api.py` obok rowerowego
   (MET 10 × 75 kg × 1 h = 750 dla intensywnego).
5. **Przycisk „Aktywności/Kroki" za wysoki** (linia ~133): w `row2` obok
   stoi `<span>` z labelem + inputem ciężaru, a przycisk rozciąga się na
   całą wysokość wiersza. Wyrównaj go do wysokości inputa: np. owiń
   przycisk w `<span style="flex:1"><label>&nbsp;</label><button …>` (pusty
   label jak u sąsiada) albo daj `align-self:flex-end` i wysokość taką jak
   input. Sprawdź w obu szerokościach (mobile + desktop).
6. **Weryfikacja:** pełny `pytest` zielony → commit + push → w GitHub
   Actions „Deploy na GCP" ma być `success` — sprawdź to, nie zakładaj.

## ~~PILNE: naprawa testów aktywności — deploy zablokowany, produkcja wciąż leży~~ ✓ zrobione — plik przepisany wg wzorca `test_saved_meals_api.py`, prawdziwy strażnik migracji (commit 7400edf), pełny pytest zielony (89 passed)

Commit `1a3401d` naprawił kod (kroki 1, 4–7 sekcji niżej), ale jego deploy
**failował**: przywrócone `tests/test_activities_api.py` są czerwone — wszystkie
6 testów. Produkcja nadal działa na zepsutym `eefa2a4` (z `kcal_manual`).
Analiza z 2026-08-31 — w testach jest KASKADA trzech błędów; naprawienie
tylko pierwszego odsłoni kolejne. Kroki dla implementującego LLM:

1. **Nie naprawiaj pliku warstwami — przepisz go wg działającego wzorca**
   z `tests/test_saved_meals_api.py` (fixture `clients`: własny engine na
   `tmp_path`, `app.dependency_overrides[db_session]`, rejestracja przez
   `POST /register`, sesja w TestClient). Kaskada błędów w obecnym pliku,
   dla świadomości co musi zniknąć:
   - `setup_db` to `@pytest.fixture` z `yield`, a testy wołają je WPROST
     (`engine, Session = setup_db(tmp_path)`) — pytest to zabrania, stąd
     natychmiastowy fail wszystkich 6 testów (to dlatego były czerwone już
     w `1aad080` i zostały wtedy skasowane zamiast naprawione);
   - hasło rejestracji `pass123` ma 7 znaków, a `auth.MIN_PASSWORD_LEN = 8`
     — rejestracja odbija na `?error=short`, klient nie ma sesji, każdy
     kolejny request = 401 (użyj `tajnehaslo1` jak w `tests/test_auth.py`);
   - testy rejestrują NOWEGO użytkownika, a dane (profil, waga 75 kg)
     seedują użytkownikom 1 i 2 z bcryptowo nieprawidłowymi hashami —
     zarejestrowany user nie ma profilu ani wagi, więc `/api/activities`
     i `/api/day` zwrócą 409. Po rejestracji seeduj przez API:
     `PUT /api/profile` + `POST /api/weight {date, weight_kg: 75}` —
     wtedy oczekiwane wartości się zgadzają (bieg 5 km × 75 kg = 375).
2. **Zachowaj pokrycie z obecnego pliku** (nazwy testów są dobre, treść do
   przepisania): bieg z dystansem ignoruje intensywność (375 kcal),
   rower liczy z MET mimo dystansu (MET 10 × 75 × 1 h = 750), kroki:
   brak wpisu → `steps == 5000` i `steps_default == true`, DELETE tylko
   ręcznych (cudzy i garminowy → 404), izolacja list między użytkownikami.
3. **Zastąp atrapę testu migracji prawdziwym strażnikiem** —
   `test_migration_backfills_garmin_source` buduje bazę przez `create_all`
   (nowy schemat), więc niczego nie pilnuje. Prawdziwy strażnik: zbuduj
   tabelę `activity` STARYM DDL-em (surowy `CREATE TABLE` bez `source`,
   kolumny jak w `app/models.py` sprzed `985b41a`), wywołaj
   `app.db._migrate(engine)` wprost, potem ORM-owo `select(Activity)`
   i `db.add(Activity(...)); commit()` — każda kolumna dodana do modelu
   bez migracji wywali ten test (dokładnie klasa błędu `kcal_manual`,
   która położyła prod).
4. **Weryfikacja końcowa:** pełny `pytest` zielony lokalnie → commit + push
   → sprawdź w GitHub Actions, że „Deploy na GCP" jest `success`
   (`https://api.github.com/repos/mariuszwojciechowski/bilans-kcal/actions/runs?per_page=2`)
   — POPRZEDNIA sesja pushnęła i nie sprawdziła, przez co produkcja leżała
   dalej. Po deployu potwierdź, że `/api/day/{dziś}` i `/api/sync` na
   fit.krasnal.cc odpowiadają bez 500.

## ~~PILNE: naprawa dodania aktywności (3/10) — produkcja zwraca 500~~ ✓ kroki 1, 4–7 zrobione (commit 1a3401d); kroki 2–3 i 8 NIE — patrz sekcja wyżej

Implementacja zakładki Aktywności/Kroki (commity `985b41a`…`216b8ce`) położyła
produkcję i zostawiła śmieci. Diagnoza wykonana 2026-08-31 na prod
(fit.krasnal.cc, VM produkcyjna) — przyczyny są PEWNE, nie szukaj innych.
Kroki dla implementującego LLM, w tej kolejności:

1. **Usuń `kcal_manual` z modelu `Activity`** (`app/models.py:74`) — pole
   dodane bez migracji w `app/db.py:_migrate()` i przez nic nieużywane
   (kcal wpisów ręcznych trafiają do `kcal_garmin`). Na prodzie tabela
   `activity` nie ma tej kolumny, więc KAŻDY SELECT/INSERT ORM na `Activity`
   rzuca `sqlite3.OperationalError: no such column: activity.kcal_manual` —
   to jest przyczyna obu 500 (`/api/day/{day}` → „nie widać dnia"
   i `/api/sync`). Lokalne testy tego nie łapią, bo `create_all` buduje
   świeże tabele z kompletem kolumn. Usunięcie pola wystarczy — NIE dodawaj
   migracji na tę kolumnę.
2. **Przywróć skasowane testy API** — commit `216b8ce` usunął
   `tests/test_activities_api.py` (267 linii), żeby przepchnąć czerwony
   deploy: `git show 1aad080:tests/test_activities_api.py > tests/test_activities_api.py`,
   uruchom, i **napraw przyczyny czerwoności zamiast kasować testy** —
   czerwony pytest to bramka deployu, kasowanie testów = wysłanie regresji
   testerom (dokładnie to się stało).
3. **Dodaj test-strażnik migracji** (do `tests/test_activities_api.py` albo
   osobno): zbuduj bazę ze STAREGO schematu `activity` (ręczny
   `CREATE TABLE` bez `source`), odpal `init_db()`/`_migrate()`, potem
   ORM-owy `select(Activity)` i `db.add(Activity(...))` — ten test łapie
   całą klasę „kolumna w modelu bez migracji", która właśnie położyła prod.
4. **Usuń duplikat formularza aktywności spod „Dodaj"** — w
   `app/templates/mobile.html` wewnątrz `page-add` jest sekcja
   `<section class="card"><h2>Aktywność fizyczna</h2>…` (pozostałość
   pierwszego podejścia `985b41a`); właściwy formularz żyje w
   `page-activities`. Usuń też martwy serwis `app/services/activity.py`
   (równoległa, niespójna tabela MET z polskimi kluczami) i nieużywany
   import `activity as activity_service` w `app/main.py`.
5. **Przycisk „Aktywności/Kroki →" na Dziś** (`mobile.html`, ~linia 133):
   usuń strzałkę „ →" z etykiety — ma być samo „Aktywności/Kroki".
6. **Martwy `saveDaySteps()`** (`mobile.html`, ~linia 603): czyta usunięte
   pole `#t-steps` → `TypeError` przy wywołaniu. Pole kroków to teraz
   `#a-steps` w zakładce Aktywności (zapis obsługuje osobna funkcja,
   ~linia 957). Usuń `saveDaySteps` albo scal w jedną funkcję podpiętą
   do `#a-steps` — sprawdź `onchange`/`onclick`, żeby nie został wiszący
   handler.
7. **Bug `steps_default` w `day_report`** (`app/main.py`):
   `(summary and summary.steps is not None) == False` daje `False`, gdy
   `summary is None` (bo `None == False` → `False`), a powinno być `True`
   (brak wpisu = pokazujemy domyślne 5000). Zamień na
   `not (summary and summary.steps is not None)`.
8. **Weryfikacja:** pełny `pytest` zielony (razem z przywróconymi testami),
   commit + push (deploy automatyczny), a po deployu potwierdź na prodzie,
   że `/api/day/{dziś}` i `/api/sync` odpowiadają bez 500.

Higiena tokenów jak w planie niżej: `main.py` i `mobile.html` czytaj
fragmentami po numerach linii z tego planu, pełny pytest raz na krok.

## ~~Landing page — drobne poprawki~~ ✓ zrobione (commit 3c99a77)

- Do karty *Fit Krasnal* dopisać informację o wygodniejszym widoku dla
  telefonu: `fit.krasnal.cc/mobile`.
- Adresy stron (`fit.krasnal.cc`, `mariuszwojciechowski.github.io/bilans-kcal`,
  `pikimocy.krasnal.cc`) zamienić na klikalne linki — teraz są tylko tekstem.

## ~~Edytowanie liczby kroków w wersji desktopowej~~ ✓ nieaktualne — jeden widok ma pole kroków (commit d5bb8e8)

## ~~Zmniejszanie zdjęcia w przeglądarce przed wysłaniem na serwer~~ ✓ zrobione (commit b30b1eb)

## ~~Redirect po zalogowaniu w zależności od urządzenia~~ ✓ nieaktualne — jeden widok pod `/` (commit d5bb8e8)

## ~~Widok Ustawienia w wersji mobilnej~~ ✓ zrobione (commit 1e3360e)

Obecny `/mobile` w zakładce *Ustawienia* linkuje do desktopowego `/settings`,
który jest ciasny na małym ekranie. Zrobić natywną wersję: formularz profilu
(płeć, data ur., wzrost, ciężar), styl życia, cel, klucz Gemini, przycisk
połączenia z Garminem. Wszystko przez fetch do istniejących endpointów.

## ~~Widok Trendy w wersji mobilnej~~ ✓ zrobione (commit 1e3360e)

`/mobile` nie ma trendów — testerzy chcący zobaczyć postęp wagi/bilansu muszą
przełączać się na `/trends` (widok desktopowy). Dodać czwartą zakładkę
z wykresami — te same, które są w desktopowej Trendy, mniejsze i bez tabel.
Wykresy już generuje `app/services/charts.py`, można je serwować przez nowy
endpoint JSON i rysować po stronie klienta, albo po prostu wstawić SVG z
serwera pod URL-em typu `/trends/embedded?days=30`.

## ~~Ręczne dodawanie posiłku (bez szacowania)~~ ✓ zrobione (commit b30b1eb + 2485da5)

## ~~Ręczny wpis aktywności + zakładka Aktywności/Kroki~~ ✓ zrobione (commit 1aad080) (5/10)

Dla testerów bez zegarka sportowego: nowa zakładka z formularzem aktywności,
polem kroków i rozbiciem dzisiejszego wydatku. Decyzje produktowe podjęte
2026-08-31 (uzgodnione z właścicielem) — nie zmieniaj ich w trakcie
implementacji. Kroki dla implementującego LLM:

**Decyzje produktowe (wiążące):**

- Typy aktywności: **bieg, rower, marsz/spacer** (czas + dystans +
  odczuwalna intensywność — wszystkie trzy pola zawsze pokazywane, dystans
  opcjonalny) oraz **siłownia** (czas + intensywność; BEZ pola typu ćwiczeń —
  push/pull/nogi nie różnicuje kcal, świadomie uproszczone).
- Kcal liczone raz, przy zapisie: bieg z dystansem `masa × km` (intensywność
  ignorowana — kcal/km ~niezależne od tempa), bez dystansu MET 8/10/12;
  rower zawsze MET z intensywności 5.5/7/10 (odczucie lepsze niż prędkość —
  teren, wiatr), dystans tylko informacyjny; marsz z dystansem
  `0.53 × masa × km`, bez MET 3.3/4.3/5; siłownia MET wg etykiet
  **„ciężko, długie przerwy (maxy)" 3.5 / „klasycznie" 5.0 /
  „obwodowo, krótkie przerwy" 6.0** (uwaga: maxy = MNIEJ kcal, nie więcej).
- Pole kroków przenosi się z widoku Dziś do nowej zakładki: na samej górze,
  wyróżnione, zawsze obecne. Gdy dzień nie ma zapisanych kroków, pole
  pokazuje **domyślne 5000** i model liczy NEAT od 5000 (każdy jakieś kroki
  robi); wartość wpisana przez użytkownika jest respektowana; synchronizacja
  Garmina nadpisuje jak dotychczas.
- W miejscu obecnego pola kroków na Dziś — przycisk **„Aktywności/Kroki"**
  przenoszący do zakładki. Każdy ręczny wpis na liście ma **✕** do
  skasowania; wpisów garminowych nie kasujemy (sync by je odtworzył).
- Zakładka pokazuje rozbicie dzisiejszego wydatku:
  `BMR 2002 + kroki 40 + aktywności 400 + TEF 300 = 2742`.
- Użytkownik z podłączonym Garminem widzi w zakładce ostrzeżenie, że ręczne
  wpisy mogą zawyżać spalone kcal (w dniu w toku bilans bierze
  `max(pomiar, model)` — patrz `app/services/balance.py:day_balance`).

**Higiena tokenów dla implementującego modelu:** `app/main.py` i
`app/templates/mobile.html` są duże — czytaj je fragmentami (offset/limit,
grep po nazwach z tego planu), nie w całości i nie ponownie po każdej
edycji. Pełny `pytest` uruchamiaj raz, po skończeniu kroku, nie po każdej
zmianie pliku.

**Kroki implementacji:**

1. **Migracja.** W `app/models.py` do `Activity` kolumna
   `source: Mapped[str] = mapped_column(String, default="garmin")`;
   w `app/db.py:_migrate()` addytywnie `PRAGMA table_info` + `ALTER TABLE
   activity ADD COLUMN source ... DEFAULT 'garmin'` (backfill istniejących).
   Wpisy ręczne dostają `garmin_id = "manual-" + uuid4().hex` — spełnia
   `UniqueConstraint(user_id, garmin_id)` i nie koliduje z upsertem
   w `app/services/sync.py`; typy nazywaj po garminowsku (`running`,
   `cycling`, `walking`, `strength_training`), żeby istniejące dopasowania
   w `energy.activity_kcal_model` i odejmowanie kroków aktywności
   (`~1400 kroków/km` dla running/walking w `tdee_theoretical`) działały
   bez zmian.
2. **`app/services/energy.py`.** Stała `DEFAULT_STEPS = 5000`; tabela
   `MANUAL_MET = {typ: {light, moderate, intense}}` z wartościami z decyzji
   wyżej; funkcja `manual_activity_kcal(type, intensity, duration_s,
   distance_m, weight_kg) -> tuple[float, str]` — zwraca kcal i jednozdaniowe
   wyjaśnienie skąd liczba (np. „bieg 5.0 km × 74 kg" albo „MET 7.0 × 74 kg
   × 0.75 h"), w duchu `assumptions` przy posiłkach. W `tdee_theoretical`
   dict aktywności może mieć opcjonalne pole `"kcal"` — gdy ustawione,
   użyj go wprost zamiast `activity_kcal_model` (przekazywane tylko dla
   wpisów ręcznych; ścieżka garminowa bez zmian — model ma zostać
   niezależnym sanity-checkiem pomiaru).
3. **API w `app/main.py`** (wzorzec auth i 404 jak przy saved-meals):
   - `POST /api/activities` — body `{day?, type, duration_min,
     distance_km?, intensity}`; masa = wygładzona waga jak w `day_report`
     (409 gdy brak pomiarów); zapis `Activity(source="manual",
     kcal_garmin=round(kcal))`; zwraca kcal + wyjaśnienie.
   - `DELETE /api/activities/{id}` — 404 gdy cudzy lub nie istnieje,
     404 także gdy `source != "manual"`.
   - `day_report`: w `activities` dodaj `id` i `source`; dla wpisów
     ręcznych przekaż `"kcal": a.kcal_garmin` do `tdee_theoretical`;
     gdy dzień nie ma kroków (brak `summary` lub `steps is None`), licz
     NEAT od `DEFAULT_STEPS` i zwróć `"steps": 5000, "steps_default": true`;
     dodaj `"garmin_connected"` (z `garmin_provider.tokens_present(user_id)`)
     do warunkowego ostrzeżenia w UI.
4. **UI w `app/templates/mobile.html`.** Nowa strona w mechanizmie
   `show(page)` + piąty przycisk w dolnym `<nav>` („Aktywności"). Na Dziś:
   pole `#t-steps` (linia ~134) zastąp przyciskiem „Aktywności/Kroki" →
   `show('activities')`. W zakładce, od góry: (a) wyróżnione pole kroków
   (prefill z `rep.steps`, zapis istniejącym `POST /api/day/{day}/steps`
   przez `saveDaySteps()`, dopisek że Garmin nadpisze przy synchronizacji),
   (b) rozbicie wydatku z `rep.tdee_model` (render z tego samego
   `day_report` co Dziś), (c) formularz: select typu, czas [min], dystans
   [km] (ukryty dla siłowni), intensywność (radio; dla siłowni etykiety
   z decyzji), po zapisie pokaż zwrócone kcal + wyjaśnienie i odśwież,
   (d) lista aktywności wybranego dnia — ręczne z ✕ (DELETE + odśwież),
   garminowe bez, (e) ostrzeżenie widoczne gdy `rep.garmin_connected`.
5. **Transfer.** W `app/services/transfer.py` eksport/import wyłącznie
   aktywności `source == "manual"` (garminowe odtworzy sync), idempotentnie
   po `garmin_id` — wzorzec jak posiłki po `external_id`.
6. **Testy.** `tests/test_activities_api.py` (fixture dwóch klientów jak
   w `tests/test_saved_meals_api.py`): kcal per typ i ścieżka
   (bieg z dystansem ignoruje intensywność; rower liczy z MET mimo
   dystansu; siłownia „maxy" < „obwodowo"); wpis podbija
   `tdee_model.activities` dokładnie o zapisane kcal; kroki: brak danych →
   5000 i `steps_default`, wpisane 8000 → 8000; DELETE cudzego i
   garminowego → 404; izolacja list między użytkownikami; migracja
   backfilluje `source="garmin"`. Wszystko zielone — czerwony pytest
   blokuje deploy.
7. **TODO.md** — oznacz ten punkt jako zrobiony z SHA.

## ~~Dashboard lepiej wyglądający na telefonie~~ ✓ zrobione — jeden widok responsive (commit d5bb8e8)

## ~~Instalowanie na ekranie głównym telefonu~~ ✓ zrobione (commit 1e3360e)

Żeby `fit.krasnal.cc/mobile` można było "dodać do ekranu głównego" jak zwykłą
aplikację (ikona krasnala na home screen, otwiera się na pełnym ekranie bez
paska adresu). Wymaga: `manifest.webmanifest` z metadanymi i ikonami,
`sw.js` w minimalnej wersji (rejestracja + fallback cache). W poprzedniej
wersji były gotowe pliki tego typu — można wziąć z historii gita.
Uwaga: sam manifest nie da działania offline — to osobna, dużo większa robota.

## ~~Moje posiłki — zapamiętane, jednym kliknięciem (WYMAGANIA.md 5.2)~~ ✓ zrobione (3/10)

1. **Model danych.** W `app/models.py` tabela `SavedMeal`: `id`, `user_id`
   (FK + index), `name` (String), `kcal`, `kcal_min`, `kcal_max`, `protein_g`,
   `fat_g`, `carbs_g`, `fiber_g`, `sugars_g`, `items_json`, `assumptions_json`,
   `created_at`, `last_used_at` — kopia wartości posiłku, bez zdjęcia.
2. **API** w `app/main.py` (wzorzec auth: `Depends(auth.current_user)`):
   - `GET /api/saved-meals` — lista posortowana po `last_used_at` malejąco;
   - `POST /api/saved-meals` — body jak `MealIn` + `name`;
   - `DELETE /api/saved-meals/{id}` (sprawdź `user_id` jak w `delete_meal`);
   - `POST /api/saved-meals/{id}/use` — aktualizuje `last_used_at` i zwraca
     dane w formacie draftu (jak `estimate_meal_photo`), które klient
     zapisuje istniejącym `POST /api/meals` z `source="saved"`.
3. **UI** w `app/templates/mobile.html`: w panelu "Dodaj posiłek" trzecia
   ścieżka obok zdjęcia i opisu — lista "Moje posiłki" (nazwa + kcal,
   jeden klik → ekran korekty z wypełnionymi wartościami → zapis);
   na ekranie korekty każdego posiłku checkbox "zapisz w moich posiłkach"
   (poprosi o nazwę, domyślnie `description`).
4. **Transfer.** Dodaj `saved_meals` do `export_payload` / `import_payload`
   w `app/services/transfer.py` (idempotentnie po `name`, jak posiłki po
   `external_id`).
5. **Testy.** `tests/test_saved_meals.py`: zapis → lista → użycie →
   `last_used_at` rośnie; izolacja między użytkownikami (wzorzec:
   `tests/test_garmin_multiuser.py`).

## ~~Konwersja HEIC — zdjęcia z iPhone'ów (WYMAGANIA.md 5.1)~~ ✓ zrobione (2/10)

Dziś `app/services/meal_vision.py` zna tylko jpg/jpeg/png/webp/gif, a Pillow
bez wtyczki nie otworzy HEIC — zdjęcie z iPhone'a wywala szacowanie.

1. **Zależność.** `pillow-heif>=0.16` w `pyproject.toml` (+ instalacja
   w `.venv`; deploy instaluje z pyproject automatycznie).
2. **Rejestracja.** W `app/services/meal_queue.py` po imporcie PIL:
   `from pillow_heif import register_heif_opener; register_heif_opener()` —
   od tej pory `Image.open` czyta HEIC/HEIF, a istniejące
   `downscale_photo()` konwertuje je do JPEG bez dalszych zmian.
3. **Ujednolicenie wejścia.** W `app/main.py:estimate_meal_photo` przepuszczaj
   każde zdjęcie przez `meal_queue.downscale_photo(data)` **przed**
   `meal_vision.estimate_from_photo(..., ext="jpg", ...)` — dziś pełny
   oryginał leci do LLM tylko przy skonfigurowanym kluczu, a downscale
   robi wyłącznie kolejka; po zmianie format i rozmiar są zawsze
   znormalizowane (mniejsze tokeny, jeden format). `ValueError` z Pillow
   (nie-obraz) → istniejący HTTPException 422.
4. **UI.** W `app/templates/mobile.html` sprawdź `accept` inputa zdjęcia —
   ma zawierać `image/*` (iPhone poda wtedy HEIC bez konwersji po swojej
   stronie); downscale w przeglądarce (canvas) HEIC nie obsłuży w każdej
   przeglądarce — fallback: wyślij oryginał, serwer skonwertuje.
5. **Testy.** W `tests/test_meal_vision.py` (albo nowy plik) wygeneruj mały
   HEIC przez `pillow_heif` w teście i sprawdź, że `downscale_photo` zwraca
   poprawny JPEG ≤1280 px.

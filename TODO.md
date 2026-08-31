# TODO — do zrobienia po pilocie

Notatnik na luźne punkty, których nie robię teraz, ale nie chcę ich zgubić.
Każdy punkt jest przyszłym samodzielnym zadaniem — nie planem wdrożenia.

Przy każdym punkcie **szacowanie złożoności w skali 1-10**:

- **1** — wpisanie tej linijki tutaj zajmuje tyle samo co samo zrobienie.
- **3** — kilka godzin roboty, znane rozwiązanie.
- **5** — wieczór do dnia pracy, jakieś decyzje po drodze.
- **7** — kilka dni, sensowny plan przed startem.
- **10** — tygodnie, wymaga zewnętrznych rzeczy (usługa mailowa, nowa infrastruktura).

---

## PILNE: naprawa dodania aktywności (3/10) — produkcja zwraca 500

Implementacja zakładki Aktywności/Kroki (commity `985b41a`…`216b8ce`) położyła
produkcję i zostawiła śmieci. Diagnoza wykonana 2026-08-31 na prod
(fit.krasnal.cc, VM 34.56.100.135) — przyczyny są PEWNE, nie szukaj innych.
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

## ~~Landing page — drobne poprawki~~ ✓ zrobione (commit 3c99a77)

- Do karty *Fit Krasnal* dopisać informację o wygodniejszym widoku dla
  telefonu: `fit.krasnal.cc/mobile`.
- Adresy stron (`fit.krasnal.cc`, `mariuszwojciechowski.github.io/bilans-kcal`,
  `pikimocy.krasnal.cc`) zamienić na klikalne linki — teraz są tylko tekstem.

## Skrypt na serwerze do resetu hasła (1/10)

Analogiczny do `scripts/adopt_local_user.py`, tyle że dla dowolnego użytkownika:
`scripts/reset_password.py <email>` — pyta o nowe hasło w terminalu (żeby nie
lądowało w historii bash), haszuje i zapisuje w bazie. Do użycia, gdy tester
zapomni hasła i napisze do Ciebie.

## ~~Edytowanie liczby kroków w wersji desktopowej~~ ✓ nieaktualne — jeden widok ma pole kroków (commit d5bb8e8)

## Zmiana hasła z poziomu Ustawień (2/10)

Dodatkowa karta w `/settings`: pola *stare hasło*, *nowe hasło*, *powtórz*.
Endpoint `POST /settings/password` używa `auth.verify_password` na starym,
`auth.hash_password` na nowym, sprawdza kryteria minimalnej długości. Ten
sam wzorzec błędów co formularze rejestracji.

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

## Statystyki użycia — widok dla Ciebie (4/10)

Nowa zakładka `/usage` widoczna wyłącznie dla `krasnal@krasnal.cc`
(twardo w kodzie, bez roli w bazie). Pokazuje agregaty per `user_id`
(bez e-maili, bez samych danych osobowych): liczba posiłków/dzień,
liczba synców Garmina, liczba szacowań przez Gemini, ostatnia aktywność,
wielkość bazy per user. Do orientacji, ilu testerów faktycznie używa
i jak intensywnie.

## ~~Instalowanie na ekranie głównym telefonu~~ ✓ zrobione (commit 1e3360e)

Żeby `fit.krasnal.cc/mobile` można było "dodać do ekranu głównego" jak zwykłą
aplikację (ikona krasnala na home screen, otwiera się na pełnym ekranie bez
paska adresu). Wymaga: `manifest.webmanifest` z metadanymi i ikonami,
`sw.js` w minimalnej wersji (rejestracja + fallback cache). W poprzedniej
wersji były gotowe pliki tego typu — można wziąć z historii gita.
Uwaga: sam manifest nie da działania offline — to osobna, dużo większa robota.

## Kasowanie konta z 7-dniowym oknem odzyskania (6/10)

Użytkownik kasuje konto. W bazie flagi `deleted_at` + soft-delete relacji,
konto znika z widoku. Przez 7 dni skrypt na serwerze potrafi je przywrócić —
warunek: nowe konto zarejestrowane na ten sam e-mail (świadoma podatność
zaakceptowana na pilota). Po założeniu nowego konta tester **nie widzi**
starych danych — musi być przekonany, że są nie do odzyskania. Twarda
kasacja po 7 dniach (skrypt uruchamiany z cron / systemd timer).

## Kasowanie danych z konta — czyszczenie historii (6/10)

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

## Integracja z innym zrodlami w zakresie spalanych kcal (??/10)

Apple Watch, Fitbit, Whoop, Oura, Health Connect

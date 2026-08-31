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

## Ręczny wpis aktywności fizycznej (bez Garmina) (4/10)

Dla testerów bez zegarka sportowego: formularz do wpisania czasu trwania
i rodzaju aktywności, który przelicza go na spalone kcal metodą MET
(Metabolic Equivalent of Task — standardowe tabele ACSM). Pola:
aktywność (lista: rower, pływanie, bieganie, ćwiczenia siłowe, marsz szybki),
czas [minuty], opcjonalnie intensywność (lekka/umiarkowana/intensywna —
różne wartości MET). Wzór: `kcal = MET × masa_ciała_kg × czas_h`.
Masa ciała z ostatniego pomiaru w bazie. Zapis do `Activity` (tabela już
istnieje, `app/models.py`) z `source="manual"` — to samo co Garmin, więc
bilans i TDEE od razu uwzględniają aktywność. Wyświetlać w dashboardzie
i `/mobile` w sekcji bilansu obok kroków. Nie zastępuje synchronizacji
Garmina — jest alternatywą dla tych, którzy go nie mają.

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

## Moje posiłki — zapamiętane, jednym kliknięciem (WYMAGANIA.md 5.2) (3/10)

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

## Konwersja HEIC — zdjęcia z iPhone'ów (WYMAGANIA.md 5.1) (2/10)

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

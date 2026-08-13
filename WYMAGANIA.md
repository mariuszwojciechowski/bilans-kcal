# Aplikacja "Bilans kcal" — analiza i doprecyzowanie wymagań

Cel produktu: **wsparcie odchudzania przez rzetelny dzienny bilans energetyczny** —
realnie zmierzony wydatek (Garmin) kontra oszacowane spożycie (zdjęcia posiłków),
z modelem teoretycznym jako punktem odniesienia i mechanizmem kalibracji.

Etap 1: web app (weryfikacja pomysłu). Etap 2: aplikacja Android.

---

## 1. Zakres MVP (web)

| Moduł | Co robi |
|---|---|
| M1 Integracja Garmin | Pobiera wagę, spalone kcal (total dzienny), kroki, aktywności |
| M2 Profil + BMR | Dane użytkownika, spoczynkowe zapotrzebowanie energetyczne |
| M3 Model teoretyczny TDEE | Dzienna weryfikacja zapotrzebowania wg kroków i aktywności |
| M4 Szacowanie spożycia | Zdjęcie posiłku → składniki → masa → kcal (+ korekta ręczna) |
| M5 Bilans dzienny | Spożycie − wydatek (Garmin), cel deficytu, trend wagi |

Poza zakresem MVP: multi-user, powiadomienia, makroskładniki (opcjonalnie), integracje inne niż Garmin.

---

## 2. M1 — Dane z Garmin Connect

### 2.1 Potrzebne dane

- **Kalorie dzienne total** (active + resting wg Garmina) — źródło prawdy dla bilansu.
- **Kroki** (dzienna suma) — wejście do modelu teoretycznego.
- **Waga** (pomiary z Garmin Connect — waga Index lub wpis ręczny).
- **Aktywności**: typ (bieg / rower / siłownia / inne), czas trwania, dystans, kcal wg Garmina, śr. tętno.

### 2.2 Sposób dostępu — kluczowa decyzja projektu

| Opcja | Plusy | Minusy |
|---|---|---|
| **A. Oficjalne Garmin Health API** | Legalne, stabilne, push (webhooki) | Wymaga aplikacji do programu deweloperskiego Garmina i zatwierdzenia biznesowego — dla prywatnego MVP wolne/niepewne |
| **B. Nieoficjalna biblioteka (`garth` / `python-garminconnect`)** | Działa od razu, pełny dostęp do własnych danych, obsługuje MFA (tokeny ważne ~rok) | Formalnie poza ToS Garmina, może się zepsuć przy zmianach po ich stronie; tylko własne konto |
| **C. (docelowy Android) Health Connect** | Garmin Connect synchronizuje się z Health Connect na Androidzie — apka mobilna czyta dane lokalnie, bez żadnego API Garmina | Tylko na Androidzie, nie rozwiązuje web MVP |

**Rekomendacja:** B na MVP (single-user, własne konto), z architekturą która pozwoli
podmienić źródło danych na C w wersji Android (warstwa `DataProvider` z interfejsem:
`get_daily_summary(date)`, `get_weight(date_range)`, `get_activities(date_range)`).

### 2.3 Synchronizacja

- Zegarek zrzuca dane do Garmin Connect kilka razy dziennie → **polling co 30–60 min**
  - przycisk "odśwież teraz" w UI.
- Dane dnia bieżącego są **częściowe do końca dnia** — patrz 6.3.
- Idempotentny zapis (upsert po dacie/ID aktywności); przechowujemy surowe odpowiedzi
  do ewentualnego przeliczenia.

---

## 3. M2 — Profil i zapotrzebowanie spoczynkowe (BMR)

### 3.1 Dane profilu

- data urodzenia (wiek), wzrost, **płeć** ⚠️ (brakowała w pierwotnych wymaganiach,
  a jest niezbędna we wzorach BMR), opcjonalnie % tkanki tłuszczowej.
- Waga: automatycznie ostatni pomiar z Garmina; możliwy wpis ręczny.

### 3.2 Model

- **Wzór podstawowy: Mifflin-St Jeor** (najlepiej zwalidowany dla ogółu populacji):
  `BMR = 10·waga[kg] + 6.25·wzrost[cm] − 5·wiek[lata] + (5 dla M / −161 dla K)`
- Jeśli znany % tłuszczu (waga Garmin Index): opcjonalnie **Katch-McArdle**
  `BMR = 370 + 21.6 · beztłuszczowa masa ciała[kg]`.
- BMR przeliczany codziennie na podstawie **wygładzonej wagi** (średnia 7-dniowa),
  nie pojedynczego pomiaru — waga dobowa fluktuuje ±1–2 kg (woda, glikogen).

---

## 4. M3 — Teoretyczny model dziennego wydatku (TDEE)

Codziennie, dla porównania z pomiarem Garmina:

```
TDEE_teoret = BMR
            + NEAT z kroków
            + Σ kcal aktywności (model)
            + TEF (termogeneza poposiłkowa, ~10% spożycia)
```

- **Kroki (NEAT):** `kcal ≈ kroki · waga[kg] · 0.00057` (chód ~0.57 kcal/kg/1000 kroków·…),
  z odjęciem kroków wykonanych w ramach zarejestrowanych aktywności (bez podwójnego liczenia).
- **Bieg:** `kcal ≈ 1.0 · waga[kg] · dystans[km]` (netto ~0.9 po odjęciu BMR za ten czas).
- **Rower:** wg MET zależnie od intensywności (6–10 MET; jeśli znane śr. tętno z Garmina —
  dobór MET wg strefy): `kcal = MET · waga[kg] · czas[h]`.
- **Siłownia:** MET 3.5–6.0 (Garmin notorycznie zaniża/szacuje słabo trening siłowy —
  tu model teoretyczny bywa lepszy niż pomiar).
- Tabela MET konfigurowalna w kodzie (Compendium of Physical Activities).

**Zasada rozdzielenia:** model teoretyczny służy do (a) prognozy zapotrzebowania na dziś,
(b) sanity-checku pomiaru Garmina, (c) fallbacku gdy zegarek nie był noszony.
**Do bilansu wchodzi pomiar Garmina** (patrz M5). Nigdy nie sumujemy własnego BMR
z totalem Garmina — total Garmina już zawiera kalorie spoczynkowe (podwójne liczenie!).

---

## 5. M4 — Szacowanie spożytych kcal ze zdjęcia

### 5.1 Pipeline

1. Użytkownik robi/wgrywa zdjęcie posiłku.
2. **Model wizyjny (LLM z vision, np. Claude API)** → strukturalny JSON:
   lista składników, szacowana masa każdego [g], stopień pewności.
3. Mapowanie składników na bazę żywieniową → kcal (+makro, jeśli w zakresie).
4. **Ekran korekty**: użytkownik może poprawić składnik, masę, dodać pominięte
   (olej, cukier w napoju), zapisać.
5. Zapis posiłku z godziną → suma dzienna.

### 5.2 Baza żywieniowa

- **Open Food Facts** (otwarta, dobre pokrycie produktów PL z kodami kreskowymi)
  + **USDA FoodData Central** (produkty generyczne: "pierś z kurczaka", "ryż gotowany").
- Brak dobrej otwartej polskiej bazy tabel IŻŻ — alternatywnie LLM sam podaje
  kaloryczność z wiedzy ogólnej (prostsze na MVP, mniej audytowalne).
- Własny słownik "moje produkty/posiłki" — powtarzalne posiłki jednym tapnięciem.

### 5.3 Uzupełniające sposoby wprowadzania (ważne dla realnego użycia)

- Wpis tekstowy naturalnym językiem ("2 jajka sadzone na maśle i kromka żytniego") → ten sam LLM.
- Skan kodu kreskowego (Open Food Facts) + gramatura.
- Szybki wpis "tylko kcal" gdy użytkownik zna wartość.

### 5.4 Ograniczenia do zakomunikowania w UI

- Realna dokładność szacunku ze zdjęcia: **±25–40%**; najgorzej dla potraw złożonych
  (zupy, sosy, zapiekanki) i tłuszczu niewidocznego na zdjęciu.
- To akceptowalne: przy odchudzaniu liczy się systematyczność i trend, nie precyzja
  pojedynczego posiłku — ale UI powinno pokazywać przedział, nie fałszywie dokładną liczbę.
- Koszt: ~1–3 grosze za zdjęcie (wywołanie API vision) — pomijalny przy 1 użytkowniku.

---

## 6. M5 — Bilans energetyczny i wsparcie odchudzania

### 6.1 Definicja

```
bilans_dnia = kcal_spożyte (M4) − kcal_spalone_total (Garmin)
```

Cel użytkownika: docelowy deficyt dzienny (np. −500 kcal/d ≈ −0.5 kg/tydzień; 1 kg
tkanki tłuszczowej ≈ 7 700 kcal). Konfigurowalne tempo z ostrzeżeniem przy deficycie
przekraczającym ~25% TDEE (zdrowotnie i behawioralnie niezrównoważone).

### 6.2 Kalibracja adaptacyjna (przewaga produktu)

Co tydzień/2 tygodnie porównujemy: **skumulowany bilans** vs **rzeczywista zmiana
wygładzonej wagi**. Jeśli waga spada wolniej niż wynika z bilansu → systematyczny błąd
(niedoszacowane spożycie albo przeszacowany wydatek) → korygujemy współczynnikiem
kalibracji prezentowane zapotrzebowanie. To podejście jak w MacroFactor: model uczy się
na własnych danych użytkownika zamiast ufać wzorom.

### 6.3 Reguły brzegowe

- **Dzień w toku:** bilans "na teraz" liczony z częściowych danych Garmina + prognoza
  reszty dnia z modelu teoretycznego; zamknięcie dnia po pierwszej synchronizacji po północy.
- **Zegarek nie noszony / brak synca:** wydatek = model teoretyczny (M3), dzień oznaczony
  jako "szacowany".
- **Brak wpisów posiłków:** dzień wykluczony z kalibracji (nie z widoku).

### 6.4 Dashboard (MVP)

- Dziś: spożyte / spalone / bilans / pozostało do celu.
- Wykres trendu wagi (punkty pomiarów + linia wygładzona 7d) i prognoza osiągnięcia celu.
- Tygodniówka: średni bilans, zgodność z celem, wynik kalibracji.

---

## 7. Wymagania niefunkcjonalne / architektura

- **API-first:** backend z REST API — web MVP i przyszła apka Android używają tych samych endpointów.
- Sugerowany stack MVP: **Python + FastAPI** (biblioteki Garmina są pythonowe) + prosty
  frontend (Next.js/React albo HTMX); **SQLite** na start, migrowalne do Postgresa.
- **Dane wrażliwe:** waga, zdrowie, zdjęcia posiłków = dane szczególnej kategorii.
  MVP single-user: sekrety Garmina poza repo (env/keychain), baza lokalna/szyfrowana.
  Jeżeli kiedykolwiek pojawią się inni użytkownicy → RODO: zgody, prawo do usunięcia,
  polityka retencji zdjęć — do zaprojektowania przed otwarciem.
- Wersjonowanie surowych danych z Garmina (możliwość przeliczenia historii po zmianie modelu).
- Strefa czasowa użytkownika jako granica "dnia" (nie UTC).

### Szkic modelu danych

```
user_profile(id, birth_date, sex, height_cm, target_deficit_kcal, tz)
weight_log(date, weight_kg, body_fat_pct?, source)          -- garmin | manual
daily_summary(date, kcal_total_garmin, kcal_active, steps, sync_ts, complete)
activity(garmin_id, date, type, duration_s, distance_m, kcal_garmin, avg_hr)
meal(id, date, time, photo_path?, description, kcal, kcal_min, kcal_max, items_json, source)
daily_balance(date, kcal_in, kcal_out_measured, kcal_out_model, balance, estimated_flag)
calibration(period_start, period_end, expected_delta_kg, actual_delta_kg, factor)
```

---

## 8. Pytania otwarte (decyzje przed startem implementacji)

1. **Płeć w profilu** — do dodania do wymagań (niezbędna do BMR). ✔ zaproponowane wyżej
2. **Single-user na zawsze czy multi-user docelowo?** Wpływa na wybór dostępu do Garmina
   (opcja B działa tylko dla własnego konta) i na wymagania RODO.
3. **Skąd waga** — waga Garmin Index (auto) czy wpis ręczny w Garmin Connect?
   (technicznie oba działają, wpływa na UX)
4. **Akceptacja opcji B (nieoficjalna biblioteka)** na MVP — formalnie poza ToS Garmina.
5. **Makroskładniki** (zwłaszcza białko — istotne przy redukcji) w zakresie MVP czy później?
6. **Baza żywieniowa**: LLM "z głowy" (prosto) vs mapowanie na OFF/USDA (audytowalnie)?
7. **Docelowa apka Android**: natywnie (Kotlin) z Health Connect, czy cross-platform
   (Flutter/React Native) reużywając backend? — decyzja może poczekać do walidacji MVP.

# Fit Krasnal — wymagania (v2)

Cel produktu: **wsparcie odchudzania przez rzetelny dzienny bilans energetyczny** —
realnie zmierzony wydatek (Garmin) kontra oszacowane spożycie (zdjęcia posiłków),
z modelem teoretycznym jako punktem odniesienia i mechanizmem kalibracji.

Etap 1: web app (weryfikacja pomysłu, single-user). Etap 2: aplikacja mobilna
(Google Play, potencjalnie iOS/App Store).

## Decyzje podjęte (2026-08-13)

| # | Decyzja |
|---|---|
| D1 | Profil zawiera **płeć** (niezbędna do BMR) |
| D2 | Web MVP single-user, ale **model danych od początku multi-user** (docelowo apka w Google Play, możliwe iOS) |
| D3 | Waga **wyłącznie z Garmin Connect** (użytkownik wpisuje ją ręcznie tam); nasza aplikacja wagi nie przyjmuje |
| D4 | Dostęp do Garmina: **nieoficjalna biblioteka** (`garth`/`python-garminconnect`) na MVP |
| D5 | **Makroskładniki w zakresie MVP** — moduł zapotrzebowania i pokrycia wg norm WHO |
| D6 | Szacowanie posiłku: **zdjęcie z dysku → model wizyjny LLM samodzielnie** określa kcal i makro (bez zewnętrznej bazy żywieniowej w MVP) |
| D7 | Mobile: rekomendacja **Flutter** (jeden kod na Android + iOS), backend API współdzielony |
| D8 | Nazwa: **Fit Krasnal**; branding wg sekcji 9 (poważny, bez infantylności) |
| D9 | Repo **publiczne** → żadne dane użytkownika/sekrety nie trafiają do repo (sekcja 8.3) |

---

## 1. Zakres MVP (web)

| Moduł | Co robi |
|---|---|
| M1 Integracja Garmin | Pobiera wagę, spalone kcal (total dzienny), kroki, aktywności |
| M2 Profil + BMR | Dane użytkownika, spoczynkowe zapotrzebowanie energetyczne |
| M3 Model teoretyczny TDEE | Dzienna weryfikacja zapotrzebowania wg kroków i aktywności |
| M4 Szacowanie spożycia | Zdjęcie posiłku z dysku → LLM → kcal + makro (+ korekta ręczna) |
| M5 Bilans dzienny | Spożycie − wydatek (Garmin), cel deficytu, trend wagi |
| M6 Makroskładniki | Zapotrzebowanie wg WHO i pokrycie z dziennika posiłków |

Poza zakresem MVP: rejestracja wielu użytkowników (ale schemat danych gotowy), powiadomienia, integracje inne niż Garmin, wersje mobilne.

---

## 2. M1 — Dane z Garmin Connect

### 2.1 Potrzebne dane

- **Kalorie dzienne total** (active + resting wg Garmina) — źródło prawdy dla bilansu.
- **Kroki** (dzienna suma) — wejście do modelu teoretycznego.
- **Waga** — pomiary wpisywane ręcznie przez użytkownika w Garmin Connect (D3);
  aplikacja tylko odczytuje, nie ma własnego formularza wagi.
- **Aktywności**: typ (bieg / rower / siłownia / inne), czas trwania, dystans, kcal wg Garmina, śr. tętno.

### 2.2 Sposób dostępu

**MVP (D4):** nieoficjalna biblioteka `garminconnect` (na bazie `garth`), logowanie na
własne konto użytkownika. Jednorazowy interaktywny login (z obsługą MFA) uruchamiany
przez użytkownika lokalnie (`scripts/garmin_login.py`); tokeny sesji zapisywane w
`~/.fit-krasnal/garth/` — **poza repozytorium**. Ryzyko: formalnie poza ToS Garmina,
może się psuć przy zmianach po stronie Garmina — akceptowane dla MVP.

**Docelowo (mobile):** dane z urządzenia przez **Health Connect** (Android) /
**HealthKit** (iOS) — Garmin Connect synchronizuje się z oboma; znika zależność od
nieoficjalnego API. Dlatego dostęp do danych za interfejsem `DataProvider`
(`get_daily_summary`, `get_weight`, `get_activities`) — wymienna implementacja.

### 2.3 Synchronizacja

- Zegarek zrzuca dane kilka razy dziennie → **polling co 30–60 min** + przycisk "odśwież teraz".
- Dane dnia bieżącego **częściowe do końca dnia** — patrz 6.3.
- Idempotentny zapis (upsert po dacie / ID aktywności); surowe odpowiedzi przechowywane
  lokalnie do przeliczeń (w `data/`, poza repo).

---

## 3. M2 — Profil i zapotrzebowanie spoczynkowe (BMR)

### 3.1 Dane profilu

- data urodzenia (wiek), **płeć** (D1), wzrost, strefa czasowa, cel deficytu [kcal/d].
- Waga: zawsze ostatni pomiar z Garmina (D3) — w profilu tylko do odczytu.

### 3.2 Model

- **Mifflin-St Jeor**: `BMR = 10·waga[kg] + 6.25·wzrost[cm] − 5·wiek[lata] + (5 M / −161 K)`
- BMR przeliczany codziennie na podstawie **wygładzonej wagi** (średnia 7-dniowa) —
  waga dobowa fluktuuje ±1–2 kg (woda, glikogen).

---

## 4. M3 — Teoretyczny model dziennego wydatku (TDEE)

Codziennie, dla porównania z pomiarem Garmina:

```
TDEE_teoret = BMR + NEAT z kroków + Σ kcal aktywności (model) + TEF (~10% spożycia)
```

- **Kroki (NEAT):** `kcal ≈ kroki · waga[kg] · 0.00057`, z odjęciem kroków wykonanych
  w ramach zarejestrowanych aktywności (bez podwójnego liczenia).
- **Bieg:** `kcal ≈ 1.0 · waga[kg] · dystans[km]` (netto ~0.9 po odjęciu BMR za ten czas).
- **Rower:** MET 6–10 wg intensywności (jeśli znane śr. tętno — dobór wg strefy):
  `kcal = MET · waga[kg] · czas[h]`.
- **Siłownia:** MET 3.5–6.0 (Garmin notorycznie słabo szacuje trening siłowy —
  tu model teoretyczny bywa lepszy niż pomiar).
- Tabela MET konfigurowalna (Compendium of Physical Activities).

**Zasada rozdzielenia:** model teoretyczny = prognoza na dziś, sanity-check pomiaru
i fallback na dni bez zegarka. **Do bilansu wchodzi pomiar Garmina.** Nigdy nie
sumujemy własnego BMR z totalem Garmina (total już zawiera kalorie spoczynkowe).

---

## 5. M4 — Szacowanie posiłku ze zdjęcia (doprecyzowane, D6)

### 5.1 Przepływ

1. Użytkownik **wgrywa zdjęcie z dysku** (JPEG/PNG/HEIC/WebP, limit np. 15 MB;
   HEIC konwertowany po stronie serwera).
2. **Model wizyjny LLM (Claude, vision)** samodzielnie — bez zewnętrznej bazy
   żywieniowej — zwraca strukturalny JSON:

   ```json
   {
     "items": [{"name": "...", "mass_g": 0, "kcal": 0,
                "protein_g": 0, "fat_g": 0, "carbs_g": 0,
                "fiber_g": 0, "confidence": "low|medium|high"}],
     "assumptions": ["np. założono smażenie na 10 g oleju"],
     "total": {"kcal": 0, "kcal_min": 0, "kcal_max": 0, "protein_g": 0, ...}
   }
   ```

3. **Ekran korekty**: edycja składników/gramatur, dodanie pominiętych (olej, cukier
   w napoju), usunięcie błędnych; przeliczenie proporcjonalne po zmianie masy.
4. Zapis posiłku (data, godzina, kcal, makro, zdjęcie) → sumy dzienne (M5, M6).

### 5.2 Wymagania jakościowe

- Wynik zawsze z **przedziałem** (kcal_min–kcal_max), nie fałszywie dokładną liczbą.
- `assumptions` prezentowane użytkownikowi — widzi, co model założył.
- Uzupełniające wejścia (również przez LLM): wpis tekstowy naturalnym językiem
  ("2 jajka sadzone na maśle i kromka żytniego") oraz "moje posiłki" (zapamiętane, jednym kliknięciem).
- Realna dokładność ±25–40% — kompensowana kalibracją (6.2); komunikowana w UI.
- Zdjęcia przechowywane wyłącznie lokalnie w `data/photos/` (poza repo, D9);
  do API LLM wysyłane tylko na czas analizy.
- Koszt: ~1–3 grosze/zdjęcie — pomijalny dla 1 użytkownika.

---

## 6. M5 — Bilans energetyczny

### 6.1 Definicja

```
bilans_dnia = kcal_spożyte (M4) − kcal_spalone_total (Garmin)
```

Cel: docelowy deficyt dzienny (np. −500 kcal/d ≈ −0.5 kg/tydz.; 1 kg tłuszczu ≈ 7 700 kcal).
Ostrzeżenie przy deficycie > ~25% TDEE (niezrównoważone zdrowotnie i behawioralnie).

### 6.2 Kalibracja adaptacyjna (przewaga produktu)

Co 1–2 tygodnie: **skumulowany bilans** vs **rzeczywista zmiana wygładzonej wagi**.
Rozbieżność → współczynnik korekty prezentowanego zapotrzebowania (jak MacroFactor:
model uczy się na danych użytkownika zamiast ufać wzorom).

### 6.3 Reguły brzegowe

- **Dzień w toku:** bilans "na teraz" z częściowych danych Garmina + prognoza reszty
  dnia z modelu teoretycznego; zamknięcie dnia po pierwszej synchronizacji po północy
  (czas wg strefy użytkownika).
- **Zegarek nie noszony / brak synca:** wydatek = model teoretyczny (M3), dzień oznaczony "szacowany".
- **Brak wpisów posiłków:** dzień wykluczony z kalibracji (nie z widoku).

### 6.4 Dashboard (MVP)

- Dziś: spożyte / spalone / bilans / pozostało do celu + panel makro (M6).
- Wykres trendu wagi (pomiary + linia wygładzona 7d) i prognoza osiągnięcia celu.
- Tygodniówka: średni bilans, zgodność z celem, wynik kalibracji.

---

## 7. M6 — Makroskładniki wg norm WHO (doprecyzowane)

Moduł w web MVP pokazujący **dzienne zapotrzebowanie** i **pokrycie** z dziennika posiłków.

### 7.1 Normy (WHO/FAO — cele populacyjne, prezentowane jako przedziały)

Punkt odniesienia energetyczny: `E_cel = zapotrzebowanie skalibrowane + cel deficytu`
(normy % liczone od energii docelowej, nie od faktycznego spożycia).

| Składnik | Norma WHO | Uwagi |
|---|---|---|
| Białko | ≥ 0.83 g/kg masy ciała/d | pokazujemy też opcjonalny "cel redukcyjny" 1.2–1.6 g/kg (oznaczony jako ponad normę WHO — istotny przy deficycie dla ochrony mięśni) |
| Tłuszcze | 15–30% E_cel | |
| Węglowodany | 55–75% E_cel | |
| Cukry wolne | < 10% E_cel | miękkie ostrzeżenie; LLM szacuje z posiłku |
| Błonnik | ≥ 25 g/d | |

### 7.2 Prezentacja

- Pasek postępu per składnik: spożycie vs przedział normy, stany
  **poniżej / w normie / powyżej** (kolory wg sekcji 9.2).
- Wartości w gramach i w % energii; aktualizacja po każdym zapisanym posiłku.
- Dzień w toku: pasek pokazuje pokrycie "do teraz" bez straszenia niedoborem przed wieczorem.
- Waga do normy białka = wygładzona waga z Garmina.

*(Mikroskładniki — witaminy/minerały — poza MVP; szacunek LLM ze zdjęcia byłby
zbyt niepewny. Do rozważenia po walidacji.)*

---

## 8. Wymagania niefunkcjonalne / architektura

### 8.1 Architektura

- **API-first:** backend REST — web MVP i przyszła apka mobilna używają tych samych endpointów.
- Stack MVP: **Python 3.12 + FastAPI** (biblioteki Garmina są pythonowe), frontend
  server-rendered (Jinja2 + lekki JS) — bez SPA na etapie walidacji; **SQLite** → migrowalne do Postgresa.
- **Model danych multi-user od początku (D2):** każda tabela domenowa z `user_id`;
  web MVP działa na jednym lokalnym koncie, bez ekranów rejestracji.

### 8.2 Mobile (D7 — rekomendacja pod przyszłe iOS)

**Flutter**: jeden kod na Android + iOS (Google Play i App Store), dojrzałe wykresy,
dobra integracja z Health Connect/HealthKit (pakiet `health`). Backend pozostaje
źródłem prawdy (sync, kalibracja, LLM); aplikacja mobilna dostarcza dane zdrowotne
z urządzenia zamiast nieoficjalnego API. Alternatywa: React Native (sensowna przy
silnym zapleczu JS); natywnie ×2 (Kotlin + Swift) — odrzucone jako podwójny koszt.

### 8.3 Prywatność i bezpieczeństwo (D9 — repo publiczne!)

- **Do repo nie trafiają nigdy:** baza danych, zdjęcia posiłków, tokeny Garmina,
  loginy/hasła, klucze API, profil użytkownika, surowe zrzuty danych.
- Wszystkie dane runtime w `data/` (w `.gitignore`); tokeny Garmina w `~/.fit-krasnal/`
  (poza drzewem repo); sekrety w `.env` (w `.gitignore`, w repo tylko `.env.example`).
- Dane zdrowotne = dane wrażliwe: przy wersji multi-user (mobile) wymagane RODO
  (zgody, prawo do usunięcia, retencja zdjęć) — do zaprojektowania przed publikacją w sklepach.
- Strefa czasowa użytkownika jako granica "dnia" (nie UTC).

### 8.4 Model danych (szkic, multi-user)

```
user(id, email, created_at)
user_profile(user_id, birth_date, sex, height_cm, target_deficit_kcal, tz)
weight_log(user_id, date, weight_kg, source)                 -- source: garmin
daily_summary(user_id, date, kcal_total_garmin, kcal_active, kcal_bmr_garmin,
              steps, sync_ts, complete)
activity(user_id, garmin_id, date, type, duration_s, distance_m, kcal_garmin, avg_hr)
meal(id, user_id, date, time, photo_path, description, kcal, kcal_min, kcal_max,
     protein_g, fat_g, carbs_g, fiber_g, sugars_g, items_json, assumptions_json, source)
daily_balance(user_id, date, kcal_in, kcal_out_measured, kcal_out_model,
              balance, estimated_flag)
calibration(user_id, period_start, period_end, expected_delta_kg,
            actual_delta_kg, factor)
```

---

## 9. Branding — Fit Krasnal (D8)

Koncept: krasnal — tradycyjnie pocieszny grubasek — przechodzi na fit. Paradoks nazwy
jest atutem marki, ale **aplikacja jest poważnym narzędziem**: zero infantylnych
ilustracji, maskotek i dziecięcej kreski. Krasnal obecny **symbolicznie**, nie dosłownie.

### 9.1 Identyfikacja

- **Logo/znak:** minimalistyczny, geometryczny sygnet **spiczastej czapki** (trójkąt
  z lekkim załamaniem) — czytelne nawiązanie bez rysowania postaci. Działa jako
  favicon i ikona aplikacji mobilnej.
- **Typografia:** nowoczesny grotesk (Inter / Manrope); nagłówki semibold, cyfry
  tabelaryczne w statystykach.
- **Ton komunikatów:** rzeczowy, z suchym humorem w mikrocopy ("Krasnal odnotował
  nadwyżkę 320 kcal"), nigdy wykrzykniki i emotki w danych. Powaga > żart, żart
  tylko w tle.

### 9.2 Paleta ("las i czapka")

| Rola | Kolor | Hex |
|---|---|---|
| Primary (akcje, nagłówki) | zieleń leśna | `#1B5E4A` |
| Primary dark / tło dark mode | las nocą | `#0F3D2E` |
| Akcent CTA / logo | czerwień czapki (cegła, stonowana) | `#B3402A` |
| Wyróżnienia, ostrzeżenia miękkie | bursztyn/miód | `#D9982B` |
| Tło jasne | pergamin | `#F5F1E8` |
| Tekst główny | atrament ciepły | `#23201B` |
| Tekst wtórny / linie | kamień | `#6B6459` |

Semantyka danych: **deficyt / w normie = zieleń `#1B5E4A`**, **nadwyżka / powyżej
normy = cegła `#B3402A`**, **blisko granicy = bursztyn `#D9982B`**.
Makro: białko `#B3402A` · węglowodany `#D9982B` · tłuszcze `#6B8E4E` (oliwka) ·
błonnik `#8A7357` (kora). Tryb ciemny od MVP (tła `#0F3D2E`/`#14261F`, tekst `#EDE8DC`).

---

## 10. Pytania otwarte (pozostałe)

1. Retencja zdjęć posiłków — trzymać bezterminowo lokalnie, czy kasować po N dniach
   (zostają tylko wartości)?
2. "Cel redukcyjny" białka (1.2–1.6 g/kg) — domyślnie włączony obok normy WHO, czy opt-in?
3. Nazwa pakietu/domena pod wydanie mobilne (np. `pl.fitkrasnal.app`) — do rezerwacji później.

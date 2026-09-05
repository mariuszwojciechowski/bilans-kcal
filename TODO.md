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
(zaokrąglenie budżetu w dół, asymetryczny clamp kalibracji — zaimplementowane,
patrz DONE.md „Poprawa wyliczania kcal na dzień w toku" i „Kalibracja
adaptacyjna"), a nie ukryte w stałych MET czy wzorze BMR, bo ukrytego
przesunięcia nie da się potem skalibrować.

**Zasada dla implementującego LLM (uruchamianie testów):** pełną suitę
testów (`pytest` bez filtra na konkretny plik) puszczaj dopiero po zgodzie
właściciela — nie automatycznie po skończeniu implementacji. Testy nowego/
zmienianego pliku (np. `pytest tests/test_usage.py`) można odpalać na
bieżąco w trakcie pracy.

**Zasada dla każdego przyszłego planu (decyzja właściciela 2026-09-05):** plan
implementacji, jeśli to ma sens, zawiera krok „Statystyki" — co zliczać i jak
pokazać na `/usage`, żeby po wdrożeniu było widać **adopcję** funkcji i jej
**funkcjonowanie**. Wprowadzone po tym, że dwa wdrożenia z 2026-09-05 (poprawka
kcal 21.5.0, kalibracja adaptacyjna 22.0.0) weszły bez tego kroku — nadrobione
w DONE.md „Statystyki: obserwowalność poprawki kcal i kalibracji adaptacyjnej".

**Zasada dla implementującego LLM (częste commity):** commituj często —
za każdym razem, gdy uznasz, że właśnie zaimplementowana zmiana jest istotna,
zasługuje na osobny bump w `VERSION`, albo ułatwi odwrót (`git revert`/
`git reset`), gdyby trzeba było ją wycofać. Nie czekaj do końca całego zadania
z jednym wielkim commitem — małe, opisowe commity po drodze są tańsze do
wycofania niż jeden duży. **Nie pushuj** (`git push` robi właściciel ręcznie)
i **nie puszczaj pełnej suity testowej** przy samym commitowaniu — to osobna
zgoda, patrz zasada wyżej.

---

## Mapa braków względem WYMAGANIA.md (audyt 2026-09-03)

Przegląd całego kontraktu z [WYMAGANIA.md](WYMAGANIA.md) przeciw stanowi kodu.
Moduły M1-M11 są zrobione (patrz [DONE.md](DONE.md)); poniżej wyłącznie to,
czego nie ma. Kolumna „gdzie plan" wskazuje punkt tej listy — **jeśli punkt
istnieje, nie dopisuj drugiego planu na to samo**, bo się rozjadą.

Zrobione punkty z tej tabeli **usuwamy** (ostatnie porządki 2026-09-05:
6.2 kalibracja, 6.4 karta kalibracji, 8.3 strefa czasowa, §4 tabela MET —
wszystkie opisane w [DONE.md](DONE.md)); tabela ma pokazywać wyłącznie braki.

| Wymóg | Stan | Gdzie plan |
|---|---|---|
| 8.3 Prawo do usunięcia (samoobsługowe) | realizowane mailem; nota `/prywatnosc` mówi o tym wprost, więc nie jest to kłamstwo — tylko brak | „«Usuń moje dane i konto»…" (6/10) |
| §10.2 Cel redukcyjny białka | `protein_cut_g_per_kg` leży w `who_norms.json`, ale nic go nie czyta | „Cel białka zależny od bilansu…" (3/10) |
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


## Cel białka zależny od bilansu (redukcja / masa) — trzeci znacznik na pasku — WYMAGANIA.md §10.2 (3/10)

**Decyzja właściciela 2026-09-05: wariant (b)**, rozszerzony: znacznik zależy
od **znaku docelowego bilansu** z profilu (punkt „Bilans zamiast deficytu"
niżej — **zrób go pierwszy**, ten punkt czyta jego wynik).

Stan faktyczny: `who_norms.json` ma per grupę martwe pole
`protein_cut_g_per_kg: [1.2, 1.6]` — nic go nie czyta; pasek białka bierze
zakres wyłącznie ze stylu życia (`protein_range_g_per_kg`), obok minimum WHO.
Dla „mało aktywnego" na deficycie zakres 0.8-1.0 g/kg jest za niski (ochrona
mięśni w deficycie: 1.2-1.6 g/kg), dla budującego masę — również (ISSN:
1.6-2.2 g/kg).

**Reguły:**

- Bilans docelowy **< 0** (deficyt) → cel „redukcyjny" `protein_cut_g_per_kg`
  (1.2-1.6). Bilans **> 0** (masa) → cel „budowy masy" — nowe pole
  `protein_bulk_g_per_kg: [1.6, 2.2]` w obu grupach `who_norms.json`.
  Bilans **= 0** (utrzymanie) → **brak** znacznika.
- Znacznik i wyjaśnienie pokazują się **tylko, gdy cel różni się od zakresu
  ze stylu życia** (którakolwiek granica różni się o > 0.05 g/kg). Dla
  „rekreacyjnie trenującego" na deficycie (1.2-1.6 = 1.2-1.6) nic się nie
  pojawia — nie dublujemy informacji.
- Wyjaśnienie w **dwóch miejscach**, ten sam tekst z jednego słownika:
  (1) pod paskiem białka na „Dziś" (gdy znacznik widoczny), (2) w Ustawieniach
  pod polem bilansu, **na żywo** przy zmianie wartości (znak ujemny/dodatni/
  zero → inny tekst, zero → tekst „bez dodatkowego celu białka"). Wzór:
  „Przy ujemnym bilansie zobaczysz na pasku białka dodatkowy znacznik —
  cel redukcyjny 1,2–1,6 g/kg (dla Ciebie 94–125 g): w deficycie wyższe
  białko chroni mięśnie i syci. Norma z Twojego stylu życia (62–78 g) jest
  niżej." Wariant masy: „…cel przy budowie masy 1,6–2,2 g/kg (…): nadwyżka
  bez białka to głównie tłuszcz." Liczby w gramach z wagi wygładzonej, jak
  reszta makro.

**Instrukcja dla implementującego LLM — co czytać:**

| Plik | Zakres | Po co |
|---|---|---|
| `app/services/macros.py` | 29-60 (`resolve_norms`), 80-120 (`MacroTargets`, `who_targets`), 142-160 (`coverage` — gałąź `protein`) | dodajesz `protein_goal` (zakres + rodzaj) i próg „różni się od stylu" |
| `app/resources/who_norms.json` | 20-36 (dwie grupy) | pole `protein_bulk_g_per_kg` obok `protein_cut_g_per_kg` |
| `app/services/day.py` | wywołanie `who_targets(...)` (~245) | przekaż znak bilansu z profilu |
| `app/templates/mobile.html` | 655-672 (`renderMacros`), 349-353 (pole bilansu w Ustawieniach — po punkcie „Bilans zamiast deficytu" numery się zmienią, szukaj `s-deficit`/`s-balance`) | znacznik + tekst pod paskiem; tekst na żywo w Ustawieniach |
| `tests/test_macros.py` | 55-70 (fixture z `protein_cut_g_per_kg`) | rozszerz fixture o `bulk`, dopisz testy |
| `tests/test_day_trends_services.py` | 124-136 | kontrakt „serwis == /api/day" — nowe klucze w obu |

**Nie czytaj:** `quips.py`/`quips.json` (kategoria `protein_low` liczy się
ze `status` zakresu stylu życia — **zostaje** tak; znacznik nie zmienia
statusu), `energy.py`, `balance.py`, `trends.py`, `transfer.py`, `privacy.html`
(bez zmian — nic nowego nie zbieramy).

**Kroki:**

1. `who_norms.json`: `protein_bulk_g_per_kg: [1.6, 2.2]` w obu grupach.
   `resolve_norms` przepuszcza oba pola (`protein_cut_g_per_kg`,
   `protein_bulk_g_per_kg`) do wyniku.
2. `who_targets(..., target_balance_kcal: int = 0)`: wybiera cel po znaku;
   `MacroTargets.protein_goal: MacroRange | None` i `protein_goal_kind:
   str | None` (`"cut"` / `"bulk"`). `None`, gdy bilans 0 **lub** zakres
   pokrywa się ze stylem (próg 0.05 g/kg na obu granicach).
3. `coverage()["protein"]` dostaje `goal_range_g: [lo, hi] | null`,
   `goal_kind`, `goal_pct: [pct_lo, pct_hi] | null` — pozycje znacznika
   liczone tą samą `bar_pct(...)`, którą liczy się wypełnienie paska (te same
   `b1,b2,b3`), żeby kreski trafiały w tę samą skalę. Bez tego znacznik
   będzie w złym miejscu.
4. `renderMacros`: dla białka, gdy `goal_range_g` — dwie pionowe kreski na
   `.bar` (absolutnie pozycjonowane `<i>` przy `left: goal_pct[i]%`, szerokość
   2px, kolor inny niż wypełnienie), w nawiasie po zakresie „· cel
   redukcyjny 94–125 g" / „· cel masy …", pod wierszem `<p class="muted">`
   z tekstem ze słownika `PROTEIN_GOAL_TEXT[kind]`. Słownik w **jednym**
   miejscu w `mobile.html`, używany też przez Ustawienia (krok 5).
5. Ustawienia: `<p class="muted" id="s-balance-protein-note">` pod polem
   bilansu; `oninput` pola → tekst wg znaku (ujemny → `cut`, dodatni →
   `bulk`, zero → „Bilans 0: utrzymanie wagi, bez dodatkowego celu białka.").
   Gramy w tym tekście: z `profile.weight_smoothed_kg` jeśli API profilu je
   daje, inaczej bez gramów (tylko g/kg) — **nie** dorabiaj nowego endpointu
   dla jednego zdania.
6. Testy `test_macros.py`: deficyt + „mało aktywny" → `cut` 1.2-1.6 i
   `goal_pct` rosnące; deficyt + „rekreacyjny" → `None` (pokrywa się);
   nadwyżka + „siłowy" (1.6-2.0 vs bulk 1.6-2.2) → `bulk` (górna granica różni
   się o 0.2); bilans 0 → `None`. `test_day_trends_services.py`: klucze
   w `macros.protein` zgodne serwis vs API.
7. **Statystyki** (`/usage`, honorując `scope` z punktu „Zakres statystyk"):
   KPI „cel białka widoczny" = liczba profili, dla których `protein_goal`
   jest nie-`None` (adopcja: ilu w ogóle to zobaczy — jeśli 0, funkcja jest
   martwa jak poprzednie pole); KPI „białko w celu" = % domkniętych dni
   z posiłkami, gdzie `protein_g ≥ goal_lo`, tylko dla tych profili
   (funkcjonowanie: czy znacznik cokolwiek zmienia). Liczone z `Meal` +
   `UserProfile` + `WeightLog` w `dashboard_stats`, agregat, bez per-user.
8. Wersja **Y**. Commit lokalny bez pusha. DONE.md: wpis + „nota `/prywatnosc`
   bez zmian".

## Bilans zamiast deficytu w Ustawieniach + jawny „cel dnia" (3/10)

**Zgłoszenie właściciela 2026-09-05:** „Ustawienie deficytu na 0 wydaje się
nie działać; nie rozumiem wartości «zostało do celu dnia» — co jest celem
dnia? ani spalone, ani spożyte."

**Diagnoza (zweryfikowana w kodzie):** cel dnia to `e_target = kcal_out ×
factor_kalibracji − target_deficit_kcal` (`app/services/day.py:241`), a
„zostało" to `floor50(e_target − kcal_in)` (linia 267). **Sama liczba `e_target`
nie jest nigdzie pokazana** — użytkownik widzi bilans i „zostało", ale nie
liczbę, do której to „zostało" się odnosi. Przy deficycie 0 spodziewa się
`zostało == −bilans`, a dostaje `0.97 × spalone − spożyte` zaokrąglone w dół
do 50 (współczynnik startowy 0.97 + zaokrąglenie konserwatywne) — różnica
~100-150 kcal, która wygląda jak błąd, bo nic jej nie tłumaczy. To **nie**
jest bug liczenia, tylko brak jawnego celu na ekranie. Dodatkowo pole
w Ustawieniach ma `min="0"` (`mobile.html:352`) — nadwyżka (budowa masy) jest
dziś niemożliwa do ustawienia.

**Decyzje:**

- **UI mówi „bilans", backend zostaje przy `target_deficit_kcal`.** Kolumna,
  pole API (`ProfileIn`), eksport/import (`transfer.py:56,122`), statystyki
  (`usage.py:452`) i `deficit_warning` **nie zmieniają nazwy** — rename to
  przebudowa tabeli SQLite + zgodność plików transferu, za drogo za jedno
  słowo. Konwersja **tylko w `mobile.html`**: `bilans_ui = −target_deficit_kcal`.
  Komentarz przy polu w `models.py:32` i przy konwersji w JS: „UI pokazuje
  bilans (znak odwrotny), patrz TODO/DONE «Bilans zamiast deficytu»".
- Pole „Docelowy bilans dnia [kcal]", `step=50`, `min=-1500`, `max=+1000`.
  Obok wartości **podpis na żywo**: `< 0` → „deficyt (redukcja)", `= 0` →
  „utrzymanie", `> 0` → „nadwyżka (budowa masy)" — „tycie" z zgłoszenia
  zastąpione „nadwyżką", bo neutralne i zgodne z resztą słownictwa apki
  (właściciel: możesz wrócić do „tycie", jeśli wolisz — jedna linia).
- **Jawny cel dnia na „Dziś":** nowy kafelek `cel dnia` = `round(e_target)`
  między „bilans" i „zostało"; etykieta „zostało do celu dnia" → „zostało
  dziś". Pod kafelkami jedna linia `muted`: „cel dnia = spalone 2889 ×
  kalibracja 0,97 + bilans −500 = 2302; zostało zaokrąglone w dół do 50"
  — składana z pól, które `/api/day` już zwraca (`kcal_out`,
  `calibration_factor`, `target_deficit_kcal`) + nowe `target_kcal`.
  Linia kalibracji (`renderCalibrationLine`, 618-626) zostaje, ale gdy
  `pct === 0` **nie** znika — pokazuje „kalibracja: 0%" (dziś pusta linia
  myli: nie wiadomo, czy działa).
- `deficit_warning` (`balance.py:52-58`) dostaje lustrzany warunek dla
  nadwyżki: `> 0.20 × tdee` → „Nadwyżka X kcal to > 20% wydatku — przyrost
  będzie głównie tłuszczem." Zwracany tym samym polem `deficit_warning`
  (nazwa pola zostaje).
- Kolor kafelka bilansu (`mobile.html:583`) liczy się względem
  `−target_deficit_kcal` — sprawdź, że dla nadwyżki (`target_deficit < 0`)
  klasy `pos/mid/neg` nadal znaczą „dobrze/średnio/źle"; jeśli nie, odwróć
  porównania gałęzią po znaku, nie nową funkcją.

**Instrukcja dla implementującego LLM — co czytać:**

| Plik | Zakres | Po co |
|---|---|---|
| `app/services/day.py` | 236-275 (`e_target`, `remaining_kcal`, słownik odpowiedzi) | nowe pole `target_kcal`; nic więcej |
| `app/services/balance.py` | 52-58 (`deficit_warning`) | gałąź nadwyżki |
| `app/templates/mobile.html` | 140-150 (kafelki), 349-353 (pole Ustawień), 580-590 (`setColored` bilansu/zostało), 618-626 (`renderCalibrationLine`), 1031 i 1115 (odczyt/zapis `s-deficit`) | całe UI zmiany |
| `app/routers/profile.py` | 24-34 (`ProfileIn`), 105 (`Form(500)`) | zdejmij ewentualne `ge=0`; formularz HTML (`/profile-form`) — sprawdź, czy ma osobne pole do przemianowania |
| `tests/test_balance.py` | 30-36 (`deficit_warning`) | dopisz test nadwyżki |
| `tests/test_activities_api.py` | 105-113 (wzorzec odczytu `/api/day`) | test `target_kcal == kcal_out×factor − deficit` |

**Nie czytaj:** `transfer.py`, `usage.py`, `models.py` poza jedną linią
komentarza, `quips.py` (kategoria liczona z `kcal_in / e_target` — działa
dla nadwyżki bez zmian), `trends.py`.

**Kroki:**

1. `day_report`: dodaj `"target_kcal": round(e_target)`; `deficit_warning`
   z gałęzią nadwyżki. Testy.
2. `mobile.html` Ustawienia: pole `s-balance` (zamiast `s-deficit`),
   konwersja znaku przy odczycie (1031) i zapisie (1115), podpis na żywo,
   `min/max` jak wyżej. Zachowaj `id` starych elementów tylko, jeśli coś
   innego je czyta (grep `s-deficit` — dziś dwa miejsca).
3. `mobile.html` „Dziś": kafelek `cel dnia`, etykieta „zostało dziś", linia
   z formułą, `renderCalibrationLine` pokazuje 0%.
4. `profile-form` (server-rendered fallback w `profile.py:105`): etykieta
   i konwersja znaku tak samo — jeden test, że `-300` z formularza zapisuje
   `target_deficit_kcal = 300`.
5. **Statystyki** (`/usage`, `scope`): rozkład znaku bilansu docelowego
   wśród profili — ilu na deficycie / utrzymaniu / nadwyżce (adopcja nowej
   możliwości; dziś wszyscy ≥ 0 z definicji pola); mediana wartości
   bezwzględnej. Jedna linia KPI z trzech liczb. Zdarzenie telemetrii
   `goal_save` już istnieje — nie dodawaj drugiego.
6. Wersja **Y**. Commit lokalny bez pusha. DONE.md: wpis + „nota
   `/prywatnosc` bez zmian" (to samo pole, inna prezentacja).

## Ikona krasnala przy komunikatach (2/10)

**Zgłoszenie właściciela 2026-09-05:** zniknęła ikonka krasnala przed
tekstem motywacyjnym; ma wrócić i pojawiać się przed różnymi komunikatami
stanu („Krasnal synchronizuje…", „Krasnal przygląda się talerzowi…",
„Krasnal stoi w kolejce…").

**Stan:** w `mobile.html` tekst krasnala to `<p id="quip">` (linia 141),
wypełniany `textContent` (588 i 598) — bez obrazka. W historii `mobile.html`
nie ma śladu ikony przy quipie (ikona była w usuniętym starym kliencie
`docs/` / `dashboard.html`). Dostępne grafiki: `app/static/icon-192.png`
(ikona PWA krasnala) i źródło `data/krasnal-icon-source.png` (poza repo
statycznym — właściciel ma plik). Komunikaty stanu są dziś rozrzucone:
„Synchronizuję…"/„Zsynchronizowano ✓" (695-698), „Przetwarzam kolejkę…"
(714), tekst przy szacowaniu posiłku (szukaj `estimate()` ~187 i jego
statusu), fallback „Brak danych…" (598-599).

**Decyzje:**

- Jedna mała grafika `app/static/krasnal-24.png` (24×24, przezroczyste tło,
  wycięta z `data/krasnal-icon-source.png` — **właściciel dostarcza plik**,
  jeśli LLM nie ma narzędzia do obróbki; do tego czasu użyj `icon-192.png`
  z `width:20px`).
- Jedna funkcja `krasnalSays(el, text)` w `mobile.html`: ustawia
  `innerHTML = '<img class="krasnal-ico" src="/static/krasnal-24.png"
  alt=""> ' + escape(text)` — **escape obowiązkowy**, quipy i błędy to
  tekst, nie HTML. CSS `.krasnal-ico { width:20px; height:20px;
  vertical-align:-4px; margin-right:6px }`.
- Słownik `KRASNAL_STATUS` w jednym miejscu, ton jak w `quips.json`:
  `sync: "Krasnal synchronizuje z Garminem…"`, `synced: "Krasnal wrócił
  z Garmina ✓"`, `estimating: "Krasnal przygląda się talerzowi…"`,
  `queue: "Krasnal stoi w kolejce…"`, `nodata: "Krasnal nie ma danych —
  uzupełnij profil i wagę w Ustawieniach."`. Nowe teksty stanu **tylko** tu.
- Quip motywacyjny (`rep.quip`) przez tę samą funkcję.

**Instrukcja dla implementującego LLM — co czytać:** `mobile.html` 138-142,
586-600, 690-720 oraz wynik `grep -n "textContent = \"" app/templates/mobile.html`
(wszystkie komunikaty stanu — zamień te, które są „głosem krasnala",
zostaw techniczne jak „Zapisano"). **Nie czytaj:** nic w `app/services`,
`quips.json` (teksty motywacyjne bez zmian), `pwa.py` (nowy plik statyczny
nie wymaga wpisu w manifeście; **dopisz go do listy cache w `sw.js`**, jeśli
lista jest jawna — sprawdź `grep -n "static/" app/static/sw.js`).

**Statystyki: brak** — zmiana czysto wizualna, nie ma adopcji do mierzenia
(zasada „krok Statystyki, jeśli ma sens" zastosowana świadomie: tu nie ma).

Wersja **Y** (UX w kilku sekcjach naraz). Test: `tests/test_pwa*.py` lub
istniejący test statyki — plik `krasnal-24.png` serwowany 200. Nota
`/prywatnosc` bez zmian.

## Nazwa pakietu i domena pod wydanie mobilne — WYMAGANIA.md §10.3 (1/10)

Pytanie otwarte §10.3, do rezerwacji **zanim** cokolwiek pójdzie do sklepów:
identyfikator aplikacji (np. `pl.fitkrasnal.app` albo `cc.krasnal.fit` —
zgodny z posiadaną domeną) plus decyzja, czy backend zostaje na
`fit.krasnal.cc`. Identyfikatora pakietu w Google Play **nie da się później
zmienić**: zmiana = nowa aplikacja i utrata wszystkich instalacji. Zadanie
administracyjne, bez kodu — sprawdzić dostępność w Play Console (i App Store
Connect, jeśli iOS w planie), zarezerwować, zapisać wybór tutaj oraz
w [deploy/README.md](deploy/README.md).

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
2. **Strefa czasowa użytkownika** — ✓ zrobione (23.0.0), patrz DONE.md
   „Strefa czasowa użytkownika…" (`app/services/clock.py`).
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

# Archiwum DONE — zakładka Aktywności i szlify UI (przed v21)

Pełne wpisy przeniesione z [DONE.md](../DONE.md), gdzie został indeks.
**Nie czytaj całego pliku** — wyciągnij jedną sekcję:
`awk '/^## <fragment tytułu>/,/^## /' archive/done-aktywnosci.md`

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

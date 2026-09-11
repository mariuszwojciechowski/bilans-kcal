# Archiwum DONE — multi-user, RODO, szyfrowanie, refaktory (przed v21)

Pełne wpisy przeniesione z [DONE.md](../DONE.md), gdzie został indeks.
**Nie czytaj całego pliku** — wyciągnij jedną sekcję:
`awk '/^## <fragment tytułu>/,/^## /' archive/done-multiuser-rodo.md`

---

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
[CLAUDE.md](../CLAUDE.md), „Rzeczy do NIE odtworzenia").

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

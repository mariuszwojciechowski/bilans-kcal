<!-- Plan wyniesiony z TODO.md (indeks). Po realizacji: wpis do DONE.md + archive/, ten plik usuń. -->
# Integracja z innymi źródłami spalanych kcal (fundament 6/10 + osobno per producent)

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

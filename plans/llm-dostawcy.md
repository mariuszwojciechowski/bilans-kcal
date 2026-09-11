<!-- Plan wyniesiony z TODO.md (indeks). Po realizacji: wpis do DONE.md + archive/, ten plik usuń. -->
# Dostawcy LLM: Claude w UI mobilnym + OpenAI (ChatGPT) jako trzeci backend (5/10)

**Stan (zweryfikowany 2026-09-10):** backend szacowania posiłków
(`app/services/meal_vision.py`) ma **dwa** dostawców — Gemini i Claude — wybierane
parą kluczy `gemini_key`/`anthropic_key` przekazywaną przez 3 miejsca wywołań.
Klucz Claude da się wpisać **tylko na desktopowym `/settings`**
(`settings.html:127-129`); mobilny ekran (`mobile.html:421-427`) pokazuje jedno
pole „Klucz LLM (Gemini)". OpenAI nie ma wcale. Tryb `auto` = Gemini, jeśli jest
jego klucz, inaczej Claude — użytkownik z dwoma kluczami nie ma jak wybrać.

**Decyzje (właściciel 2026-09-10):**

- Trzech dostawców: `gemini`, `claude`, `openai`. **Rejestr dostawców** w jednym
  miejscu (`meal_vision.PROVIDERS`), zamiast par kluczy w sygnaturach — dodanie
  czwartego ma być dopisaniem wpisu do rejestru + jednej funkcji `_estimate_*`.
- Nowe ustawienie **nie-sekretne** `llm_backend` ∈ {`auto`, `gemini`, `claude`,
  `openai`} per użytkownik. `auto` = pierwszy z kluczem w kolejności
  gemini → claude → openai (najtańszy pierwszy). Zmienna `FIT_KRASNAL_LLM`
  zostaje jako globalny override do developmentu.
- `LlmKeys` dostaje pole `openai`; publiczne funkcje `meal_vision` przyjmują
  **cały** `LlmKeys` + `preferred` zamiast dwu kwargów.
- **Nowy odbiorca danych = zmiana noty `/prywatnosc` + bump `PRIVACY_VERSION`**
  → wszyscy testerzy dostaną ponowną prośbę o zgodę. To świadoma cena (RODO:
  nowy odbiorca to zmiana istotna). Bump robi implementujący, w tym samym
  commicie co nota.
- Model OpenAI: `FIT_KRASNAL_OPENAI_MODEL`, domyślnie `gpt-5-mini` — **zweryfikuj
  nazwę** w dokumentacji OpenAI w dniu implementacji (krok 0); wizja + structured
  output wymagane.

**Instrukcja dla implementującego LLM — czytaj tylko to:**

| Plik | Zakres | Po co |
|---|---|---|
| `app/services/meal_vision.py` | 1-27 (docstring, importy), 68-120 (wybór backendu, API publiczne), 124-200 (`_estimate_claude`, `_estimate_gemini` — wzór dla `_estimate_openai`) | serce zmiany |
| `app/services/settings.py` | 15-30 (`LlmKeys`, `LLM_KEYS`, `SECRET_SETTING_KEYS`), 70-77 (`get_llm_keys`) | trzeci klucz + `llm_backend` |
| `app/config.py` | 55-59 | stałe modeli |
| `app/routers/settings.py` | 28-52 (strona), 81-95 (`/settings/llm`), 158-170 (`/api/settings`), 195-210 (`/api/settings/llm`) | trzeci klucz i `llm_backend` w obu formularzach |
| `app/routers/meals.py` | 48-66, 85-94 | 2 wywołania do przepięcia na `keys` |
| `app/services/meal_queue.py` | 126-137 | 1 wywołanie do przepięcia |
| `app/templates/mobile.html` | 421-427 (karta klucza), 1218-1220 (render), 1320-1336 (`saveLlmKey`) | select backendu + 3 pola |
| `app/templates/settings.html` | 120-145 (formularz + instrukcje), 171 (tekst zgody) | pole OpenAI + instrukcja + select |
| `app/templates/privacy.html` | 88-119 | akapit o OpenAI, tekst „Gemini albo Claude" |
| `app/services/usage.py` | 26-48 (`EVENTS`), ~150 (lejek: krotka kluczy LLM) | telemetria per dostawca |
| `tests/test_meal_vision.py` | całość (50 linii) | testy wyboru backendu do przepisania |
| `pyproject.toml` | 12-15 | zależność `openai` |

**Nie czytaj:** `consent.py` poza docstringiem (mechanizm zgody per wersja noty
działa bez zmian — bump `PRIVACY_VERSION` w `config.py:76` wystarczy),
`crypto.py` (szyfrowanie idzie przez `SECRET_SETTING_KEYS` — dopisz klucz do
zbioru i tyle), `transfer.py` (klucze nigdy nie wchodzą do eksportu — pilnuje
`test_consent.py::test_transfer_export_never_contains_llm_keys`, sprawdź tylko,
że nadal przechodzi), `day.py`, `energy.py`, `trends.py`, `WYMAGANIA.md`.
Przed pracą: `grep -rn "2026-09-03" tests/` — jeśli test przypina wersję noty,
zaktualizuj go razem z bumpem.

**Kroki (3 commity):**

0. **Weryfikacja API OpenAI (15 min, bez kodu):** nazwa modelu z wizją i
   structured output; wywołanie w SDK `openai` (Python): `client.responses.parse(
   model=..., input=[{"role":"user","content":[{"type":"input_image",
   "image_url": "data:<media_type>;base64,<...>"}, {"type":"input_text",
   "text": prompt}]}], instructions=SYSTEM, text_format=MealEstimate)` →
   `response.output_parsed`. Jeśli SDK ma inną sygnaturę — użyj aktualnej,
   zapisz jedno zdanie w DONE.md. Brak klucza → `MealVisionNotConfigured`
   jak u Gemini (nie polegaj na wyjątku SDK).
1. **Commit 1 — rejestr dostawców + OpenAI w backendzie (X: 24.x → 25.0.0).**
   - `settings.py`: `LlmKeys(gemini, anthropic, openai)`; `LLM_KEYS` i
     `SECRET_SETTING_KEYS` + `"openai_api_key"`; `get_llm_keys` czyta trzeci
     klucz; nowa funkcja `get_llm_backend(db, user_id) -> str` (ustawienie
     `llm_backend`, default `"auto"`, **nie** w `SECRET_SETTING_KEYS`).
   - `config.py`: `OPENAI_MODEL = os.getenv("FIT_KRASNAL_OPENAI_MODEL", "gpt-5-mini")`;
     komentarz `auto | claude | gemini | openai`.
   - `meal_vision.py`: `PROVIDERS: dict[str, Provider]` (`Provider` = dataclass:
     `label`, `key_attr` w `LlmKeys`, `env_vars`, `estimate` callable). Kolejność
     słownika = kolejność `auto`. `pick_backend(keys: LlmKeys, preferred: str =
     "auto") -> str`: override z `LLM_BACKEND` (gdy ≠ auto) > `preferred` (gdy ma
     klucz w `keys` albo env) > pierwszy z rejestru z kluczem > `"claude"` (jak
     dziś, żeby komunikat o braku klucza się nie zmienił). `llm_configured(keys,
     preferred)`, `estimate_from_photo(image_bytes, ext, note, keys, preferred)`,
     `estimate_from_text(description, keys, preferred)`. `_estimate_openai` wg
     kroku 0, zbudowany na wzór `_estimate_gemini` (klucz z argumentu albo
     `OPENAI_API_KEY` z env). Docstring modułu: trzech dostawców, rejestr.
   - Przepięcie 3 wywołań (`meals.py` ×2, `meal_queue.py` ×1) i 2 w
     `routers/settings.py` (status backendu) na `keys` + `preferred =
     settings_service.get_llm_backend(...)`.
   - `pyproject.toml`: `"openai>=1.60"`; `.env.example`: `OPENAI_API_KEY=`,
     `FIT_KRASNAL_OPENAI_MODEL=`.
   - Testy `tests/test_meal_vision.py`: przepisz 3 testy backendu na `LlmKeys`
     (auto z kluczem Gemini → gemini; auto bez Gemini z Claude → claude; auto
     tylko OpenAI → openai; `preferred="openai"` bez klucza OpenAI → spada do
     auto; override `LLM_BACKEND="claude"` wygrywa); `_estimate_openai("test")`
     bez klucza → `MealVisionNotConfigured`; rejestr ma dokładnie 3 wpisy
     i każdy ma `estimate`. Uruchom `pytest tests/test_meal_vision.py
     tests/test_consent.py tests/test_crypto.py -q -p no:warnings`.
2. **Commit 2 — UI (Y: 25.1.0).**
   - `mobile.html` karta „Szacowanie posiłków (LLM)": `<select id="s-llm-backend">`
     (auto / Gemini / Claude / ChatGPT) z `onchange` zapisującym przez
     `/api/settings/llm` `{llm_backend}`; trzy pola kluczy z własnym masked
     statusem (`s-gemini-key`, `s-anthropic-key`, `s-openai-key`) i jednym
     przyciskiem „Zapisz klucze" (wysyła tylko niepuste). Status: „backend:
     claude (wybrany)" albo „backend: gemini (auto)". `renderSettings` czyta
     `gemini_masked`, `anthropic_masked`, `openai_masked`, `llm_backend`, `backend`.
   - `routers/settings.py`: `LlmKeysIn` + `openai_api_key`, `llm_backend`
     (walidacja `Literal["auto","gemini","claude","openai"]`); `/api/settings`
     zwraca `openai_masked` i `llm_backend`; formularz `/settings/llm` analogicznie
     (+ `<select name="llm_backend">` w `settings.html`, pole OpenAI, punkt
     instrukcji „ChatGPT (płatny): platform.openai.com → API keys").
   - Testy: w `tests/test_queue_settings.py` (albo tam, gdzie testowany jest
     `/api/settings/llm` — `grep -n "settings/llm" tests/`) dopisz: zapis
     `openai_api_key` ląduje zaszyfrowany (nie plaintext w `AppSetting.value`),
     `llm_backend="openai"` zapisuje się i wraca w `/api/settings`, wartość
     spoza listy → 422.
3. **Commit 3 — nota prywatności + zgoda (Z: 25.1.1).**
   - `privacy.html:88-91`: „Google Gemini, Anthropic Claude **albo OpenAI
     (ChatGPT)**"; nowy `<li><b>OpenAI (ChatGPT API):</b>` — wg polityki API
     OpenAI dane z API **nie są używane do trenowania** domyślnie; retencja do
     30 dni na potrzeby nadzoru nadużyć; serwery w USA — z linkiem do
     `https://openai.com/policies/api-data-usage-policies` i datą sprawdzenia
     (**zweryfikuj treść polityki w dniu implementacji**, nie kopiuj tego
     zdania w ciemno).
   - `settings.html:171` i docstring `consent.py`: „(Gemini/Claude/ChatGPT)".
   - `config.py:76`: `PRIVACY_VERSION` → data wdrożenia. Skutek: wszyscy
     testerzy zobaczą ponowną prośbę o zgodę — **wpisz to w DONE.md jako
     świadomą decyzję** i daj właścicielowi jedno zdanie do ogłoszenia
     testerom (`krasnal@krasnal.cc`).
4. **Statystyki** (w commicie 1, `usage.py`):
   - `EVENTS` + `llm_ok_gemini`, `llm_ok_claude`, `llm_ok_openai`,
     `llm_err_gemini`, `llm_err_claude`, `llm_err_openai` — bump w `meals.py`
     po udanym/nieudanym `estimate_*` (nazwa backendu z `pick_backend`); w
     `meal_queue` analogicznie. Na `/usage` w sekcji „Najczęściej klikane" pojawią
     się same; dodatkowo mała tabela „LLM: dostawca → wywołania OK / błędy (30 d)"
     — funkcjonowanie każdego dostawcy osobno (czerwono, gdy błędy > 20%).
   - Lejek `with_llm_key` (`usage.py:~150`): krotka kluczy + `"openai_api_key"`;
     nowy KPI „użytkownicy per dostawca" (liczba distinct `user_id` z danym
     kluczem, agregat) — adopcja. Honoruje `scope`.
   - Testy w `tests/test_usage.py`: nowe zdarzenia są w `EVENTS`; KPI per
     dostawca liczy 1 użytkownika po zapisie klucza OpenAI.
5. **DONE.md** jeden wpis dla trzech commitów: stan przed, decyzje, wynik
   kroku 0 (nazwa modelu, sygnatura SDK), zdanie o bumpie noty i ponownej
   zgodzie. Punkt usuń z TODO. Bez pusha, bez pełnej suity.

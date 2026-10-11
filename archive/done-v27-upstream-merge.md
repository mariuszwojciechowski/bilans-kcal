# Done — scalenie z upstreamem

Najnowsze u góry.

## Scalenie z upstreamem (18 commitów, 27.0.0)

- Z upstreamu (18 commitów `a393061..26.2.5`, przyjęte jako nowe, nie kolidujące
  funkcje): prognoza doby (75% zwykłego treningu, zapis godziny prognozy),
  deduplikacja aktywności (`activity_dedup.py`), kolejka/timeouty LLM + kaskada
  modeli Gemini + `classify_error` + krotka `(estymata, model)` w zwrocie,
  UX szacowania zdjęcia w `mobile.html` (postęp/etap błędu, ekran nie gaśnie,
  karta `draft` nad „Dodaj", `msg-step`), nowe liczniki `/usage`.
- Fork zachował (zweryfikowane na VM i telefonie — wygrywają wg decyzji
  właściciela): utwardzenie publiczne, OIDC Google, ścieżkę klienta **Vertex**
  (ADC, bez kluczy) przez `gemini_client`, loader OAuth z Secret Manager, most
  natywny Capacitora w `mobile.html`. Żaden z tych plików nie zmieniony przez
  scalenie poza `meal_vision.py` i `mobile.html` (integracja ręczna).
- Konflikty: `VERSION`→27.0.0 (łączony bump, X za notę prywatności forka
  2026-09-16); `usage.EVENTS`→suma zbiorów; `meal_vision.py`→krotka+kaskada+
  timeouty upstreamu i ścieżka Vertex forka, każdy klient Gemini przez
  `gemini_client` (per-model timeout upstreamu także na ścieżce ADC — po
  przeglądzie: zawieszone wywołanie Vertex trzymałoby wątek i worker kolejki;
  zweryfikowane szacowaniem z telefonu po wdrożeniu); `mobile.html`→UX zdjęcia
  upstreamu + most natywny forka, zdjęcie natywne pomija ponowny downscale
  (Camera.getPhoto już je zmniejszył). Po przeglądzie też: `llm_configured`
  dla `vertex` wymaga projektu, `MealVisionNotConfigured`→`no_key`,
  `_estimate_gemini` bez klienta wybiera backend przez `pick_backend`.
- `tests/test_meal_vision.py`: rozpakowanie krotki `(estymata, model)` i
  `GEMINI_MODELS[0]` zamiast `GEMINI_MODEL` (konflikt semantyczny bez markera).
  ARCHITEKTURA.md: env `GEMINI_MODELS`, moduł `activity_dedup`, nowe zdarzenia.
- Pełna suita zielona: `286 passed`. Nota `/prywatnosc` bez zmian (scalenie nie
  dodaje odbiorcy danych → `PRIVACY_VERSION` 2026-09-16 bez bumpu).

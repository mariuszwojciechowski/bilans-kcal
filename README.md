# Fit Krasnal 🔺

Aplikacja wspierająca odchudzanie przez rzetelny dzienny bilans energetyczny:
**realnie zmierzony wydatek (Garmin) kontra spożycie oszacowane ze zdjęć posiłków (Claude vision)**,
z teoretycznym modelem energetycznym jako punktem odniesienia i normami makro wg WHO.

Etap 1: web app (walidacja pomysłu). Etap 2: aplikacja mobilna (Android, docelowo też iOS).
Pełne wymagania: [WYMAGANIA.md](WYMAGANIA.md).

**Publiczna instancja pilotowa:** https://fit.krasnal.cc (multi-user, wymaga
kodu zaproszenia do rejestracji; szczegóły wdrożenia w [deploy/README.md](deploy/README.md)).

**Kontakt:** [krasnal@krasnal.cc](mailto:krasnal@krasnal.cc).

## Architektura (MVP)

- **Python 3.12 + FastAPI**, SQLite, server-rendered dashboard (Jinja2)
- `app/providers/` — dostęp do danych zdrowotnych za wymiennym interfejsem
  (MVP: nieoficjalne API Garmin Connect; docelowo Health Connect / HealthKit)
- `app/services/energy.py` — BMR (Mifflin-St Jeor), NEAT z kroków, MET aktywności
- `app/services/meal_vision.py` — zdjęcie/opis posiłku → kcal + makro (Claude API)
- `app/services/macros.py` — zapotrzebowanie i pokrycie makro wg norm WHO
- `app/services/balance.py` — bilans dnia, prognozy, ostrzeżenia

## Uruchomienie

Wymagany [uv](https://docs.astral.sh/uv/) (albo własny Python ≥3.12).

```bash
uv venv --python 3.12 && uv pip install -e . --group dev
```

1. **Klucz LLM** (szacowanie posiłków) — jeden z dwóch:
   - **Gemini, darmowy tier** (zalecane do użytku prywatnego):
     klucz z https://aistudio.google.com → `export GEMINI_API_KEY=...`
   - Claude API (płatny): `export ANTHROPIC_API_KEY=sk-ant-...`

   Wybór backendu: `FIT_KRASNAL_LLM=auto|claude|gemini` (auto preferuje Gemini,
   jeśli ma klucz). Szczegóły w `.env.example`.
2. **Logowanie do Garmina** (jednorazowo, interaktywnie — obsługuje MFA):

   ```bash
   .venv/bin/python scripts/garmin_login.py
   ```

3. **Start:**

   ```bash
   .venv/bin/uvicorn app.main:app --port 8321
   ```

   Dashboard: http://localhost:8321 — przy pierwszym uruchomieniu uzupełnij profil,
   potem kliknij „Synchronizuj z Garminem".

## Testy

```bash
.venv/bin/python -m pytest
```

## Prywatność (repo jest publiczne!)

Żadne dane użytkownika nie trafiają do repozytorium:

- baza danych i zdjęcia posiłków → `data/` (w `.gitignore`),
- tokeny sesji Garmina → `~/.fit-krasnal/garth` (poza drzewem repo),
- sekrety → zmienne środowiskowe / `.env` (w `.gitignore`).

Uwaga: integracja z Garminem używa nieoficjalnej biblioteki
[garminconnect](https://github.com/cyberjunky/python-garminconnect) — działa na własnym
koncie użytkownika i może przestać działać przy zmianach po stronie Garmina.

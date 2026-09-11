# TODO — indeks zadań

Punkty do zrobienia po pilocie. Każdy jest samodzielnym zadaniem. **Plany
dłuższe niż ~60 linii leżą w `plans/`** — tutaj zostaje tytuł, złożoność
i 2–3 zdania. Zasady obowiązujące każdego implementującego (nota
`/prywatnosc`, kierunek błędu w bilansie, krok „Statystyki", commity, pełna
suita testów) są w [CLAUDE.md](CLAUDE.md) — nie powtarzamy ich tutaj.

Złożoność 1–10: **1** = wpisanie punktu zajmuje tyle co zrobienie, **3** kilka
godzin, **5** wieczór–dzień, **7** kilka dni, **10** tygodnie + rzeczy poza
kodem. Zrealizowane punkty → [DONE.md](DONE.md) (indeks) + `archive/`.

## Pochodne naprawy czerwonego CI z 2026-09-06

Hotfix zrobiony (DONE.md „Testy: «dziś» ze strefy użytkownika…"); zostało:

- **`date.today()` poza `clock`** (2/10): `services/calibration.py:117,208,305`
  (na VM bez strefy = UTC, więc 00:00–02:00 CEST liczy zły dzień),
  `routers/settings.py:162`, `routers/profile.py:45` (tylko rok — niegroźne).
  Przepuścić przez `clock.user_today(profile)`; `usage.py` zostaje na dniu
  serwera (świadomie — statystyki admina).
- **Strażnik w testach** (1/10): test grepujący `tests/*.py` (poza
  `test_timezone.py`, `conftest.py`) pod `date.today()` w plikach z
  `TestClient` → „użyj `app_today()`". Tani, zamyka klasę awarii na stałe.
- **Deterministyczny zegar w testach** (4/10): autouse fixture zamrażająca
  czas przez `clock.now_utc()` po przepięciu `sync`/`calibration`/`usage`.

## Braki względem WYMAGANIA.md (audyt 2026-09-03)

Moduły M1–M11 zrobione. Otwarte tylko trzy wymogi, każdy ma punkt niżej:
**8.3** prawo do usunięcia (dziś mailem — nota `/prywatnosc` mówi o tym wprost),
**§10.3** nazwa pakietu/domena mobilna, **Etap 2** aplikacja mobilna.
§10.1 (retencja zdjęć) rozstrzygnięte: zdjęcie kasowane po oszacowaniu, w
kolejce max 21 dni. Odstępstwa świadome, nie braki: rok urodzenia zamiast
pełnej daty, ręczny wpis wagi i kroków w mobile (od D3), wycofana paczka PWA.
Nie dopisuj drugiego planu na wymóg, który ma już punkt — rozjadą się.

## Dostawcy LLM: Claude w UI mobilnym + OpenAI jako trzeci backend (5/10)

→ [plans/llm-dostawcy.md](plans/llm-dostawcy.md). Rejestr dostawców w
`meal_vision.PROVIDERS`, ustawienie `llm_backend` per user, klucz OpenAI.
Uwaga: nowy odbiorca danych = bump `PRIVACY_VERSION` i ponowna zgoda testerów.

## Integracja z innymi źródłami spalanych kcal (fundament 6/10 + per producent)

→ [plans/zrodla-kcal.md](plans/zrodla-kcal.md). Wspólny fundament (rejestr
źródeł, klasy *pull* i *push*, jedno aktywne źródło totali) + niezależne
części per producent: Polar, Fitbit/Google, Whoop, Oura, Apple, Health
Connect, dodatki (Withings). Zanim cokolwiek zaczniesz — ankieta wśród
testerów, kto co nosi; API producentów weryfikuj na starcie każdej części.

## „Usuń moje dane i konto" w Ustawieniach (6/10)

→ [plans/usun-konto.md](plans/usun-konto.md). Wymóg WYMAGANIA.md 8.3 i warunek
wyjścia pilota poza znajomych. Soft-delete z oknem odzyskania: konto 7 dni,
historia 3 dni; kasujemy wiersze naprawdę, a kopię zrzucamy w formacie
transferu (odzysk = `import_payload`). Plan wchłonął dwa wcześniejsze punkty
listy (kasowanie konta, czyszczenie historii) — nie implementuj ich osobno.

## Aplikacja mobilna (Etap 2) — Flutter (10/10)

→ [plans/mobile-flutter.md](plans/mobile-flutter.md). Nie jest planem
implementacji, tylko listą warunków wejścia (token urządzenia zamiast
ciasteczka, Health Connect/HealthKit, kasowanie konta, nazwa pakietu,
formularze sklepowe). Dopóki pilot działa na `/mobile` jako PWA, nie jest
na ścieżce krytycznej.

## Prawdziwe „zapomniałem hasła" (mailem) (8/10)

Link resetu na e-mail: tabela tokenów, szablon maila, wysyłka (Gmail SMTP
relay albo usługa), SPF/DKIM na `krasnal.cc`, test że nie ląduje w spamie.
Większość pracy poza kodem appki.

## Zmiana hasła z poziomu Ustawień (2/10)

Karta w `/settings` (stare / nowe / powtórz) + `POST /settings/password` na
`auth.verify_password` i `auth.hash_password`, wzorzec błędów jak w rejestracji.

## Skrypt na serwerze do resetu hasła (1/10)

`scripts/reset_password.py <email>` wzorem `scripts/adopt_local_user.py` —
pyta o hasło w terminalu (żeby nie trafiło do historii bash). Dla testera,
który zapomni hasła, dopóki nie ma resetu mailem.

## Nazwa pakietu i domena pod wydanie mobilne (1/10) — WYMAGANIA.md §10.3

Zadanie administracyjne, bez kodu: identyfikator aplikacji (np.
`pl.fitkrasnal.app` / `cc.krasnal.fit`) do rezerwacji **zanim** cokolwiek
pójdzie do sklepów — w Google Play nie da się go później zmienić. Wybór
zapisz tutaj i w [deploy/README.md](deploy/README.md).

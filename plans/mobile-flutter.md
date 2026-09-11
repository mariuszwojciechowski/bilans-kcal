<!-- Plan wyniesiony z TODO.md (indeks). Po realizacji: wpis do DONE.md + archive/, ten plik usuń. -->
# Aplikacja mobilna (Etap 2) — Flutter — WYMAGANIA.md 8.2 / D7 (10/10)

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

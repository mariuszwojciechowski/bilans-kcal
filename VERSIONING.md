# Wersjonowanie (vX.Y.Z)

Ten dokument opisuje zasady wersjonowania aplikacji. **Każdy, kto (człowiek czy LLM)
wprowadza zmianę w kodzie, musi podnieść wersję zgodnie z poniższymi regułami** —
to część definicji "done" dla każdej zmiany, nie osobny krok do pominięcia.

## Gdzie żyje wersja

Jedyne źródło prawdy: plik [VERSION](VERSION) w korzeniu repo, format `X.Y.Z`
(bez prefiksu `v`, bez znaku nowej linii poza jednym `\n` na końcu).

`app/config.py` czyta ten plik do stałej `APP_VERSION`, router `dashboard.py`
przekazuje ją do szablonu `mobile.html` jako `app_version`, a JS wypisuje ją
pod datą w navbarze (`#hdr-date`) jako `vX.Y.Z`.

Żeby podnieść wersję: **edytuj tylko plik `VERSION`.** Nie trzeba nic więcej
zmieniać w kodzie.

## Trzy poziomy: X.Y.Z

### Z — patch (naprawy, poprawki w ramach sekcji)
Podnoś Z, gdy zmiana to:
- naprawa istniejącej funkcjonalności (bugfix),
- poprawka UI/UX w ramach istniejącej sekcji/karty,
- drobna zmiana treści, walidacji, komunikatu błędu,
- zmiana, która nie zmienia zachowania funkcji, tylko je koryguje.

**Ważne:** jeśli w ramach jednej sesji/PR robisz kilka niezależnych poprawek
w różnych sekcjach na raz (np. fix w "Dodaj posiłek" + fix w "Trendy"), **każda
z nich osobno podnosi Z** — nie łącz ich w jeden bump. Czyli 3 niezależne
poprawki w jednym PR = Z rośnie o 3 (np. 1.2.5 → 1.2.8), a nie o 1.

### Y — minor (zmiany wewnątrz taba/funkcjonalności)
Podnoś Y (i zeruj Z), gdy zmiana to:
- przenoszenie/reorganizacja sekcji w ramach tego samego taba,
- zmiana zachowania istniejącej funkcjonalności (nie tylko naprawa, ale nowy
  sposób działania — np. inny sort, inny domyślny widok, nowe pole w
  istniejącym formularzu),
- zauważalna zmiana UX w obrębie taba, która nie jest tylko kosmetyką.

### X — major (struktura aplikacji, nowe funkcjonalności, kluczowe zmiany)
Podnoś X (i zeruj Y, Z), gdy zmiana to:
- zmiana treści noty prywatności (`/prywatnosc`) — **uwaga:** to osobny,
  niezależny licznik `PRIVACY_VERSION` w `app/config.py`, ale sama zmiana
  noty jest też na tyle istotna, że bumpuje X aplikacji,
  patrz [CLAUDE.md](CLAUDE.md),
- dodanie nowego taba/widoku głównego,
- przenoszenie sekcji między tabami,
  ważna zmiana logiki działania aplikacji (np. sposobu liczenia bilansu,
  TDEE, sync z Garminem),
- dodanie nowej funkcjonalności (nie poprawka istniejącej — coś, czego
  wcześniej nie było),
- kluczowa zmiana istniejącej funkcjonalności (przeprojektowanie, nie
  rozszerzenie).

## Przykłady

| Zmiana | Bump |
|---|---|
| Fix: przycisk "Zapisz posiłek" nie czyścił formularza | Z |
| Fix w "Dodaj posiłek" + fix w "Trendy" w jednym PR | Z + Z (dwa bumpy) |
| Zmiana domyślnego sortowania "Moje posiłki" | Y |
| Przeniesienie sekcji "Makroskładniki" nad "Posiłki" w tabie Dziś | Y |
| Nowy tab "Cele" | X |
| Przeniesienie sekcji "Aktywności" z taba Dziś do osobnego taba | X |
| Zmiana treści `/prywatnosc` | X (+ bump `PRIVACY_VERSION`) |
| Zmiana sposobu liczenia TDEE | X |

## Dla LLM-a wykonującego zmianę

1. Zaimplementuj zmianę.
2. Zdecyduj, który poziom bumpować, wg tabeli/zasad powyżej. W razie wątpliwości
   między dwoma poziomami — wybierz wyższy.
3. Jeśli w jednej sesji robisz kilka niezależnych poprawek patch (Z), policz
   je osobno i podnieś Z o tyle, ile ich jest.
4. Zaktualizuj plik `VERSION` (jedna linia, `X.Y.Z\n`).
5. Nie zmieniaj nic innego — reszta (config, template, navbar) czyta ten plik
   automatycznie.

# Done — konto: hasła (27.3.0–27.4.0)

Najnowsze u góry.

## Zmiana hasła w widoku /mobile (27.4.0)

- Pierwsza funkcja pod nową zasadą „rozwijamy tylko /mobile" (CLAUDE.md,
  decyzja właściciela 2026-10-15): karta „Hasło" w Ustawieniach mobilnych,
- `POST /api/settings/password` (JSON, błędy 400 z `detail`) — walidacja
  wspólna z formularzem `/settings/password` przez `_password_change_problem`
  / `_apply_password_change`, więc oba UI nie mogą się rozjechać,
- `/api/settings` dokłada `has_password` i `password_enabled` — mobile wie,
  czy pokazać pole „obecne hasło" (konto z Google: „Ustaw hasło") i czy
  karta w ogóle istnieje (tryb `oidc`: znika, POST → 404).

## Zmiana hasła w Ustawieniach (27.3.0)

- Karta w `/settings` (obecne / nowe / powtórz) → `POST /settings/password`
  na `auth.verify_password` + `auth.hash_password`; błędy jak w rejestracji
  (`bad_password`, `mismatch`, `short`, `long`) mapowane na polskie opisy
  na banerze, osobny słownik `PASSWORD_ERRORS` w `routers/settings.py`.
- Konto założone przez Google (bez hasła) widzi formularz „Ustaw hasło" —
  bez pola obecnego. W trybie `FIT_KRASNAL_AUTH=oidc` karta znika,
  POST → 404 (jak POST `/login`).
- Statystyki: zdarzenie `password_change` w `usage.EVENTS` — adopcję widać
  na `/usage`; test `test_password_change_bumps_usage`.
- Sesja pozostaje ważna po zmianie (celowo — zmienia sam zalogowany
  właściciel, to nie reakcja na kradzież).

## Skrypt na serwerze do resetu hasła (27.3.0)

- `scripts/reset_password.py <email>` wzorem `scripts/adopt_local_user.py`;
  nowe hasło pyta przez `getpass` (×2), więc nie zostaje w historii basha
  ani w argumentach procesu (`ps`).
- Walidacja przez `auth.password_problem`, potem zwykły
  `user.password_hash = auth.hash_password(...)` + commit.
- Mostek do czasu „prawdziwego" resetu mailem (TODO); działa lokalnie na VM
  z uprawnieniami admina, więc bez throttla.

# Done — konto: hasła (27.3.0–28.0.0)

Najnowsze u góry.

## „Nie pamiętam hasła" — reset mailem przez Resend (28.0.0)

- Decyzja właściciela 2026-10-15: kanał **Resend** (darmowy tier 100
  maili/dzień), nadawca `noreply@krasnal.cc`, region eu-west-1 —
  odpadły Gmail SMTP („via gmail.com") i Amazon SES (IAM/SNS na e2-micro).
- Trasy przy `/login` (server-rendered — przed sesją nie ma `/mobile`):
  formularz → `POST /password-reset/request` (anti-enumeracja: zawsze
  `?sent=1`), `GET/POST /password-reset/{token}`; w trybie `oidc` → 404.
- Token 32 B w bazie tylko jako SHA-256, TTL 60 min, jednorazowy atomowym
  UPDATE-em, throttle 3 żądania/h na e-mail; `peek` nie zużywa (skanery
  linków), reset unieważnia wszystkie tokeny usera i zdejmuje lockout login.
- Nota `/prywatnosc`: nowy odbiorca Resend + retencja tokenów —
  `PRIVACY_VERSION` 2026-10-15 (ponowna zgoda testerów); statystyki
  `password_reset_request` / `password_reset_done` na `/usage`.
- Runbook konta Resend (DNS, API key, definicja „gotowe") przeniesiony do
  [deploy/README.md](../deploy/README.md) „Wysyłka maili"; 13 testów
  w `tests/test_password_reset.py`. **Klucz wsadzony ręcznie w env na VM —
  przy odtworzeniu VM z Terraforma trzeba wpisać ponownie** (docelowo
  Secret Manager jak OAuth).

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

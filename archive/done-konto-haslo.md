# Done — konto: hasła (27.3.0–28.0.4)

Najnowsze u góry.

## Mail resetu: krasnalowe akcenty (28.0.2–28.0.4)

- Poprawki po oględzie realnego maila przez właściciela: „nowe hasło"
  (było „nowy"), podpis „Serdecznie pozdrawiam," + TAB + „Fit Krasnal".
- „Ikona krasnala" w plain tekście = jednolinijkowe kaomoji — ASCII-art
  rozjeżdża proporcjonalna czcionka Gmaila; HTML odpada świadomie
  (dostarczalność i filtry antyspamowe > szata graficzna).
- Losowa grzeczna „krasnalowa mądrość" z osobnej listy w `mail.py`
  (quips.json zostaje niecenzuralnym korpusem panelu „Dodaj posiłek");
  `tests/test_mail.py` pilnuje kształtu maila i grzeczności cytatów.

## Klucz API Resend w Secret Manager (28.0.1)

- Zamknięcie długu z 28.0.0 (klucz ręcznie w env na VM): kontener
  `fit-krasnal-resend-key` + `secretAccessor` dla konta VM w Terraformie
  (`resend_secret_name`), wersję z jedną linią `FIT_KRASNAL_RESEND_KEY=…`
  dodaje operator w konsoli GCP — wartość nigdy nie trafia do repo, stanu
  Terraforma ani na terminal.
- `deploy/load-oauth-secret.sh` uogólniony na dowolne klucze env (argumenty;
  bez nich — domyślna para OAuth, więc komendy z outputów terraform
  i instalacja na VM bez zmian). Alternacja BRE zachowana jak w oryginale:
  zwykły `|` w BRE GNU grepa jest literalny i dublowałby linie
  przy ponownym ładowaniu.
- Na VM: `load-oauth-secret fit-krasnal-resend-key FIT_KRASNAL_RESEND_KEY`
  — podmienia też ręcznie wpisaną linię (idempotentny); po odtworzeniu VM
  z Terraforma wystarczy output `resend_secret_load_command`.
- Przetestowany atrapami gcloud/systemctl: ładowanie, idempotencja, rotacja,
  odrzucenia (nadmiarowa linia, zły charset, duplikat klucza).
- Na produkcji (2026-10-15): API Secret Manager świeżo włączony, sekret
  i `secretAccessor` utworzone gcloud-em (Terraform nigdy nie aplikowany —
  komendy import w deploy/README), scope VM →`cloud-platform` (stop/start
  za zgodą właściciela), wartość przeniesiona rurą VM→Secret Manager bez
  wyświetlania.

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

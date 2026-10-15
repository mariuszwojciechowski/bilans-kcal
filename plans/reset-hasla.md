# „Nie pamiętam hasła" — reset mailem przez Resend

## Decyzja (właściciel, 2026-10-15)

- **Kanał: Resend** (darmowy tier 100 maili/dzień — przy pilotach zapas),
  nadawca `noreply@krasnal.cc`. Odpadły: Gmail SMTP (niski koszt, ale „via
  gmail.com", hasło aplikacji, brak obsługi odbić), Amazon SES (IAM/SNS na
  e2-micro nieopłacalne przy tej skali).
- Strony resetu są **server-rendered przy `/login`** — przed zalogowaniem nie
  istnieje `/mobile`, więc to jedyny słuszny wyjątek od zasady „rozwijamy
  tylko /mobile".

## Część poza kodem (właściciel, blokuje wdrożenie)

1. Konto Resend + weryfikacja domeny `krasnal.cc`: rekordy DNS pokazane
   w dashboardzie (SPF, DKIM `resend._domainkey`); rozważić DMARC `p=none`.
2. API key → **Secret Manager**, na VM przez istniejący wzór
   (`deploy/load-oauth-secret.sh` → `/etc/fit-krasnal/env`).
3. Deliverability: mail-tester.com + ręcznie Gmail/Outlook (spam?) na
   adres z domeny, nie z Gmaila.

## Część kodowa (bez konta Resend — bez klucza sender nie wysyła,
a loguje link resetu; testy lecą na mocku)

1. **`services/mail.py`** — cienki klient Resend: `httpx.post` na
   `https://api.resend.com/emails` (httpx już w zależnościach), wolny od
   FastAPI (reguła warstwy services). Config: `FIT_KRASNAL_RESEND_KEY`,
   `FIT_KRASNAL_MAIL_FROM` (default `noreply@krasnal.cc`).
2. **Tabela `PasswordResetToken`**: `user_id`, `token_hash` (SHA-256 tokenu —
   wyciek bazy **nie** daje działających linków), `expires_at`, `used_at`,
   `created_at`. Migracja addytywna w `db.py:_migrate()`, niczego nie trzeba
   backfillować.
3. **`services/password_reset.py`** — token 32 B `secrets.token_urlsafe`,
   **TTL 60 min**, **jednorazowy** (`used_at`), throttle max 3 żądania/h na
   e-mail (w pamięci procesu — legalne,`workers > 1` zakazane per CLAUDE.md),
   sprzątanie wygasłych. Nie logujemy tokenu w plaintext.
4. **Routery — w `routers/auth.py` (naturalne sąsiedztwo `/login`):**
   - `GET /password-reset` — formularz „podaj e-mail",
   - `POST /password-reset/request` — **anti-enumeracja**: odpowiedź zawsze
     identyczna („jeśli konto istnieje, wysłaliśmy link"); mail z linkiem
     `GET /password-reset/{token}` tylko dla istniejącego konta,
   - `GET /password-reset/{token}` + `POST /password-reset/{token}` —
     nowe hasło (walidacja `auth.password_problem`, hash, unieważnienie
     **wszystkich** tokenów usera po sukcesie),
   - `login.html`: link „Nie pamiętasz hasła?".
5. **Nota prywatności** — nowy odbiorca: Resend (przetwarza e-mail i treść
   maila transakcyjnego). Aktualizacja `privacy.html` w tym samym zadaniu;
   przy wdrożeniu decyzja o bumpie `PRIVACY_VERSION` (nadawca zależy od
   env, na produkcji domyślnie Resend — liczy się stan produkcyjny).
6. **Statystyki**: `password_reset_request`, `password_reset_done`
   w `usage.EVENTS` — na `/usage` adopcja (ile resetów) i funkcjonowanie
   (ile zakończonych sukcesem).
7. **Testy** (`tests/test_password_reset.py`): request istniejące/nieistniejące
   konto (identyczna odpowiedź, druga bez wysyłki), konsumpcja tokenu
   (jednorazowość), TTL wygaśnięcie, throttle, sukces → hasło działa,
   konto Google (bez hasła) — reset ustawia pierwsze hasło, tryb `oidc` → 404.

## Okazałe ograniczenia

- e2-micro: wyłącznie HTTPS 443 do `api.resend.com` — żadnych portów SMTP.
- Mail zawsze PL, bez śledzenia otwarć (nie włączamy open-trackingu Resend).
- Reset nie wylogowuje innych sesji (zmiana z poziomu konta tak samo nie
  robi tego dziś).

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

## Runbook: konto Resend i DNS (dla właściciela, poza kodem)

**Krok 0 — konto.** https://resend.com → „Sign up" (e-mail albo GitHub).
Free tier: 100 maili/dzień, 3000/mies. — przy pilotach zapas. Kreditówka
nie jest wymagana na start.

**Krok 1 — domena.** Dashboard → „Domains" → „Add Domain" → `krasnal.cc`
(jeśli pyta o region: **eu-west-1**, Irlandia — dane w EU). Resend wypisze
rekordy DNS do dodania w strefie `krasnal.cc` (tam, gdzie trzymasz DNS —
registrar/Cloudflare):

- SPF: TXT na `krasnal.cc`, wartość w rodzaju `v=spf1 include:resend.com ~all`,
- DKIM: TXT na `resend._domainkey.krasnal.cc`, długi klucz `p=MII…`,
- ewentualnie DMARC: TXT na `_dmarc.krasnal.cc`, `v=DMARC1; p=none`.

**Wklejaj dokładnie to, co pokazuje dashboard** — wartości są per konto
i Resend bywa zmieniał format (kiedyś `include:amazonses.com`). Wróć
do dashboardu → „Verify" — zielony status zwykle w ~15 min.

**Krok 2 — API key.** Dashboard → „API Keys" → „Create API Key" →
nazwa `fit-krasnal-prod`, uprawnienia **Sending access** (nie full).
Kopiuj `re_…` od razu — pokaże się tylko raz. Klucz nigdy nie idzie do
repo, commitów ani czatu — tylko do Secret Managera.

**Krok 3 — test ręczny (zanim cokolwiek ruszy w appce).** Z dowolnej
maszyny z `curl`:

```bash
curl -X POST 'https://api.resend.com/emails' \
  -H 'Authorization: Bearer re_TWOJ_KLUCZ' \
  -H 'Content-Type: application/json' \
  -d '{"from":"Fit Krasnal <noreply@krasnal.cc>","to":["TWOJ@EMAIL"],
       "subject":"Test Resend","text":"Test wysylki resetu hasla z krasnal.cc"}'
```

- 200 + `"id":"…"` = klucz i domena działają,
- w Gmailu: „Pokaż oryginał" → mają być `SPF: PASS` i `DKIM: PASS`
  **dla krasnal.cc** — bez tego nie włączamy,
- punktowe sprawdzenie antyspamowe: wejdź na mail-tester.com, skopiuj
  pokazany tam jednorazowy adres, wyślij na niego drugi mail — cel to 9–10/10.

**Krok 4 — klucz na produkcję.** Do GCP (przeżyje odtworzenie VM):

```bash
printf 'FIT_KRASNAL_RESEND_KEY=re_TWOJ_KLUCZ' \
  | gcloud secrets create fit-krasnal-resend --data-file=-
```

Na VM dziś najszybciej ręcznie (plik jest 0600 root, tam już leżą inne
sekrety), potem restart:

```bash
echo 'FIT_KRASNAL_RESEND_KEY=re_TWOJ_KLUCZ' >> /etc/fit-krasnal/env
systemctl restart fit-krasnal
```

Docelowo (zadanie implementacji): rozszerzyć `deploy/load-oauth-secret.sh`
o ten sekret, żeby leciał z Secret Managera jak OAuth, nie ręcznie.

**Krok 5 — definicja „gotowe" po stronie ownera:** domena „Verified"
w dashboardzie + SPF/DKIM PASS w Gmailu + mail-tester ≥9. Wtedy mówimy
o włączeniu wysyłki na produkcji (razem z notą prywatności).

## Znane ograniczenia

- e2-micro: wyłącznie HTTPS 443 do `api.resend.com` — żadnych portów SMTP.
- Mail zawsze PL, bez śledzenia otwarć (nie włączamy open-trackingu Resend).
- Reset nie wylogowuje innych sesji (zmiana z poziomu konta tak samo nie
  robi tego dziś).

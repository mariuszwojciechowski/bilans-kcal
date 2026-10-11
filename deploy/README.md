# Wdrożenie Fit Krasnal (GCP + GitHub Actions)

Docelowo: `fit.krasnal.cc` → Caddy (HTTPS) → uvicorn na `127.0.0.1:8321`.
Deploy uruchamia się automatycznie po pushu na `main`.

## Rozkład na maszynie

| Ścieżka | Co to |
|---|---|
| `/opt/fit-krasnal` | kod (klon repo), właściciel `fitkrasnal` |
| `/var/lib/fit-krasnal` | **dane**: baza SQLite, zdjęcia, tokeny Garmina |
| `/etc/fit-krasnal/env` | sekrety (`root:fitkrasnal`, `640`) — poza repo |
| `/etc/systemd/system/fit-krasnal.service` | usługa |
| `/etc/systemd/system/fit-krasnal-queue.{service,timer}` | timer: przetwarzanie kolejki posiłków co minutę |

Dane leżą **poza katalogiem repo**, więc `git reset --hard` przy deployu ich nie rusza.

## 0. Infrastruktura GCP (Terraform)

Katalog `deploy/terraform/` opisuje całą infrastrukturę: włączenie API,
konto usługi VM (tylko `roles/aiplatform.user` + `roles/logging.logWriter`,
bez kluczy), regionalny adres statyczny (tier STANDARD), reguły firewalla
(80/443 z internetu, 22 **tylko** z zakresu IAP `35.235.240.0/20`) i VM
`e2-micro` (free tier w `us-central1`, 30 GB pd-standard, Debian 12,
Shielded VM, OS Login). **Prawdziwe wartości (`terraform.tfvars`), stan i
notatki (`NOTES.local.md`) leżą obok konfiguracji w `deploy/terraform/` i są
w `.gitignore`** — nigdy nie trafiają do repo:

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars      # uzupełnij
terraform init -backend-config="path=terraform.tfstate"
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Jeśli adres statyczny albo API istniały wcześniej (ręcznie), zaimportuj je
przed `apply`, żeby stan się zgadzał:

```bash
terraform import -var-file=... 'google_project_service.apis["compute.googleapis.com"]' <project>/compute.googleapis.com
terraform import -var-file=... google_compute_address.ip projects/<project>/regions/<region>/addresses/<nazwa>
# sekret OAuth utworzony wcześniej ręcznie (gcloud secrets create …) i jego binding:
terraform import -var-file=... google_secret_manager_secret.oauth projects/<project>/secrets/fit-krasnal-oauth
terraform import -var-file=... google_secret_manager_secret_iam_member.oauth_vm_accessor \
  "projects/<project>/secrets/fit-krasnal-oauth roles/secretmanager.secretAccessor serviceAccount:<sa-email>"
```

SSH wyłącznie tunelem IAP (output `ssh_command`):

```bash
gcloud compute ssh fit-krasnal --project <project> --zone <zone> --tunnel-through-iap
```

Uwaga: domyślna VPC ma regułę `default-allow-ssh` (22 z `0.0.0.0/0`, bez
tagów), która obejmuje **każdą** VM w sieci — dopóki istnieje, port 22 jest
widoczny z internetu mimo reguły IAP. Terraform jej nie rusza; usuń ją
świadomie (`gcloud compute firewall-rules delete default-allow-ssh`).

Ekran zgody OAuth i klient OAuth (Web application, origin
`https://<FIT_DOMAIN>`, redirect `https://<FIT_DOMAIN>/auth/google/callback`)
powstają ręcznie w Console i nie są w Terraformie.

### Allowlista logowania w metadanych VM

Lista e-maili dopuszczonych do logowania (`FIT_KRASNAL_ALLOWED_EMAILS`)
**nie** mieszka w `/etc/fit-krasnal/env`, tylko w metadanych instancji
(klucz `fit-krasnal-allowed-emails`, zmienna `allowed_emails` w Terraformie).
Unit `fit-krasnal.service` woła przed startem `deploy/fetch-metadata-env.sh`,
który przepisuje ją do `/run/fit-krasnal/env` (drugi `EnvironmentFile`,
nadpisuje `/etc`). Dodanie testera bez Terraforma:

```bash
gcloud compute instances add-metadata fit-krasnal --zone <zone> \
  --metadata fit-krasnal-allowed-emails=a@example.com,b@example.com
gcloud compute ssh fit-krasnal --zone <zone> --tunnel-through-iap -- sudo systemctl restart fit-krasnal
```

Potem dopisz ten sam e-mail do `allowed_emails` w tfvars, inaczej następny
`terraform plan` pokaże dryf i `apply` go cofnie.

### Bucket na APK

`google_storage_bucket.apk` (domyślnie `fit-krasnal-apk`): prywatny,
`uniform_bucket_level_access`, `public_access_prevention = enforced`,
`roles/storage.objectViewer` tylko dla kont z `apk_viewers` — nic więcej.
Wgranie i link do pobrania (wymaga zalogowania kontem z listy):

```bash
gcloud storage cp android-app/dist/fit-krasnal-debug.apk gs://<bucket>/fit-krasnal.apk
# https://storage.cloud.google.com/<bucket>/fit-krasnal.apk
```

## 1. Bootstrap maszyny (raz)

Po SSH na VM (skrypt jest idempotentny, można go powtarzać):

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/bilans-kcal/main/deploy/setup-vm.sh \
  | sudo FIT_DOMAIN=fit.example.com FIT_AUTH=oidc FIT_ALLOWED_EMAILS=you@example.com \
         FIT_LLM=vertex FIT_VERTEX_PROJECT=<project> FIT_VERTEX_LOCATION=europe-west1 bash
```

Parametry: `FIT_DOMAIN` (wymagane), `FIT_REPO_URL` (domyślnie fork
`bobert-bag-bounty/bilans-kcal`), `FIT_BRANCH`, `FIT_PYTHON` (domyślnie 3.12),
oraz opcjonalne `FIT_AUTH`, `FIT_ALLOWED_EMAILS`, `FIT_LLM`,
`FIT_VERTEX_PROJECT`, `FIT_VERTEX_LOCATION`, które przy pierwszym uruchomieniu
trafiają do `/etc/fit-krasnal/env`.

Skrypt: instaluje pakiety (w tym `caddy` i `unattended-upgrades`), zakłada
użytkownika `fitkrasnal`, klonuje repo, instaluje Pythona ≥ 3.12 przez `uv`
do `/opt/uv-python` (poza `/home`, bo usługa ma `ProtectHome=true`), robi
venv, generuje `FIT_KRASNAL_SECRET_KEY`, `FIT_KRASNAL_ENC_KEY`
i `FIT_KRASNAL_USAGE_SALT`, pisze `/etc/caddy/Caddyfile` (HTTPS z Let's
Encrypt dla `FIT_DOMAIN`, `reverse_proxy 127.0.0.1:8321`, nagłówek `Server`
usunięty, bez rate-limitu — limituje aplikacja), wstawia usługę systemd
i wąską regułę sudo (CI może tylko restartować tę jedną usługę), a także timer
`fit-krasnal-queue.timer`, który co minutę woła `scripts/process_meal_queue.py`
(patrz `app/services/meal_queue.py`).

Trzy zmienne, których brak boli inaczej: bez `FIT_KRASNAL_SECRET_KEY` (własnego)
i `FIT_KRASNAL_ENC_KEY` proces **nie wstanie** (świadomie — lepiej awaria niż ciche
szyfrowanie kluczem deweloperskim). Bez `FIT_KRASNAL_USAGE_SALT` wstanie, ale
statystyki użycia nie zapiszą ani jednego zdarzenia i `/usage` zostanie puste —
w logu jest wtedy ostrzeżenie przy starcie. Sól jest **stała**: jej zmiana zrywa
ciągłość statystyk (ten sam użytkownik dostaje nowy pseudonim).

Potem uzupełnij logowanie: dla `FIT_KRASNAL_AUTH=oidc` wpisz
`FIT_KRASNAL_GOOGLE_CLIENT_ID/SECRET`, dla `password` — kod zaproszenia:

```bash
sudo nano /etc/fit-krasnal/env
sudo systemctl restart fit-krasnal
```

## 2. Klucz SSH dla GitHub Actions

> **W wariancie Terraform (sekcja 0) ten krok nie ma zastosowania.** Firewall
> dopuszcza port 22 **tylko** z zakresu IAP (`35.235.240.0/20`) — o ile
> usunięto regułę `default-allow-ssh` (sekcja 0) — więc runner GitHub Actions
> nie dosięgnie VM i automatyczny deploy przez SSH nie zadziała.
> Zamiast niego wdrażaj ręcznie tunelem IAP:
> `gcloud compute ssh <vm> --tunnel-through-iap --zone <zone> --command 'bash /opt/fit-krasnal/deploy/deploy.sh'`.
> Otwarcie 22 dla GitHuba (dodatkowa reguła firewalla na IP runnerów i klucz
> jak niżej) to **świadoma decyzja**, nie stan domyślny. Poniższy podrozdział
> opisuje właśnie ten wariant z otwartym 22.

**Na swoim komputerze** (nie na VM) wygeneruj parę tylko do deployu:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/fit-krasnal-deploy -N "" -C "github-actions-deploy"
```

Klucz **publiczny** na VM:

```bash
sudo mkdir -p /home/fitkrasnal/.ssh
sudo tee -a /home/fitkrasnal/.ssh/authorized_keys < ~/.ssh/fit-krasnal-deploy.pub
sudo chown -R fitkrasnal:fitkrasnal /home/fitkrasnal/.ssh
sudo chmod 700 /home/fitkrasnal/.ssh && sudo chmod 600 /home/fitkrasnal/.ssh/authorized_keys
```

Klucz **prywatny** do GitHuba: *Settings → Secrets and variables → Actions → New secret*

| Secret | Wartość |
|---|---|
| `DEPLOY_HOST` | statyczne IP maszyny |
| `DEPLOY_USER` | `fitkrasnal` |
| `DEPLOY_SSH_KEY` | zawartość `~/.ssh/fit-krasnal-deploy` (cały plik, z nagłówkiem i stopką) |

Klucza prywatnego nie trzymaj nigdzie indziej — w razie wycieku usuń wpis
z `authorized_keys` na VM i wygeneruj nową parę.

## 3. Caddy

`setup-vm.sh` pisze minimalny `/etc/caddy/Caddyfile` dla `FIT_DOMAIN`. Wariant
z domeną główną (landing) plus aplikacją wygląda tak:

```
krasnal.cc {
	root * /opt/fit-krasnal/deploy/landing
	file_server
}

fit.krasnal.cc {
	basic_auth {
		krasnal <HASH_Z_caddy_hash-password>
	}
	reverse_proxy 127.0.0.1:8321
}
```

Strona `krasnal.cc` to `deploy/landing/index.html` w tym repo — jest wersjonowana
i aktualizuje się przy każdym deployu razem z resztą kodu (Caddy czyta plik
z dysku przy każdym żądaniu, więc nie trzeba go przeładowywać).

```bash
caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

### Log dostępowy (diagnoza „network error” przy zdjęciach)

W bloku `fit.krasnal.cc` dopisz, żeby widzieć czas i status każdego żądania
(także przerwanych przez telefon):

```
	log {
		output file /var/log/caddy/fit-access.log {
			roll_size 10mb
			roll_keep 3
			roll_keep_for 720h
		}
		format json
	}
```

`roll_keep_for 720h` = 30 dni, zgodnie z retencją z `/prywatnosc` (log zawiera IP).
Szukanie zerwanych wysyłek: `sudo grep '/api/meals/photo' /var/log/caddy/fit-access.log | jq -c '{ts,status,duration,size,ua:.request.headers["User-Agent"][0]}'`
(`status` 0/502 + `size` 0 = telefon nie dosłał ciała żądania).

### Zmiana plików systemd

`deploy.sh` **nie** podmienia plików jednostek. Po zmianie `deploy/*.service`:

```bash
sudo cp /opt/fit-krasnal/deploy/fit-krasnal.service /opt/fit-krasnal/deploy/fit-krasnal-queue.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart fit-krasnal
```

`basic_auth` to **tymczasowa** kłódka na czas, gdy aplikacja nie ma jeszcze
własnego logowania. Po skończeniu multi-user auth usuń ten blok.

Domena główna wymaga własnego rekordu A w Cloudflare (`@` → to samo IP);
bez niego Caddy nie wyrobi certyfikatu dla `krasnal.cc` i **cała** konfiguracja
się nie przeładuje.

## Codzienne użycie

- Deploy: `git push` na `main` (albo *Actions → Deploy na GCP → Run workflow*)
- Logi aplikacji: `sudo journalctl -u fit-krasnal -f`
- Logi Caddy: `sudo journalctl -u caddy -f`
- Restart ręczny: `sudo systemctl restart fit-krasnal`
- Backup danych: `sudo tar czf ~/fk-backup.tar.gz /var/lib/fit-krasnal`
  (baza chodzi w trybie WAL, więc obok `fit-krasnal.db` leżą `-wal` i `-shm` —
  archiwizuj **cały katalog**, sam plik `.db` może nie mieć ostatnich transakcji)
- Retencja logów journald: 30 dni (`/etc/systemd/journald.conf.d/fit-krasnal.conf`,
  zgodne z `/prywatnosc`) — zakłada `setup-vm.sh`; jeśli VM postawiona przed tym
  punktem, dopisz plik ręcznie i `sudo systemctl restart systemd-journald`.
- Kolejka posiłków offline: `sudo systemctl status fit-krasnal-queue.timer`,
  logi ostatniego przebiegu `sudo journalctl -u fit-krasnal-queue -n 20`.
  Jeśli VM postawiona przed dodaniem timera, doinstaluj ręcznie:
  `sudo cp deploy/fit-krasnal-queue.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now fit-krasnal-queue.timer`.

### Rotacja klucza szyfrującego (`FIT_KRASNAL_ENC_KEY`)

Klucze LLM i tokeny Garmina leżą w bazie zaszyfrowane Fernetem
(`FIT_KRASNAL_ENC_KEY` w `/etc/fit-krasnal/env`). Rotacja (np. po podejrzeniu
wycieku):

```bash
cd /opt/fit-krasnal
sudo -u fitkrasnal bash -c '
  export FIT_KRASNAL_ENC_KEY=$(grep ^FIT_KRASNAL_ENC_KEY= /etc/fit-krasnal/env | cut -d= -f2-)
  NEW=$(.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  .venv/bin/python scripts/rotate_enc_key.py "$NEW"
  echo "Nowy klucz: $NEW"
'
```

Skrypt sam nie zmienia `/etc/fit-krasnal/env` — po jego sukcesie wklej
wypisany nowy klucz jako `FIT_KRASNAL_ENC_KEY` ręcznie i
`sudo systemctl restart fit-krasnal`. Bez tego kroku proces nadal używa
starego klucza (zgodnie z wypisanym środowiskiem `EnvironmentFile`), a baza
ma już sekrety zaszyfrowane nowym — restart jest częścią rotacji, nie
opcjonalnym krokiem.

## Wariant GCP z logowaniem Google

Fork dla jednego testera na własnym projekcie GCP: zamiast kodu zaproszenia
i hasła — logowanie kontem Google (OIDC) z allowlistą adresów. Żadnych
wartości nie ma w repo, wszystko przez zmienne środowiskowe w
`/etc/fit-krasnal/env`:

| Zmienna | Znaczenie |
|---|---|
| `FIT_KRASNAL_PUBLIC_URL` | publiczny adres aplikacji, np. `https://fit-<ip>.sslip.io` |
| `FIT_KRASNAL_AUTH` | `oidc` (tylko Google) albo `both` (Google + hasło) |
| `FIT_KRASNAL_GOOGLE_CLIENT_ID` / `_SECRET` | klient OAuth 2.0 „Web application" z Google Cloud Console |
| `FIT_KRASNAL_ALLOWED_EMAILS` | lista e-maili (małe litery, po przecinku), którym wolno się zalogować |
| `FIT_KRASNAL_ALLOWED_HOSTS` | lista hostów akceptowanych w nagłówku `Host` (domyślnie `*`) |
| `FIT_KRASNAL_VERTEX_PROJECT` / `_LOCATION` | Gemini przez Vertex AI z konta serwera (ADC), bez kluczy API. Kod domyślnie `europe-west1`; **najnowsze modele (np. `gemini-3.5-flash`) bywają dostępne tylko pod `global`** — fork używa `global`. Nota `/prywatnosc` upstreamu mówi o regionie UE; operator, który wybiera `global`, powinien ją dopasować |
| `FIT_KRASNAL_GEMINI_MODEL` | model Gemini (kod domyślnie `gemini-3.5-flash`). Obserwacja 2026-10-08: w `europe-west1` ten model zwracał `404 Publisher model … was not found`, pod `global` działa; `gemini-2.5-flash` działa w obu. Proces WWW przy błędzie LLM po cichu odkłada posiłek do kolejki — treść błędu zobaczysz w `journalctl -u fit-krasnal-queue`. Gdy model zwraca 404: najpierw `FIT_KRASNAL_VERTEX_LOCATION=global`, potem dopiero starszy model |

W konsoli Google (APIs & Services → Credentials) adres zwrotny (redirect URI)
klienta musi być dokładnie `<FIT_KRASNAL_PUBLIC_URL>/auth/google/callback`.
Konto usługi VM potrzebuje roli `roles/aiplatform.user`, jeśli używasz Vertex AI.

### Klient OAuth w Secret Manager

Klient OAuth nie leży w repo ani w stanie Terraforma. Terraform
(`deploy/terraform`) tworzy tylko pusty sekret o nazwie z `var.oauth_secret_name`
(domyślnie `fit-krasnal-oauth`) i daje kontu usługi VM rolę
`roles/secretmanager.secretAccessor`. Wersję sekretu dodaje operator; payload
to dokładnie dwie linie w formacie pliku env:

```
FIT_KRASNAL_GOOGLE_CLIENT_ID=...
FIT_KRASNAL_GOOGLE_CLIENT_SECRET=...
```

Na VM wczytuje je skrypt [`deploy/load-oauth-secret.sh`](load-oauth-secret.sh).
Root uruchamia **kopię spoza checkoutu** (`/opt/fit-krasnal` należy do
użytkownika usługi, który robi tam `git pull` — skrypt z checkoutu mógłby
zostać podmieniony). `gcloud` jest na obrazie Debiana z GCE; skrypt używa go
z pustym `CLOUDSDK_CONFIG`, więc widzi tylko konto usługi VM z serwera
metadanych (projekt też stamtąd). Pobiera wersję `latest` do pliku 0600 na
tmpfs, sprawdza — bez wypisywania wartości — że są dokładnie dwie linie
`ID`/`SECRET` ze znakami `[A-Za-z0-9._-]`, podmienia w `/etc/fit-krasnal/env`
dwie puste linie zostawione przez `setup-vm.sh` (zachowując
`root:fitkrasnal 640`) i restartuje usługę:

```bash
sudo install -o root -g root -m 0755 /opt/fit-krasnal/deploy/load-oauth-secret.sh /usr/local/sbin/load-oauth-secret
sudo /usr/local/sbin/load-oauth-secret            # [nazwa-sekretu], domyślnie fit-krasnal-oauth
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' <FIT_KRASNAL_PUBLIC_URL>/auth/google
# 302 https://accounts.google.com/… = OK; 503 = brak klienta w env; 404 = FIT_KRASNAL_AUTH bez oidc
```

Nie wypisuj zawartości sekretu na terminal (`cat`, `gcloud … access` bez
przekierowania); sprawdzaj obecność, nie wartości:
`sudo grep -c '^FIT_KRASNAL_GOOGLE_CLIENT_\(ID\|SECRET\)=.' /etc/fit-krasnal/env` → `2`.

Sekret ma `prevent_destroy`: zmiana jego nazwy albo replikacji wymaga
świadomego usunięcia tego bloku (stare wersje przepadają), zmiana etykiety
zasobu w HCL — `terraform state mv`.

### Kreator: klient OAuth i wersja sekretu (konsola, działa z telefonu)

Etykiety podane po angielsku (konsola w tym języku jest stabilniejsza; po
polsku są tłumaczone 1:1). Wklejanie z telefonu: uważaj na autokorektę
i „inteligentne" cudzysłowy — skrypt z poprzedniego podrozdziału odrzuci
payload, w którym brakuje którejś linii, ale nie wykryje literówki w wartości.

1. https://console.cloud.google.com/auth/overview → wybierz projekt → jeśli
   to pierwszy raz: *Get started* → App name „Fit Krasnal", support e-mail,
   Audience **External**, contact e-mail → *Create*. Potem *Audience* →
   *Test users* → *Add users* → e-maile z allowlisty (w trybie *Testing*
   tylko oni mogą się zalogować). Zakresów (*Data access*) nie dodawaj —
   `openid email profile` są domyślne.
2. https://console.cloud.google.com/auth/clients → *+ Create client* →
   Application type **Web application**, Name np. „fit-krasnal-web".
3. *Authorized redirect URIs* → *+ Add URI* → dokładnie
   `<FIT_KRASNAL_PUBLIC_URL>/auth/google/callback` (ten sam host, co
   `FIT_KRASNAL_PUBLIC_URL`, `https`, bez ukośnika na końcu). *Authorized
   JavaScript origins* zostaw puste. *Create*.
4. W oknie „OAuth client created" skopiuj *Client ID* i *Client secret*
   (sekret widać też później w szczegółach klienta). Nie pobieraj pliku JSON;
   jeśli pobrałeś — usuń go po wklejeniu do Secret Managera.
5. https://console.cloud.google.com/security/secret-manager → sekret
   `fit-krasnal-oauth` (istnieje po `terraform apply`) → *+ New version*.
6. *Secret value* → wklej dokładnie dwie linie
   `FIT_KRASNAL_GOOGLE_CLIENT_ID=<id>` i
   `FIT_KRASNAL_GOOGLE_CLIENT_SECRET=<sekret>` (bez spacji wokół `=`, bez
   cudzysłowów, każda w osobnej linii) → *Add new version*.
7. Na VM: komenda z `terraform output oauth_secret_load_command` (kopia
   skryptu do `/usr/local/sbin` + uruchomienie). Test:
   `<FIT_KRASNAL_PUBLIC_URL>/login` → „Zaloguj przez Google".

## Onboarding testera

1. Wejdź na `https://fit.krasnal.cc` (przez basic_auth Caddy, dopóki nie
   zdejmiemy tej kłódki po zamknięciu pilota).
2. Kliknij *Zarejestruj się*, podaj e-mail, hasło (≥ 8 znaków) i **kod
   zaproszenia** (wartość `FIT_KRASNAL_INVITE_CODE` z `/etc/fit-krasnal/env`
   — trzymaj przy sobie i przekazuj testerom osobno).
3. Wejdź w **Ustawienia** → wklej własny darmowy klucz Gemini
   (https://aistudio.google.com → *Get API key*) — dzięki temu szacowanie
   posiłków idzie z Twojej quoty, nie z jakiegoś wspólnego.
4. (Opcjonalnie) w Ustawieniach podłącz konto Garmin — login/hasło + kod MFA
   z aplikacji Garmin. Token sesji leży zaszyfrowany w bazie (per użytkownik),
   nie jako plik na dysku.
5. Dwa widoki, ta sama sesja:
   - `/` — pełny dashboard desktopowy (server-rendered).
   - `/mobile` — cienki klient dla telefonu (SPA używający `/api/*`;
     bez kolejki offline, wymaga internetu przy każdej operacji).

Bez Garmina można wpisać wagę i kroki ręcznie z widoku mobile — trafi to
do `WeightLog(source="manual")` i `DailySummary.steps`.

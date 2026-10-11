<!-- Plan forka (bobert-bag-bounty). Po realizacji: wpis do DONE.md + archive/, ten plik usuń. -->
# Publikacja forka i przekazanie autorowi (lista kontrolna)

Cel: wypchnąć fork do publicznego repo, domknąć tanie resztki, uporządkować
kod pod czytanie (człowiek + LLM autora) i oddać autorowi działającą
infrastrukturę GCP razem z instrukcją przeniesienia. Kolejność sekcji =
kolejność wykonania. Żadnych wartości z laboratorium w repo (adresy, ID
projektu, numery seryjne, e-maile); te leżą w `deploy/terraform/*.tfvars`,
`deploy/terraform/NOTES.local.md` i w `/etc/fit-krasnal/env` na VM.

## A. Przed pierwszym `git push` (fork)

- [x] **GitHub Actions wyłączone na forku** (2026-10-08; job `deploy` dodatkowo ograniczony do repo upstreamu). *Settings → Actions → General →
  Disable actions.* Workflow `deploy.yml` z upstreamu i tak nie dosięgnie VM
  (port 22 tylko z zakresu IAP, fork nie ma sekretów), ale każdy push
  robiłby czerwony przebieg i pełną suitę na runnerze GitHuba.
- [x] **Pełna suita `pytest` lokalnie** (248 passed, 2026-10-08) (za zgodą właściciela, CLAUDE.md).
  Dotąd przeszły tylko testy dotkniętych plików (66). Czerwony = nie pushuj.
- [x] **Audyt treści** zrobiony 2026-10-07 i powtórzony przez osobnego agenta 2026-10-08 przed pushem (0 blokerów, poprawki w 25.6.1): brak adresów, hostów, ID projektu,
  e-maili, numeru seryjnego, ścieżek domowych; brak keystore, `.env`,
  `tfstate`; każdy commit z `app/` podnosi `VERSION`. Powtórzyć
  `git grep` po dopisaniu czegokolwiek nowego przed pushem.
- [x] **`git status` czysty, `main` ahead N / behind 0** (push 2026-10-08) względem `origin`
  (`git fetch` przed sprawdzeniem). Pushuje właściciel.
- [x] **Po pushu:** na VM `bash /opt/fit-krasnal/deploy/deploy.sh` przez IAP
  SSH, żeby maszyna wróciła na `origin/main` (dziś ma kod wgrany tar-em na
  stary commit). Potem `terraform plan` → „No changes".

## B. Resztki w toku — tanie do domknięcia przed przekazaniem

| # | Co | Stan | Koszt | Uwagi |
|---|---|---|---|---|
| 1 | ✅ 2026-10-08 **Klient OAuth 2.0** (Web application, redirect `<PUBLIC_URL>/auth/google/callback`) i wpis `FIT_KRASNAL_GOOGLE_CLIENT_ID/_SECRET` do `/etc/fit-krasnal/env` + restart | brak; `/auth/google` → 503, nikt nie może się zalogować | 10 min, tylko GUI konsoli | Blokuje każdy test end-to-end poniżej |
| 2 | ✅ 2026-10-08 **Zdjęcie z aparatu → oszacowanie przez Vertex** | niezweryfikowane (lokalnie bez klucza, na VM bez logowania) | 15 min po #1 | Sprawdzić też zdarzenia `photo_native_camera`, `native_app_open` na `/usage` |
| 3 | ⏸ scoping **Health Connect: waga** | `android-app/README.md` i manifest deklarują `READ_WEIGHT`, `mobile.html` czyta tylko kroki | ~1 h kodu (ten sam wzorzec co kroki → istniejący POST wagi) **albo** 5 min: usunąć obietnicę z README i manifestu | Decyzja: zrobić czy wyciąć. Rekomendacja: wyciąć, autor i tak wybierze stos (Flutter vs Capacitor) |
| 4 | ✅ **`deploy/README.md` §2 „Klucz SSH dla GitHub Actions"** | sprzeczne z wariantem Terraform (22 tylko z IAP) | 20 min doc | Dopisać: w wariancie Terraform deploy ręczny `gcloud compute ssh … --tunnel-through-iap --command 'bash /opt/fit-krasnal/deploy/deploy.sh'`; otwarcie 22 dla GitHuba = świadoma decyzja, nie domyślna |
| 5 | ✅ **`CLAUDE.md` „Struktura repo"** | nie zna `app/middleware.py`, `app/routers/oidc.py`, backendu `vertex`, `android-app/`, `deploy/terraform/` | 30 min doc | Wchodzi w sekcję C, ale to minimum trzeba zrobić i tak |
| 6 | ✅ **`.env.example`** | brak kilku zmiennych z `config.py` (m.in. `FIT_KRASNAL_STRAVA_*`, `_USAGE_SALT`, `_ADMIN_EMAIL`, `_PRIVACY_VERSION`, modele) — luka jeszcze z upstreamu | 15 min doc | Dopisać z komentarzem, bez wartości |
| 7 | ✅ **`TODO.md`** | „Aplikacja mobilna — Flutter (10/10)" i „Nazwa pakietu (1/10)" nie wiedzą o PoC Capacitora (`cc.krasnal.fit`) ani o przycisku Health Connect | 15 min doc | Dopisać odnośnik do `android-app/README.md`; **nie decydować za autora** Flutter vs Capacitor ani nazwy pakietu — tylko zanotować, że `cc.krasnal.fit` jest użyte w PoC i w APK testowym |
| 8 | **VM: 6 oczekujące aktualizacje apt** | unattended-upgrades robi tylko security | 5 min | `sudo apt upgrade` + ewentualny reboot przez IAP |
| 9 | ✅ **APK w buckecie** | build debug, URL sslip wszyty na stałe | 0 teraz | Ważny, dopóki IP się nie zmieni. Przy zmianie domeny (sekcja D) przebudować i wgrać ponownie |

Nie domykać tutaj: punkty z `TODO.md` (reset hasła, usuwanie konta, Flutter)
— to roadmapa autora, nie resztki forka.

## C. Przegląd kodu pod czytanie (człowiek + LLM autora)

Skill do tego dojdzie później; tutaj tylko zakres, żeby nie zgubić.

1. **Mapa repo** w jednym pliku (`ARCHITEKTURA.md` albo sekcja w README):
   żądanie → middleware → router → serwis → model; gdzie leżą decyzje
   (auth, LLM, providery, kolejka). Diagramy jako **Mermaid w Markdown**
   (GitHub renderuje, LLM czyta tekst) — nie obrazki.
2. **Tabela „co czyta co"** dla rzeczy nieoczywistych: `config.py` →
   zmienne env → kto ich używa; `usage.EVENTS` → gdzie emitowane; `mobile.html`
   → które `/api/*`.
3. **Sekcja „most natywny"** w `mobile.html` i `android-app/` — jeden diagram
   sekwencji (GET z UA markerem → reload guard → plugin → POST).
4. **Nowe moduły forka w `CLAUDE.md`** (B.5) + jedno zdanie w `README.md`,
   że fork dodaje OIDC/Vertex/hardening/Android, wszystko za flagami env,
   domyślne zachowanie upstreamu bez zmian.
5. **Język:** dokumenty po polsku jak reszta repo; nazwy identyfikatorów i
   komendy bez zmian. Zero duplikatów planów (CLAUDE.md zabrania).
6. **Nie refaktoryzować kodu** w tym kroku — tylko dokumentacja i komentarze
   nagłówkowe modułów. Refaktor = osobna decyzja autora.

## D. Przekazanie infrastruktury GCP — szybki start

Dwie drogi; rekomendacja: **D1**, bo nic nie trzeba odtwarzać.

### D1. Oddać istniejący projekt autorowi (zmiana właściciela + billingu)

Projekt bez organizacji **nie da się „przenieść"** między dwoma kontami
Gmail — przeniesienie to zmiana IAM i billingu, projekt zostaje ten sam.
(`gcloud projects move` działa tylko między organizacjami.)

1. Autor podaje konto Google i **własne konto rozliczeniowe** (ID billingu).
2. Obecny właściciel: `gcloud projects add-iam-policy-binding <PROJECT>
   --member=user:<autor> --role=roles/owner`. Konto spoza organizacji dostaje
   **zaproszenie mailem — musi je przyjąć**.
3. Autor (po przyjęciu): `gcloud billing projects link <PROJECT>
   --billing-account=<JEGO_BILLING>` (potrzebuje `billing.user` na swoim koncie
   rozliczeniowym). Od tej chwili Vertex i VM idą na jego rachunek.
4. Autor zmienia **support email ekranu zgody OAuth** na swój (GUI: *APIs &
   Services → OAuth consent screen*); jeśli status to „Testing", dopisuje
   siebie i testerów do *Test users*.
5. Autor dopisuje siebie do allowlisty: `gcloud compute instances add-metadata
   fit-krasnal --zone <zone> --metadata fit-krasnal-allowed-emails=<lista>` +
   `sudo systemctl restart fit-krasnal`; oraz do `apk_viewers` w tfvars.
6. Obecny właściciel przekazuje **poza repo** katalog
   `deploy/terraform/{terraform.tfvars,terraform.tfstate,NOTES.local.md}`
   (stan nie zawiera sekretów, tylko e-maile i adresy) i usuwa swoje
   `roles/owner`. Autor: `terraform init -backend-config="path=terraform.tfstate"`,
   `terraform plan` → „No changes".
7. Opcjonalnie autor rotuje sekrety w `/etc/fit-krasnal/env` (`FIT_KRASNAL_SECRET_KEY`
   sesji — wylogowuje wszystkich; `FIT_KRASNAL_ENC_KEY` — procedura w
   `deploy/README.md` „Rotacja klucza"; sekret OAuth — nowy w konsoli).

### D2. Świeży projekt autora (odtworzenie z Terraforma)

1. Autor tworzy projekt + billing, włącza ekran zgody OAuth (tylko GUI),
   `gcloud auth application-default login`.
2. `cp terraform.tfvars.example terraform.tfvars` — **inna
   `apk_bucket_name`** (nazwa globalna, stara jest zajęta), jego `project_id`,
   `domain`, `allowed_emails`, `apk_viewers`. `terraform apply`.
3. Przez IAP: `sudo FIT_DOMAIN=<host> bash deploy/setup-vm.sh`
   (`FIT_REPO_URL`, jeśli nie fork). Klient OAuth w GUI z redirect
   `https://<host>/auth/google/callback` → `/etc/fit-krasnal/env`.
4. **Dane:** skopiować `/var/lib/fit-krasnal/` (SQLite + zdjęcia) **razem z
   `FIT_KRASNAL_ENC_KEY`** ze starego env — bez klucza zaszyfrowane ustawienia
   userów (tokeny Garmin/Strava, klucze LLM) są nie do odczytu.
5. APK: `FIT_KRASNAL_APP_URL=https://<host> npx cap sync android` + build +
   `gsutil cp` do nowego bucketu.

### D3. Własna domena zamiast sslip.io (w obu drogach)

Rekord A `<host>` → statyczne IP (output `public_ip`), potem na VM:
`FIT_DOMAIN` w `/etc/caddy/Caddyfile`, `FIT_KRASNAL_PUBLIC_URL` i
`FIT_KRASNAL_ALLOWED_HOSTS` w env, redirect URI klienta OAuth w konsoli,
`systemctl restart caddy fit-krasnal`, przebudowa APK (B.9). Caddy sam
wystawi nowy certyfikat.

## E. Ściąga dla autora: co zostaje, co trzeba stworzyć

| Element | D1 (ten sam projekt) | D2 (nowy projekt) |
|---|---|---|
| VM, dysk, statyczne IP, firewall | zostaje | Terraform tworzy |
| Konto usługi VM (`roles/aiplatform.user`, `logWriter`) | zostaje; **nie ma żadnych kluczy SA** do odtwarzania (ADC z metadanych VM) | Terraform tworzy, też bez kluczy |
| Ekran zgody OAuth + klient OAuth | zostają; zmień support email, test users | **tylko GUI**, od zera |
| Allowlista logowania (metadane VM) | zostaje; dopisz siebie | w tfvars |
| Bucket APK + IAM czytelników | zostaje; dopisz siebie | nowa nazwa bucketu |
| Sekrety w `/etc/fit-krasnal/env` (sesja, ENC_KEY, OAuth) | zostają na dysku; rotacja opcjonalna | nowe (setup-vm.sh generuje), ENC_KEY **skopiować** jeśli przenosisz dane |
| Baza i zdjęcia `/var/lib/fit-krasnal/` | zostają | skopiować |
| Stan Terraforma + tfvars | przekazać poza repo | nowy |
| Dostęp SSH | tylko IAP + OS Login; `roles/owner` wystarcza | j.w. |
| Certyfikat TLS | Caddy odnawia sam | j.w. |
| Billing | **zmienić na konto autora** | od początku autora |

## F. Decyzje autora przy scaleniu do upstreamu (nie rozstrzygać za niego)

- **`PRIVACY_VERSION` = 2026-09-16** i nowi odbiorcy w `/prywatnosc` (Google
  przy logowaniu, Vertex AI). Scalenie do `main` upstreamu = **ponowna zgoda
  wszystkich testerów pilota**, choć w produkcji flagi `FIT_KRASNAL_AUTH` i
  `FIT_KRASNAL_LLM` zostają domyślne. Opcje: zostawić (zgodnie z CLAUDE.md:
  nowy odbiorca = bump) albo warunkować tekst noty flagą i cofnąć bump.
- **Utwardzenie (25.5.0) zmienia produkcję** od razu po scaleniu: CSP, CSRF po
  origin, limit zdjęcia 15 → 8 MB, `TrustedHost` (domyślnie `*`). Testy
  przechodzą, ale przejrzeć na stagingu, którego nie ma — czyli przez
  `FIT_KRASNAL_DEBUG` lokalnie z prawdziwym `mobile.html`.
- Workflow upstreamu **wdraża na produkcję przy każdym pushu do `main`** —
  scalać PR-em, nie pushem, i w godzinie, w której autor patrzy.
- Flutter vs Capacitor, nazwa pakietu (`cc.krasnal.fit` użyte w PoC).

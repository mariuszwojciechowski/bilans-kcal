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

Dane leżą **poza katalogiem repo**, więc `git reset --hard` przy deployu ich nie rusza.

## 1. Bootstrap maszyny (raz)

Po SSH na VM:

```bash
curl -fsSL https://raw.githubusercontent.com/mariuszwojciechowski/bilans-kcal/main/deploy/setup-vm.sh | sudo bash
```

Skrypt: instaluje pakiety, zakłada użytkownika `fitkrasnal`, klonuje repo, robi venv,
generuje `FIT_KRASNAL_SECRET_KEY`, wstawia usługę systemd i wąską regułę sudo
(pozwala CI tylko na restart tej jednej usługi, nie na cokolwiek innego).

Potem ustaw kod zaproszenia:

```bash
sudo nano /etc/fit-krasnal/env      # wpisz FIT_KRASNAL_INVITE_CODE=...
sudo systemctl restart fit-krasnal
```

## 2. Klucz SSH dla GitHub Actions

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

`/etc/caddy/Caddyfile` — strona-rozdzielnik na domenie głównej plus aplikacja:

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
- Retencja logów journald: 30 dni (`/etc/systemd/journald.conf.d/fit-krasnal.conf`,
  zgodne z `/prywatnosc`) — zakłada `setup-vm.sh`; jeśli VM postawiona przed tym
  punktem, dopisz plik ręcznie i `sudo systemctl restart systemd-journald`.

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
   z aplikacji Garmin. Tokeny lądują w `~/.fit-krasnal/garth/<user_id>/`
   izolowane od innych testerów.
5. Dwa widoki, ta sama sesja:
   - `/` — pełny dashboard desktopowy (server-rendered).
   - `/mobile` — cienki klient dla telefonu (SPA używający `/api/*`;
     bez kolejki offline, wymaga internetu przy każdej operacji).

Bez Garmina można wpisać wagę i kroki ręcznie z widoku mobile — trafi to
do `WeightLog(source="manual")` i `DailySummary.steps`.

#!/usr/bin/env bash
# Bootstrap maszyny (Debian 12/13) pod Fit Krasnal. Idempotentny — można
# uruchamiać wielokrotnie. Uruchom na VM jako użytkownik z sudo:
#   curl -fsSL https://raw.githubusercontent.com/<owner>/bilans-kcal/main/deploy/setup-vm.sh \
#     | sudo FIT_DOMAIN=fit.example.com bash
# albo po sklonowaniu repo: sudo FIT_DOMAIN=fit.example.com bash deploy/setup-vm.sh
#
# Parametry (zmienne środowiskowe):
#   FIT_DOMAIN        (wymagane) publiczna nazwa hosta; Caddy wystawi na nią
#                     HTTPS (Let's Encrypt) i przekaże ruch do uvicorna.
#   FIT_REPO_URL      repo do sklonowania; przy istniejącym checkoucie pusta
#                     wartość zostawia dotychczasowy origin (świeży klon: upstream).
#   FIT_BRANCH        gałąź (domyślnie main).
#   FIT_ALLOWED_EMAILS, FIT_AUTH, FIT_LLM, FIT_VERTEX_PROJECT,
#   FIT_VERTEX_LOCATION — opcjonalne; jeśli podane przy PIERWSZYM uruchomieniu,
#                     trafiają do /etc/fit-krasnal/env. Później plik nie jest
#                     nadpisywany (brakujące klucze są tylko dopisywane:
#                     puste, a FIT_KRASNAL_LLM=auto i FIT_KRASNAL_VERTEX_LOCATION=global).
#   FIT_PYTHON        wersja Pythona dla venv (domyślnie 3.12; pyproject
#                     wymaga >=3.12, Debian 12 ma 3.11 → instalowana przez uv).
set -euo pipefail

FIT_DOMAIN="${FIT_DOMAIN:?Ustaw FIT_DOMAIN=<publiczna nazwa hosta>}"
REPO_URL="${FIT_REPO_URL:-}"   # pusty = istniejący origin, a przy świeżym klonie upstream
BRANCH="${FIT_BRANCH:-main}"
PY_VERSION="${FIT_PYTHON:-3.12}"
APP_DIR="/opt/fit-krasnal"
DATA_DIR="/var/lib/fit-krasnal"
ENV_FILE="/etc/fit-krasnal/env"
APP_USER="fitkrasnal"
APP_PORT=8321
# Pythony zarządzane przez uv leżą POZA /home: usługa ma ProtectHome=true,
# więc interpreter spod ~fitkrasnal dałby "Permission denied" przy starcie.
UV_PY_DIR="/opt/uv-python"

need_sudo() { [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"; }
need_sudo "$@"

export DEBIAN_FRONTEND=noninteractive

echo "== pakiety systemowe =="
apt-get update -qq
apt-get install -y -qq git curl ca-certificates build-essential \
  python3 python3-venv python3-dev unattended-upgrades caddy

echo "== automatyczne aktualizacje bezpieczeństwa =="
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true

echo "== użytkownik $APP_USER =="
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"

echo "== katalogi =="
mkdir -p "$DATA_DIR" "$(dirname "$ENV_FILE")" "$UV_PY_DIR"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR" "$UV_PY_DIR"
chmod 750 "$DATA_DIR"

echo "== kod (${REPO_URL:-istniejący origin}, $BRANCH) =="
if [ -d "$APP_DIR/.git" ]; then
  if [ -n "$REPO_URL" ]; then
    sudo -u "$APP_USER" git -C "$APP_DIR" remote set-url origin "$REPO_URL"
  fi
  REPO_URL="$(sudo -u "$APP_USER" git -C "$APP_DIR" remote get-url origin)"
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout --quiet "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only --quiet origin "$BRANCH"
else
  REPO_URL="${REPO_URL:-https://github.com/mariuszwojciechowski/bilans-kcal.git}"
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

echo "== Python $PY_VERSION (uv) + venv + zależności =="
# pyproject wymaga Pythona >= 3.12; systemowy może być starszy. uv pobiera
# wersję zarządzaną do $UV_PY_DIR i buduje z niej venv (--seed dodaje pip,
# którego używa deploy.sh). Venv wskazujący gdzie indziej jest przebudowywany.
sudo -u "$APP_USER" UV_PYTHON_INSTALL_DIR="$UV_PY_DIR" bash -c '
  set -e
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh -s -- -q
  uv python install "'"$PY_VERSION"'" -q
  cd "'"$APP_DIR"'"
  case "$(readlink -f .venv/bin/python 2>/dev/null || true)" in
    "'"$UV_PY_DIR"'"/*) .venv/bin/python -c "import sys; assert sys.version_info >= (3,12)" ;;
    *) rm -rf .venv; uv venv --seed --python "'"$PY_VERSION"'" .venv -q ;;
  esac
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e .
'

echo "== plik z sekretami =="
gen_secret() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }
if [ ! -f "$ENV_FILE" ]; then
  SECRET="$(gen_secret)"
  ENC_KEY="$("$APP_DIR/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  USAGE_SALT="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > "$ENV_FILE" <<ENV
# Sekrety Fit Krasnal — poza repo. Po zmianie: systemctl restart fit-krasnal
FIT_KRASNAL_SECRET_KEY=$SECRET
# Klucz szyfrujący sekretów użytkownika (klucze LLM, tokeny) — Fernet.
# Rotacja: scripts/rotate_enc_key.py (odszyfruj starym, zaszyfruj nowym).
FIT_KRASNAL_ENC_KEY=$ENC_KEY
# Sól HMAC do pseudonimizacji statystyk użycia (/usage). STAŁA — zmiana zrywa
# ciągłość statystyk. Bez niej telemetria po cichu nie zapisuje nic.
FIT_KRASNAL_USAGE_SALT=$USAGE_SALT
# Kod zaproszenia do rejestracji hasłem. Pusty = rejestracja wyłączona.
FIT_KRASNAL_INVITE_CODE=
FIT_KRASNAL_DATA=$DATA_DIR
GARMINTOKENS=$DATA_DIR/garth

# Publiczny adres i dozwolone hosty (Caddy terminuje TLS).
FIT_KRASNAL_PUBLIC_URL=https://$FIT_DOMAIN
FIT_KRASNAL_ALLOWED_HOSTS=$FIT_DOMAIN,localhost,127.0.0.1   # localhost: health check deploy.sh

# Logowanie: password | oidc (Google). Dla oidc uzupełnij CLIENT_ID/SECRET
# (Console → APIs & Services → Credentials → OAuth client, typ Web application,
# redirect URI https://$FIT_DOMAIN/auth/google/callback).
FIT_KRASNAL_AUTH=${FIT_AUTH:-password}
FIT_KRASNAL_ALLOWED_EMAILS=${FIT_ALLOWED_EMAILS:-}
FIT_KRASNAL_GOOGLE_CLIENT_ID=
FIT_KRASNAL_GOOGLE_CLIENT_SECRET=

# LLM: auto | vertex (konto usługi VM, bez kluczy) | gemini | claude.
# Pusta wartość zmiennej NIE oznacza domyślnej z kodu (nadpisuje ją pustym
# stringiem), dlatego wpisujemy jawne domyślne. Region global: najnowsze
# modele Gemini bywają dostępne tylko tam.
FIT_KRASNAL_LLM=${FIT_LLM:-auto}
FIT_KRASNAL_VERTEX_PROJECT=${FIT_VERTEX_PROJECT:-}
FIT_KRASNAL_VERTEX_LOCATION=${FIT_VERTEX_LOCATION:-global}
ENV
  echo "   utworzono $ENV_FILE (wygenerowano SECRET_KEY, ENC_KEY i USAGE_SALT)"
else
  echo "   $ENV_FILE już istnieje — nie nadpisuję; dopisuję tylko brakujące klucze"
  for key in FIT_KRASNAL_ENC_KEY FIT_KRASNAL_USAGE_SALT FIT_KRASNAL_PUBLIC_URL \
             FIT_KRASNAL_ALLOWED_HOSTS FIT_KRASNAL_AUTH FIT_KRASNAL_ALLOWED_EMAILS \
             FIT_KRASNAL_GOOGLE_CLIENT_ID FIT_KRASNAL_GOOGLE_CLIENT_SECRET \
             FIT_KRASNAL_LLM FIT_KRASNAL_VERTEX_PROJECT FIT_KRASNAL_VERTEX_LOCATION; do
    case $key in FIT_KRASNAL_LLM) def=auto ;; FIT_KRASNAL_VERTEX_LOCATION) def=global ;; *) def= ;; esac
    grep -q "^$key=" "$ENV_FILE" || { echo "$key=$def" >> "$ENV_FILE"; echo "   dopisano $key=$def — uzupełnij, jeśli trzeba"; }
  done
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "== Caddy: HTTPS dla $FIT_DOMAIN → 127.0.0.1:$APP_PORT =="
# Bez rate-limitu w Caddy — limity robi aplikacja. -Server: nie zdradzaj wersji.
cat > /etc/caddy/Caddyfile <<CADDY
$FIT_DOMAIN {
	encode gzip
	header {
		-Server
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
	}
	reverse_proxy 127.0.0.1:$APP_PORT
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable --now caddy >/dev/null
systemctl reload caddy

echo "== retencja logów journald (30 dni, RODO) =="
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/fit-krasnal.conf <<CONF
[Journal]
MaxRetentionSec=30day
CONF
systemctl restart systemd-journald

echo "== usługi systemd =="
cp "$APP_DIR/deploy/fit-krasnal.service" /etc/systemd/system/fit-krasnal.service
cp "$APP_DIR/deploy/fit-krasnal-queue.service" /etc/systemd/system/fit-krasnal-queue.service
cp "$APP_DIR/deploy/fit-krasnal-queue.timer" /etc/systemd/system/fit-krasnal-queue.timer
systemctl daemon-reload
systemctl enable --now fit-krasnal-queue.timer
systemctl enable fit-krasnal >/dev/null
systemctl restart fit-krasnal

echo "== pozwolenie na restart usługi z CI (bez pełnego sudo) =="
cat > /etc/sudoers.d/fit-krasnal-deploy <<CONF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart fit-krasnal, /bin/systemctl status fit-krasnal
CONF
chmod 440 /etc/sudoers.d/fit-krasnal-deploy

echo
echo "GOTOWE. Pozostało ręcznie:"
echo "  1. Uzupełnij w $ENV_FILE: FIT_KRASNAL_GOOGLE_CLIENT_ID/SECRET (oidc)"
echo "     albo FIT_KRASNAL_INVITE_CODE (password); potem: systemctl restart fit-krasnal"
echo "  2. (CI) Dodaj klucz publiczny deployu do /home/$APP_USER/.ssh/authorized_keys"
echo
systemctl --no-pager status fit-krasnal | head -5

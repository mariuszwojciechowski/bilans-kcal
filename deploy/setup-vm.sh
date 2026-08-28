#!/usr/bin/env bash
# Jednorazowy bootstrap maszyny (Debian 13) pod Fit Krasnal.
# Uruchom na VM jako użytkownik z sudo:
#   curl -fsSL https://raw.githubusercontent.com/mariuszwojciechowski/bilans-kcal/main/deploy/setup-vm.sh | bash
# albo po sklonowaniu repo: sudo bash deploy/setup-vm.sh
set -euo pipefail

REPO_URL="https://github.com/mariuszwojciechowski/bilans-kcal.git"
APP_DIR="/opt/fit-krasnal"
DATA_DIR="/var/lib/fit-krasnal"
ENV_FILE="/etc/fit-krasnal/env"
APP_USER="fitkrasnal"

need_sudo() { [ "$(id -u)" -eq 0 ] || exec sudo -E bash "$0" "$@"; }
need_sudo "$@"

echo "== pakiety systemowe =="
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-dev build-essential

echo "== użytkownik $APP_USER =="
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"

echo "== katalogi =="
mkdir -p "$DATA_DIR" "$(dirname "$ENV_FILE")"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR"

echo "== kod =="
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

echo "== venv + zależności =="
sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e ."

echo "== plik z sekretami =="
if [ ! -f "$ENV_FILE" ]; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$ENV_FILE" <<EOF
# Sekrety Fit Krasnal — poza repo. Po zmianie: systemctl restart fit-krasnal
FIT_KRASNAL_SECRET_KEY=$SECRET
# USTAW WŁASNY kod zaproszenia, inaczej rejestracja jest wyłączona:
FIT_KRASNAL_INVITE_CODE=
FIT_KRASNAL_DATA=$DATA_DIR
GARMINTOKENS=$DATA_DIR/garth
EOF
  echo "   utworzono $ENV_FILE (wygenerowano SECRET_KEY)"
else
  echo "   $ENV_FILE już istnieje — nie ruszam"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

echo "== usługa systemd =="
cp "$APP_DIR/deploy/fit-krasnal.service" /etc/systemd/system/fit-krasnal.service
systemctl daemon-reload
systemctl enable --now fit-krasnal

echo "== pozwolenie na restart usługi z CI (bez pełnego sudo) =="
cat > /etc/sudoers.d/fit-krasnal-deploy <<EOF
$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart fit-krasnal, /bin/systemctl status fit-krasnal
EOF
chmod 440 /etc/sudoers.d/fit-krasnal-deploy

echo
echo "GOTOWE. Pozostało ręcznie:"
echo "  1. Ustaw FIT_KRASNAL_INVITE_CODE w $ENV_FILE, potem: systemctl restart fit-krasnal"
echo "  2. Dodaj klucz publiczny deployu do /home/$APP_USER/.ssh/authorized_keys"
echo "  3. Przestaw Caddy na: reverse_proxy 127.0.0.1:8321"
echo
systemctl --no-pager status fit-krasnal | head -5

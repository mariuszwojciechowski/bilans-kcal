#!/usr/bin/env bash
# Wdrożenie nowej wersji na VM. Uruchamiane przez GitHub Actions po SSH
# (jako użytkownik fitkrasnal) albo ręcznie na maszynie.
set -euo pipefail

APP_DIR="/opt/fit-krasnal"
cd "$APP_DIR"

echo "== pobieram kod =="
git fetch --quiet origin main
git reset --hard --quiet origin/main    # deploy jest bezstanowy: repo == origin/main
git log -1 --format='   %h %s'

echo "== zależności =="
.venv/bin/pip install -q -e .

echo "== restart usługi =="
# Migracje bazy wykonują się same przy starcie (init_db -> _migrate).
sudo /bin/systemctl restart fit-krasnal

echo "== health check =="
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null http://127.0.0.1:8321/login; then
    echo "   OK — aplikacja odpowiada"
    exit 0
  fi
  sleep 1
done

echo "BŁĄD: aplikacja nie odpowiedziała w 20 s" >&2
sudo /bin/systemctl status fit-krasnal --no-pager | tail -20 >&2
exit 1

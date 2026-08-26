#!/usr/bin/env bash
# Startuje backend Fit Krasnal (uvicorn) w tle, jeśli jeszcze nie działa.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FIT_KRASNAL_PORT:-8321}"
DATA_DIR="${FIT_KRASNAL_DATA:-$ROOT/data}"
PID_FILE="$DATA_DIR/server.pid"
LOG_FILE="$DATA_DIR/server.log"

mkdir -p "$DATA_DIR"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Backend już działa (PID $(cat "$PID_FILE"), port $PORT)."
  exit 0
fi

if lsof -i ":$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT jest zajęty przez inny proces (nie uruchomiony przez ten skrypt)." >&2
  lsof -i ":$PORT" -sTCP:LISTEN
  exit 1
fi

cd "$ROOT"
nohup .venv/bin/uvicorn app.main:app --port "$PORT" >>"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
disown

for _ in $(seq 1 20); do
  if curl -s -o /dev/null "http://localhost:$PORT/"; then
    echo "Backend wystartował: http://localhost:$PORT (PID $(cat "$PID_FILE"))"
    exit 0
  fi
  sleep 0.3
done

echo "Backend nie odpowiedział w czasie — sprawdź $LOG_FILE" >&2
exit 1

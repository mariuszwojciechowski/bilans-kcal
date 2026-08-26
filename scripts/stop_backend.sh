#!/usr/bin/env bash
# Zatrzymuje backend Fit Krasnal uruchomiony przez start_backend.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FIT_KRASNAL_PORT:-8321}"
DATA_DIR="${FIT_KRASNAL_DATA:-$ROOT/data}"
PID_FILE="$DATA_DIR/server.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for _ in $(seq 1 20); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$PID" 2>/dev/null; then
      echo "Proces $PID nie odpowiedział na SIGTERM, wysyłam SIGKILL." >&2
      kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Backend zatrzymany (PID $PID)."
  else
    echo "PID $PID z $PID_FILE już nie istnieje."
  fi
  rm -f "$PID_FILE"
else
  echo "Brak $PID_FILE — sprawdzam port $PORT."
fi

# Domiataj wszystko, co jeszcze słucha na porcie (np. odpalone poza tym skryptem).
LEFTOVER="$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$LEFTOVER" ]; then
  echo "Zamykam pozostałe procesy na porcie $PORT: $LEFTOVER"
  kill $LEFTOVER 2>/dev/null || true
fi

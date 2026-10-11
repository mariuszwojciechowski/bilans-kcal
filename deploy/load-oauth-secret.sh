#!/usr/bin/env bash
# Wczytuje klienta OAuth Google z Secret Manager do /etc/fit-krasnal/env
# i restartuje usługę. Uruchamiać na VM jako root; gcloud działa tam z konta
# usługi VM (bez logowania), projekt bierze z serwera metadanych.
#
#   sudo install -o root -g root -m 0755 deploy/load-oauth-secret.sh /usr/local/sbin/load-oauth-secret
#   sudo /usr/local/sbin/load-oauth-secret [nazwa-sekretu]   # domyślnie fit-krasnal-oauth
#
# Root uruchamia KOPIĘ spoza checkoutu, bo /opt/fit-krasnal należy do
# użytkownika usługi (git pull) — skrypt z checkoutu mógłby zostać podmieniony.
#
# Payload wersji sekretu to dokładnie dwie linie (nic więcej):
#   FIT_KRASNAL_GOOGLE_CLIENT_ID=...
#   FIT_KRASNAL_GOOGLE_CLIENT_SECRET=...
# Wartości nigdy nie trafiają do zmiennej powłoki ani na stdout/stderr:
# gcloud (tylko z poświadczeń serwera metadanych, bez ~/.config/gcloud roota)
# pisze prosto do pliku tymczasowego 0600 na tmpfs, skrypt sprawdza tylko
# kształt (2 linie, każdy klucz raz, znaki [A-Za-z0-9._-]) i dopiero wtedy
# podmienia stare linie w pliku env. Nie uruchamiać pod `bash -x`.
set -euo pipefail

SECRET_NAME="${1:-fit-krasnal-oauth}"
ENV_FILE="${ENV_FILE:-/etc/fit-krasnal/env}"
SERVICE="${SERVICE:-fit-krasnal}"
KEY_ID="FIT_KRASNAL_GOOGLE_CLIENT_ID"
KEY_SECRET="FIT_KRASNAL_GOOGLE_CLIENT_SECRET"

[ "$(id -u)" -eq 0 ] || { echo "uruchom jako root (sudo)" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "brak $ENV_FILE" >&2; exit 1; }

PROJECT="${PROJECT:-$(curl -sf -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/project/project-id || true)}"
[ -n "$PROJECT" ] || { echo "nie znam projektu GCP (ustaw PROJECT=...)" >&2; exit 1; }

umask 077
TMPFS="${TMPFS:-/run}"
payload="$(mktemp -p "$TMPFS" fit-krasnal-payload.XXXXXX)"   # tmpfs: nie zostaje na dysku
new="$(mktemp "$ENV_FILE.new.XXXXXX")"
gcloud_cfg="$(mktemp -d -p "$TMPFS" fit-krasnal-gcloud.XXXXXX)"
trap 'rm -rf "$payload" "$new" "$gcloud_cfg"' EXIT

# Pusty CLOUDSDK_CONFIG: gcloud widzi wyłącznie konto usługi VM z metadanych,
# nie ewentualne `gcloud auth login` zrobione kiedyś pod sudo.
CLOUDSDK_CONFIG="$gcloud_cfg" gcloud secrets versions access latest \
  --secret "$SECRET_NAME" --project "$PROJECT" | tr -d '\r' > "$payload"
# gcloud oddaje payload bez końcowego znaku nowej linii — domknij ostatnią linię.
[ -s "$payload" ] && [ -n "$(tail -c1 "$payload")" ] && printf '\n' >> "$payload"

count() { grep -c "$1" "$2" || [ $? -eq 1 ]; }   # 0 trafień → "0", błąd odczytu → exit
VAL='[A-Za-z0-9._-]\+'   # ID: …apps.googleusercontent.com, sekret: GOCSPX-…; wyklucza cudzysłowy i autokorektę
lines="$(wc -l < "$payload")"
id_ok="$(count "^${KEY_ID}=${VAL}$" "$payload")"
secret_ok="$(count "^${KEY_SECRET}=${VAL}$" "$payload")"
if [ "$lines" != "2" ] || [ "$id_ok" != "1" ] || [ "$secret_ok" != "1" ]; then
  echo "sekret $SECRET_NAME: oczekiwano dokładnie 2 linii ${KEY_ID}=… i ${KEY_SECRET}=… (znaki [A-Za-z0-9._-]);" \
       "jest linii: $lines, ID: $id_ok, SECRET: $secret_ok — nic nie zmieniam" >&2
  exit 1
fi

rc=0
grep -v "^\(${KEY_ID}\|${KEY_SECRET}\)=" "$ENV_FILE" > "$new" || rc=$?
[ "$rc" -le 1 ] || { echo "grep na $ENV_FILE zwrócił $rc" >&2; exit 1; }
[ -s "$new" ] && [ -n "$(tail -c1 "$new")" ] && printf '\n' >> "$new"
cat "$payload" >> "$new"
chown --reference="$ENV_FILE" "$new"
chmod --reference="$ENV_FILE" "$new"
mv -f "$new" "$ENV_FILE"

echo "linie ID/SECRET w $ENV_FILE: $(count "^\(${KEY_ID}\|${KEY_SECRET}\)=." "$ENV_FILE") (oczekiwane 2)"
systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || { echo "usługa $SERVICE nie działa po restarcie — journalctl -u $SERVICE" >&2; exit 1; }
echo "usługa $SERVICE: active"

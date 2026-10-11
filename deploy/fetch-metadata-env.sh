#!/usr/bin/env bash
# ExecStartPre usługi fit-krasnal: przepisuje wybrane atrybuty metadanych
# instancji GCE do pliku środowiskowego, który unit ładuje jako drugi
# EnvironmentFile (nadpisuje wartości z /etc/fit-krasnal/env).
#
# Jedno źródło prawdy dla allowlisty logowania leży w GCP, nie na dysku VM:
#   gcloud compute instances add-metadata <vm> --zone <zone> \
#     --metadata fit-krasnal-allowed-emails=a@x.com,b@y.com
#   sudo systemctl restart fit-krasnal
#
# Użycie: fetch-metadata-env.sh [PLIK_WYJŚCIOWY]   (domyślnie /run/fit-krasnal/env)
# Mapowanie atrybut → zmienna jest w tablicy MAP. Poza GCE (brak serwera
# metadanych) skrypt pisze pusty plik i kończy się sukcesem — usługa startuje
# z wartościami z /etc/fit-krasnal/env.
set -euo pipefail

OUT="${1:-/run/fit-krasnal/env}"
MD="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
declare -A MAP=(
  [fit-krasnal-allowed-emails]=FIT_KRASNAL_ALLOWED_EMAILS
)

TMP="$(mktemp "${OUT}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
{
  echo "# generowane przez deploy/fetch-metadata-env.sh przy starcie usługi — nie edytuj"
  for attr in "${!MAP[@]}"; do
    val="$(curl -fsS --max-time 3 -H 'Metadata-Flavor: Google' "$MD/$attr" 2>/dev/null || true)"
    if [ -n "$val" ]; then
      # jedna linia, bez znaków, które rozbiłyby plik env
      val="${val//$'\n'/}"; val="${val//$'\r'/}"
      printf '%s=%s\n' "${MAP[$attr]}" "$val"
    fi
  done
} > "$TMP"
chmod 640 "$TMP"
mv -f "$TMP" "$OUT"
trap - EXIT

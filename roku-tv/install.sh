#!/usr/bin/env bash
# Zip the app and, if it knows where the Roku is, sideload it.
#
#   ./install.sh                                                 # only builds out/retro-tv.zip
#   ROKU_IP=<roku-ip> ROKU_DEV_PASSWORD=<password> ./install.sh  # builds and uploads
#
# The two values can also sit in roku-tv/.env (git-ignored). The password is the
# one you chose when you turned on developer mode; the user is "rokudev".
# Needs zip, and curl for the upload.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
mkdir -p out
rm -f out/retro-tv.zip
zip -qr out/retro-tv.zip manifest source components images fonts -x "fonts/*.txt"
echo "Built out/retro-tv.zip ($(du -h out/retro-tv.zip | cut -f1))"

if [[ -z "${ROKU_IP:-}" || -z "${ROKU_DEV_PASSWORD:-}" ]]; then
  echo "ROKU_IP and ROKU_DEV_PASSWORD are not both set, so nothing was uploaded."
  echo "Upload the zip yourself: open http://<roku-ip> in a browser, sign in as rokudev, Install."
  exit 0
fi

reply=$(curl -sS --digest -u "rokudev:${ROKU_DEV_PASSWORD}" \
  -F "mysubmit=Install" -F "archive=@out/retro-tv.zip" \
  "http://${ROKU_IP}/plugin_install")

# The Roku answers with an HTML page; its status line says what happened.
status=$(printf '%s' "$reply" | grep -o "Install Success\|Identical to previous version\|Install Failure[^<]*\|Unauthorized" | head -1 || true)
echo "Roku says: ${status:-no status line (check http://${ROKU_IP} in a browser)}"
[[ "$status" == "Install Success" || "$status" == "Identical to previous version" ]]

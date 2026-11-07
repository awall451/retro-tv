#!/usr/bin/env bash
# Zip the app and sideload it onto a Roku in developer mode.
#
#   ROKU_IP=<roku-ip> ROKU_DEV_PASSWORD=<password> ./install.sh
#
# or put those two lines in roku-tv/.env (git-ignored). The password is the
# one you chose when you turned on developer mode; the user is "rokudev".
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
: "${ROKU_IP:?set ROKU_IP (the Roku address on your network)}"
: "${ROKU_DEV_PASSWORD:?set ROKU_DEV_PASSWORD (chosen when enabling developer mode)}"

mkdir -p out
rm -f out/retro-tv.zip
zip -qr out/retro-tv.zip manifest source components images fonts -x "fonts/*.txt"
echo "Built out/retro-tv.zip ($(du -h out/retro-tv.zip | cut -f1))"

reply=$(curl -sS --digest -u "rokudev:${ROKU_DEV_PASSWORD}" \
  -F "mysubmit=Install" -F "archive=@out/retro-tv.zip" \
  "http://${ROKU_IP}/plugin_install")

# The Roku answers with an HTML page; its status line says what happened.
status=$(printf '%s' "$reply" | grep -o "Install Success\|Identical to previous version\|Install Failure[^<]*\|Unauthorized" | head -1 || true)
echo "Roku says: ${status:-no status line (check http://${ROKU_IP} in a browser)}"
[[ "$status" == "Install Success" || "$status" == "Identical to previous version" ]]

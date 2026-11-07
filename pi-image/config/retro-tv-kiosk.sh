#!/bin/sh
# Chromium in kiosk mode on the viewer, run by cage (see retro-tv.service).
# One window, full screen, no browser frame, no cursor (cage hides it).
#
# The viewer is served by this box's own nginx; ?tv asks for the plain
# 640x480 layout, which the CRT shows at 4:3.
URL="http://127.0.0.1:8410/?tv"
PROFILE=/data/chromium            # writable: the viewer's settings (theme, quality) live here

BROWSER=$(command -v chromium || command -v chromium-browser)
exec "$BROWSER" \
    --kiosk "$URL" \
    --ozone-platform=wayland \
    --user-data-dir="$PROFILE" \
    --no-first-run --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    --password-store=basic \
    --enable-features=VaapiVideoDecodeLinuxGL,UseOzonePlatform \
    --ignore-gpu-blocklist

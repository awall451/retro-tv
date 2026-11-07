#!/bin/sh
# Chromium in kiosk mode on the viewer, run by cage (see retro-tv.service).
# One window, full screen, no browser frame, no cursor (cage hides it).
#
# The viewer is served by this box's own nginx; ?tv asks for the plain
# 640x480 layout, which the CRT shows at 4:3.
URL="http://127.0.0.1:8410/?tv"
PROFILE=/data/chromium            # writable: the viewer's settings (theme, quality) live here

# cage starts every output at the display's own preferred mode (the
# HDMI-to-composite converter claims 1280x720), whatever the kernel command
# line says. Ask for the box's mode from inside the session instead.
DISPLAY_MODE=hdmi480
[ -r /etc/retro-tv.env ] && . /etc/retro-tv.env
case "$DISPLAY_MODE" in
    composite) MODE=720x480@60 ;;
    *)         MODE=640x480@60 ;;
esac
if command -v wlr-randr >/dev/null 2>&1; then
    for out in $(wlr-randr 2>/dev/null | awk '/^[A-Za-z]/ { print $1 }'); do
        wlr-randr --output "$out" --mode "$MODE" >/dev/null 2>&1 \
            || wlr-randr --output "$out" --custom-mode "$MODE" >/dev/null 2>&1 \
            || true
    done
fi

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

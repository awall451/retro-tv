#!/bin/sh
# Chromium in kiosk mode on the viewer, run by cage (see retro-tv.service).
# One window, full screen, no browser frame, no cursor (cage hides it).
#
# The viewer is served by this box's own nginx; ?tv asks for the plain
# 640x480 layout, which the CRT shows at 4:3.
PROFILE=/data/chromium            # writable: the viewer's settings (theme, quality) live here

DISPLAY_MODE=hdmi480
PAGE=guide
[ -r /etc/retro-tv.env ] && . /etc/retro-tv.env
case "$PAGE" in
    overscan) URL="http://127.0.0.1:8410/overscan.html" ;;      # the margin test pattern
    tvguide)  URL="http://127.0.0.1:8410/tvguide.html?tv" ;;    # the scrolling listings channel page
    *)        URL="http://127.0.0.1:8410/?tv" ;;
esac
# The Pi's composite output is 720x480 pixels shown as 4:3: tell the viewer so
# it lays out for a 4:3 screen and stretches to the pixel width.
[ "$PAGE" != overscan ] && [ "$DISPLAY_MODE" = composite ] && URL="$URL&screen=4:3"
# The listings page plays a channel in its top half (promos, infomercials).
[ "$PAGE" = tvguide ] && [ -n "$TVGUIDE_PROMO" ] && URL="$URL&promo=$TVGUIDE_PROMO"

# cage starts every output at the display's own preferred mode (the
# HDMI-to-composite converter claims 1280x720), whatever the kernel command
# line says. Ask for the box's mode from inside the session instead.
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

# Sound goes where the picture goes: the HDMI port in use (the converter takes
# its audio from HDMI), or the 3.5 mm jack in composite mode (the same jack
# carries the video). PipeWire's own default is the jack. Full volume here;
# the TV's remote sets the loudness.
if command -v wpctl >/dev/null 2>&1; then
    # The jack shows up as "Headphones" on some builds and as "Built-in Audio"
    # on others (Trixie); in composite mode it is also the only sink there is.
    case "$DISPLAY_MODE" in
        composite) want="Headphones|Built-in|bcm2835" ;;
        *)         want="HDMI" ;;
    esac
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sinks=$(wpctl status 2>/dev/null | sed -n '/Sinks:/,/Sources:/p')
        sink=$(echo "$sinks" | grep -iE "$want" | grep -oE '[0-9]+\.' | head -1 | tr -d .)
        # Nothing matched but there is exactly one sink: that is the one.
        [ -z "$sink" ] && [ "$(echo "$sinks" | grep -cE '^ *│ +\*? *[0-9]+\.')" = 1 ] && sink=$(echo "$sinks" | grep -oE '[0-9]+\.' | head -1 | tr -d .)
        [ -n "$sink" ] && break
        sleep 1
    done
    if [ -n "$sink" ]; then
        wpctl set-default "$sink"
        wpctl set-volume "$sink" 1.0
    fi
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

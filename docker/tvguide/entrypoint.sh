#!/bin/bash
# Render the TV Guide Channel page and stream it as live HLS.
#
#   Xvfb        a 640x480 screen nobody looks at
#   PulseAudio  a silent sink the browser plays into; ffmpeg records its monitor
#   Chromium    the page, kiosk mode, from the viewer container
#   ffmpeg      grabs the screen and the sink, encodes H.264 + AAC, writes HLS to /out
#   http.server hands /out to ErsatzTV at :TVGUIDE_PORT/live.m3u8
#
# If any of them dies the whole thing exits and Docker restarts it.
set -u

VIEWER_URL=${VIEWER_URL:-http://web:8080}
FPS=${TVGUIDE_FPS:-30}
BITRATE=${TVGUIDE_BITRATE:-1800k}
PORT=${TVGUIDE_PORT:-8082}
OUT=/out
W=640; H=480
DISPLAY_NUM=:99

URL="$VIEWER_URL/tvguide.html?tv"
[ -n "${TVGUIDE_PROMO:-}" ] && URL="$URL&promo=$TVGUIDE_PROMO"

log() { echo "[tvguide] $*"; }
cleanup() { log "stopping"; kill 0 2>/dev/null; }
trap cleanup EXIT INT TERM

rm -f "$OUT"/live*.ts "$OUT"/live.m3u8
export XDG_RUNTIME_DIR=/tmp/runtime; mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"

# ---- sound: a null sink called "tv"; its monitor is what ffmpeg records ----------
pulseaudio --daemonize=no --exit-idle-time=-1 --disallow-exit \
  --load="module-native-protocol-unix socket=$XDG_RUNTIME_DIR/pulse/native" \
  --load="module-null-sink sink_name=tv sink_properties=device.description=TV" \
  --load="module-always-sink" -n >/tmp/pulse.log 2>&1 &
for _ in $(seq 1 50); do pactl info >/dev/null 2>&1 && break; sleep 0.2; done
pactl set-default-sink tv >/dev/null 2>&1 || log "warning: could not set the default sink"

# ---- screen ----------------------------------------------------------------------------
Xvfb "$DISPLAY_NUM" -screen 0 "${W}x${H}x24" -nolisten tcp -nocursor >/tmp/xvfb.log 2>&1 &
export DISPLAY=$DISPLAY_NUM
for _ in $(seq 1 50); do [ -e "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ] && break; sleep 0.2; done

# ---- the page ----------------------------------------------------------------------------
log "page: $URL"
chromium --no-sandbox --disable-dev-shm-usage --disable-gpu --use-gl=angle --use-angle=swiftshader \
  --kiosk --window-position=0,0 --window-size=$W,$H --force-device-scale-factor=1 \
  --autoplay-policy=no-user-gesture-required --no-first-run --noerrdialogs --disable-infobars \
  --disable-session-crashed-bubble --disable-features=TranslateUI --password-store=basic \
  --user-data-dir=/tmp/chromium --hide-scrollbars --enable-features=OverlayScrollbar \
  "$URL" >/tmp/chromium.log 2>&1 &
sleep 3

# ---- capture and encode --------------------------------------------------------------------
# Progressive 640x480 at FPS; ErsatzTV transcodes it again into the channel's
# own profile, so this only has to be clean, not small. Two-second keyframes,
# 4 s segments, the last eight kept.
log "encoding ${W}x${H} at ${FPS} fps, ${BITRATE}"
ffmpeg -hide_banner -loglevel warning -nostdin \
  -f x11grab -framerate "$FPS" -video_size "${W}x${H}" -draw_mouse 0 -i "$DISPLAY_NUM" \
  -f pulse -i tv.monitor \
  -map 0:v -map 1:a \
  -c:v libx264 -preset veryfast -profile:v main -pix_fmt yuv420p \
  -g $((FPS * 2)) -keyint_min $((FPS * 2)) -sc_threshold 0 \
  -b:v "$BITRATE" -maxrate "$BITRATE" -bufsize "$((${BITRATE%k} * 2))k" \
  -c:a aac -b:a 128k -ac 2 -ar 48000 \
  -f hls -hls_time 4 -hls_list_size 8 -hls_flags delete_segments+independent_segments \
  -hls_segment_filename "$OUT/live%05d.ts" "$OUT/live.m3u8" >/tmp/ffmpeg.log 2>&1 &

# ---- serve ------------------------------------------------------------------------------------
cd "$OUT" && python3 -m http.server "$PORT" --bind 0.0.0.0 >/tmp/http.log 2>&1 &
log "serving http://0.0.0.0:$PORT/live.m3u8"

# The first process to die takes the container down (Docker restarts it).
wait -n
log "a process ended; last lines of the logs:"
tail -n 5 /tmp/ffmpeg.log /tmp/chromium.log /tmp/xvfb.log /tmp/pulse.log 2>/dev/null
exit 1

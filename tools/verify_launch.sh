#!/bin/bash
# Usage: verify_launch.sh <outdir> <system>:<rom> [<system>:<rom> ...]
# Launches each game through Batocera's real launcher (emulatorlauncher, same path as the
# menu), waits, captures the whole screen with grim, closes the game normally, and reports
# the shader, scaling, smoothing, overlay and centering RetroArch was started with.
export XDG_RUNTIME_DIR=/var/run WAYLAND_DISPLAY=wayland-1 DISPLAY=:0 SWAYSOCK=/var/run/sway-ipc.0.sock \
       HOME=/userdata/system XDG_CONFIG_HOME=/userdata/system/configs SDL_NOMOUSE=1
out=$1; shift; mkdir -p "$out"
CFG=/userdata/system/configs/retroarch/retroarchcustom.cfg
for item in "$@"; do
    sys=${item%%:*}; rom=${item#*:}
    emulatorlauncher -system "$sys" -rom "$rom" >/tmp/verify-launch.log 2>&1 &
    for i in $(seq 1 30); do pgrep -f "retroarch -L" >/dev/null && break; sleep 1; done
    sleep ${WAIT:-12}
    grim "$out/$sys.png" 2>/dev/null
    cmd=$(ps -eo args | grep "[r]etroarch -L")
    shader=$(echo "$cmd" | grep -o -- "--set-shader [^ ]*" | cut -d" " -f2)
    printf "%-10s shader=%-55s %s\n" "$sys" "${shader:-none}" \
        "$(grep -E '^(video_scale_integer|video_smooth|input_overlay_enable|video_viewport_bias_x|aspect_ratio_index) ' $CFG | sed 's/ = /=/' | tr '\n' ' ')"
    pkill -TERM -f "retroarch -L"; wait 2>/dev/null; sleep 2
done

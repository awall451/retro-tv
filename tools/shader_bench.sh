#!/bin/bash
# Usage: shader_bench.sh <core> <rom> <outdir> <shader.glslp|none> [<shader> ...]
# Runs RetroArch fullscreen with vsync on and audio sync off (real display pacing), for a short and a long run,
# and reports delivered FPS = extra frames / extra seconds (cancels out load time).
# Also saves a GPU screenshot (shader applied) from the long run.
# Env: LONG=<frames> measured frames (default 1200 = 20 s at 60 Hz),
#      EXTRA_CFG=<file> extra RetroArch settings to append (e.g. integer scaling).
# See docs/shaders.html ("How they were measured") in the project repo.
export XDG_RUNTIME_DIR=/var/run WAYLAND_DISPLAY=wayland-1 DISPLAY=:0 SWAYSOCK=/var/run/sway-ipc.0.sock \
       HOME=/userdata/system XDG_CONFIG_HOME=/userdata/system/configs SDL_NOMOUSE=1

core=$1; rom=$2; out=$3; shift 3
mkdir -p "$out"
cat > /tmp/bench-append.cfg <<'EOF'
video_vsync = "true"
audio_sync = "false"
audio_enable = "false"
video_gpu_screenshot = "true"
video_shader_enable = "true"
fps_show = "false"
pause_nonactive = "false"
EOF

run() { # frames shaderargs...
    local frames=$1; shift
    local t0=$(date +%s.%N)
    timeout 120 /usr/bin/retroarch -L "/usr/lib/libretro/${core}_libretro.so" \
        --config /userdata/system/configs/retroarch/retroarchcustom.cfg \
        --appendconfig "/tmp/bench-append.cfg${EXTRA_CFG:+|$EXTRA_CFG}" "$@" --max-frames="$frames" \
        --max-frames-ss --max-frames-ss-path="$out/last.png" "$rom" >/dev/null 2>&1
    local rc=$?
    local t1=$(date +%s.%N)
    echo "$rc $(echo "$t1 - $t0" | bc -l)"
}

for sh in "$@"; do
    if [ "$sh" = none ]; then args=(); name=none; else args=(--set-shader "$sh"); name=$(basename "$sh" .glslp); fi
    read rc1 ta < <(run 120 "${args[@]}")
    read rc2 tb < <(run $((120 + ${LONG:-1200})) "${args[@]}")
    [ -f "$out/last.png" ] && mv "$out/last.png" "$out/$name.png"
    fps=$(echo "${LONG:-1200} / ($tb - $ta)" | bc -l 2>/dev/null)
    printf "%-45s fps=%7.1f  rc=%s/%s\n" "$name" "${fps:-0}" "$rc1" "$rc2"
done

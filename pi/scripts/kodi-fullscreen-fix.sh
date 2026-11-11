#!/bin/bash
# Installed to /userdata/system/scripts/. Batocera's emulatorlauncher runs every executable
# here with: gameStart|gameStop <system> <emulator> <core> <rom>, and waits for it to return.
#
# Kodi 21 on Batocera's sway sometimes comes up with its full-screen picture shifted 19 px
# down (bottom rows cut, black band at the top), although Kodi's own frame is correct.
# Switching sway's full screen off and on again once Kodi's window exists fixes it.
[ "$1" = "gameStart" ] && [ "$2" = "kodi" ] || exit 0
(
    export SWAYSOCK=/var/run/sway-ipc.0.sock XDG_RUNTIME_DIR=/var/run
    for _ in $(seq 1 60); do
        swaymsg -t get_tree 2>/dev/null | grep -q '"app_id": "Kodi"' && break
        sleep 1
    done
    sleep 4
    swaymsg '[app_id=Kodi] fullscreen disable'
    sleep 0.5
    swaymsg '[app_id=Kodi] fullscreen enable'
) </dev/null >/dev/null 2>&1 &
exit 0

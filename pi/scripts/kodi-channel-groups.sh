#!/bin/bash
# Installed to /userdata/system/scripts/. Batocera's emulatorlauncher runs every executable
# here with: gameStart|gameStop <system> <emulator> <core> <rom>, and waits for it to return.
#
# Before Kodi starts, refresh the list of channel groups Kodi's IPTV Simple loads: every group
# in ErsatzTV's channel list except HD (the HD twins are for the browser viewer, not the CRT).
# If the server can't be reached within a few seconds, the last list is kept.
[ "$1" = "gameStart" ] && [ "$2" = "kodi" ] || exit 0
timeout 8 python3 /userdata/system/display-profiles/kodi_tv_settings.py --groups \
    >> /userdata/system/logs/kodi-channel-groups.log 2>&1
exit 0

#!/bin/bash
# Switch the Pi between display profiles, then reboot.
#   apply.sh hdmi   16:9 flat-panel TV: 1080p output, Trinitron-simulating shaders
#   apply.sh crt    4:3 Sony Trinitron through the HDMI-to-composite converter:
#                   640x480 output (square pixels on 4:3, exactly 2x a 240-line game),
#                   no CRT shaders (the tube does that), handheld color correction only,
#                   Plex (PM4K) limited to 480p at 1.5 Mbps (Kodi decodes in software here)
# Installed at /userdata/system/display-profiles/apply.sh and run from the two
# "Display" entries under Ports. Both profiles give a picture on either TV, so a wrong
# choice is never a lockout: just pick the other entry.
# Add "--no-reboot" to apply without rebooting (for testing).

set -u
profile=${1:-}
LOG=/userdata/system/logs/display-profile.log
BOOTCONF=/boot/batocera-boot.conf
CONF=/userdata/system/batocera.conf
BACKUPS=/userdata/system/display-profiles/backups

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

case "$profile" in
    hdmi)
        shaderset=trinitron-hdmi
        resolution=""            # Batocera default: best mode up to 1920x1080
        gba_integerscale=""      # use the global setting (integer scaling on)
        plex_quality=""          # PM4K default (16 = original quality)
        ;;
    crt)
        shaderset=trinitron-crt
        resolution=max-640x480
        gba_integerscale=0       # 3x does not fit 640 wide; fill the screen instead
        plex_quality=5           # PM4K index 5 = 720x480 at 1.5 Mbps, like the ErsatzTV channels
        ;;
    *)
        echo "usage: $0 hdmi|crt [--no-reboot]" >&2
        exit 1
        ;;
esac

log "switching to '$profile'"
mkdir -p "$BACKUPS"
stamp=$(date +%Y%m%d-%H%M%S)
cp "$CONF" "$BACKUPS/batocera.conf.$stamp"
cp "$BOOTCONF" "$BACKUPS/batocera-boot.conf.$stamp"

# Settings shared by both profiles, set every time so the profile is complete.
batocera-settings-set global.shaderset "$shaderset"
batocera-settings-set global.integerscale 1
batocera-settings-set global.smooth 0
batocera-settings-set global.bezel none
if [ -n "$gba_integerscale" ]; then
    batocera-settings-set gba.integerscale "$gba_integerscale"
else
    sed -i '/^gba\.integerscale=/d' "$CONF"
fi

# Output resolution: the menu reads es.resolution from the boot partition at startup, but the
# shutdown service S65values4boot copies es.resolution from batocera.conf over it on every
# reboot. So batocera.conf is the master: set it there, and in the boot file too so the
# two agree even if the shutdown sync doesn't run. Empty = Batocera default (best mode
# up to 1920x1080).
batocera-settings-set es.resolution "$resolution"
mount -o remount,rw /boot
batocera-settings-set -f "$BOOTCONF" es.resolution "$resolution"

# CRT overscan: the Pi's HDMI output has hardware margins (DRM "left/right/top/bottom margin",
# 0-100 px). They shrink the whole picture inside the frame, so the menu, Kodi and games all
# clear the tube's hidden edges, while apps still render 640x480 (integer scaling unaffected).
# They can only be set at boot, via a video= option on the kernel command line. Ours is
# appended last, so it overrides the video= the firmware adds. Measured on the Trinitron
# with an overscan test pattern; edit crt-margins.conf to fine-tune.
CMDLINE=/boot/cmdline.txt
cp "$CMDLINE" "$BACKUPS/cmdline.txt.$stamp"
sed -i -E 's/ ?video=HDMI-A-1:[^ ]*//g' "$CMDLINE"
if [ "$profile" = crt ]; then
    MARGINS=/userdata/system/display-profiles/crt-margins.conf
    [ -f "$MARGINS" ] || printf 'left=13\nright=27\ntop=0\nbottom=20\n' > "$MARGINS"
    . "$MARGINS"
    sed -i -E "1 s/\$/ video=HDMI-A-1:640x480@60,margin_left=${left},margin_right=${right},margin_top=${top},margin_bottom=${bottom}/" "$CMDLINE"
fi
log "cmdline: $(cat "$CMDLINE")"
sync
mount -o remount,ro /boot

# Plex (PM4K) streaming quality. PM4K keeps local/remote/online quality in Kodi's settings
# file for the add-on. Kodi rewrites that file when it exits, so close Kodi first.
PM4K_SETTINGS=/userdata/system/.kodi/userdata/addon_data/script.plexmod/settings.xml
if ps -eo args | grep -q "^/usr/lib/kodi/[k]odi.bin"; then
    log "closing Kodi so it can't overwrite its settings"
    pkill -TERM -f "^/usr/lib/kodi/[k]odi.bin"
    for i in $(seq 1 15); do ps -eo args | grep -q "^/usr/lib/kodi/[k]odi.bin" || break; sleep 1; done
fi
if [ -f "$PM4K_SETTINGS" ]; then
    cp "$PM4K_SETTINGS" "$BACKUPS/pm4k-settings.xml.$stamp"
    python3 - "$PM4K_SETTINGS" "$plex_quality" <<'EOF'
import sys, xml.etree.ElementTree as ET
path, quality = sys.argv[1], sys.argv[2]
tree = ET.parse(path)
root = tree.getroot()
for key in ("local_quality2", "remote_quality2", "online_quality2"):
    for el in root.findall(f"setting[@id='{key}']"):
        root.remove(el)
    if quality:
        el = ET.SubElement(root, "setting", id=key)
        el.text = quality
ET.indent(tree, space="    ")
tree.write(path, encoding="utf-8")
EOF
fi

# Kodi live TV. Both profiles: Select in the guide switches channel, guide refresh every
# 15 minutes, Circle opens the guide without stopping the show (kodi_tv_settings.py).
# Trinitron: the "Estuary CRT" skin with the retro guide (make_kodi_crt_skin.sh, rebuilt
# from stock Estuary each time); HDMI: stock Estuary. Kodi is closed at this point.
KODI_GUI=/userdata/system/.kodi/userdata/guisettings.xml
python3 /userdata/system/display-profiles/kodi_tv_settings.py >> "$LOG" 2>&1
if [ "$profile" = crt ]; then
    /userdata/system/display-profiles/make_kodi_crt_skin.sh >> "$LOG" 2>&1 && kodi_skin=skin.estuary.crt || kodi_skin=skin.estuary
else
    kodi_skin=skin.estuary
fi
if [ -f "$KODI_GUI" ]; then
    cp "$KODI_GUI" "$BACKUPS/guisettings.xml.$stamp"
    sed -i -E "s|<setting id=\"lookandfeel.skin\"[^>]*>[^<]*</setting>|<setting id=\"lookandfeel.skin\">$kodi_skin</setting>|" "$KODI_GUI"
fi
log "kodi skin: $kodi_skin"

# Batocera Control Center (Hotkey + A): at 640x480 it still picks its full-size layout and
# runs off the right edge. Trinitron mode installs a compact stylesheet, rebuilt from the
# stock one each time so it follows Batocera updates; HDMI mode removes it (stock look).
BCC_CSS=/userdata/system/configs/controlcenter/style.css
# Both profiles: a Control Center layout without the Plane Mode toggle, which stops Bluetooth
# and so disconnects the controller you'd need to turn it back on.
mkdir -p "$(dirname "$BCC_CSS")"
python3 /userdata/system/display-profiles/make_bcc_layout.py \
    /usr/share/batocera/controlcenter/controlcenter.xml \
    /userdata/system/configs/controlcenter/controlcenter.xml >> "$LOG" 2>&1
if [ "$profile" = crt ]; then
    mkdir -p "$(dirname "$BCC_CSS")"
    python3 /userdata/system/display-profiles/make_bcc_compact_css.py \
        /usr/share/batocera/controlcenter/style.css "$BCC_CSS" 12 >> "$LOG" 2>&1
elif grep -q "make_bcc_compact_css" "$BCC_CSS" 2>/dev/null; then
    rm -f "$BCC_CSS"
fi

# Menu theme: the Trinitron uses a copy of carbon with bold, bigger, solid-white game titles
# (make_crt_theme.sh, rebuilt each time so it follows Batocera updates); HDMI uses stock carbon.
# The menu doesn't rewrite es_settings.cfg on shutdown, so editing it while it runs is safe.
ES_SETTINGS=/userdata/system/configs/emulationstation/es_settings.cfg
if [ "$profile" = crt ]; then
    /userdata/system/display-profiles/make_crt_theme.sh >> "$LOG" 2>&1 && theme=es-theme-carbon-crt || theme=es-theme-carbon
else
    theme=es-theme-carbon
fi
if grep -q '<string name="ThemeSet"' "$ES_SETTINGS"; then
    sed -i "s|<string name=\"ThemeSet\" value=\"[^\"]*\"|<string name=\"ThemeSet\" value=\"$theme\"|" "$ES_SETTINGS"
else
    sed -i "s|</config>|\t<string name=\"ThemeSet\" value=\"$theme\" />\n</config>|" "$ES_SETTINGS"
fi
log "theme: $theme"

echo "$profile" > /userdata/system/display-profiles/current
log "applied: shaderset=$shaderset resolution=${resolution:-default} gba.integerscale=${gba_integerscale:-global} plex_quality=${plex_quality:-default}"

if [ "${2:-}" != "--no-reboot" ]; then
    log "rebooting"
    sync
    reboot
fi

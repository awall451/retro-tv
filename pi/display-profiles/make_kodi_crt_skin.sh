#!/bin/bash
# Build /userdata/system/.kodi/addons/skin.estuary.crt: a copy of Kodi's stock Estuary skin
# for the Trinitron, with
#   - a retro cable-style TV guide (kodi-skin/MyPVRGuide.xml),
#   - Cabin Bold fonts crt_* (the same font as the CRT game-menu titles),
# and register it as an enabled add-on in Kodi's database.
# Rebuilt from the stock skin on every switch to the Trinitron, so Batocera updates carry over.
# Kodi must not be running (apply.sh closes it first). Selecting the skin is apply.sh's job.
set -eu
HERE=/userdata/system/display-profiles
SRC=/usr/share/kodi/addons/skin.estuary
DST=/userdata/system/.kodi/addons/skin.estuary.crt
FONT=/usr/share/emulationstation/themes/es-theme-carbon/art/fonts/Cabin-Bold.ttf
DB=$(ls /userdata/system/.kodi/userdata/Database/Addons*.db 2>/dev/null | sort -V | tail -1)

if ps -eo args | grep -q "^/usr/lib/kodi/[k]odi.bin"; then
    echo "make_kodi_crt_skin: Kodi is running; close it first" >&2
    exit 1
fi

rm -rf "$DST.tmp"
mkdir -p "$(dirname "$DST")"
cp -a "$SRC" "$DST.tmp"
sed -i -e 's/id="skin.estuary"/id="skin.estuary.crt"/' -e 's/name="Estuary"/name="Estuary CRT"/' "$DST.tmp/addon.xml"
cp "$FONT" "$DST.tmp/fonts/Cabin-Bold.ttf"
cp "$HERE/kodi-skin/MyPVRGuide.xml" "$DST.tmp/xml/MyPVRGuide.xml"
cp "$HERE/kodi-skin/DialogPVRInfo.xml" "$DST.tmp/xml/DialogPVRInfo.xml"

# Add the crt_* fonts to every fontset. Sizes are in 1920x1440 units: divide by 3 for real pixels.
python3 - "$DST.tmp/xml/Font.xml" <<'PY'
import re, sys
path = sys.argv[1]
fonts = [("crt_guide", 45), ("crt_title", 63), ("crt_info", 48), ("crt_plot", 42), ("crt_big", 72)]
block = "".join(
    "\n\t\t<font><name>%s</name><filename>Cabin-Bold.ttf</filename><size>%d</size></font>" % f
    for f in fonts)
text = open(path, encoding="utf-8").read()
text, n = re.subn(r'(<fontset id="[^"]*"[^>]*>)', lambda m: m.group(1) + block, text)
if n == 0:
    sys.exit("no <fontset> found in Font.xml")
open(path, "w", encoding="utf-8").write(text)
print("fonts added to %d fontsets" % n)
PY

rm -rf "$DST"
mv "$DST.tmp" "$DST"

# Kodi disables add-ons copied in by hand until they're enabled; enable it in the add-on database.
if [ -n "$DB" ]; then
    python3 - "$DB" <<'PY'
import sqlite3, sys, datetime
c = sqlite3.connect(sys.argv[1])
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
c.execute("INSERT OR IGNORE INTO installed (addonID, enabled, installDate, origin) VALUES (?, 1, ?, '')",
          ("skin.estuary.crt", now))
c.execute("UPDATE installed SET enabled = 1, disabledReason = 0 WHERE addonID = ?", ("skin.estuary.crt",))
c.commit()
PY
fi

# Start from the stock skin's settings (home menu items etc.) the first time.
SET=/userdata/system/.kodi/userdata/addon_data
if [ -f "$SET/skin.estuary/settings.xml" ] && [ ! -f "$SET/skin.estuary.crt/settings.xml" ]; then
    mkdir -p "$SET/skin.estuary.crt"
    cp "$SET/skin.estuary/settings.xml" "$SET/skin.estuary.crt/settings.xml"
fi
echo "make_kodi_crt_skin: built $DST"

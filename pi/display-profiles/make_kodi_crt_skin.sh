#!/bin/bash
# Build /userdata/system/.kodi/addons/skin.estuary.crt: a copy of Kodi's stock Estuary skin
# for the Trinitron, with
#   - a retro cable-style TV guide (kodi-skin/MyPVRGuide.xml) that Home → TV opens,
#   - a big-text show details pop-up (kodi-skin/DialogPVRInfo.xml),
#   - a channel banner while watching live TV (kodi-skin/crt-banner.xml, into DialogSeekBar.xml),
#   - every font 1.5x bigger and in Cabin Bold (the same font as the CRT game-menu titles),
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
fonts = [("crt_guide", 45), ("crt_title", 63), ("crt_info", 48), ("crt_plot", 42), ("crt_big", 72),
         ("crt_num", 108)]
block = "".join(
    "\n\t\t<font><name>%s</name><filename>Cabin-Bold.ttf</filename><size>%d</size></font>" % f
    for f in fonts)
text = open(path, encoding="utf-8").read()

# Every stock font: Cabin Bold, bigger. Estuary draws a 4:3 screen on a 1920x1440 canvas, so at
# 640x480 its text is a third of the designed size (list text 8-10 px). x1.5 brings body text to
# ~15 px like the guide; big display fonts (45 and up) only x1.25 so headings still fit. The
# "lighten" style is dropped (it thins strokes, which flicker on 480i). Monospace stays as is.
def bigger(m):
    block = m.group(0)
    if "Mono" in block:
        return block
    size = int(re.search(r"<size>(\d+)</size>", block).group(1))
    # the top-right clock sits against the screen edge: grow it only 10%
    factor = 1.1 if "<name>font_clock</name>" in block else (1.5 if size < 45 else 1.25)
    new = round(size * factor)
    block = re.sub(r"<size>\d+</size>", "<size>%d</size>" % new, block)
    block = re.sub(r"<filename>[^<]+</filename>", "<filename>Cabin-Bold.ttf</filename>", block)
    return re.sub(r"\s*<style>lighten</style>", "", block)
text, scaled = re.subn(r"<font>.*?</font>", bigger, text, flags=re.S)
print("scaled %d stock fonts" % scaled)

text, n = re.subn(r'(<fontset id="[^"]*"[^>]*>)', lambda m: m.group(1) + block, text)
if n == 0:
    sys.exit("no <fontset> found in Font.xml")
open(path, "w", encoding="utf-8").write(text)
print("fonts added to %d fontsets" % n)
PY

# Live TV: our channel banner replaces Estuary's info while watching (Info / channel change),
# and Home's TV item opens the retro guide instead of the channel list. Each patch must match
# exactly once; if a Batocera update changes Estuary, fail so apply.sh falls back to stock.
python3 - "$DST.tmp/xml" "$HERE/kodi-skin/crt-banner.xml" <<'PY'
import re, sys
xml, banner_file = sys.argv[1], sys.argv[2]
BANNER = ("[Player.ShowInfo | Window.IsActive(fullscreeninfo)] + VideoPlayer.Content(LiveTV)"
          " + !Window.IsVisible(videoosd)")

def patch(name, old, new, count=1):
    path = "%s/%s" % (xml, name)
    text = open(path, encoding="utf-8").read()
    found = text.count(old)
    if found < count:
        sys.exit("make_kodi_crt_skin: %s: expected %d x %r, found %d" % (name, count, old[:60], found))
    open(path, "w", encoding="utf-8").write(text.replace(old, new, count))
    print("patched %s" % name)

seek = "DialogSeekBar.xml"
# Estuary's own live-TV info group: only together with the on-screen controls now.
live_info = "<visible>[Player.ShowInfo | Window.IsActive(fullscreeninfo)] + VideoPlayer.Content(LiveTV)</visible>"
patch(seek, live_info, live_info + "\n\t\t\t<visible>Window.IsVisible(videoosd)</visible>")
# Bottom time/progress bar: hidden while the banner shows.
bar = "<visible>Player.ShowInfo | Window.IsActive(fullscreeninfo) | Player.ShowTime"
patch(seek, bar, "<visible>![%s]</visible>\n\t\t\t%s" % (BANNER, bar))
# The banner itself, at the end of the dialog.
banner = open(banner_file, encoding="utf-8").read()
banner = re.sub(r"<!--.*?-->\s*", "", banner, count=1, flags=re.S)
path = "%s/%s" % (xml, seek)
text = open(path, encoding="utf-8").read()
cut = text.rfind("</controls>")
if cut < 0:
    sys.exit("make_kodi_crt_skin: no </controls> in %s" % seek)
open(path, "w", encoding="utf-8").write(text[:cut] + banner + "\n\t" + text[cut:])
print("inserted banner into %s" % seek)
# Top bar (title, clock, "Ends at"): out of the way while the banner shows.
top = '<window type="dialog" id="1109">'
patch("Custom_1109_TopBarOverlay.xml", top, top + "\n\t<visible>![%s]</visible>" % BANNER)
# Home → TV opens the guide.
patch("Home.xml", "<onclick>ActivateWindow(TVChannels)</onclick>", "<onclick>ActivateWindow(TVGuide)</onclick>")
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

#!/bin/bash
# Build /userdata/themes/es-theme-carbon-crt: Batocera's carbon theme with game titles made
# readable on the Trinitron (640x480, 480i composite).
#   Stock grid titles: 2.2% of screen height (~11 px at 480), 50% transparent, Cabin Regular.
#   CRT copy:          3.4% (~16 px), solid white, Cabin Bold. Thin 1-px strokes flicker
#                      between interlaced fields and faint grey smears over composite.
# The 179 MB of artwork is linked, not copied. Rebuilt on every switch to the Trinitron
# profile (apply.sh crt), so it follows Batocera updates to the stock theme.
set -eu
SRC=/usr/share/emulationstation/themes/es-theme-carbon
DST=/userdata/themes/es-theme-carbon-crt

rm -rf "$DST"
mkdir -p "$DST"
for item in "$SRC"/*; do
    name=$(basename "$item")
    if [ "$name" = art ]; then
        ln -s "$item" "$DST/art"
    else
        cp -a "$item" "$DST/"
    fi
done

python3 - "$DST/views/grid.xml" <<'EOF'
import re, sys
path = sys.argv[1]
xml = open(path).read()
new = """    <text name="gridtile">
      <color>FFFFFFFF</color>
      <backgroundColor>00000000</backgroundColor>
      <fontPath>./../art/fonts/Cabin-Bold.ttf</fontPath>
      <fontSize>0.034</fontSize>
      <alignment>center</alignment>
      <size>1 0.24</size>
    </text>"""
xml, n = re.subn(r'    <text name="gridtile">.*?</text>', new, xml, count=1, flags=re.S)
if n != 1:
    sys.exit("gridtile text block not found in " + path)
open(path, "w").write(xml)
EOF
# Carbon's default game-list view is "Icons", which draws each title with its own text
# element, textOfGame in views/icons.xml ({game:fullNameNoTags}: 2.2% of screen height,
# Cabin Regular), not with the grid rule above. Make it bold, 3.0% (~14 px), stronger outline.
python3 - "$DST/views/icons.xml" <<'EOF'
import re, sys
path = sys.argv[1]
xml = open(path).read()
start = xml.find('<text name="textOfGame">')
if start < 0:
    sys.exit("textOfGame not found in " + path)
end = xml.find("<storyboard", start)
block = xml[start:end]
block = block.replace("Cabin-Regular.ttf", "Cabin-Bold.ttf")
block = re.sub(r"<fontSize>[^<]*</fontSize>", "<fontSize>0.030</fontSize>", block, count=1)
block = re.sub(r"<glowColor>[^<]*</glowColor>", "<glowColor>000000C0</glowColor>", block, count=1)
xml = xml[:start] + block + xml[end:]
open(path, "w").write(xml)
print("icons.xml: textOfGame patched")
EOF
echo "built $DST"

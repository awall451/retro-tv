#!/usr/bin/env python3
"""Unpack the viewer's web fonts for the splash renderer.

The viewer ships its fonts as WOFF2 (docker/web/app/fonts); the rasterizer
behind render.mjs (resvg) reads TTF/OTF only. This writes a TTF next to each
WOFF2 into fonts/ttf/ here (git-ignored), keeping the family names and weights
the viewer's CSS uses, so the scenes render with the same type as the browser.

Needs the fonttools and brotli Python packages:  pip install fonttools brotli
Run from this folder:  python fonts.py
"""
import pathlib
import sys

try:
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("fonttools (and brotli) are needed: pip install fonttools brotli")

here = pathlib.Path(__file__).resolve().parent
src = here.parent.parent / "docker" / "web" / "app" / "fonts"
out = here / "fonts" / "ttf"
out.mkdir(parents=True, exist_ok=True)

count = 0
for woff2 in sorted(src.glob("*.woff2")):
    ttf = out / (woff2.stem + ".ttf")
    if ttf.exists() and ttf.stat().st_mtime >= woff2.stat().st_mtime:
        continue
    font = TTFont(str(woff2))
    font.flavor = None          # plain sfnt: a TTF
    font.save(str(ttf))
    count += 1
print(f"{count} font(s) unpacked into {out.relative_to(here)}")

# The Roku app needs the themes' faces as TTF too (roku-tv/fonts, committed).
# Cabin and Audiowide are already there as full files.
roku = here.parent.parent / "roku-tv" / "fonts"
ROKU = {
    "arimo-latin-400-normal": "Arimo-Regular", "arimo-latin-700-normal": "Arimo-Bold",
    "exo-2-latin-400-normal": "Exo2-Regular", "exo-2-latin-800-normal": "Exo2-ExtraBold",
    "nunito-latin-400-normal": "Nunito-Regular", "nunito-latin-800-normal": "Nunito-ExtraBold",
    "open-sans-latin-300-normal": "OpenSans-Light", "open-sans-latin-400-normal": "OpenSans-Regular",
    "open-sans-latin-600-normal": "OpenSans-SemiBold",
    "lato-latin-400-normal": "Lato-Regular", "lato-latin-700-normal": "Lato-Bold",
    "chakra-petch-latin-400-normal": "ChakraPetch-Regular", "chakra-petch-latin-700-normal": "ChakraPetch-Bold",
    "archivo-black-latin-400-normal": "ArchivoBlack-Regular",
}
import shutil
for stem, name in ROKU.items():
    shutil.copyfile(out / (stem + ".ttf"), roku / (name + ".ttf"))
shutil.copyfile(src / "PrevueGrid.ttf", roku / "PrevueGrid.ttf")
for notice in list(src.glob("*-LICENSE-OFL.txt")) + [src / "PrevueGrid-NOTICE.txt"]:
    if notice.name.split("-")[0] in {"Arimo", "Exo2", "Nunito", "OpenSans", "Lato", "ChakraPetch", "ArchivoBlack", "PrevueGrid"}:
        shutil.copyfile(notice, roku / notice.name)
print(f"{len(ROKU) + 1} font(s) copied into roku-tv/fonts")


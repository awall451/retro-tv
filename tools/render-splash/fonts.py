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

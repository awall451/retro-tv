#!/usr/bin/env python3
"""Turn the Roku theme splashes that render.mjs left in out/ into JPEGs in
roku-tv/images (splash_<theme>_fhd.jpg). Needs Pillow:  pip install pillow
"""
import pathlib
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is needed: pip install pillow")

here = pathlib.Path(__file__).resolve().parent
dest = here.parent.parent / "roku-tv" / "images"
for png in sorted((here / "out").glob("splash_*_fhd.png")):
    jpg = dest / (png.stem + ".jpg")
    Image.open(png).convert("RGB").save(jpg, quality=90, optimize=True)
    print(f"roku-tv/images/{jpg.name} {jpg.stat().st_size // 1024} KB")

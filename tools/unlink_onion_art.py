"""Move box art imported from the Miyoo (Onion) back out of Batocera, so the scraper refills it.

Usage: python3 unlink_onion_art.py <roms_dir> <dest_dir> <system> [<system> ...] [--dry-run]
An entry counts as Miyoo-imported when it is the shape import_onion.py / import_onion_psx.py
wrote: path, name, image (and optionally hidden) and nothing else. Batocera's bundled games
carry descriptions, developers etc., so they are left alone. Each image moves to
<dest_dir>/<system>/ and the <image> line is removed from gamelist.xml (backup: gamelist.xml.bak-art).
"""
import os
import shutil
import sys
import xml.etree.ElementTree as ET

IMPORT_SHAPE = {"path", "name", "image", "hidden"}


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    roms, dest, systems = args[0], args[1], args[2:]
    total = 0
    for system in systems:
        sysdir = os.path.join(roms, system)
        gamelist = os.path.join(sysdir, "gamelist.xml")
        if not os.path.isfile(gamelist):
            print(f"{system:10} no gamelist.xml, skipped")
            continue
        tree = ET.parse(gamelist)
        moved = kept = missing = 0
        for game in tree.getroot().findall("game"):
            img = game.find("image")
            if img is None or not img.text:
                continue
            if {child.tag for child in game} - IMPORT_SHAPE:
                kept += 1  # has scraped/bundled metadata: not ours
                continue
            src = os.path.join(sysdir, img.text)
            if not dry:
                if os.path.isfile(src):
                    os.makedirs(os.path.join(dest, system), exist_ok=True)
                    shutil.move(src, os.path.join(dest, system, os.path.basename(src)))
                game.remove(img)
            if os.path.isfile(src) or not dry:
                moved += 1
            else:
                missing += 1
        if not dry and moved:
            shutil.copy2(gamelist, gamelist + ".bak-art")
            ET.indent(tree, space="  ")
            tree.write(gamelist, encoding="UTF-8", xml_declaration=True)
        total += moved
        print(f"{system:10} {'would move' if dry else 'moved'}: {moved:4}   kept (bundled/scraped): {kept}"
              + (f"   image file missing: {missing}" if missing else ""))
    print(f"total {'to move' if dry else 'moved'}: {total}")


if __name__ == "__main__":
    main()

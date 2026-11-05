"""Move Onion (Miyoo) PS1 games (.cue + .bin tracks) into Batocera's psx folder.

Usage: python3 import_onion_psx.py <onion_ps_dir> <batocera_psx_dir> <broken_art_dir> [--dry-run]
- Each .cue moves with every track file it references (all must exist, or the game is skipped).
- Multi-disc games ("... (Disc N).cue") get one "<game>.m3u" playlist; the discs are hidden
  in gamelist.xml so the game shows once and discs switch in-game.
- Art: Imgs/<game>.png, else Imgs/<game> (Track 01).png, checked with png_ok() from
  import_onion.py; broken images go to <broken_art_dir>.
"""
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from import_onion import display_name, png_ok  # noqa: E402

DISC_RE = re.compile(r"\s*\(Disc (\d+)\)", re.I)


def cue_tracks(path):
    tracks = []
    for line in open(path, errors="replace"):
        m = re.match(r'\s*FILE\s+"(.+?)"', line, re.I) or re.match(r"\s*FILE\s+(\S+)", line, re.I)
        if m:
            tracks.append(m.group(1))
    return tracks


def find_art(imgs, stem):
    for cand in (stem, stem + " (Track 01)", stem + " (Track 1)"):
        p = os.path.join(imgs, cand + ".png")
        if os.path.isfile(p):
            return p
    return None


def main():
    src, dst, broken_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    dry = "--dry-run" in sys.argv
    imgs_src, imgs_dst = os.path.join(src, "Imgs"), os.path.join(dst, "images")
    gamelist = os.path.join(dst, "gamelist.xml")
    if os.path.exists(gamelist):
        tree = ET.parse(gamelist)
    else:
        tree = ET.ElementTree(ET.Element("gameList"))
    root = tree.getroot()
    known = {g.findtext("path") for g in root.findall("game")}

    def add_entry(rel, name, image=None, hidden=False):
        if rel in known:
            return
        g = ET.SubElement(root, "game")
        ET.SubElement(g, "path").text = rel
        ET.SubElement(g, "name").text = name
        if image:
            ET.SubElement(g, "image").text = image
        if hidden:
            ET.SubElement(g, "hidden").text = "true"
        known.add(rel)

    def move(name):
        if not dry:
            shutil.move(os.path.join(src, name), os.path.join(dst, name))

    def place_art(stem):
        """Validate and move art for stem; return gamelist image path or None."""
        art = find_art(imgs_src, stem)
        if not art:
            return None, "no art"
        if not png_ok(art):
            if not dry:
                os.makedirs(broken_dir, exist_ok=True)
                shutil.move(art, os.path.join(broken_dir, os.path.basename(art)))
            return None, "broken art"
        name = stem + "-image.png"
        if not dry:
            os.makedirs(imgs_dst, exist_ok=True)
            shutil.move(art, os.path.join(imgs_dst, name))
        return "./images/" + name, None

    cues = sorted(f for f in os.listdir(src) if f.lower().endswith(".cue"))
    sets = {}
    games = discs = art = skipped = 0
    for cue in cues:
        tracks = cue_tracks(os.path.join(src, cue))
        missing = [t for t in tracks if not os.path.isfile(os.path.join(src, t))]
        if not tracks or missing or os.path.exists(os.path.join(dst, cue)):
            print("  SKIP", cue, "missing tracks:" if missing else "(already there or empty)", missing)
            skipped += 1
            continue
        stem = cue[:-4]
        image, problem = place_art(stem)
        for t in tracks:
            move(t)
        move(cue)
        m = DISC_RE.search(stem)
        if m:
            # Everything before "(Disc N)": "Red Alert (USA) (Disc 2) (Soviet)" -> "Red Alert (USA)"
            base = stem[:m.start()].strip()
            sets.setdefault(base, []).append((int(m.group(1)), cue, image))
            add_entry("./" + cue, display_name(stem) + f" (Disc {m.group(1)})", image, hidden=True)
            discs += 1
        else:
            add_entry("./" + cue, display_name(stem), image)
            games += 1
            art += bool(image)
        if problem:
            print("  ", problem + ":", cue)

    for base, ds in sorted(sets.items()):
        ds.sort()
        m3u = base + ".m3u"
        if not dry:
            with open(os.path.join(dst, m3u), "w") as fh:
                fh.write("\n".join(cue for _, cue, _ in ds) + "\n")
        image = next((img for _, _, img in ds if img), None)
        add_entry("./" + m3u, display_name(base), image)
        games += 1
        art += bool(image)
        print(f"  playlist: {m3u}  ({len(ds)} discs)")

    if not dry:
        ET.indent(tree, space="  ")
        tree.write(gamelist, encoding="UTF-8", xml_declaration=True)
    print(f"{'(dry run) ' if dry else ''}games shown: {games} (with art: {art}), "
          f"discs hidden behind playlists: {discs}, skipped: {skipped}")


if __name__ == "__main__":
    main()

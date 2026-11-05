"""Move an Onion (Miyoo) ROM folder into a Batocera system folder and link its box art.

Usage: python3 import_onion.py <onion_dir> <batocera_system_dir> <broken_art_dir> [--dry-run]
Accepted ROM extensions come from <system_dir>/_info.txt. ROMs go to <system_dir>/,
art from <onion_dir>/Imgs/<rom>.png goes to <system_dir>/images/<rom>-image.png when it
decodes cleanly (broken PNGs go to <broken_art_dir>/), and gamelist.xml gets an entry per ROM.
"""
import os
import re
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
import zlib


def accepted_exts(system_dir):
    text = open(os.path.join(system_dir, "_info.txt"), encoding="utf-8", errors="replace").read()
    m = re.search(r'accepted: "([^"]*)"', text)
    return {e.lower() for e in m.group(1).split()}


def png_ok(path):
    # Walk every chunk, check CRCs, require IEND, and inflate the image data.
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    pos, idat = 8, b""
    try:
        while True:
            ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + ln]
            crc, = struct.unpack(">I", data[pos + 8 + ln:pos + 12 + ln])
            if len(body) != ln or zlib.crc32(typ + body) & 0xffffffff != crc:
                return False
            if typ == b"IDAT":
                idat += body
            if typ == b"IEND":
                zlib.decompress(idat)
                return True
            pos += 12 + ln
    except Exception:
        return False


def display_name(stem):
    # "Legend of Zelda, The - A Link to the Past (USA) (Rev 1)" -> "Legend of Zelda, The - A Link to the Past"
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", stem).strip()
    return name or stem


def main():
    src, dst, broken_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    dry = "--dry-run" in sys.argv
    exts = accepted_exts(dst)
    imgs_src = os.path.join(src, "Imgs")
    imgs_dst = os.path.join(dst, "images")
    gamelist = os.path.join(dst, "gamelist.xml")

    if os.path.exists(gamelist):
        tree = ET.parse(gamelist)
        root = tree.getroot()
    else:
        root = ET.Element("gameList")
        tree = ET.ElementTree(root)
    known = {g.findtext("path") for g in root.findall("game")}

    moved = art = broken = skipped = 0
    no_art, other = [], []
    for f in sorted(os.listdir(src)):
        full = os.path.join(src, f)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(f)
        if ext.lower() not in exts:
            other.append(f)
            continue
        if os.path.exists(os.path.join(dst, f)):
            print("  SKIP already there:", f)
            skipped += 1
            continue
        img_src = os.path.join(imgs_src, stem + ".png")
        img_name = stem + "-image.png"
        has_img = os.path.isfile(img_src)
        good_img = has_img and png_ok(img_src)
        if not dry:
            os.makedirs(imgs_dst, exist_ok=True)
            shutil.move(full, os.path.join(dst, f))
            if good_img:
                shutil.move(img_src, os.path.join(imgs_dst, img_name))
            elif has_img:
                os.makedirs(broken_dir, exist_ok=True)
                shutil.move(img_src, os.path.join(broken_dir, stem + ".png"))
        moved += 1
        if has_img and not good_img:
            broken += 1
            no_art.append(f + "  [broken art]")
        elif not has_img:
            no_art.append(f + "  [no art]")
        rel = "./" + f
        if rel in known:
            continue
        game = ET.SubElement(root, "game")
        ET.SubElement(game, "path").text = rel
        ET.SubElement(game, "name").text = display_name(stem)
        if good_img:
            ET.SubElement(game, "image").text = "./images/" + img_name
            art += 1

    if not dry:
        ET.indent(tree, space="  ")
        tree.write(gamelist, encoding="UTF-8", xml_declaration=True)
    print(f"  {'(dry run) ' if dry else ''}ROMs: {moved}, art linked: {art}, broken art: {broken}, "
          f"no art: {moved - art - broken}, skipped: {skipped}")
    for x in no_art:
        print("   -", x)
    if other:
        print("  not a ROM type here (left in place):", other)
    if os.path.isdir(imgs_src) and not dry:
        left = os.listdir(imgs_src)
        if left:
            print("  unmatched images left in Imgs/:", left)


if __name__ == "__main__":
    main()

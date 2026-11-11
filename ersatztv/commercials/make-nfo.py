"""Write guide titles for the content sets as .nfo files next to the clips.

    python3 make-nfo.py OUT_DIR             # every set in guide-titles.tsv
    python3 make-nfo.py OUT_DIR cnn weather # only these sets
    python3 make-nfo.py OUT_DIR --check     # only report clips without a title

OUT_DIR is the folder build.py filled (OUT_DIR/<set>/<clip>). Needs Python
3.8+, nothing else.

Why: ErsatzTV names a local video after its file, so the guide of a channel
that plays these clips as programmes (CNN, News, The Weather Channel, Paid
Programming) reads "capture-a-6954_CaptureA_6954". A movie-style .nfo with
the same name as the clip gives it a title, a year and a description.

Each .nfo also carries the two tags the clip had without one: "filler" and
the set name. ErsatzTV takes folder names as tags only for a video that has
no .nfo, and the collections here are built on those tags, so an .nfo
without them drops the clip from its collection.

After writing: scan the library in ErsatzTV, wait for the scan to end, then
reset the playouts of the channels that play these sets.
"""
import csv
import os
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))


def nfo(row):
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<movie>",
             f"  <title>{escape(row['title'])}</title>"]
    if row["year"]:
        lines.append(f"  <year>{row['year']}</year>")
    if row["date"]:
        lines.append(f"  <premiered>{row['date']}</premiered>")
    if row["plot"]:
        lines.append(f"  <plot>{escape(row['plot'])}</plot>")
    lines += ["  <tag>filler</tag>", f"  <tag>{row['set']}</tag>", "</movie>", ""]
    return "\n".join(lines)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    check = "--check" in argv
    if not args:
        sys.exit(__doc__)
    out, only = args[0], set(args[1:])
    with open(os.path.join(HERE, "guide-titles.tsv"), newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                if not only or r["set"] in only]
    titled = {(r["set"], r["clip"]) for r in rows}
    written = missing = 0
    for r in rows:
        clip = os.path.join(out, r["set"], r["clip"])
        if not os.path.exists(clip):
            missing += 1
            print(f"no such clip: {r['set']}/{r['clip']}")
            continue
        if not check:
            with open(os.path.splitext(clip)[0] + ".nfo", "w", encoding="utf-8") as f:
                f.write(nfo(r))
            written += 1
    for s in sorted({r["set"] for r in rows}):
        folder = os.path.join(out, s)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".nfo") and (s, name) not in titled:
                print(f"no title: {s}/{name}")
    print(f"{written} .nfo files written, {missing} clips in the list not found")


if __name__ == "__main__":
    main(sys.argv[1:])

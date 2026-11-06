"""Rebuild the commercial sets from the Internet Archive.

    python3 build.py OUT_DIR                    # every set
    python3 build.py OUT_DIR fifties starwars   # only these sets
    python3 build.py OUT_DIR --list             # the sets and how many clips each makes
    python3 build.py sheet DIR OUT.jpg          # contact sheet: one frame per clip, to review by eye

Needs Python 3.8+, curl and ffmpeg/ffprobe on the PATH. Nothing else.

What it does, per row of sources.tsv (see README.md for the columns):

1. Downloads the file to OUT_DIR/_downloads/<set>/ and checks it against
   the Internet Archive's md5 where the catalog has one. Downloads resume;
   a file already there with the right md5 is not fetched again.
2. Processes it into OUT_DIR/<set>/, the folder you point ErsatzTV at:
   - copy: used as it is.
   - fit:  a 4:3 picture boxed inside a wider frame is cropped to the
           picture and scaled to 640x480; anything else is copied.
   - split: a reel (many ads recorded back to back) is cut in the middle of
           every black gap; pieces under 8 s are dropped.
   - toonami / christmas: hand-made clean-ups in fixes/, run once the whole
           set is downloaded.
3. Moves every clip that clips.tsv marks "rejected" (with the reason we
   rejected it) to OUT_DIR/_rejected/<set>/. Rejected single clips are not
   downloaded at all.

Rows whose status is "not used" or "not kept" are skipped.

Splitting is repeatable: the same file and the same settings give the same
pieces with the same numbers, which is how the rejects in clips.tsv find
their piece. If your ffmpeg cuts a reel differently, build.py says which
rejects it could not find; look at those pieces yourself (sheet).

Every ffmpeg runs at the lowest CPU priority with two threads, so a
media server on the same machine keeps priority. Run it on a machine
with room: the full build downloads about 20 GB and keeps about 13 GB.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_S = 8.0
LONG_S = 130.0
VIDEO = (".mp4", ".mkv", ".avi", ".mpg", ".mpeg", ".mov", ".m4v", ".wmv", ".webm")
NICE = ["nice", "-n", "19"] if shutil.which("nice") else []


def read_tsv(name):
    with open(os.path.join(HERE, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


# ---------------------------------------------------------------- download

def md5sum(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(row, folder):
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, row["file"])
    want = row["md5"]
    if os.path.exists(dest) and (not want or md5sum(dest) == want):
        return dest
    part = dest + ".part"
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "-L", "--fail", "-C", "-", "--retry", "3",
                            "--retry-delay", "5", "-o", part, row["url"]])
        if r.returncode == 0:
            break
    else:
        print("  DOWNLOAD FAILED", row["url"], flush=True)
        return None
    if want and md5sum(part) != want:
        print("  MD5 MISMATCH, kept as .part:", row["file"], flush=True)
        return None
    os.replace(part, dest)
    return dest


# ---------------------------------------------------------------- video

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True).stdout
    d = json.loads(out or "{}")
    s = (d.get("streams") or [{}])[0]
    return s.get("width", 0), s.get("height", 0), float(d.get("format", {}).get("duration", 0) or 0)


def picture(path, duration, samples=3):
    """(w, h, x, y) of the area that is not black bars, the most common over a few samples."""
    seen = {}
    for i in range(samples):
        at = duration * (i + 1) / (samples + 1)
        err = subprocess.run(NICE + ["ffmpeg", "-v", "info", "-ss", "%.2f" % at, "-i", path, "-t", "3",
                              "-vf", "cropdetect=24:2:0", "-an", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        for m in re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", err):
            seen[m] = seen.get(m, 0) + 1
    if not seen:
        return None
    return tuple(int(v) for v in max(seen, key=seen.get))


def crop_filter(width, height, crop):
    """A crop to the 4:3 picture when it sits inside a wider frame, else None."""
    if not crop or not width:
        return None
    w, h, x, y = crop
    if not (w < width * 0.9 and h > height * 0.85 and 1.2 < w / max(h, 1) < 1.45):
        return None
    nw = min(width, round(h * 4 / 3 / 2) * 2)
    nx = max(0, min(width - nw, x + (w - nw) // 2))
    return "crop=%d:%d:%d:%d" % (nw, h, nx, y)


def encode(src, dst, vf, start=None, end=None):
    cmd = NICE + ["ffmpeg", "-v", "error", "-y", "-threads", "2"]
    if start is not None:
        cmd += ["-ss", "%.3f" % start, "-to", "%.3f" % end]
    cmd += ["-i", src, "-vf", vf + ",scale=640:480,setsar=1", "-r", "30000/1001",
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)


def black_gaps(path):
    err = subprocess.run(NICE + ["ffmpeg", "-v", "info", "-i", path, "-vf",
                          "blackdetect=d=0.05:pic_th=0.95:pix_th=0.12", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def split(path, out_dir):
    width, height, duration = probe(path)
    vf = crop_filter(width, height, picture(path, duration, 6)) or "null"
    cuts = [0.0] + [(a + b) / 2 for a, b in black_gaps(path)] + [duration]
    base = os.path.splitext(os.path.basename(path))[0]
    made = []
    for n, (start, end) in enumerate(zip(cuts, cuts[1:]), 1):
        if end - start < MIN_S:
            continue
        out = os.path.join(out_dir, "%s_%03d_%ds.mp4" % (base, n, round(end - start)))
        if not os.path.exists(out):
            encode(path, out, vf, start, end)
        made.append(os.path.basename(out))
    return made


def fit(path, out_dir):
    width, height, duration = probe(path)
    if not duration:
        print("  UNREADABLE", path, flush=True)
        return None
    vf = crop_filter(width, height, picture(path, duration))
    name = os.path.basename(path)
    if vf:
        out = os.path.join(out_dir, os.path.splitext(name)[0] + "_43.mp4")
        if not os.path.exists(out):
            encode(path, out, vf)
    else:
        out = os.path.join(out_dir, name)
        if not os.path.exists(out):
            shutil.copyfile(path, out)
    return os.path.basename(out)


def sheet(directory, out):
    names = sorted(n for n in os.listdir(directory) if n.lower().endswith(VIDEO))
    tmp = out + ".frames"
    os.makedirs(tmp, exist_ok=True)
    for i, name in enumerate(names):
        path = os.path.join(directory, name)
        duration = probe(path)[2]
        subprocess.run(NICE + ["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % (duration * 0.4), "-i", path,
                        "-frames:v", "1", "-vf", "scale=200:150,setsar=1", os.path.join(tmp, "%04d.png" % i)])
    rows = (len(names) + 7) // 8
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(tmp, "%04d.png"),
                    "-vf", "tile=8x%d:padding=4:color=white" % max(rows, 1), "-frames:v", "1", out], check=True)
    with open(os.path.splitext(out)[0] + ".txt", "w") as f:
        for i, name in enumerate(names):
            f.write("%d\t%s\n" % (i, name))
    print("sheet", out, len(names), "clips (index -> name in the .txt beside it)")


# ---------------------------------------------------------------- build

def reject(out, set_, name, reason):
    src = os.path.join(out, set_, name)
    if not os.path.exists(src):
        return False
    dest = os.path.join(out, "_rejected", set_)
    os.makedirs(dest, exist_ok=True)
    os.replace(src, os.path.join(dest, name))
    with open(os.path.join(dest, "REASONS.tsv"), "a") as f:
        f.write("%s\t%s\n" % (name, reason))
    return True


def build(out, wanted):
    sources = read_tsv("sources.tsv")
    clips = read_tsv("clips.tsv")
    # Pieces cut from a reel. A rejected single clip (clip == its own source) is never downloaded.
    rejected = {(c["set"], c["clip"]): c["reason"] for c in clips
                if c["status"] == "rejected" and c["clip"] != c["from"]}
    sets = sorted({r["set"] for r in sources})
    for set_ in sets:
        if wanted and set_ not in wanted:
            continue
        rows = [r for r in sources if r["set"] == set_
                and not r["status"].startswith(("not used", "not kept", "rejected"))]
        print("== %s: %d files" % (set_, len(rows)), flush=True)
        set_dir = os.path.join(out, set_)
        os.makedirs(set_dir, exist_ok=True)
        dl_dir = os.path.join(out, "_downloads", set_)
        fix = os.path.join(HERE, "fixes", "fix-%s.py" % set_)
        fixed = os.path.join(set_dir, ".cleaned")
        if os.path.exists(fixed):
            print("  already cleaned up; delete %s to redo this set" % set_dir, flush=True)
            continue
        for row in rows:
            path = download(row, dl_dir)
            if not path:
                continue
            if row["process"] == "split":
                made = split(path, set_dir)
                print("  %s: %d pieces" % (row["file"], len(made)), flush=True)
            elif row["process"] == "fit":
                fit(path, set_dir)
            else:  # copy, toonami, christmas: the clean-up script works on the copies
                dest = os.path.join(set_dir, row["file"])
                if not os.path.exists(dest):
                    shutil.copyfile(path, dest)
        if rows and rows[0]["process"] == set_ and os.path.exists(fix):
            subprocess.run([sys.executable, fix], check=True, env=dict(os.environ, KIT_OUT=out))
            open(fixed, "w").close()
        missing = []
        for (s, name), reason in sorted(rejected.items()):
            if s == set_ and not reject(out, set_, name, reason):
                if not os.path.exists(os.path.join(out, "_rejected", set_, name)):
                    missing.append(name)
        for name in missing:
            print("  reject not found (cut differently?):", name, flush=True)
        kept = len([n for n in os.listdir(set_dir) if n.lower().endswith(VIDEO)])
        expected = len([c for c in clips if c["set"] == set_ and c["status"] == "on air"])
        print("  %s: %d clips (the catalog has %d)" % (set_, kept, expected), flush=True)


def list_sets():
    clips = read_tsv("clips.tsv")
    sources = read_tsv("sources.tsv")
    for set_ in sorted({r["set"] for r in sources}):
        n = sum(1 for c in clips if c["set"] == set_ and c["status"] == "on air")
        r = sum(1 for c in clips if c["set"] == set_ and c["status"] == "rejected")
        files = sum(1 for s in sources if s["set"] == set_)
        size = sum(int(s["bytes"] or 0) for s in sources if s["set"] == set_
                   and not s["status"].startswith(("not used", "not kept", "rejected")))
        print("%-12s %4d clips, %3d rejected, from %3d files, %5.1f GB to download"
              % (set_, n, r, files, size / 1e9))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
    elif args[0] == "sheet":
        sheet(*args[1:3])
    elif "--list" in args:
        list_sets()
    else:
        build(os.path.abspath(args[0]), set(args[1:]))

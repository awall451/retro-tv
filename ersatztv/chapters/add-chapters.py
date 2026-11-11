#!/usr/bin/env python3
"""Find the ad breaks in TV episodes and write them into the files as chapter marks.

Why: ErsatzTV can only cut to commercials at a chapter mark. An episode
with no chapters gets its whole ad time in one block at the end (8 minutes
after a 22-minute cartoon, 17 after a 43-minute drama). Shows made for
commercial TV fade to black and go silent where the ads were; this script
finds those points and stores them as chapters, so the breaks land where
they originally did.

It never re-encodes. By default it changes nothing and only reports:

    add-chapters.py /media/tv/Batman\\ The\\ Animated\\ Series      # report only
    add-chapters.py --write /media/tv/Batman\\ The\\ Animated\\ Series
    add-chapters.py --write --jobs 4 show1/ show2/ one-episode.mkv

Needs Python 3.8+ and ffmpeg/ffprobe on the PATH. With mkvpropedit
(package mkvtoolnix) an MKV is edited in place in under a second; without
it, and for MP4/M4V, the file is copied stream-for-stream into a new file
with the chapters and swapped in (as fast as the disk copies). AVI and OGM
cannot hold chapters: they are reported and left alone unless
--convert-to-mkv is given.

A file that already has usable chapters is left alone. Chapters that lie
past the end of the file (a known kind of damage) are replaced.

What counts as a break (all adjustable, see --help): the picture is black
for at least 0.25 s while the sound is silent, at least 4 min 10 s into
the episode and at least 3 min 20 s before its end, breaks at least 5 min
30 s apart, and no more than one per 8 minutes of running time. Those
limits match the mid-roll rule this project's ErsatzTV presets use
(point > 240, remaining_duration > 180, last_mid_filler > 300), with a
margin. An episode where nothing qualifies is left as it is.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VIDEO = {".mkv", ".mp4", ".m4v", ".avi", ".ogm", ".mov", ".webm", ".ts", ".mpg", ".mpeg", ".wmv"}
IN_PLACE = {".mkv", ".webm"}                 # mkvpropedit can edit these
REMUX = {".mkv", ".mp4", ".m4v", ".mov"}      # ffmpeg can copy these with chapters
BLACK = re.compile(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)")
SIL_START = re.compile(r"silence_start: (-?[\d.]+)")
SIL_END = re.compile(r"silence_end: ([\d.]+)")


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", path],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("ffprobe: " + out.stderr.strip()[-200:])
    info = json.loads(out.stdout)
    duration = float(info.get("format", {}).get("duration") or 0)
    streams = info.get("streams", [])
    chapters = [float(c["start_time"]) for c in info.get("chapters", [])]
    return {
        "duration": duration,
        "chapters": chapters,
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "streams": len(streams),
    }


def detect(path, has_audio, args):
    """Black stretches and silent stretches, from one decoding pass."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", path, "-map", "0:v:0",
           "-vf", "scale=160:-2,blackdetect=d=%s:pic_th=%s:pix_th=%s" % (args.black, args.picture, args.pixel)]
    if has_audio:
        cmd += ["-map", "0:a:0", "-af", "silencedetect=noise=%sdB:d=%s" % (args.noise, args.silence)]
    cmd += ["-sn", "-dn", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        raise RuntimeError("ffmpeg: " + out.stderr.strip()[-200:])
    blacks = [(float(a), float(b)) for a, b, _ in BLACK.findall(out.stderr)]
    starts = [float(x) for x in SIL_START.findall(out.stderr)]
    ends = [float(x) for x in SIL_END.findall(out.stderr)]
    silences = list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))
    return blacks, silences


def pick(blacks, silences, duration, has_audio, args):
    """The break points: the best black-and-silent moments, far enough apart."""
    found = []
    for start, end in blacks:
        point = (start + end) / 2
        if point < args.min_point or duration - point < args.min_remaining:
            continue
        quiet = sum(max(0.0, min(end, s_end) - max(start, s_start)) for s_start, s_end in silences)
        if has_audio and not args.ignore_sound and quiet <= 0:
            continue
        found.append((end - start + 2 * quiet, point))
    limit = max(1, int(duration // (args.every * 60)))
    chosen = []
    for _, point in sorted(found, reverse=True):
        if all(abs(point - other) >= args.spacing for other in chosen):
            chosen.append(point)
        if len(chosen) == limit:
            break
    return sorted(chosen)


def stamp(seconds):
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return "%02d:%02d:%06.3f" % (hours, minutes, secs)


def write_in_place(path, points):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', "<Chapters><EditionEntry>"]
    for n, point in enumerate([0.0] + points, 1):
        xml.append("<ChapterAtom><ChapterTimeStart>%s</ChapterTimeStart><ChapterDisplay>"
                   "<ChapterString>Part %d</ChapterString><ChapterLanguage>eng</ChapterLanguage>"
                   "</ChapterDisplay></ChapterAtom>" % (stamp(point), n))
    xml.append("</EditionEntry></Chapters>")
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
        handle.write("\n".join(xml))
    try:
        out = subprocess.run(["mkvpropedit", path, "--chapters", handle.name], capture_output=True, text=True)
        if out.returncode not in (0, 1):      # 1 is "done, with warnings"
            raise RuntimeError("mkvpropedit: " + (out.stdout + out.stderr).strip()[-200:])
    finally:
        os.unlink(handle.name)


def write_by_copy(path, points, before, target=None, keep_original=False):
    """Copy every stream into a new file that has the chapters, check it, swap it in."""
    target = target or path
    folder = os.path.dirname(os.path.abspath(target))
    meta = [";FFMETADATA1"]
    bounds = [0.0] + points + [before["duration"]]
    for n in range(len(bounds) - 1):
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", "START=%d" % round(bounds[n] * 1000),
                 "END=%d" % round(bounds[n + 1] * 1000), "title=Part %d" % (n + 1)]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write("\n".join(meta) + "\n")
    fd, temp = tempfile.mkstemp(suffix=os.path.splitext(target)[1], prefix=".chapters-", dir=folder)
    os.close(fd)
    try:
        cmd = ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-y", "-fflags", "+genpts", "-i", path,
               "-f", "ffmetadata", "-i", handle.name,
               "-map", "0", "-map_metadata", "0", "-map_chapters", "1", "-c", "copy", temp]
        out = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if out.returncode != 0:
            raise RuntimeError("ffmpeg copy: " + out.stderr.strip()[-200:])
        after = probe(temp)
        if after["streams"] < before["streams"] or abs(after["duration"] - before["duration"]) > 2:
            raise RuntimeError("the copy does not match the original (%d/%d streams, %.0f/%.0f s); original untouched"
                               % (after["streams"], before["streams"], after["duration"], before["duration"]))
        if len(after["chapters"]) != len(points) + 1:
            raise RuntimeError("the copy did not take the chapters; original untouched")
        shutil.copystat(path, temp)
        if keep_original or target != path:
            if target == path:
                os.replace(path, path + ".orig")
            os.replace(temp, target)
        else:
            os.replace(temp, path)
        temp = None
    finally:
        os.unlink(handle.name)
        if temp and os.path.exists(temp):
            os.unlink(temp)


def handle(path, args):
    row = {"file": path, "action": "", "points": [], "note": ""}
    try:
        ext = os.path.splitext(path)[1].lower()
        info = probe(path)
        row["duration"] = info["duration"]
        if not info["has_video"] or info["duration"] < args.min_point + args.min_remaining:
            row["action"] = "skipped"
            row["note"] = "too short for a break" if info["has_video"] else "no video"
            return row
        broken = any(start >= info["duration"] for start in info["chapters"])
        if len(info["chapters"]) >= 2 and not broken and not args.redo:
            row["action"] = "has chapters"
            row["note"] = "%d already" % len(info["chapters"])
            return row
        blacks, silences = detect(path, info["has_audio"], args)
        points = pick(blacks, silences, info["duration"], info["has_audio"], args)
        row["points"] = points
        if broken:
            row["note"] = "replaces chapters that lie past the end"
        if not points:
            row["action"] = "no break found"
            row["note"] = (row["note"] + "; " if row["note"] else "") + "%d black, %d silent stretches" % (len(blacks), len(silences))
            return row
        if not args.write:
            row["action"] = "would write"
            return row
        if ext in IN_PLACE and shutil.which("mkvpropedit"):
            write_in_place(path, points)
            row["action"] = "written in place"
        elif ext in REMUX:
            write_by_copy(path, points, info, keep_original=args.keep_original)
            row["action"] = "written by copy"
        elif args.convert_to_mkv:
            target = os.path.splitext(path)[0] + ".mkv"
            if os.path.exists(target):
                raise RuntimeError(target + " exists already")
            write_by_copy(path, points, info, target=target)
            if not args.keep_original:
                os.unlink(path)
            row["action"] = "converted to .mkv"
        else:
            row["action"] = "cannot hold chapters"
            row["note"] = ext + ": use --convert-to-mkv"
    except Exception as error:               # one bad file must not stop the run
        row["action"] = "failed"
        row["note"] = str(error)
    return row


def files_under(paths):
    for path in paths:
        if os.path.isdir(path):
            for folder, _, names in sorted(os.walk(path)):
                for name in sorted(names):
                    if os.path.splitext(name)[1].lower() in VIDEO and not name.startswith("."):
                        yield os.path.join(folder, name)
        else:
            yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+", help="episode files, or folders to walk")
    parser.add_argument("--write", action="store_true", help="write the chapters (without it: report only)")
    parser.add_argument("--jobs", type=int, default=2, help="files worked on at once (default 2)")
    parser.add_argument("--report", default="chapters-report.tsv", help="where the report goes (default chapters-report.tsv)")
    parser.add_argument("--redo", action="store_true", help="also work on files that already have chapters")
    parser.add_argument("--keep-original", action="store_true", help="keep the old file beside the new one (.orig)")
    parser.add_argument("--convert-to-mkv", action="store_true", help="copy AVI/OGM and the like into an MKV so they can hold chapters")
    parser.add_argument("--ignore-sound", action="store_true", help="a black picture is enough; do not ask for silence")
    parser.add_argument("--black", type=float, default=0.25, help="shortest black stretch, seconds (0.25)")
    parser.add_argument("--picture", type=float, default=0.97, help="share of the picture that must be black (0.97)")
    parser.add_argument("--pixel", type=float, default=0.10, help="how dark counts as black, 0 to 1 (0.10)")
    parser.add_argument("--noise", type=float, default=-45, help="how quiet counts as silent, dB (-45)")
    parser.add_argument("--silence", type=float, default=0.25, help="shortest silent stretch, seconds (0.25)")
    parser.add_argument("--min-point", type=float, default=250, help="no break in the first N seconds (250)")
    parser.add_argument("--min-remaining", type=float, default=200, help="no break in the last N seconds (200)")
    parser.add_argument("--spacing", type=float, default=330, help="seconds between breaks, at least (330)")
    parser.add_argument("--every", type=float, default=8, help="at most one break per N minutes of running time (8)")
    args = parser.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(tool + " is not on the PATH")
    if args.write and not shutil.which("mkvpropedit"):
        print("mkvpropedit not found (package mkvtoolnix): MKV files will be copied instead of edited in place", file=sys.stderr)

    files = list(files_under(args.paths))
    counts = {}
    with open(args.report, "w") as report, concurrent.futures.ThreadPoolExecutor(max(1, args.jobs)) as pool:
        report.write("action\tminutes\tbreaks at\tnote\tfile\n")
        for row in pool.map(lambda path: handle(path, args), files):
            counts[row["action"]] = counts.get(row["action"], 0) + 1
            times = ", ".join("%d:%02d" % divmod(int(point), 60) for point in row["points"])
            report.write("%s\t%.1f\t%s\t%s\t%s\n" % (row["action"], row.get("duration", 0) / 60, times, row["note"], row["file"]))
            report.flush()
            print("%-20s %-18s %s%s" % (row["action"], times, os.path.basename(row["file"]), "  (" + row["note"] + ")" if row["note"] else ""))
    print("\n%d files: %s" % (len(files), ", ".join("%d %s" % (n, action) for action, n in sorted(counts.items()))))
    print("report: " + args.report)
    if not args.write:
        print("nothing was changed; add --write to write the chapters")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Turn a YouTube channel's full-length films into ErsatzTV remote stream files.

Two steps, so the list can be read and edited in between:

  1. list    read a channel listing made by yt-dlp and write a table (TSV) of its films
  2. write   write one small .yml file per kept row of that table

The listing comes from yt-dlp (any machine that has it):

  yt-dlp --flat-playlist --print "%(id)s|%(duration)s|%(title)s" \\
      https://www.youtube.com/@SomeChannel/videos > listing.txt

  ./make-streams.py list listing.txt films.tsv
  ./make-streams.py write films.tsv out/ --relay http://relay.example:8090

Each .yml points at the stream relay (see README.md), which hands ErsatzTV the video
as an ordinary segmented playlist. Nothing is downloaded or stored.
"""
import argparse
import csv
import os
import re
import sys

FIELDS = ["id", "title", "duration", "status", "note", "youtube_title"]
MIN_SECONDS = 60 * 60
# Longer than this is a double feature or marathon of films that are also listed singly.
MAX_SECONDS = 135 * 60

# Parts of a YouTube title that are labels, not the film's name.
LABEL = re.compile(
    r"full\b.*\bmovie|free\b.*\bmovie|\bmovie channel\b|^the[y]? asylum$|official trailer|"
    r"^(full|free) hd$|"
    r"^full movie$|\b(sci-?fi|action|horror|thriller|disaster|adventure|fantasy|comedy|"
    r"western|war|monster|shark|creature|family|drama|mystery)\b.*\b(movie|film)s?$",
    re.IGNORECASE)


def film_title(youtube_title):
    """The film's name from a YouTube title.

    Two layouts are common: 'Name | labels | Actor' and 'Hook sentence! | Name | labels'.
    """
    youtube_title = re.sub(r"^\*+\s*republished\s*\*+\s*", "", youtube_title, flags=re.IGNORECASE)
    parts = [p.strip() for p in re.split(r"\s*\|+\s*", youtube_title) if p.strip()]
    names = [p for p in parts if not LABEL.search(p)] or parts
    first = names[0]
    hook = len(first.split()) >= 6 or first.endswith(("!", "?", ".", "\u2026"))
    return names[1] if len(names) > 1 and hook else first


def clock(seconds):
    seconds = int(float(seconds))
    return "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


def file_name(title):
    """A name safe on any filesystem; ErsatzTV shows the file name as the guide title."""
    name = re.sub(r'[\\/:*?"<>|]', " ", title)
    return re.sub(r"\s+", " ", name).strip().rstrip(".")


def cmd_list(args):
    rows, seen = [], set()
    with open(args.listing, encoding="utf-8") as handle:
        for line in handle:
            parts = re.split(r"\\t|\t|\|", line.rstrip("\n"), maxsplit=2)
            if len(parts) != 3:
                continue
            video, duration, youtube_title = parts
            try:
                seconds = float(duration)
            except ValueError:
                continue  # live or upcoming: no length
            if seconds < MIN_SECONDS:
                continue
            title = film_title(youtube_title)
            key = "".join(c for c in title.casefold() if c.isalnum())  # "Vs." and "VS" are the same film
            status, note = "keep", ""
            if seconds > MAX_SECONDS:
                status, note = "skip", "double feature or marathon"
            elif key in seen:
                status, note = "skip", "same film listed twice"
            if status == "keep":
                seen.add(key)
            rows.append({"id": video, "title": title, "duration": clock(seconds),
                         "status": status, "note": note, "youtube_title": youtube_title})
    rows.sort(key=lambda row: row["title"].lower())
    with open(args.table, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    kept = sum(row["status"] == "keep" for row in rows)
    print("%d films an hour or longer, %d kept, %d skipped" % (len(rows), kept, len(rows) - kept))


def cmd_write(args):
    os.makedirs(args.out, exist_ok=True)
    written = 0
    with open(args.table, newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle, delimiter="\t") if row["status"] == "keep"]
    names = {}
    for row in rows:
        names.setdefault(file_name(row["title"]) + ".yml", []).append(row["id"])
    clashes = {name: ids for name, ids in names.items() if len(ids) > 1}
    if clashes:
        for name, ids in clashes.items():
            print("%s would be written for %s" % (name, ", ".join(ids)), file=sys.stderr)
        sys.exit("nothing written: mark all but one film of each name as skip in the table")
    for row in rows:
        path = os.path.join(args.out, file_name(row["title"]) + ".yml")
        with open(path, "w", encoding="utf-8") as out:
            out.write("# %s: YouTube video %s, through the stream relay.\n" % (row["title"], row["id"]))
            out.write('url: "%s/vod/%s.m3u8"\n' % (args.relay.rstrip("/"), row["id"]))
            out.write("is_live: false\n")
            out.write("duration: %s\n" % row["duration"])
        written += 1
    print("%d stream files written to %s" % (written, args.out))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    lister = commands.add_parser("list", help="channel listing -> table of films")
    lister.add_argument("listing")
    lister.add_argument("table")
    lister.set_defaults(run=cmd_list)
    writer = commands.add_parser("write", help="table of films -> one .yml per kept row")
    writer.add_argument("table")
    writer.add_argument("out")
    writer.add_argument("--relay", required=True, help="address of the stream relay, e.g. http://relay.example:8090")
    writer.set_defaults(run=cmd_write)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    sys.exit(main())

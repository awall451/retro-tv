"""Print the smart collection query for channels in lineups.json.

    python3 build-queries.py                        # every channel in lineups.example.json
    python3 build-queries.py my-lineups.json 29 33  # only these channel numbers
    python3 build-queries.py --json 29              # {"name": ..., "query": ...} for the API

Movies are matched on title plus release year, because a quoted title
also matches longer titles that contain it (see README.md, "Smart collection queries").
A movie whose year is null (Plex has no year for the file) is matched on
title alone. Shows are matched on show title, specials (season 0) left
out. An optional "exclude" list holds query clauses to leave out (other
shows whose titles contain a wanted title, episodes whose chapter marks
would get them dropped); they are joined with AND NOT. Test a new query
on the ErsatzTV search page before saving it.
"""
import json
import pathlib
import sys

LINEUPS = pathlib.Path(__file__).with_name("lineups.example.json")


def phrase(text):
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')


def movie_term(title, year):
    if not year:
        return "title:%s" % phrase(title)
    return "(title:%s AND release_date:[%d0101 TO %d1231])" % (phrase(title), year, year)


def query(channel):
    movies = channel.get("movies", []) + channel.get("picks", [])
    parts = []
    if channel.get("shows"):
        shows = " OR ".join("show_title:%s" % phrase(s) for s in channel["shows"])
        parts.append("(type:episode AND NOT season_number:0 AND (%s))" % shows)
    if movies:
        parts.append("(type:movie AND (%s))" % " OR ".join(movie_term(t, y) for t, y in movies))
    q = " OR ".join(parts) if len(parts) > 1 else parts[0][1:-1]
    if channel.get("exclude"):
        q = "(%s) AND NOT (%s)" % (q, " OR ".join(channel["exclude"]))
    return q


def main(args):
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    path = LINEUPS
    if args and args[0].endswith(".json"):
        path = pathlib.Path(args.pop(0))
    wanted = set(args)
    for channel in json.loads(path.read_text())["channels"]:
        if wanted and channel["number"] not in wanted:
            continue
        name = channel["name"]
        if as_json:
            print(json.dumps({"name": name, "query": query(channel)}, ensure_ascii=False))
        else:
            print("%s\n  %s\n" % (name, query(channel)))


if __name__ == "__main__":
    main(sys.argv[1:])

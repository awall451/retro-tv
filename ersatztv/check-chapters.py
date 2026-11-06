"""List episodes that a mid-roll channel would drop (see README.md, "Chapter marks").

ErsatzTV drops a program, but keeps its ad time, when the file has
chapter marks and none of them passes the mid-roll expression. This
reads ErsatzTV's database read-only and prints every such episode of
the shows named on the command line, so they can be excluded in the
smart collection query before the show goes on a channel.

Run it where ErsatzTV's config folder is (the database is
/config/ersatztv.sqlite3 inside the official container), with show
titles exactly as ErsatzTV lists them:

    docker exec -i ersatztv python3 - "Record of Lodoss War" "Fighting Spirit" < check-chapters.py
    kubectl -n ersatztv exec -i deploy/ersatztv -- python3 - "Record of Lodoss War" < check-chapters.py

Set ETV_DB to read a copy of the database somewhere else. It opens
the database read-only.

The window matches the "shows" presets: a break point must be more
than 240 s in and leave more than 180 s. A show with nothing printed
under it is safe; so is a file with no chapters at all (its ads go in
one block after it).
"""
import os
import sqlite3
import sys

MIN_POINT = 240
MIN_REMAINING = 180


def seconds(timespan):
    hours, minutes, secs = timespan.split(":")[-3:]
    return int(hours.split(".")[-1]) * 3600 + int(minutes) * 60 + float(secs)


def main(titles):
    db = sqlite3.connect("file:%s?mode=ro" % os.environ.get("ETV_DB", "/config/ersatztv.sqlite3"), uri=True)
    for title in titles:
        episodes = db.execute(
            """select s.SeasonNumber,
                      (select EpisodeNumber from EpisodeMetadata em
                        where em.EpisodeId = e.Id limit 1),
                      mv.Id, mv.Duration
                 from ShowMetadata sm
                 join Season s on s.ShowId = sm.ShowId
                 join Episode e on e.SeasonId = s.Id
                 join MediaVersion mv on mv.EpisodeId = e.Id
                where sm.Title = ? and s.SeasonNumber > 0
                order by 1, 2""", (title,)).fetchall()
        chaptered = 0
        dropped = []
        for season, number, version, duration in episodes:
            length = seconds(duration)
            ends = [seconds(row[0]) for row in db.execute(
                "select EndTime from MediaChapter where MediaVersionId = ? "
                "order by StartTime", (version,))]
            if not ends:
                continue
            chaptered += 1
            # The end of the last chapter is the end of the file, not a break.
            points = ends[:-1]
            if not any(p > MIN_POINT and length - p > MIN_REMAINING
                       for p in points):
                dropped.append("  S%sE%s chapter ends at %s s of %d s" % (
                    season, number, [round(p) for p in ends], length))
        print("%s: %d episodes, %d with chapters, %d would be dropped" % (
            title, len(episodes), chaptered, len(dropped)))
        for line in dropped:
            print(line)


if __name__ == "__main__":
    main(sys.argv[1:])

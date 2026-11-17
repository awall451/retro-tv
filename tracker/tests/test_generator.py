"""The snapshot generator: the query evaluator, and copying the database through each
access path (a fake "docker" stands in for the container). Run: python3 -m unittest discover -s tests"""

import argparse
import importlib.util
import os
import sqlite3
import stat
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_generator():
    spec = importlib.util.spec_from_file_location("make_snapshot", os.path.join(ROOT, "generator", "make_snapshot.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g = load_generator()

# A stand-in for "docker exec -i <container> cmd...": runs cmd here. FAKE_NO_PY makes the
# python3 probe answer no, as in an image without Python.
FAKE_DOCKER = """#!/bin/sh
[ "$1" = exec ] && [ "$2" = -i ] || exit 64
shift 3
case "$*" in
  *"command -v python3"*) if [ -n "$FAKE_NO_PY" ]; then echo no; else echo yes; fi; exit 0 ;;
esac
exec "$@"
"""


class QueryTest(unittest.TestCase):
    def doc(self, **kw):
        d = {"type": ["movie"], "title": [g.analyze("The Last Starfighter")], "genre": [g.analyze("Science Fiction")],
             "release_date": ["19840713"], "minutes": ["101"], "state": ["Normal"]}
        d.update(kw)
        return d

    def match(self, q, **kw):
        return g.evaluate(g.parse_query(q), self.doc(**kw))

    def test_terms_phrases_ranges(self):
        self.assertTrue(self.match('type:movie AND title:"Last Starfighter"'))
        self.assertTrue(self.match('genre:"science fiction" AND release_date:[19840101 TO 19841231]'))
        self.assertFalse(self.match('genre:"science fiction" AND release_date:[19850101 TO 19851231]'))
        self.assertTrue(self.match("type:movie AND minutes:[45 TO 400]"))
        self.assertFalse(self.match("type:movie AND minutes:[45 TO 90]"))
        self.assertTrue(self.match("type:movie AND NOT state:FileNotFound"))
        self.assertTrue(self.match("(type:episode OR type:movie) AND genre:fiction"))

    def test_not_excludes(self):
        # Lucene: NOT (or -) is a prohibited clause of its group, never "or everything else"
        ep = {"type": ["episode"], "show_title": [g.analyze("Seinfeld")], "season_number": ["1"]}
        for q in ("show_title:seinfeld NOT season_number:0", "show_title:seinfeld -season_number:0"):
            self.assertTrue(self.match(q, **ep))
            self.assertFalse(self.match(q, **{**ep, "season_number": ["0"]}))
            self.assertFalse(self.match(q, **{**ep, "show_title": [g.analyze("Frasier")]}))
        self.assertTrue(self.match("type:movie OR NOT genre:western"))
        self.assertFalse(self.match("type:movie OR NOT genre:fiction"))

    def test_lucene_precedence(self):
        # Classic parser, default OR: AND makes the clause before it required as well, so
        # "a OR b AND NOT c" is b without c (a no longer counts), "a AND b OR c" is a and b
        q = "genre:western OR type:movie AND NOT state:FileNotFound"
        self.assertTrue(self.match(q))
        self.assertFalse(self.match(q, type=["episode"], genre=[g.analyze("Western")]))
        self.assertFalse(self.match(q, state=["FileNotFound"], genre=[g.analyze("Western")]))
        self.assertFalse(self.match("type:movie AND genre:western OR minutes:101"))
        self.assertTrue(self.match("type:movie AND genre:fiction OR minutes:999"))
        self.assertTrue(self.match("+type:movie genre:western"))
        self.assertFalse(self.match("+type:episode genre:fiction"))
        self.assertTrue(self.match("type:episode genre:fiction"))
        self.assertFalse(self.match("(type:episode OR type:movie) AND NOT (genre:fiction OR genre:western)"))

    def test_unsupported(self):
        # NOT alone matches nothing in Lucene: not guessed at
        for q in ("NOT type:movie", "type:movie AND (NOT state:FileNotFound)", "-type:movie",
                  "AND type:movie", "(type:movie", "type:movie)", "type:movie AND", "NOT NOT type:movie"):
            with self.assertRaises(g.Unsupported, msg=q):
                g.parse_query(q)
        for q in ("title:trek*", "language:english", "title:x~2"):
            with self.assertRaises(g.Unsupported):
                g.parse_query(q)

    def test_open_ranges(self):
        # Lucene's * leaves a range open at that end; it is not compared as text
        self.assertTrue(self.match("release_date:[* TO 19891231]"))
        self.assertFalse(self.match("release_date:[* TO 19831231]"))
        self.assertTrue(self.match("release_date:[19800101 TO *]"))
        self.assertFalse(self.match("release_date:[19850101 TO *]"))
        self.assertTrue(self.match("minutes:[100 TO *]"))
        self.assertFalse(self.match("minutes:{101 TO *]"))         # exclusive lower end
        self.assertTrue(self.match("minutes:[* TO 101]"))
        self.assertFalse(self.match("minutes:[* TO 101}"))
        self.assertTrue(self.match("minutes:[* TO *]"))
        self.assertFalse(self.match("minutes:[* TO *]", minutes=[]))   # no value: no match, as in Lucene
        self.assertTrue(self.match("minutes:[45 TO 400]", minutes=["101"]))
        self.assertFalse(self.match("minutes:[45 TO 99]", minutes=["101"]))   # numbers, not text

    def test_query_types_and_fields(self):
        every = {"movie", "episode", "other_video"}
        t = lambda q: g.query_types(g.parse_query(q), every)  # noqa: E731
        self.assertEqual(t("type:movie AND genre:action"), {"movie"})
        self.assertEqual(t("(type:movie OR type:episode) AND genre:action"), {"movie", "episode"})
        self.assertEqual(t("genre:action NOT type:other_video"), {"movie", "episode"})
        self.assertEqual(t("genre:action"), every)
        self.assertEqual(t("type:movie OR genre:action"), every)
        self.assertEqual(g.query_fields(g.parse_query("type:movie AND (genre:x OR release_date:[* TO 1]) NOT state:FileNotFound")),
                         {"genre", "release_date"})

    def test_missing_field_notes(self):
        news = lambda **kw: {"type": ["other_video"], "title": [g.analyze("Newsreel")], "tag": [g.analyze("news")],  # noqa: E731
                             "state": ["Normal"], **kw}
        docs = {1: self.doc(), 2: news(), 3: news(title=[g.analyze("Pathe Weekly")])}
        notes = lambda q: g.missing_field_notes(g.parse_query(q), docs)  # noqa: E731
        # named by type, or reached through another field: said
        self.assertEqual(notes("type:other_video AND release_date:[19400101 TO 19501231]"),
                         ["2 other videos cannot match: none have release_date"])
        self.assertEqual(notes("tag:news AND genre:news AND release_date:[* TO 19591231]"),
                         ["2 other videos cannot match: none have genre, release_date"])
        self.assertEqual(notes("title:newsreel AND genre:news"), ["1 other videos cannot match: none have genre"])
        # matched anyway, or nothing ties the query to them: quiet
        self.assertEqual(notes("type:movie AND release_date:[* TO 19891231]"), [])
        self.assertEqual(notes("release_date:[* TO 19891231] OR tag:news"), [])
        self.assertEqual(notes("show_title:seinfeld OR show_title:frasier"), [])
        self.assertEqual(notes("genre:comedy AND release_date:[* TO 19901231]"), [])
        self.assertEqual(notes("tag:news AND NOT genre:news"), [])

    def test_mirror_source(self):
        # An HD twin (PlayoutSource 1 = Mirror) has no playout: its members are its source's
        def ch(i, src=None):
            return {"Id": i, "PlayoutSource": 1 if src is not None else 0, "MirrorSourceChannelId": src}
        chans = {1: ch(1), 2: ch(2, 1), 3: ch(3, 2), 4: ch(4, 99), 5: ch(5, 6), 6: ch(6, 5)}
        self.assertEqual(g.mirror_source(chans, 1), 1)
        self.assertEqual(g.mirror_source(chans, 2), 1)
        self.assertEqual(g.mirror_source(chans, 3), 1)        # a mirror of a mirror
        self.assertIsNone(g.mirror_source(chans, 4))          # the source is gone
        self.assertIsNone(g.mirror_source(chans, 5))          # round in a circle
        self.assertEqual(g.mirror_source({7: {"Id": 7}}, 7), 7)   # an ErsatzTV without mirrors
        # as build() sees them: sqlite3.Row
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("create table Channel (Id integer primary key, PlayoutSource integer, MirrorSourceChannelId integer)")
        db.executemany("insert into Channel values (?, ?, ?)", [(1, 0, None), (2, 1, 1), (3, 1, None)])
        rows = {r["Id"]: r for r in db.execute("select * from Channel")}
        self.assertEqual(g.mirror_source(rows, 2), 1)
        self.assertIsNone(g.mirror_source(rows, 3))
        db.close()

    def test_break_rule(self):
        g.BREAK = g.parse_break_rule("240,180,300")
        # 100: too early; 350: a break; 700: a break (350 s later); 1000: only 300 s later;
        # 1700: under 180 s left
        self.assertEqual(g.breaks_for([100, 350, 700, 1000, 1700], 1800), 2)
        self.assertEqual(g.break_rule_text(), "point > 240 and remaining_duration > 180 and last_mid_filler > 300")


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.db = os.path.join(d, "ersatztv.sqlite3")
        self.live = sqlite3.connect(self.db)
        self.live.execute("pragma journal_mode=wal")
        self.live.execute("pragma wal_autocheckpoint=0")    # keep the newest rows in the WAL only
        self.live.execute("create table Channel (Id integer primary key, Number text)")
        self.live.executemany("insert into Channel (Number) values (?)", [(str(n),) for n in range(1, 51)])
        self.live.commit()
        self.assertTrue(os.path.getsize(self.db + "-wal") > 0)
        self.fake = os.path.join(d, "fake-docker")
        with open(self.fake, "w") as f:
            f.write(FAKE_DOCKER)
        os.chmod(self.fake, stat.S_IRWXU)
        self.before = open(self.db, "rb").read()

    def tearDown(self):
        self.live.close()
        os.environ.pop("FAKE_NO_PY", None)
        self.tmp.cleanup()

    def settings(self, **kw):
        args = argparse.Namespace(**kw)
        return g.Settings(args, os.devnull)

    def copy(self, cfg):
        src = g.Source(cfg)
        out = os.path.join(self.tmp.name, "copy.sqlite3")
        how = src.fetch_db(out)
        c = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        n = c.execute("select count(*) from Channel").fetchone()[0]
        c.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(out + suffix):
                os.remove(out + suffix)
        return how, n

    def test_local_file(self):
        how, n = self.copy(self.settings(ETV_DB_ACCESS="file", ETV_DB_PATH=self.db))
        self.assertEqual((n, how), (50, "SQLite backup API, read-only"))

    def test_docker_with_python(self):
        how, n = self.copy(self.settings(ETV_DB_ACCESS="docker", ETV_DB_PATH=self.db, ETV_DOCKER=self.fake))
        self.assertEqual((n, how), (50, "SQLite backup API, read-only"))

    def test_docker_without_python(self):
        os.environ["FAKE_NO_PY"] = "1"
        how, n = self.copy(self.settings(ETV_DB_ACCESS="docker", ETV_DB_PATH=self.db, ETV_DOCKER=self.fake))
        self.assertEqual(n, 50)                       # rows still only in the WAL are in the copy
        self.assertTrue(how.startswith("file copy"))

    def test_source_is_not_written(self):
        self.copy(self.settings(ETV_DB_ACCESS="docker", ETV_DB_PATH=self.db, ETV_DOCKER=self.fake))
        os.environ["FAKE_NO_PY"] = "1"
        self.copy(self.settings(ETV_DB_ACCESS="docker", ETV_DB_PATH=self.db, ETV_DOCKER=self.fake))
        self.assertEqual(open(self.db, "rb").read(), self.before)

    def test_commands(self):
        k = g.Source(self.settings(ETV_DB_ACCESS="kubectl", ETV_KUBECTL="k3s kubectl"))
        self.assertEqual(k.prefix, ["k3s", "kubectl", "exec", "-i", "-n", "ersatztv", "deploy/ersatztv", "--"])
        d = g.Source(self.settings(ETV_DB_ACCESS="docker", ETV_DOCKER="sudo docker", ETV_SSH="tvserver"))
        self.assertEqual(d.prefix, ["sudo", "docker", "exec", "-i", "ersatztv"])
        self.assertEqual(d.label, "/config/ersatztv.sqlite3 in container ersatztv on tvserver")
        with self.assertRaises(SystemExit):
            g.Source(self.settings(ETV_DB_ACCESS="nfs"))


# A tiny ErsatzTV database: the tables and columns build() reads.
SCHEMA = """
create table Library (Id integer primary key, Name text);
create table LibraryPath (Id integer primary key, LibraryId integer);
create table MediaItem (Id integer primary key, State integer, LibraryPathId integer);
create table MediaVersion (Id integer primary key, EpisodeId integer, MovieId integer, OtherVideoId integer,
                           Duration text, Width integer, Height integer);
create table MediaChapter (Id integer primary key, MediaVersionId integer, StartTime text);
create table MediaFile (Id integer primary key, MediaVersionId integer, Path text);
create table Genre (Id integer primary key, Name text, MovieMetadataId integer, ShowMetadataId integer,
                    OtherVideoMetadataId integer);
create table Studio (Id integer primary key, Name text, MovieMetadataId integer, ShowMetadataId integer);
create table Director (Id integer primary key, Name text, MovieMetadataId integer);
create table Tag (Id integer primary key, Name text, OtherVideoMetadataId integer);
create table Movie (Id integer primary key);
create table MovieMetadata (Id integer primary key, MovieId integer, Title text, Year integer, ReleaseDate text,
                            ContentRating text, SortTitle text);
create table Show (Id integer primary key);
create table ShowMetadata (Id integer primary key, ShowId integer, Title text, Year integer, ContentRating text,
                           SortTitle text);
create table Season (Id integer primary key, ShowId integer, SeasonNumber integer);
create table Episode (Id integer primary key, SeasonId integer);
create table EpisodeMetadata (Id integer primary key, EpisodeId integer, Title text, EpisodeNumber integer,
                              ReleaseDate text);
create table OtherVideo (Id integer primary key);
create table OtherVideoMetadata (Id integer primary key, OtherVideoId integer, Title text, Year integer,
                                 ReleaseDate text);
create table SmartCollection (Id integer primary key, Name text, Query text);
create table FillerPreset (Id integer primary key, Name text, SmartCollectionId integer, FillerKind integer,
                           FillerMode integer, Expression text, PadToNearestMinute integer);
create table ProgramScheduleOneItem (Id integer primary key);
create table ProgramScheduleMultipleItem (Id integer primary key);
create table ProgramScheduleDurationItem (Id integer primary key);
create table ProgramScheduleFloodItem (Id integer primary key);
create table ProgramScheduleItem (Id integer primary key, ProgramScheduleId integer, "Index" integer,
                                  PlaybackOrder integer, PreRollFillerId integer, MidRollFillerId integer,
                                  PostRollFillerId integer, TailFillerId integer, FallbackFillerId integer,
                                  SmartCollectionId integer, CollectionType integer);
create table FFmpegProfile (Id integer primary key, Name text);
create table Playout (Id integer primary key, ChannelId integer, ProgramScheduleId integer);
create table PlayoutItem (Id integer primary key, PlayoutId integer, MediaItemId integer, FillerKind integer,
                          SchedulingContext text);
create table Channel (Id integer primary key, Number text, Name text, "Group" text, IsEnabled integer,
                      FFmpegProfileId integer, FallbackFillerId integer, SortNumber real, PlayoutSource integer,
                      MirrorSourceChannelId integer);
"""


def make_db(path):
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    ins = lambda t, *rows: c.executemany(f"insert into {t} values ({','.join('?' * len(rows[0]))})", rows)  # noqa: E731
    ins("Library", (1, "TV"), (2, "Films"), (3, "News"))
    ins("LibraryPath", (1, 1), (2, 2), (3, 3))
    ins("MediaItem", (10, 0, 1), (11, 0, 1), (20, 0, 2), (21, 0, 2), (30, 0, 3))
    ins("MediaVersion", (1, 10, None, None, "00:22:00", 640, 480), (2, 11, None, None, "00:22:00", 640, 480),
        (3, None, 20, None, "02:12:00", 1920, 1080), (4, None, 21, None, "01:56:00", 1920, 1080),
        (5, None, None, 30, "00:09:00", 640, 480))
    ins("Show", (1,))
    ins("ShowMetadata", (1, 1, "Seinfeld", 1989, "TV-PG", None))
    ins("Genre", (1, "Comedy", None, 1, None), (2, "Action", 1, None, None), (3, "Action", 2, None, None))
    ins("Season", (1, 1, 1))
    ins("Episode", (10, 1), (11, 1))
    ins("EpisodeMetadata", (1, 10, "The Pilot", 1, "1989-07-05 00:00:00"), (2, 11, "The Stakeout", 2, "1990-05-31 00:00:00"))
    ins("Movie", (20,), (21,))
    ins("MovieMetadata", (1, 20, "Die Hard", 1988, "1988-07-15 00:00:00", "R", None),
        (2, 21, "Speed", 1994, "1994-06-10 00:00:00", "R", None))
    ins("OtherVideo", (30,))
    ins("OtherVideoMetadata", (1, 30, "Newsreel 1947", None, None))
    ins("Tag", (1, "news", 1))
    ins("SmartCollection", (1, "Sitcoms", "type:episode AND show_title:seinfeld"),
        (2, "Old action", "type:movie AND genre:action AND release_date:[* TO 19891231]"),
        (3, "Postwar news", "type:other_video AND release_date:[19450101 TO 19501231]"))
    ins("ProgramScheduleItem", *[(i, i, 0, 3, None, None, None, None, None, i, 5) for i in (1, 2, 3)])
    ins("ProgramScheduleFloodItem", (1,), (2,), (3,))
    ins("FFmpegProfile", (1, "SD"))
    ins("Playout", (1, 1, 1), (2, 2, 2), (3, 3, 3))
    ins("PlayoutItem", (1, 1, 10, 0, None), (2, 1, 11, 0, None), (3, 2, 20, 0, None))
    ins("Channel", (1, "24", "Sitcoms", "Main", 1, 1, None, 24, 0, None),
        (2, "30", "Action", "Main", 1, 1, None, 30, 0, None),
        (3, "40", "Newsreels", "Main", 1, 1, None, 40, 0, None),
        (4, "124", "Sitcoms HD", "HD", 1, 1, None, 124, 1, 1),
        (5, "130", "Action HD", "HD", 1, 1, None, 130, 1, 2))
    c.commit()
    c.close()


class SnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db = os.path.join(cls.tmp.name, "ersatztv.sqlite3")
        make_db(db)
        cls.snap = g.build(db, None, None, None, "test")
        cls.ch = {c["number"]: c for c in cls.snap["channels"]}
        lib = cls.snap["library"]
        cls.lib = {("show", x["id"]): x for x in lib["shows"]} | {("movie", x["id"]): x for x in lib["movies"]}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_mirror_membership(self):
        # A mirror (HD twin) has its source's members, and the library lists both numbers
        self.assertEqual(self.ch["124"]["mirrorOf"], "24")
        self.assertEqual(self.ch["124"]["members"], self.ch["24"]["members"])
        self.assertEqual(self.lib[("show", 1)]["on"], ["24", "124"])
        self.assertEqual(self.lib[("movie", 20)]["on"], ["30", "130"])
        self.assertEqual(self.lib[("movie", 21)]["on"], [])            # 1994: outside the open range

    def test_membership_both_ways(self):
        # forward: every member of every channel lists that channel; reverse: every
        # channel a title lists has it as a member
        for num, c in self.ch.items():
            for m in c["members"]:
                self.assertIn(num, self.lib[(m["type"], m["id"])]["on"], (num, m["t"]))
        for key, x in self.lib.items():
            for num in x["on"]:
                self.assertIn(key, {(m["type"], m["id"]) for m in self.ch[num]["members"]}, (num, x["t"]))

    def test_missing_field_is_noted(self):
        notes = self.ch["40"]["notes"]
        self.assertEqual(self.ch["40"]["kind"], "empty")
        self.assertIn("Postwar news: 1 other videos cannot match: none have release_date", notes)
        self.assertIn("Postwar news: the query matches nothing in the library", notes)
        self.assertEqual(self.ch["24"]["notes"], [])
        self.assertEqual(self.ch["24"]["check"], {"playoutItems": 2, "outsideMembers": 0})


# The rest of ErsatzTV's schema that build() reads where it is there: people, tags with
# their type, plots, episode metadata of its own.
FIELDS_SCHEMA = """
alter table Genre add column EpisodeMetadataId integer;
alter table Studio add column EpisodeMetadataId integer;
alter table Director add column EpisodeMetadataId integer;
alter table Tag add column MovieMetadataId integer;
alter table Tag add column EpisodeMetadataId integer;
alter table Tag add column ShowMetadataId integer;
alter table Tag add column ExternalTypeId text;
alter table MovieMetadata add column Plot text;
alter table EpisodeMetadata add column Plot text;
create table Actor (Id integer primary key, Name text, MovieMetadataId integer, EpisodeMetadataId integer,
                    OtherVideoMetadataId integer, ShowMetadataId integer);
create table Writer (Id integer primary key, Name text, MovieMetadataId integer, EpisodeMetadataId integer,
                     OtherVideoMetadataId integer);
"""


class FieldsTest(unittest.TestCase):
    """Fields as ErsatzTV v26.11.6 indexes and parses them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.tmp.name, "ersatztv.sqlite3")
        make_db(cls.db)
        c = sqlite3.connect(cls.db)
        c.executescript(FIELDS_SCHEMA)
        c.execute("insert into Actor (Name, MovieMetadataId) values ('Bruce Willis', 1)")
        c.execute("insert into Writer (Name, EpisodeMetadataId) values ('Larry David', 1)")
        c.execute("insert into Genre (Name, EpisodeMetadataId) values ('Mystery', 2)")
        c.execute("insert into Tag (Name, MovieMetadataId, ExternalTypeId) values ('USA', 1, 'nfo/country')")
        c.execute("insert into Tag (Name, MovieMetadataId) values ('Christmas', 1)")
        c.execute("insert into Tag (Name, ShowMetadataId, ExternalTypeId) values ('NBC', 1, '319')")
        c.execute("update MovieMetadata set Plot = 'A cop takes on the terrorists in a tower.' where Id = 1")
        c.execute("update MovieMetadata set Title = 'It', ContentRating = 'PG-13/R' where Id = 2")
        c.execute("update ShowMetadata set Title = 'Star Trek: Voyager' where Id = 1")
        # a second version of Die Hard, in 720p
        c.execute("insert into MediaVersion values (6, null, 20, null, '02:12:00', 1280, 720)")
        c.commit()
        c.close()
        cls.snap = g.build(cls.db, None, None, None, "test")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def members(self, query):
        """The ids a query matches in the test library (via build(): a channel of its own)."""
        c = sqlite3.connect(self.db)
        c.execute("update SmartCollection set Query = ? where Id = 1", (query,))
        c.commit()
        c.close()
        snap = g.build(self.db, None, None, None, "test")
        ch = next(x for x in snap["channels"] if x["number"] == "24")
        ids = {(m["type"], m["id"]) for m in ch["members"]}
        return ids, ch["notes"]

    def test_text_fields_whitespace_lowercase(self):
        # CustomAnalyzer: split on whitespace, lowercased, no stop words
        self.assertEqual(g.analyze("Star Trek: The Next Generation"),
                         [(0, "star"), (1, "trek:"), (2, "the"), (3, "next"), (4, "generation")])
        self.assertEqual(self.members("title:it")[0], {("movie", 21)})       # not a stop word
        self.assertEqual(self.members("title:IT")[0], {("movie", 21)})
        self.assertEqual(self.members('show_title:"star trek:"')[0], {("show", 1)})
        self.assertEqual(self.members("show_title:trek")[0], set())         # "trek:" is the token

    def test_plot_standard_analyzer(self):
        self.assertEqual(self.members('plot:"terrorists in a tower"')[0], {("movie", 20)})
        self.assertEqual(self.members("plot:Tower")[0], {("movie", 20)})
        with self.assertRaises(g.Unsupported):
            g.parse_query("type:movie AND plot:the")      # Lucene drops the clause

    def test_exact_fields_keep_case(self):
        self.assertEqual(self.members("content_rating:R")[0], {("movie", 20), ("movie", 21)})
        self.assertEqual(self.members("content_rating:PG-13")[0], {("movie", 21)})   # "PG-13/R": both
        self.assertEqual(self.members("content_rating:r")[0], set())
        self.assertEqual(self.members("type:Movie")[0], set())
        self.assertEqual(self.members("tag_full:Christmas")[0], {("movie", 20)})
        self.assertEqual(self.members("tag_full:christmas")[0], set())

    def test_people_tags_country(self):
        self.assertEqual(self.members('type:movie AND actor:"Bruce Willis"')[0], {("movie", 20)})
        self.assertEqual(self.members("writer:david")[0], {("show", 1)})
        self.assertEqual(self.members("tag:christmas")[0], {("movie", 20)})
        self.assertEqual(self.members("country:usa")[0], {("movie", 20)})
        self.assertEqual(self.members("tag:usa")[0], set())                 # a country is not a tag

    def test_unreadable_fields_are_unsupported(self):
        for q in ("year:1988", "type:movie AND year:[1980 TO 1989]", "network:nbc", "language:english"):
            ids, notes = self.members(q)
            self.assertEqual(ids, set(), q)
            self.assertTrue(any(n.startswith("query not evaluated") for n in notes), (q, notes))
        self.assertIn("ErsatzTV has no year field", " ".join(self.members("year:1988")[1]))

    def test_episode_and_show_metadata_apart(self):
        # the show is a comedy; its episodes have no genre of their own (one is a mystery)
        self.assertEqual(self.members("type:episode AND genre:comedy")[0], set())
        self.assertEqual(self.members("type:episode AND show_genre:comedy")[0], {("show", 1)})
        snap = self.members("type:episode AND genre:mystery")
        self.assertEqual(snap[0], {("show", 1)})
        self.assertEqual(self.members("show_content_rating:TV-PG")[0], {("show", 1)})
        self.assertEqual(self.members("type:episode AND content_rating:TV-PG")[0], set())
        self.assertEqual(self.members("show_network:nbc")[0], {("show", 1)})
        self.assertEqual(self.members("show_tag:nbc")[0], set())

    def test_every_media_version(self):
        # Die Hard in 1080p and 720p: a range or a term on either height finds it
        self.assertEqual(self.members("type:movie AND height:[700 TO 800]")[0], {("movie", 20)})
        self.assertEqual(self.members("type:movie AND height:1080")[0], {("movie", 20), ("movie", 21)})
        self.assertEqual(self.members("type:movie AND width:[* TO 1300}")[0], {("movie", 20)})

    def test_text_ranges(self):
        # a range on a text field compares its words, the bounds lowercased (TermRangeQuery)
        self.assertEqual(self.members("type:movie AND title:[A TO Z]")[0], {("movie", 20), ("movie", 21)})
        self.assertEqual(self.members("type:movie AND title:[h TO hz]")[0], {("movie", 20)})    # "hard"
        self.assertEqual(self.members("release_date:[1988 TO 1989]")[0], {("movie", 20)})      # as text
        with self.assertRaises(g.Unsupported):
            g.parse_query("minutes:[a TO b]")

    def test_evaluator_error_is_a_note(self):
        real = g.evaluate

        def broken(node, doc):
            raise AttributeError("boom")
        g.evaluate = broken
        try:
            ids, notes = self.members("type:movie")
        finally:
            g.evaluate = real
        self.assertEqual(ids, set())
        self.assertIn("query not evaluated (evaluator error: AttributeError: boom)", notes)


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

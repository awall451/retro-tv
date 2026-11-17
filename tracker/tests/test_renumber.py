"""tools/renumber.py: moving watch history to new channel numbers.
Run: python3 -m unittest discover -s tests"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("renumber", os.path.join(ROOT, "tools", "renumber.py"))
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)


def day(s, dev, hour, hd=0, u=0):
    h = [0] * 24
    h[hour] = s
    return {"s": s, "hd": hd, "dev": dev, "h": h, "u": u}


DAILY = {"since": "2026-11-01", "tz": "UTC", "days": {
    "2026-11-01": {"24": day(600, {"Pi box": 600}, 20, hd=100), "13": day(300, {"direct": 300}, 9),
                   "124": day(60, {"Laptop": 60}, 20)},
    "2026-11-02": {"24": day(120, {"Laptop": 120}, 8)},
}}
EVENTS = [
    {"k": "b", "c": "24", "d": "Pi box", "kind": "stream", "hd": 1, "a": 1000, "b": 1600},
    {"k": "etv", "id": "124@2026-11-01T20:00:00Z", "c": "24", "hd": 1, "d": "direct", "a": 900, "b": 1700},
    {"k": "w", "c": "13", "a": 990, "b": 1045},
    {"k": "b", "c": "201", "d": "Laptop", "kind": "stream", "hd": 0, "a": 1000, "b": 1100},
]


class RenumberTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        for name, obj in (("watch-daily.json", DAILY), ("watch-events.json", EVENTS)):
            with open(os.path.join(self.d, name), "w") as f:
                json.dump(obj, f)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        with open(os.path.join(self.d, name)) as f:
            return json.load(f)

    def run_tool(self, *pairs, apply=False):
        out = io.StringIO()
        rc = rn.run(self.d, list(pairs), apply, out=out)
        return rc, out.getvalue()

    def test_parse_map(self):
        self.assertEqual(rn.parse_map(["24=124", "1=2", "2=1"]), {"24": "124", "1": "2", "2": "1"})
        self.assertEqual(rn.parse_map(["101-103=+900"]), {"101": "1001", "102": "1002", "103": "1003"})
        self.assertEqual(rn.parse_map(["110-111=-100", "5=5"]), {"110": "10", "111": "11"})
        for bad in (["24"], ["24=x"], ["a=1"], ["5-3=+1"], ["1-2=-5"], ["24=1", "24=2"]):
            with self.assertRaises(ValueError, msg=bad):
                rn.parse_map(bad)

    def test_dry_run_writes_nothing(self):
        before = {n: self.read(n) for n in ("watch-daily.json", "watch-events.json")}
        rc, out = self.run_tool("24=1024")
        self.assertEqual(rc, 0)
        self.assertIn("24 -> 1024", out)
        self.assertIn("dry run", out)
        self.assertEqual({n: self.read(n) for n in before}, before)
        self.assertEqual(sorted(os.listdir(self.d)), ["watch-daily.json", "watch-events.json"])

    def test_apply_moves_days_events_and_backs_up(self):
        rc, out = self.run_tool("24=1024", "13=113", apply=True)
        self.assertEqual(rc, 0)
        daily = self.read("watch-daily.json")
        self.assertEqual((daily["since"], daily["tz"]), ("2026-11-01", "UTC"))
        d1 = daily["days"]["2026-11-01"]
        self.assertEqual(set(d1), {"1024", "113", "124"})
        self.assertEqual(d1["1024"], DAILY["days"]["2026-11-01"]["24"])
        self.assertEqual(set(daily["days"]["2026-11-02"]), {"1024"})
        ev = self.read("watch-events.json")
        self.assertEqual([e["c"] for e in ev], ["1024", "1024", "113", "201"])
        self.assertEqual(ev[1]["id"], "124@2026-11-01T20:00:00Z")     # 124 not renumbered
        baks = [f for f in os.listdir(self.d) if ".bak-" in f]
        self.assertEqual(len(baks), 2)
        with open(os.path.join(self.d, next(b for b in baks if b.startswith("watch-daily")))) as f:
            self.assertEqual(json.load(f), DAILY)

    def test_backups_are_never_overwritten(self):
        # two applications within the same second: the first one's backups stay as they were
        real = rn.backup_stamp
        rn.backup_stamp = lambda: "20261117T000000"
        try:
            self.run_tool("24=1024", apply=True)
            self.run_tool("1024=2024", apply=True)
        finally:
            rn.backup_stamp = real
        baks = sorted(f for f in os.listdir(self.d) if f.startswith("watch-daily.json.bak-"))
        self.assertEqual(baks, ["watch-daily.json.bak-20261117T000000", "watch-daily.json.bak-20261117T000000-2"])
        with open(os.path.join(self.d, baks[0])) as f:
            self.assertEqual(json.load(f), DAILY)                 # the original history
        with open(os.path.join(self.d, baks[1])) as f:
            self.assertIn("1024", json.load(f)["days"]["2026-11-01"])

    def test_failed_apply_changes_neither_file(self):
        # the second file cannot be replaced: the first is put back, so the two never disagree
        before = {n: self.read(n) for n in ("watch-daily.json", "watch-events.json")}
        real, calls = rn.os.replace, []

        def failing(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst)
        rn.os.replace = failing
        try:
            with self.assertRaises(OSError):
                self.run_tool("1=2", "24=1024", "13=113", apply=True)
        finally:
            rn.os.replace = real
        self.assertEqual({n: self.read(n) for n in before}, before)
        self.assertFalse([f for f in os.listdir(self.d) if f.endswith(".tmp")])   # no temp files left
        rc, out = self.run_tool("24=1024", apply=True)             # a retry applies once, cleanly
        self.assertEqual(rc, 0)
        self.assertEqual([e["c"] for e in self.read("watch-events.json")][:2], ["1024", "1024"])

    def test_merge_and_swap(self):
        # 124's own minutes (an HD twin before the snapshot knew it) folded into 24; 13 and 201 swapped
        self.run_tool("124=24", "13=201", "201=13", apply=True)
        d1 = self.read("watch-daily.json")["days"]["2026-11-01"]
        self.assertEqual(set(d1), {"24", "201"})
        self.assertEqual(d1["24"]["s"], 660)
        self.assertEqual(d1["24"]["hd"], 100)
        self.assertEqual(d1["24"]["dev"], {"Pi box": 600, "Laptop": 60})
        self.assertEqual(d1["24"]["h"][20], 660)
        self.assertEqual(d1["201"]["s"], 300)
        ev = self.read("watch-events.json")
        self.assertEqual([e["c"] for e in ev], ["24", "24", "201", "13"])
        self.assertEqual(ev[1]["id"], "24@2026-11-01T20:00:00Z")

    def test_hd_offset_move_changes_nothing(self):
        # HD twins are counted under their channel: once 124's stray minutes are folded
        # into 24, moving the twins from +100 to +1000 finds nothing to move
        self.run_tool("124=24", apply=True)
        for f in [f for f in os.listdir(self.d) if ".bak-" in f]:
            os.remove(os.path.join(self.d, f))
        rc, out = self.run_tool("101-199=+900", apply=True)
        self.assertEqual(rc, 0)
        self.assertIn("nothing stored under the old numbers", out)
        self.assertFalse([f for f in os.listdir(self.d) if ".bak-" in f])

    def test_no_history(self):
        empty = tempfile.TemporaryDirectory()
        try:
            self.assertEqual(rn.run(empty.name, ["1=2"], True, out=io.StringIO()), 1)
        finally:
            empty.cleanup()

    def test_cli(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(rn.main(["--data-dir", self.d, "24=124"]), 0)
            with self.assertRaises(SystemExit):
                rn.main(["--data-dir", self.d, "nonsense"])


if __name__ == "__main__":
    unittest.main()

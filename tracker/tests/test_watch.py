"""Watch tracking: the counting rules (unit) and the poller + beacon API (end to end).
Run: python3 -m unittest discover -s tests"""

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_server import ROOT, SNAP, TOKEN, free_port

SNAP_W = dict(SNAP, channels=SNAP["channels"] + [{"number": "4", "name": "Weather"}, {"number": "13", "name": "Toons"},
                                                   {"number": "113", "name": "Toons HD", "group": "HD"}, {"number": "12", "name": "Kids"},
                                                   {"number": "112", "name": "Kids Plus"}])


def load_server():
    os.environ["TRACKER_TZ"] = "UTC"
    os.environ["TRACKER_DEVICES"] = "192.0.2.58=Pi box; 192.0.2.60 = Laptop"
    d = tempfile.mkdtemp(prefix="tracker-unit-")
    with open(os.path.join(d, "snapshot.json"), "w") as f:
        json.dump(SNAP_W, f)
    os.environ["DATA_DIR"] = d
    spec = importlib.util.spec_from_file_location("tracker_server", os.path.join(ROOT, "app", "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.snapshot.refresh()      # sd_of() and the beacon checks read it; a test run alone needs it too
    return mod


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load_server()
        cls.T0 = dt.datetime(2026, 11, 10, 20, 0, tzinfo=dt.timezone.utc).timestamp()

    def etv(self, c, a, b, hd=0):
        return {"k": "etv", "id": f"{c}@{a}", "c": c, "hd": hd, "d": "direct", "a": self.T0 + a, "b": self.T0 + b}

    def bea(self, c, d, a, b, hd=0, kind="stream"):
        return {"k": "b", "c": c, "d": d, "kind": kind, "hd": hd, "a": self.T0 + a, "b": self.T0 + b}

    def test_direct_session_counts_until_last_access(self):
        days = self.s.watch_days([self.etv("24", 0, 600)])
        r = days["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["dev"], r["h"][20]), (600, {"direct": 600}, 600))

    def test_short_session_is_dropped(self):
        self.assertEqual(self.s.watch_days([self.etv("24", 0, 15)]), {})

    def test_beacon_claims_its_channel(self):
        # A browser on 24 from 100 to 400; the server session (one for all clients) runs 0..600.
        days = self.s.watch_days([self.etv("24", 0, 600), self.bea("24", "browser (desktop)", 100, 400)])
        r = days["2026-11-10"]["24"]
        # direct only outside [100-30, 400+60]
        self.assertEqual(r["dev"], {"browser (desktop)": 300, "direct": 70 + 140})
        self.assertEqual(r["s"], 510)

    def test_two_devices_add_up_same_device_unions(self):
        ev = [self.bea("24", "Pi box", 0, 300), self.bea("24", "Pi box", 200, 500), self.bea("24", "Laptop", 0, 100)]
        r = self.s.watch_days(ev)["2026-11-10"]["24"]
        self.assertEqual(r["dev"], {"Pi box": 500, "Laptop": 100})
        self.assertEqual(r["s"], 600)

    def test_warm_claim_and_hd_twin(self):
        ev = [self.etv("12", 0, 40), {"k": "w", "c": "12", "a": self.T0, "b": self.T0 + 45},
              self.etv("13", 0, 1200, hd=1)]
        days = self.s.watch_days(ev)["2026-11-10"]
        self.assertNotIn("12", days)
        self.assertEqual((days["13"]["s"], days["13"]["hd"]), (1200, 1200))

    def test_hours_and_midnight(self):
        # 23:50 to 00:10 the next day
        ev = [self.etv("24", 3 * 3600 + 50 * 60, 4 * 3600 + 10 * 60)]
        days = self.s.watch_days(ev)
        self.assertEqual(days["2026-11-10"]["24"]["h"][23], 600)
        self.assertEqual(days["2026-11-11"]["24"]["h"][0], 600)

    def test_unattended_is_kept_apart(self):
        # A Pi on 24 from 0 to 1000, nobody at the controls from 600: 600 s watched, 400 s
        # unattended. The whole span still claims the channel (no "direct" time from the poller).
        ev = [self.etv("24", 0, 1000), dict(self.bea("24", "Pi box", 0, 1000), x=self.T0 + 600)]
        r = self.s.watch_days(ev)["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["u"], r["dev"]), (600, 400, {"Pi box": 600}))
        self.assertEqual(sum(r["h"]), 600)

    def test_only_unattended(self):
        ev = [dict(self.bea("24", "Pi box", 0, 300), x=self.T0)]
        r = self.s.watch_days(ev)["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["u"], r["dev"]), (0, 300, {}))

    def test_beacon_idle_marks_and_ends_unattended(self):
        w = self.s.Watch()
        b = lambda dt, idle, **kw: w.beacon(dict({"client": "idlecli01", "channel": "24", "kind": "stream", "ua": "tv",
                                                  "idle": idle, "idleAfter": 600}, **kw), "192.0.2.9", t=self.T0 + dt)
        for dt in range(0, 601, 60):
            b(dt, dt)                     # no input since 0
        b(700, 700)                       # past the 600 s threshold: unattended since 600
        b(760, 760)
        b(820, 5)                         # a key at 815: a new, attended interval
        b(880, 65, event="stop")
        r = self.s.watch_days(w.events)["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["u"]), (600 + 60, 220))
        # The idle stop of the viewer: a stop beacon already past the threshold.
        w2 = self.s.Watch()
        w2.beacon({"client": "idlecli02", "channel": "24", "kind": "stream", "idle": 0, "idleAfter": 60}, "192.0.2.9", t=self.T0)
        w2.beacon({"client": "idlecli02", "channel": "24", "kind": "stream", "idle": 100, "idleAfter": 60, "event": "stop"},
                  "192.0.2.9", t=self.T0 + 100)
        r = self.s.watch_days(w2.events)["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["u"]), (60, 40))

    def test_beacon_idle_default_threshold_and_checks(self):
        w = self.s.Watch()
        for dt in range(0, 90 * 60 + 61, 60):   # heartbeats, no input; no idleAfter: TRACKER_IDLE_MIN (90)
            w.beacon({"client": "idlecli03", "channel": "24", "kind": "stream", "idle": dt}, "192.0.2.9", t=self.T0 + dt)
        r = self.s.watch_days(w.events)["2026-11-10"]["24"]
        self.assertEqual((r["s"], r["u"]), (90 * 60, 60))
        for bad in ({"idle": -1}, {"idle": "5"}, {"idle": True}, {"idleAfter": -5}, {"idle": 10 ** 9}):
            with self.assertRaises(self.s.BadRequest):
                w.beacon(dict({"client": "idlecli04", "channel": "24", "kind": "stream"}, **bad), "192.0.2.9", t=self.T0)

    def test_sd_of(self):
        self.assertEqual(self.s.sd_of("113"), ("13", True))
        self.assertEqual(self.s.sd_of("13"), ("13", False))
        self.assertEqual(self.s.sd_of("112"), ("112", False))   # 12 + 100, but not in group HD

    def test_request_on_a_mirror(self):
        # A mirror (HD twin) has no schedule: a request naming it goes to its source
        s = self.s
        saved = dict(s.snapshot.__dict__)
        snap = dict(SNAP, channels=SNAP["channels"] + [{"number": "124", "name": "Sitcom TV HD", "group": "HD",
                                                         "mirrorOf": "24"}])
        try:
            s.snapshot.load(json.dumps(snap).encode())
            r = s.build_request({"action": "remove", "items": [{"type": "show", "id": 10}], "from": "124"}, [])
            self.assertEqual(r["from"], {"number": "24", "name": "Sitcom TV", "via": "124"})
            self.assertIn("REMOVE from ch24 Sitcom TV (asked as its mirror ch124)", s.describe(r))
            r = s.build_request({"action": "add", "items": [{"type": "movie", "id": 1}], "channel": "124"}, [])
            self.assertEqual(r["channel"]["number"], "24")
            r = s.build_request({"action": "move", "items": [{"type": "movie", "id": 1}], "from": "201", "channel": "24"}, [])
            self.assertEqual((r["from"], r["channel"]), ({"number": "201", "name": "Favorites"}, {"number": "24", "name": "Sitcom TV"}))
            with self.assertRaisesRegex(s.BadRequest, "a mirror and its source are one channel"):
                s.build_request({"action": "move", "items": [{"type": "show", "id": 10}], "from": "24", "channel": "124"}, [])
        finally:
            s.snapshot.__dict__.clear()
            s.snapshot.__dict__.update(saved)

    def test_device_pairs(self):
        self.assertEqual(self.s.parse_pairs("192.0.2.58=Pi box; 192.0.2.60 = Laptop;bad;=x"),
                         {"192.0.2.58": "Pi box", "192.0.2.60": "Laptop"})
        self.assertEqual(self.s.device_label("192.0.2.60", "desktop"), "Laptop")
        self.assertEqual(self.s.device_label("192.0.2.99", "mobile"), "browser (mobile)")

    def test_live_after_a_browser_leaves(self):
        # ErsatzTV keeps the session a while after the browser's stop: not "direct" on now.
        w = self.s.Watch()
        for dt_ in range(0, 300, 60):
            w.beacon({"client": "livecli01", "channel": "24", "kind": "stream"}, "192.0.2.9", t=self.T0 + dt_)
        w.beacon({"client": "livecli01", "channel": "24", "kind": "stream", "event": "stop"}, "192.0.2.9", t=self.T0 + 300)
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()
        w.poll_once([{"channelNumber": "24", "startedAt": iso(self.T0), "lastAccess": iso(self.T0 + 300)}], t=self.T0 + 310)
        self.assertEqual(w.live(t=self.T0 + 320), [])

    def test_session_before_snapshot_is_reclassified(self):
        # The poller saw HD twin 113 before any snapshot: counted as 113. Once the snapshot
        # is there, it counts under 13 as an HD twin, so a beacon on 13 claims it.
        s = self.s
        saved = dict(s.snapshot.__dict__)
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()  # noqa: E731
        sess = [{"channelNumber": "113", "startedAt": iso(self.T0), "lastAccess": iso(self.T0 + 600)}]
        w = s.Watch()
        try:
            s.snapshot.__init__()
            s.snapshot.refresh = lambda: None       # no snapshot yet
            w.poll_once(sess, t=self.T0 + 610)
            (e,) = w.etv.values()
            self.assertEqual((e["c"], e["hd"]), ("113", 0))
        finally:
            s.snapshot.__dict__.clear()
            s.snapshot.__dict__.update(saved)
        w.dirty = False
        w.poll_once(sess, t=self.T0 + 620)
        self.assertEqual((e["c"], e["hd"]), ("13", 1))
        self.assertTrue(w.dirty)
        days = s.watch_days([e, self.bea("13", "Laptop", 0, 600, hd=1)])["2026-11-10"]
        self.assertEqual(days["13"]["dev"], {"Laptop": 600})
        self.assertNotIn("113", days)

    def test_etv_time(self):
        t = self.s.parse_etv_time("2026-11-15T08:37:40.0255048-05:00")
        self.assertAlmostEqual(t, dt.datetime(2026, 11, 15, 13, 37, 40, 25504, tzinfo=dt.timezone.utc).timestamp(), 3)

    def test_beacon_joins_heartbeats(self):
        w = self.s.Watch()
        w.beacon({"client": "abcdefgh12", "channel": "4", "kind": "web", "ua": "desktop"}, "192.0.2.58", t=self.T0)
        w.beacon({"client": "abcdefgh12", "channel": "4", "kind": "web", "ua": "desktop"}, "192.0.2.58", t=self.T0 + 60)
        w.beacon({"client": "abcdefgh12", "channel": "113", "kind": "stream", "ua": "desktop",
                  "warm": ["12"]}, "192.0.2.58", t=self.T0 + 90)
        w.beacon({"client": "abcdefgh12", "channel": "113", "kind": "stream", "event": "stop"}, "192.0.2.58", t=self.T0 + 150)
        days = self.s.watch_days(w.events)["2026-11-10"]
        self.assertEqual(days["4"]["dev"], {"Pi box": 90})
        self.assertEqual((days["13"]["s"], days["13"]["hd"]), (60, 60))
        with self.assertRaises(self.s.BadRequest):
            w.beacon({"client": "abcdefgh12", "channel": "999", "kind": "web"}, "192.0.2.9", t=self.T0)
        with self.assertRaises(self.s.BadRequest):
            w.beacon({"client": "x", "channel": "4", "kind": "web"}, "192.0.2.9", t=self.T0)


class FakeEtv(BaseHTTPRequestHandler):
    sessions = []

    def do_GET(self):
        if self.path != "/api/sessions" or self.headers.get("X-Etv-Api-Key") != "etv-key":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(self.sessions).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class WatchApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.etv = ThreadingHTTPServer(("127.0.0.1", 0), FakeEtv)
        threading.Thread(target=cls.etv.serve_forever, daemon=True).start()
        n = time.time()
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5))).isoformat()
        FakeEtv.sessions = [{"channelNumber": "24", "state": "next", "startedAt": iso(n - 600), "lastAccess": iso(n - 2)},
                            {"channelNumber": "201", "state": "next", "startedAt": iso(n - 10), "lastAccess": iso(n - 1)}]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.port = free_port()
        env = dict(os.environ, DATA_DIR=cls.tmp.name, PORT=str(cls.port), TRACKER_TOKEN=TOKEN, TRACKER_TZ="UTC",
                   ERSATZTV_URL=f"http://127.0.0.1:{cls.etv.server_address[1]}", ERSATZTV_API_KEY="etv-key",
                   TRACKER_POLL_SECONDS="0.3", TRACKER_ORIGINS="http://tv.example:8410",
                   TRACKER_DEVICES="192.0.2.58=Pi box", TRACKER_TV_LABEL="TV box", TRACKER_TRUST_PROXY="1")
        cls.proc = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "app", "server.py")], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/healthz", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        cls.call("PUT", "/api/snapshot", SNAP_W, {"X-Tracker-Token": TOKEN, "Content-Type": "application/json"})

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.etv.shutdown()
        cls.tmp.cleanup()

    @classmethod
    def call(cls, method, path, body=None, headers=None):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        req = urllib.request.Request(f"http://127.0.0.1:{cls.port}{path}", data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                out = r.read()
                return r.status, (json.loads(out) if out else None), dict(r.headers)
        except urllib.error.HTTPError as e:
            out = e.read()
            return e.code, (json.loads(out) if out else None), dict(e.headers)

    def beacon(self, body, origin="http://tv.example:8410", xff=None):
        h = {"Content-Type": "text/plain"}
        if origin:
            h["Origin"] = origin
        if xff:
            h["X-Forwarded-For"] = xff
        return self.call("POST", "/api/watch/beacon", body, h)

    def test_beacons_and_poller(self):
        st, _, h = self.call("OPTIONS", "/api/watch/beacon", headers={"Origin": "http://127.0.0.1:8410"})
        self.assertEqual((st, h.get("Access-Control-Allow-Origin")), (204, "http://127.0.0.1:8410"))
        self.assertEqual(self.beacon({"client": "client-0001", "channel": "4", "kind": "web"}, origin="https://evil.example")[0], 403)
        self.assertEqual(self.beacon({"client": "client-0001", "channel": "4", "kind": "web"}, origin=None)[0], 403)
        self.assertEqual(self.beacon({"client": "client-0001", "channel": "77", "kind": "web"})[0], 400)
        self.assertEqual(self.beacon(b"not json")[0], 400)
        st, r, h = self.beacon({"client": "client-0001", "channel": "4", "kind": "web", "ua": "tv"}, xff="192.0.2.58")
        self.assertEqual((st, r["device"], h.get("Access-Control-Allow-Origin")), (200, "Pi box", "http://tv.example:8410"))
        self.assertEqual(self.beacon({"client": "client-0004", "channel": "4", "kind": "web", "ua": "tv"}, xff="192.0.2.1")[1]["device"], "TV box")
        st, r, _ = self.beacon({"client": "client-0002", "channel": "113", "kind": "stream", "ua": "mobile"}, xff="192.0.2.77")
        self.assertEqual((r["device"], r["channel"], r["hd"]), ("browser (mobile)", "13", True))
        # Nobody at the controls for an hour (sleep timer 60 s): unattended, not watch time.
        self.assertEqual(self.beacon({"client": "client-0005", "channel": "12", "kind": "stream", "ua": "desktop",
                                      "idle": 3600, "idleAfter": 60}, xff="192.0.2.78")[0], 200)
        self.assertEqual(self.beacon({"client": "client-0005", "channel": "12", "kind": "stream", "idle": "x"})[0], 400)
        codes = [self.beacon({"client": "client-0003", "channel": "4", "kind": "web"})[0] for _ in range(25)]
        self.assertIn(429, codes)
        time.sleep(1.2)
        self.beacon({"client": "client-0005", "channel": "12", "kind": "stream", "ua": "desktop", "idle": 3602,
                     "idleAfter": 60, "event": "stop"}, xff="192.0.2.78")
        time.sleep(1.0)
        st, w, _ = self.call("GET", "/api/watch?days=7")
        self.assertEqual(st, 200)
        self.assertIsNone(w["poller"]["lastError"])
        self.assertEqual(w["poller"]["sessions"], 2)
        # Summed over the days reported: a run just after midnight (UTC) splits the sessions.
        days = w["days"].values()
        total = lambda ch, k: sum(d.get(ch, {}).get(k, 0) for d in days)  # noqa: E731
        self.assertGreaterEqual(total("24", "s"), 590)            # a direct client on 24 for ~10 min
        self.assertEqual(set().union(*(d["24"]["dev"].keys() for d in days if "24" in d)), {"direct"})
        self.assertFalse(any("201" in d for d in days))           # 10 s session: a probe or a warm-up
        self.assertEqual(total("12", "s"), 0)                     # unattended only
        self.assertGreaterEqual(total("12", "u"), 1)
        self.assertEqual(w["rules"]["idleMin"], 90)
        live = {x["channel"]: x["devices"] for x in w["live"]}
        self.assertEqual(live["24"], ["direct"])
        self.assertIn("Pi box", live["4"])
        self.assertEqual(live["13"], ["browser (mobile)"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "watch-daily.json")))


if __name__ == "__main__":
    unittest.main()

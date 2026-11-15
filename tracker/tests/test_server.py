"""Smoke tests for the tracker API. Run: python3 -m unittest discover -s tests"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "test-token-0123456789abcdef0123456789"
SNAP = {
    "generatedAt": "2026-01-01T00:00:00Z",
    "channels": [{"number": "24", "name": "Sitcom TV"}, {"number": "201", "name": "Favorites"}],
    "library": {"shows": [{"id": 10, "t": "Seinfeld", "on": ["24"]}],
                "movies": [{"id": 1, "t": "Die Hard", "on": ["201"]}]},
}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.port = free_port()
        env = dict(os.environ, DATA_DIR=cls.tmp.name, PORT=str(cls.port), TRACKER_TOKEN=TOKEN)
        cls.proc = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "app", "server.py")], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/healthz", timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(5)
        cls.tmp.cleanup()

    def call(self, method, path, body=None, token=None, raw=False):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-Tracker-Token", token)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                out = r.read()
                return r.status, (out.decode() if raw else json.loads(out))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def test_flow(self):
        self.assertEqual(self.call("GET", "/healthz")[0], 200)
        self.assertEqual(self.call("GET", "/api/snapshot")[0], 404)
        self.assertEqual(self.call("PUT", "/api/snapshot", SNAP)[0], 403)
        self.assertEqual(self.call("PUT", "/api/snapshot", SNAP, token="wrong")[0], 403)
        self.assertEqual(self.call("PUT", "/api/snapshot", {"x": 1}, token=TOKEN)[0], 400)
        self.assertEqual(self.call("PUT", "/api/snapshot", SNAP, token=TOKEN)[0], 200)
        self.assertEqual(self.call("GET", "/api/snapshot")[1]["channels"][0]["name"], "Sitcom TV")

        st, r = self.call("POST", "/api/requests", {"action": "move", "items": [{"type": "movie", "id": 1}],
                                                    "from": "201", "channel": "24", "note": "test"})
        self.assertEqual(st, 201)
        self.assertEqual(r["items"][0]["title"], "Die Hard")
        self.assertEqual(r["status"], "pending")
        self.assertEqual(self.call("POST", "/api/requests", {"action": "add", "items": [{"type": "show", "id": 99}],
                                                             "channel": "24"})[0], 400)
        self.assertEqual(self.call("POST", "/api/requests", {"action": "add", "items": [{"type": "show", "id": 10}],
                                                             "channel": "7"})[0], 400)
        st, p = self.call("POST", "/api/planned", {"name": "Saturday Morning", "number": "8", "kind": "shows"})
        self.assertEqual(st, 201)
        self.assertEqual(self.call("POST", "/api/planned", {"name": "Dup", "number": "24"})[0], 409)
        st, r2 = self.call("POST", "/api/requests", {"action": "add", "items": [{"type": "show", "id": 10}],
                                                     "channel": {"planned": p["id"]}})
        self.assertEqual(st, 201)
        self.assertEqual(self.call("DELETE", f"/api/planned/{p['id']}")[0], 409)

        self.assertEqual(self.call("PATCH", f"/api/requests/{r['id']}", {"status": "applied"})[0], 403)
        st, done = self.call("PATCH", f"/api/requests/{r['id']}", {"status": "applied", "result": "ok"}, token=TOKEN)
        self.assertEqual((st, done["status"], done["result"]), (200, "applied", "ok"))
        self.assertIsNotNone(done["appliedAt"])
        self.assertEqual(self.call("DELETE", f"/api/requests/{r['id']}")[0], 403)
        self.assertEqual(self.call("DELETE", f"/api/requests/{r2['id']}")[0], 200)
        self.assertEqual(self.call("DELETE", f"/api/planned/{p['id']}")[0], 200)

        st, text = self.call("GET", "/api/requests?format=text", raw=True)
        self.assertEqual(st, 200)
        self.assertIn("APPLIED", text)
        self.assertIn('"Die Hard" (movie 1)', text)
        self.assertEqual(len(self.call("GET", "/api/requests?status=pending")[1]), 0)


class TokenFileTest(unittest.TestCase):
    """No TRACKER_TOKEN: the server makes one in DATA_DIR/token. X-Forwarded-For is
    ignored unless TRACKER_TRUST_PROXY is on."""

    def test_token_file_and_proxy_header(self):
        with tempfile.TemporaryDirectory() as d:
            port = free_port()
            env = {k: v for k, v in os.environ.items() if not k.startswith("TRACKER_")}
            env.update(DATA_DIR=d, PORT=str(port), TRACKER_DEVICES="192.0.2.58=Pi box")
            proc = subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "app", "server.py")], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(50):
                    try:
                        urllib.request.urlopen(base + "/healthz", timeout=1)
                        break
                    except OSError:
                        time.sleep(0.1)
                path = os.path.join(d, "token")
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
                with open(path) as f:
                    token = f.read().strip()
                self.assertGreaterEqual(len(token), 32)
                req = urllib.request.Request(base + "/api/snapshot", data=json.dumps(SNAP).encode(), method="PUT",
                                             headers={"Content-Type": "application/json", "X-Tracker-Token": token})
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertEqual(r.status, 200)
                req = urllib.request.Request(base + "/api/watch/beacon", method="POST",
                                             data=json.dumps({"client": "client-0001", "channel": "24", "kind": "stream",
                                                              "ua": "desktop"}).encode(),
                                             headers={"Content-Type": "text/plain", "Origin": "http://127.0.0.1:8410",
                                                      "X-Forwarded-For": "192.0.2.58"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertEqual(json.loads(r.read())["device"], "browser (desktop)")
            finally:
                proc.terminate()
                proc.wait(5)


if __name__ == "__main__":
    unittest.main()

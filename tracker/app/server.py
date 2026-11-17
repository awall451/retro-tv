#!/usr/bin/env python3
"""Retro TV channel tracker: a small JSON API and static page.

Standard library only. Data lives in DATA_DIR (default /data):
  snapshot.json   channels + library, uploaded by generator/make_snapshot.py
  token           the upload/apply token, when TRACKER_TOKEN is not set (made at first start)
  requests.json   queued change requests
  planned.json    planned (not yet built) channels
  watch-events.json  raw watch intervals of the last 14 days (channel popularity)
  watch-daily.json   per-day, per-channel watch seconds (kept ~400 days)

Writes are atomic (temp file in the same directory, fsync, rename).
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import urllib.request
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DATA_DIR = os.environ.get("DATA_DIR", "/data")
STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))
PORT = int(os.environ.get("PORT", "8080"))
TOKEN = os.environ.get("TRACKER_TOKEN", "").strip()
VERSION = os.environ.get("APP_VERSION", "dev")

MAX_SNAPSHOT = 64 * 1024 * 1024
MAX_BODY = 256 * 1024
ACTIONS = ("add", "remove", "move", "note")
STATUSES = ("pending", "applied", "rejected")
KINDS = ("shows", "movies", "mixed")

lock = threading.RLock()

STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon",
                ".png": "image/png", ".json": "application/json"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_of(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def atomic_write(name: str, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path_of(name))
        try:
            dfd = os.open(DATA_DIR, os.O_RDONLY)
            os.fsync(dfd)
            os.close(dfd)
        except OSError:
            pass
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_json(name: str, default):
    try:
        with open(path_of(name), "rb") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        return default


def save_json(name: str, obj) -> None:
    atomic_write(name, json.dumps(obj, ensure_ascii=False, indent=1).encode())


# ---------------------------------------------------------------------------
# Snapshot cache: raw bytes, gzip, etag and an id index for validation

class Snapshot:
    def __init__(self):
        self.raw = None
        self.gz = None
        self.etag = None
        self.mtime = None
        self.index = {}
        self.channels = {}
        self.groups = {}
        self.mirrors = {}
        self.generated = None

    def refresh(self):
        p = path_of("snapshot.json")
        try:
            m = os.stat(p).st_mtime_ns
        except FileNotFoundError:
            self.__init__()
            return
        if m == self.mtime:
            return
        with open(p, "rb") as f:
            raw = f.read()
        self.load(raw, m)

    def load(self, raw: bytes, mtime=None):
        obj = json.loads(raw)
        self.raw = raw
        self.gz = gzip.compress(raw, 6)
        self.etag = '"' + hashlib.sha256(raw).hexdigest()[:20] + '"'
        self.mtime = mtime
        lib = obj.get("library") or {}
        self.index = {}
        for s in lib.get("shows") or []:
            self.index[("show", s.get("id"))] = s.get("t")
        for m in lib.get("movies") or []:
            self.index[("movie", m.get("id"))] = m.get("t")
        self.channels = {str(c.get("number")): c.get("name") for c in obj.get("channels") or []}
        self.groups = {str(c.get("number")): c.get("group") for c in obj.get("channels") or []}
        # mirror (an HD twin, no schedule of its own) -> the channel it plays
        self.mirrors = {str(c.get("number")): str(c["mirrorOf"]) for c in obj.get("channels") or []
                        if c.get("mirrorOf") is not None}
        self.generated = obj.get("generatedAt")


snapshot = Snapshot()


def validate_snapshot(obj) -> str | None:
    if not isinstance(obj, dict):
        return "snapshot must be an object"
    if not isinstance(obj.get("channels"), list):
        return "snapshot.channels must be a list"
    lib = obj.get("library")
    if not isinstance(lib, dict) or not isinstance(lib.get("shows"), list) or not isinstance(lib.get("movies"), list):
        return "snapshot.library.shows and .movies must be lists"
    return None


# ---------------------------------------------------------------------------
# Requests and planned channels

class BadRequest(Exception):
    def __init__(self, msg, status=HTTPStatus.BAD_REQUEST):
        super().__init__(msg)
        self.status = status


def clean_str(v, name, maxlen, required=False):
    if v is None or v == "":
        if required:
            raise BadRequest(f"{name} is required")
        return None
    if not isinstance(v, (str, int)):
        raise BadRequest(f"{name} must be a string")
    v = str(v).strip()
    if len(v) > maxlen:
        raise BadRequest(f"{name} is longer than {maxlen} characters")
    return v or None


def channel_ref(v, name, planned):
    """A target/source channel: {"number": "24"} or {"planned": <id>}."""
    if v is None or v == "":
        return None
    if isinstance(v, (str, int)):
        v = {"number": str(v)}
    if not isinstance(v, dict):
        raise BadRequest(f"{name} must be a channel reference")
    if v.get("planned") is not None:
        pid = v["planned"]
        p = next((p for p in planned if p["id"] == pid), None)
        if not p:
            raise BadRequest(f"{name}: no planned channel {pid}")
        return {"planned": pid, "name": p["name"], "number": p.get("number")}
    num = clean_str(v.get("number"), f"{name}.number", 10, required=True)
    nm = snapshot.channels.get(num)
    if snapshot.channels and nm is None:
        raise BadRequest(f"{name}: no channel {num} in the snapshot")
    src = snapshot.mirrors.get(num)
    if src is not None and src in snapshot.channels:
        # A mirror (HD twin) has no schedule: the change is made on its source.
        return {"number": src, "name": snapshot.channels[src], "via": num}
    return {"number": num, "name": nm or clean_str(v.get("name"), f"{name}.name", 80)}


def build_request(body, planned):
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    action = body.get("action")
    if action not in ACTIONS:
        raise BadRequest(f"action must be one of {', '.join(ACTIONS)}")
    items_in = body.get("items") or []
    if not isinstance(items_in, list) or len(items_in) > 500:
        raise BadRequest("items must be a list of at most 500")
    items, seen = [], set()
    for it in items_in:
        if not isinstance(it, dict) or it.get("type") not in ("show", "movie") or not isinstance(it.get("id"), int):
            raise BadRequest("each item needs type (show|movie) and an integer id")
        key = (it["type"], it["id"])
        if key in seen:
            continue
        seen.add(key)
        title = snapshot.index.get(key)
        if snapshot.index and title is None:
            raise BadRequest(f"no {it['type']} {it['id']} in the snapshot")
        items.append({"type": it["type"], "id": it["id"],
                      "title": title or clean_str(it.get("title"), "item.title", 300)})
    note = clean_str(body.get("note"), "note", 4000)
    target = channel_ref(body.get("channel"), "channel", planned)
    source = channel_ref(body.get("from"), "from", planned)
    if action in ("add", "move") and not target:
        raise BadRequest(f"{action} needs a target channel")
    if action in ("remove", "move") and not source:
        raise BadRequest(f"{action} needs a from channel")
    if action == "move" and target and source and \
            (target.get("planned"), target.get("number")) == (source.get("planned"), source.get("number")):
        raise BadRequest("move needs two different channels"
                         + (" (a mirror and its source are one channel)" if target.get("via") or source.get("via") else ""))
    if action in ("add", "remove", "move") and not items:
        raise BadRequest(f"{action} needs at least one item")
    if action == "note" and not note and not items:
        raise BadRequest("a note needs text or items")
    return {"action": action, "items": items, "channel": target if action in ("add", "move", "note") else None,
            "from": source if action in ("remove", "move") else None, "note": note,
            "status": "pending", "createdAt": now(), "appliedAt": None, "result": None,
            "snapshotAt": snapshot.generated}


def describe(r) -> str:
    def ch(c):
        if not c:
            return "?"
        if c.get("planned") is not None:
            return f"planned channel #{c['planned']} \"{c['name']}\"" + (f" (number {c['number']})" if c.get("number") else "")
        s = f"ch{c['number']} {c.get('name') or ''}".strip()
        return s + (f" (asked as its mirror ch{c['via']})" if c.get("via") else "")
    titles = ", ".join(f"\"{i['title']}\" ({i['type']} {i['id']})" for i in r["items"])
    a = r["action"]
    if a == "add":
        s = f"ADD to {ch(r['channel'])}: {titles}"
    elif a == "remove":
        s = f"REMOVE from {ch(r['from'])}: {titles}"
    elif a == "move":
        s = f"MOVE from {ch(r['from'])} to {ch(r['channel'])}: {titles}"
    else:
        s = "NOTE" + (f" about {ch(r['channel'])}" if r.get("channel") else "") + (f": {titles}" if titles else "")
    return s


def text_export(reqs, planned) -> str:
    out = ["Retro TV channel tracker: queued change requests",
           f"Exported {now()}; snapshot generated {snapshot.generated or 'never'}.",
           "Item ids are ErsatzTV database ids (show = Show.Id, movie = Movie.Id). To close a request:",
           "  PATCH /api/requests/<id> {\"status\": \"applied\"|\"rejected\", \"result\": \"...\"} with header X-Tracker-Token.",
           ""]
    pending = [r for r in reqs if r["status"] == "pending"]
    done = [r for r in reqs if r["status"] != "pending"]
    out.append(f"PENDING ({len(pending)})")
    for r in pending:
        out.append(f"#{r['id']} [{r['createdAt']}] {describe(r)}")
        if r.get("note"):
            out.extend("    note: " + line for line in r["note"].splitlines() or [""])
    if not pending:
        out.append("  (none)")
    out.append("")
    out.append(f"PLANNED CHANNELS ({len(planned)})")
    for p in planned:
        bits = [f"#{p['id']} \"{p['name']}\""]
        if p.get("number"):
            bits.append(f"number {p['number']}")
        if p.get("kind"):
            bits.append(p["kind"])
        out.append("  ".join(bits) + f" [{p['createdAt']}]")
        if p.get("note"):
            out.append("    note: " + p["note"])
    if not planned:
        out.append("  (none)")
    out.append("")
    out.append(f"DONE ({len(done)})")
    for r in done:
        out.append(f"#{r['id']} {r['status'].upper()} {r.get('appliedAt') or ''} {describe(r)}")
        if r.get("note"):
            out.append("    note: " + r["note"].replace("\n", " / "))
        if r.get("result"):
            out.append("    result: " + r["result"].replace("\n", " / "))
    if not done:
        out.append("  (none)")
    return "\n".join(out) + "\n"


def next_id(items) -> int:
    return max((i["id"] for i in items), default=0) + 1


# ---------------------------------------------------------------------------
# Watch tracking: which channels get watched, and for how long.
#
# Two sources:
#  - the poller reads ErsatzTV's GET /api/sessions every WATCH_POLL_SECONDS.
#    A session is one running channel (all clients share it) with startedAt
#    and lastAccess; lastAccess stops moving when the last client leaves, so
#    [startedAt, lastAccess] is the watched span and the ~90 s the session
#    lingers afterwards is never counted. It carries no client address.
#  - beacons from the browser viewer (POST /api/watch/beacon): on tune and
#    every ~60 s, {channel, kind: web|stream, client, ua, hd, warm} and, from
#    viewers with a sleep timer, {idle, idleAfter}. The tracker labels the
#    device by the sender's address (TRACKER_DEVICES) or the ua class; the
#    client id is only kept in memory, to join heartbeats.
#
# Which source wins (no double counting), per channel:
#  - any beacon (web or stream) claims its channel from 30 s before it
#    started to 60 s after its last heartbeat; poller time on that channel
#    inside a claim is dropped. Browsers are counted per device from beacons.
#  - channels a beacon says it is pre-warming ("fast flipping") are claimed
#    from 10 s before that beacon to 45 s after it, and count for nobody.
#  - poller sessions shorter than 20 s (lastAccess - startedAt) are dropped:
#    probes, flips, warm-ups.
#  - what is left of the poller's time counts once, as device "direct"
#    (Roku, Kodi or anything else playing ErsatzTV directly).
# A channel's minutes are the sum over device labels of the union of that
# label's intervals. HD twins (group HD, number + TRACKER_HD_OFFSET) count
# toward the SD channel and are kept as the "hd" share.
#
# Unattended viewing (optional): a beacon may say how long ago the viewer last
# had a key press, click or touch ("idle", seconds) and its sleep-timer setting
# ("idleAfter", seconds; 0 or missing: TRACKER_IDLE_MIN). Minutes from that
# threshold on (a TV left on with nobody pressing anything) are kept apart as
# "u" (unattended): they still claim the channel against the poller, but are
# not watch time and not in the rankings. A key press ends it (a new interval).

ETV_URL = os.environ.get("ERSATZTV_URL", "").strip().rstrip("/")
ETV_API_KEY = os.environ.get("ERSATZTV_API_KEY", "").strip()
POLL_SECONDS = max(0.1, float(os.environ.get("TRACKER_POLL_SECONDS") or "30"))
WATCH_TZ = os.environ.get("TRACKER_TZ") or "UTC"
RAW_DAYS = 14
DAILY_DAYS = 400
MIN_SESSION = 20
CLAIM_BEFORE, CLAIM_AFTER = 30, 60
WARM_HOLD = 45
BEACON_GAP = 150
WATCH_IDLE_MIN = float(os.environ.get("TRACKER_IDLE_MIN") or "90")
MAX_IDLE = 30 * 86400
# HD twins: the viewer's convention is group "HD" at number + 100.
HD_OFFSETS = [int(x) for x in re.split(r"[,;\s]+", os.environ.get("TRACKER_HD_OFFSET") or "100") if x.isdigit() and int(x) > 0]
UA_CLASSES = ("tv", "mobile", "desktop", "other")
KINDS_WATCH = ("web", "stream")
TRUST_PROXY = (os.environ.get("TRACKER_TRUST_PROXY") or "").strip().lower() in ("1", "true", "yes", "on")
CHANNEL_RE = re.compile(r"^\d{1,4}(\.\d{1,2})?$")
CLIENT_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def parse_pairs(s):
    """'<address>=<label>;<address>=<label>' (labels may contain spaces)."""
    out = {}
    for part in re.split(r"[;,\n]+", s or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()[:24]
            if k and v:
                out[k] = v
    return out


WATCH_DEVICES = parse_pairs(os.environ.get("TRACKER_DEVICES", ""))
WATCH_ORIGINS = {o.rstrip("/").lower() for o in re.split(r"[;\s,]+", os.environ.get("TRACKER_ORIGINS", "")) if o}
LOCAL_ORIGIN = re.compile(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?$")


def origin_allowed(origin) -> bool:
    return bool(origin) and (origin.rstrip("/").lower() in WATCH_ORIGINS or bool(LOCAL_ORIGIN.match(origin)))


def load_tz():
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(WATCH_TZ)
    except Exception:  # noqa: BLE001
        print(f"warning: time zone {WATCH_TZ!r} not available; watch days are UTC", flush=True)
        return dt.timezone.utc


TZ = load_tz()


def parse_etv_time(s) -> float:
    """ErsatzTV writes 7 fractional digits (2026-11-15T08:37:40.0255048-05:00)."""
    s = re.sub(r"(\.\d{6})\d+", r"\1", str(s)).replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=TZ)
    return t.timestamp()


def sd_of(num: str):
    """(SD channel number, is the HD twin) for a channel number. A twin is a
    channel in group HD whose number minus an HD offset is a channel too."""
    if not num.isdigit() or str(snapshot.groups.get(num) or "").strip().upper() != "HD":
        return num, False
    for off in HD_OFFSETS:
        sd = str(int(num) - off)
        if int(num) > off and sd in snapshot.channels:
            return sd, True
    return num, False


def union(iv):
    out = []
    for a, b in sorted(iv):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(iv, cut):
    """Intervals iv minus the (sorted, disjoint) intervals cut."""
    out = []
    for a, b in iv:
        cur = a
        for x, y in cut:
            if y <= cur or x >= b:
                continue
            if x > cur:
                out.append([cur, x])
            cur = max(cur, y)
            if cur >= b:
                break
        if cur < b:
            out.append([cur, b])
    return out


def split_hours(a, b):
    """Yield (local date, hour, seconds) for the interval [a, b)."""
    t = a
    while t < b:
        loc = dt.datetime.fromtimestamp(t, TZ)
        nxt = min(b, t - (loc.minute * 60 + loc.second + loc.microsecond / 1e6) + 3600)
        if nxt <= t:
            nxt = min(b, t + 3600)
        yield loc.date().isoformat(), loc.hour, nxt - t
        t = nxt


def watch_spans(events):
    """Per channel and device label: the counted intervals (see the rules above)."""
    beacons, warm, etv = {}, {}, {}
    for e in events:
        if e["k"] == "b":
            beacons.setdefault(e["c"], {}).setdefault(e["d"], []).append((e["a"], e["b"], e.get("hd", 0), e.get("x")))
        elif e["k"] == "w":
            warm.setdefault(e["c"], []).append((e["a"], e["b"]))
        elif e["k"] == "etv" and e["b"] - e["a"] >= MIN_SESSION:
            etv.setdefault(e["c"], []).append((e["a"], e["b"], e.get("hd", 0)))
    spans = {}
    for c in set(beacons) | set(etv):
        devs, away = {}, {}
        claims = []
        for d, iv in beacons.get(c, {}).items():
            # Attended up to the unattended mark x (if any), unattended after it.
            devs[d] = [(a, min(b, x) if x is not None else b, hd) for a, b, hd, x in iv]
            away[d] = [(max(a, x), b) for a, b, _, x in iv if x is not None]
            claims += [(a - CLAIM_BEFORE, b + CLAIM_AFTER) for a, b, _, _ in iv]
        claims = union(claims + warm.get(c, []))
        direct = []
        for a, b, hd in etv.get(c, []):
            direct += [(x, y, hd) for x, y in subtract([[a, b]], claims)]
        if direct:
            devs["direct"] = direct
        for d, iv in devs.items():
            spans.setdefault(c, {})[d] = (union([(a, b) for a, b, _ in iv]), union([(a, b) for a, b, hd in iv if hd]),
                                          union(away.get(d, [])))
    return spans


def watch_days(events):
    """{date: {channel: {"s": seconds, "hd": seconds, "dev": {label: seconds}, "h": [24 x seconds],
    "u": unattended seconds (not in s)}}}"""
    days = {}
    new = lambda: {"s": 0, "hd": 0, "dev": {}, "h": [0] * 24, "u": 0}
    for c, devs in watch_spans(events).items():
        for d, (iv, hdiv, uiv) in devs.items():
            for a, b in iv:
                for day, hour, sec in split_hours(a, b):
                    r = days.setdefault(day, {}).setdefault(c, new())
                    r["s"] += sec
                    r["dev"][d] = r["dev"].get(d, 0) + sec
                    r["h"][hour] += sec
            for a, b in hdiv:
                for day, _, sec in split_hours(a, b):
                    days[day][c]["hd"] += sec
            for a, b in uiv:
                for day, _, sec in split_hours(a, b):
                    days.setdefault(day, {}).setdefault(c, new())["u"] += sec
    for chans in days.values():
        for r in chans.values():
            r["s"] = round(r["s"])
            r["hd"] = round(r["hd"])
            r["u"] = round(r["u"])
            r["dev"] = {k: round(v) for k, v in r["dev"].items()}
            r["h"] = [round(v) for v in r["h"]]
    return days


class RateLimit:
    def __init__(self, n, per=60.0):
        self.n, self.per, self.hits = n, per, {}

    def ok(self, key, t) -> bool:
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= t - self.per:
            q.popleft()
        if len(q) >= self.n:
            return False
        q.append(t)
        if len(self.hits) > 5000:
            self.hits = {k: v for k, v in self.hits.items() if v and v[-1] > t - self.per}
        return True


class Watch:
    def __init__(self):
        self.lock = threading.RLock()
        self.events = []
        self.etv = {}       # session id -> event (sessions seen in the raw window)
        self.clients = {}   # hashed client id -> its open beacon event (memory only)
        self.live_etv = {}  # session id -> lastAccess, from the last poll
        self.classified_by = None   # the snapshot (etag) the sessions' channels were read with
        self.daily = {}
        self.dirty = False
        self.computed = None
        self.status = {"enabled": bool(ETV_URL and ETV_API_KEY), "lastPoll": None, "lastError": None,
                       "sessions": 0, "since": None}
        self.rl_client, self.rl_addr, self.rl_all = RateLimit(20), RateLimit(60), RateLimit(600)

    def load(self):
        with self.lock:
            self.events = [e for e in load_json("watch-events.json", []) if isinstance(e, dict) and "k" in e]
            self.etv = {e["id"]: e for e in self.events if e["k"] == "etv" and "id" in e}
            d = load_json("watch-daily.json", {})
            self.daily = d.get("days", {}) if isinstance(d, dict) else {}
            self.status["since"] = d.get("since") if isinstance(d, dict) else None

    # -- poller -------------------------------------------------------------
    def reclassify(self):
        """Sessions seen with no snapshot, or with an older one, counted under the channel the
        current snapshot says (an HD twin under its SD channel, so beacons claim it)."""
        if not snapshot.channels or self.classified_by == snapshot.etag:
            return
        self.classified_by = snapshot.etag
        for sid, e in self.etv.items():
            c, hd = sd_of(sid.split("@", 1)[0])
            if (e.get("c"), e.get("hd")) != (c, int(hd)):
                e["c"], e["hd"] = c, int(hd)
                self.dirty = True

    def poll_once(self, sessions, t=None):
        t = t or time.time()
        with lock:
            snapshot.refresh()
        with self.lock:
            self.reclassify()
            live = {}
            for s in sessions or []:
                if not isinstance(s, dict) or s.get("channelNumber") is None:
                    continue
                raw = str(s["channelNumber"])
                try:
                    a = parse_etv_time(s["startedAt"])
                    b = parse_etv_time(s.get("lastAccess") or s["startedAt"])
                except (KeyError, ValueError, TypeError):
                    continue
                c, hd = sd_of(raw)
                sid = f"{raw}@{s['startedAt']}"
                e = self.etv.get(sid)
                if e is None:
                    e = {"k": "etv", "id": sid, "c": c, "hd": int(hd), "d": "direct", "a": round(a), "b": round(b)}
                    self.etv[sid] = e
                    self.events.append(e)
                    self.dirty = True
                elif round(b) > e["b"]:
                    e["b"] = round(b)
                    self.dirty = True
                live[sid] = b
            self.live_etv = live
            self.status.update(lastPoll=now(), lastError=None, sessions=len(live))

    def fetch_sessions(self):
        req = urllib.request.Request(ETV_URL + "/api/sessions", headers={"X-Etv-Api-Key": ETV_API_KEY})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read(1024 * 1024))

    def run(self):
        while True:
            if self.status["enabled"]:
                try:
                    self.poll_once(self.fetch_sessions())
                except Exception as e:  # noqa: BLE001
                    with self.lock:
                        self.status["lastError"] = f"{now()} {type(e).__name__}: {e}"[:300]
            try:
                self.flush()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"watch flush: {type(e).__name__}: {e}\n")
            time.sleep(POLL_SECONDS)

    # -- beacons ------------------------------------------------------------
    def beacon(self, body, addr, t=None):
        t = t or time.time()
        if not isinstance(body, dict):
            raise BadRequest("body must be a JSON object")
        cid = body.get("client")
        if not isinstance(cid, str) or not CLIENT_RE.match(cid):
            raise BadRequest("client must be 8-64 letters, digits, - or _")
        num = body.get("channel")
        num = str(num) if isinstance(num, (str, int)) else ""
        if not CHANNEL_RE.match(num):
            raise BadRequest("channel must be a channel number")
        with lock:
            snapshot.refresh()
        if snapshot.channels and num not in snapshot.channels:
            raise BadRequest(f"no channel {num} in the snapshot")
        kind = body.get("kind")
        if kind not in KINDS_WATCH:
            raise BadRequest("kind must be web or stream")
        ua = body.get("ua") if body.get("ua") in UA_CLASSES else "other"
        event = body.get("event") or "watch"
        if event not in ("watch", "stop"):
            raise BadRequest("event must be watch or stop")
        warm = body.get("warm") or []
        if not isinstance(warm, list) or len(warm) > 3:
            raise BadRequest("warm must be a list of at most 3 channel numbers")
        idle, after = body.get("idle"), body.get("idleAfter")
        if idle is not None and (isinstance(idle, bool) or not isinstance(idle, (int, float)) or not 0 <= idle <= MAX_IDLE):
            raise BadRequest("idle must be the seconds since the last input")
        if after is not None and (isinstance(after, bool) or not isinstance(after, (int, float)) or not 0 <= after <= MAX_IDLE):
            raise BadRequest("idleAfter must be a number of seconds")
        c, hd = sd_of(num)
        hd = hd or body.get("hd") is True
        key = hashlib.sha256(cid.encode()).hexdigest()[:16]
        if not (self.rl_all.ok("*", t) and self.rl_addr.ok(addr, t) and self.rl_client.ok(key, t)):
            raise BadRequest("too many beacons", HTTPStatus.TOO_MANY_REQUESTS)
        dev = device_label(addr, ua)
        ts = round(t)
        # From when nobody has been at the controls: last input + threshold.
        away = None
        if idle is not None:
            threshold = after if after else WATCH_IDLE_MIN * 60
            if idle >= threshold:
                away = round(ts - idle + threshold)
        with self.lock:
            prev = self.clients.get(key)
            if prev and ts - prev["b"] > BEACON_GAP:
                prev = None
                self.clients.pop(key, None)
            same = prev and prev["c"] == c and prev["kind"] == kind and prev["hd"] == int(hd) and prev["d"] == dev
            if same and "x" in prev and away is None:
                same = False        # back at the controls: a new, attended interval
            if prev:
                prev["b"] = ts      # what it was watching ran until now
                if away is not None and "x" not in prev:
                    prev["x"] = min(ts, max(prev["a"], away))
            if event == "stop":
                self.clients.pop(key, None)
            elif not same:
                e = {"k": "b", "c": c, "d": dev, "kind": kind, "hd": int(hd), "a": ts, "b": ts}
                if away is not None:
                    e["x"] = ts
                self.events.append(e)
                self.clients[key] = e
            for w in warm:
                w = str(w) if isinstance(w, (str, int)) else ""
                if not CHANNEL_RE.match(w) or (snapshot.channels and w not in snapshot.channels):
                    continue
                wc, _ = sd_of(w)
                if wc == c:
                    continue
                last = next((e for e in reversed(self.events[-50:]) if e["k"] == "w" and e["c"] == wc), None)
                if last and last["b"] >= ts:
                    last["b"] = ts + WARM_HOLD
                else:
                    # The warm-up starts ~1 s before the beacon that reports it.
                    self.events.append({"k": "w", "c": wc, "a": ts - 10, "b": ts + WARM_HOLD})
            self.dirty = True
        return {"ok": True, "channel": c, "hd": bool(hd), "device": dev}

    # -- aggregates -----------------------------------------------------------
    def flush(self, t=None):
        t = t or time.time()
        with self.lock:
            cutoff = t - RAW_DAYS * 86400
            before = len(self.events)
            self.events = [e for e in self.events if e["b"] >= cutoff]
            if len(self.events) != before:
                self.dirty = True
                self.etv = {e["id"]: e for e in self.events if e["k"] == "etv"}
            if not self.dirty and self.computed is not None:
                return
            days = watch_days(self.events)
            # Days fully inside the raw window are recomputed; older ones stay as stored.
            first = (dt.datetime.fromtimestamp(cutoff, TZ) + dt.timedelta(days=1)).date().isoformat()
            for day in [d for d in self.daily if d >= first and d not in days]:
                del self.daily[day]
            for day, chans in days.items():
                if day >= first or day not in self.daily:
                    self.daily[day] = chans
            last = (dt.datetime.fromtimestamp(t, TZ) - dt.timedelta(days=DAILY_DAYS)).date().isoformat()
            for day in [d for d in self.daily if d < last]:
                del self.daily[day]
            since = [d for d in (self.status["since"], min(self.daily, default=None)) if d]
            self.status["since"] = min(since) if since else dt.datetime.fromtimestamp(t, TZ).date().isoformat()
            save_json("watch-events.json", self.events)
            atomic_write("watch-daily.json", json.dumps({"since": self.status["since"], "tz": WATCH_TZ,
                                                         "days": self.daily}, separators=(",", ":")).encode())
            self.dirty = False
            self.computed = t

    def live(self, t=None):
        """Who is on which channel right now (device labels only)."""
        t = t or time.time()
        out = {}
        with self.lock:
            for e in self.clients.values():
                if t - e["b"] <= 90:
                    out.setdefault(e["c"], set()).add(e["d"])
            claimed = set(out)
            for e in self.events[-200:]:
                # warm-ups, and a browser that just left: ErsatzTV keeps its session for a while
                if (e["k"] == "w" and e["b"] >= t) or (e["k"] == "b" and e["b"] + CLAIM_AFTER >= t):
                    claimed.add(e["c"])
            for sid, last in self.live_etv.items():
                e = self.etv.get(sid)
                if e and t - last <= 45 and e["c"] not in claimed and e["b"] - e["a"] >= MIN_SESSION:
                    out.setdefault(e["c"], set()).add("direct")
        return [{"channel": c, "devices": sorted(d)} for c, d in sorted(out.items(), key=lambda x: float(x[0]))]

    def report(self, ndays):
        self.flush()
        t = time.time()
        today = dt.datetime.fromtimestamp(t, TZ).date()
        first = (today - dt.timedelta(days=ndays - 1)).isoformat()
        with self.lock:
            days = {d: v for d, v in self.daily.items() if d >= first}
            status = dict(self.status)
        return {"tz": WATCH_TZ, "today": today.isoformat(), "generatedAt": now(), "days": days,
                "live": self.live(t), "poller": status, "since": status.get("since"),
                "rules": {"minSession": MIN_SESSION, "claimBefore": CLAIM_BEFORE, "claimAfter": CLAIM_AFTER,
                          "warmHold": WARM_HOLD, "hdOffsets": HD_OFFSETS, "idleMin": WATCH_IDLE_MIN}}


WATCH_TV_LABEL = (os.environ.get("TRACKER_TV_LABEL") or "").strip()[:24]


def device_label(addr, ua) -> str:
    """Known address first (TRACKER_DEVICES); else the ua class. A viewer in TV
    mode (?tv, as on the Retro TV box) can be given one name with TRACKER_TV_LABEL,
    for when every client shows up with the same address (a proxy, NAT)."""
    if addr in WATCH_DEVICES:
        return WATCH_DEVICES[addr]
    if ua == "tv" and WATCH_TV_LABEL:
        return WATCH_TV_LABEL
    return f"browser ({ua})" if ua in ("tv", "mobile", "desktop") else "browser"


watch = Watch()


# ---------------------------------------------------------------------------
# HTTP

ROUTE_REQ = re.compile(r"^/api/requests/(\d+)$")
ROUTE_PLANNED = re.compile(r"^/api/planned/(\d+)$")


class Handler(BaseHTTPRequestHandler):
    server_version = "retro-tv-tracker"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.path.startswith("/healthz"):
            return
        sys.stdout.write("%s %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    # helpers --------------------------------------------------------------
    def send(self, status, body=b"", ctype="application/json", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if self.path.startswith("/api") else "no-cache")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def error(self, status, msg):
        self.send(status, {"error": msg})

    def authed(self) -> bool:
        got = self.headers.get("X-Tracker-Token", "")
        return bool(TOKEN) and hmac.compare_digest(got.encode(), TOKEN.encode())

    def body(self, limit=MAX_BODY, require_json=True):
        n = self.headers.get("Content-Length")
        if n is None:
            raise BadRequest("Content-Length required", HTTPStatus.LENGTH_REQUIRED)
        # Only a plain count: int() would also take -1 (which passes the limit
        # and reads to the end), "+5" or "1_000".
        n = n.strip()
        if not (n.isascii() and n.isdigit()):
            raise BadRequest("Content-Length must be a number of bytes")
        n = int(n)
        if n > limit:
            raise BadRequest("body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        ct = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if require_json and ct != "application/json":
            raise BadRequest("Content-Type must be application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        raw = self.rfile.read(n) if n else b""
        try:
            return raw, (json.loads(raw) if raw else None)
        except ValueError:
            raise BadRequest("body is not valid JSON")

    def dispatch(self, method):
        u = urlsplit(self.path)
        p = u.path
        qs = parse_qs(u.query)
        try:
            handler = self.route(method, p)
            if handler is None:
                return self.error(HTTPStatus.NOT_FOUND if method in ("GET", "HEAD") or p.startswith("/api")
                                  else HTTPStatus.METHOD_NOT_ALLOWED, "not found")
            handler(qs)
        except BadRequest as e:
            self.error(e.status, str(e))
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"error {method} {p}: {type(e).__name__}: {e}\n")
            self.error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error")

    def route(self, method, p):
        m = ROUTE_REQ.match(p)
        if m:
            rid = int(m.group(1))
            return {"GET": lambda q: self.get_request(rid), "PATCH": lambda q: self.patch_request(rid),
                    "DELETE": lambda q: self.delete_request(rid)}.get(method)
        m = ROUTE_PLANNED.match(p)
        if m:
            pid = int(m.group(1))
            return {"DELETE": lambda q: self.delete_planned(pid)}.get(method)
        table = {
            ("GET", "/healthz"): self.healthz, ("HEAD", "/healthz"): self.healthz,
            ("GET", "/api/snapshot"): self.get_snapshot, ("HEAD", "/api/snapshot"): self.get_snapshot,
            ("PUT", "/api/snapshot"): self.put_snapshot,
            ("GET", "/api/requests"): self.list_requests, ("POST", "/api/requests"): self.create_request,
            ("GET", "/api/planned"): self.list_planned, ("POST", "/api/planned"): self.create_planned,
            ("GET", "/api/meta"): self.meta,
            ("GET", "/api/watch"): self.get_watch,
            ("POST", "/api/watch/beacon"): self.post_beacon, ("OPTIONS", "/api/watch/beacon"): self.beacon_preflight,
        }
        h = table.get((method, p))
        if h:
            return h
        if method in ("GET", "HEAD") and not p.startswith("/api"):
            return lambda q: self.static(p)
        return None

    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        self.dispatch("HEAD")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def do_OPTIONS(self):
        self.dispatch("OPTIONS")

    # endpoints ------------------------------------------------------------
    def healthz(self, q):
        ok = os.access(DATA_DIR, os.W_OK)
        self.send(HTTPStatus.OK if ok else HTTPStatus.SERVICE_UNAVAILABLE,
                  {"ok": ok, "version": VERSION, "snapshot": snapshot.generated})

    def meta(self, q):
        with lock:
            reqs = load_json("requests.json", [])
        self.send(HTTPStatus.OK, {"version": VERSION, "snapshot": snapshot.generated, "tokenConfigured": bool(TOKEN),
                                  "pending": sum(1 for r in reqs if r["status"] == "pending")})

    def get_snapshot(self, q):
        with lock:
            snapshot.refresh()
            raw, gz, etag = snapshot.raw, snapshot.gz, snapshot.etag
        if raw is None:
            return self.error(HTTPStatus.NOT_FOUND, "no snapshot yet: run the generator")
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        hdrs = {"ETag": etag, "Vary": "Accept-Encoding"}
        if "gzip" in (self.headers.get("Accept-Encoding") or ""):
            hdrs["Content-Encoding"] = "gzip"
            return self.send(HTTPStatus.OK, gz, headers=hdrs)
        self.send(HTTPStatus.OK, raw, headers=hdrs)

    def put_snapshot(self, q):
        if not self.authed():
            # read and discard nothing: refuse before reading a large body
            self.close_connection = True
            return self.error(HTTPStatus.FORBIDDEN, "X-Tracker-Token missing or wrong")
        raw, obj = self.body(MAX_SNAPSHOT)
        err = validate_snapshot(obj)
        if err:
            raise BadRequest(err)
        with lock:
            atomic_write("snapshot.json", raw)
            snapshot.mtime = None
            snapshot.refresh()
        self.send(HTTPStatus.OK, {"ok": True, "generatedAt": obj.get("generatedAt"),
                                  "channels": len(obj["channels"]), "shows": len(obj["library"]["shows"]),
                                  "movies": len(obj["library"]["movies"])})

    def list_requests(self, q):
        status = (q.get("status") or [None])[0]
        with lock:
            reqs = load_json("requests.json", [])
            planned = load_json("planned.json", [])
            snapshot.refresh()
        if status:
            reqs = [r for r in reqs if r["status"] == status]
        if (q.get("format") or [""])[0] == "text":
            return self.send(HTTPStatus.OK, text_export(reqs, planned), "text/plain; charset=utf-8")
        self.send(HTTPStatus.OK, reqs)

    def get_request(self, rid):
        with lock:
            r = next((r for r in load_json("requests.json", []) if r["id"] == rid), None)
        if not r:
            return self.error(HTTPStatus.NOT_FOUND, "no such request")
        self.send(HTTPStatus.OK, r)

    def create_request(self, q):
        _, body = self.body()
        with lock:
            snapshot.refresh()
            reqs = load_json("requests.json", [])
            planned = load_json("planned.json", [])
            r = build_request(body, planned)
            r = {"id": next_id(reqs), **r}
            reqs.append(r)
            save_json("requests.json", reqs)
        self.send(HTTPStatus.CREATED, r)

    def patch_request(self, rid):
        _, body = self.body()
        if not isinstance(body, dict):
            raise BadRequest("body must be a JSON object")
        with lock:
            reqs = load_json("requests.json", [])
            r = next((r for r in reqs if r["id"] == rid), None)
            if not r:
                return self.error(HTTPStatus.NOT_FOUND, "no such request")
            status = body.get("status")
            privileged = (status is not None and status != r["status"]) or "result" in body or r["status"] != "pending"
            if privileged and not self.authed():
                return self.error(HTTPStatus.FORBIDDEN, "changing status or result needs X-Tracker-Token")
            if status is not None:
                if status not in STATUSES:
                    raise BadRequest(f"status must be one of {', '.join(STATUSES)}")
                r["status"] = status
                r["appliedAt"] = now() if status != "pending" else None
            if "result" in body:
                r["result"] = clean_str(body["result"], "result", 8000)
            if "note" in body:
                r["note"] = clean_str(body["note"], "note", 4000)
            save_json("requests.json", reqs)
        self.send(HTTPStatus.OK, r)

    def delete_request(self, rid):
        with lock:
            reqs = load_json("requests.json", [])
            r = next((r for r in reqs if r["id"] == rid), None)
            if not r:
                return self.error(HTTPStatus.NOT_FOUND, "no such request")
            if r["status"] != "pending" and not self.authed():
                return self.error(HTTPStatus.FORBIDDEN, "only pending requests can be deleted without the token")
            reqs.remove(r)
            save_json("requests.json", reqs)
        self.send(HTTPStatus.OK, {"ok": True, "deleted": rid})

    def list_planned(self, q):
        with lock:
            self.send(HTTPStatus.OK, load_json("planned.json", []))

    def create_planned(self, q):
        _, body = self.body()
        if not isinstance(body, dict):
            raise BadRequest("body must be a JSON object")
        name = clean_str(body.get("name"), "name", 80, required=True)
        number = clean_str(body.get("number"), "number", 10)
        if number and not re.fullmatch(r"\d{1,4}(\.\d{1,2})?", number):
            raise BadRequest("number must look like 12 or 12.5")
        kind = clean_str(body.get("kind"), "kind", 10)
        if kind and kind not in KINDS:
            raise BadRequest(f"kind must be one of {', '.join(KINDS)}")
        note = clean_str(body.get("note"), "note", 4000)
        with lock:
            snapshot.refresh()
            if number and number in snapshot.channels:
                raise BadRequest(f"channel {number} already exists ({snapshot.channels[number]})", HTTPStatus.CONFLICT)
            planned = load_json("planned.json", [])
            p = {"id": next_id(planned), "name": name, "number": number, "kind": kind, "note": note,
                 "createdAt": now()}
            planned.append(p)
            save_json("planned.json", planned)
        self.send(HTTPStatus.CREATED, p)

    def delete_planned(self, pid):
        with lock:
            planned = load_json("planned.json", [])
            p = next((p for p in planned if p["id"] == pid), None)
            if not p:
                return self.error(HTTPStatus.NOT_FOUND, "no such planned channel")
            reqs = load_json("requests.json", [])
            used = [r["id"] for r in reqs if r["status"] == "pending" and any(
                (c or {}).get("planned") == pid for c in (r.get("channel"), r.get("from")))]
            if used:
                raise BadRequest(f"pending requests {used} target this planned channel; delete them first",
                                 HTTPStatus.CONFLICT)
            planned.remove(p)
            save_json("planned.json", planned)
        self.send(HTTPStatus.OK, {"ok": True, "deleted": pid})

    # watch tracking ---------------------------------------------------------
    def client_addr(self) -> str:
        """The sender's address; with TRACKER_TRUST_PROXY, the last X-Forwarded-For
        entry when the peer (the reverse proxy) is a private address."""
        peer = self.client_address[0]
        xff = self.headers.get("X-Forwarded-For")
        try:
            if TRUST_PROXY and xff and ipaddress.ip_address(peer).is_private:
                return str(ipaddress.ip_address(xff.split(",")[-1].strip()))
        except ValueError:
            pass
        return peer

    def cors(self):
        origin = self.headers.get("Origin")
        if not origin_allowed(origin):
            return None
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600"}

    def beacon_preflight(self, q):
        hdrs = self.cors()
        if hdrs is None:
            return self.error(HTTPStatus.FORBIDDEN, "origin not allowed")
        self.send(HTTPStatus.NO_CONTENT, b"", headers=hdrs)

    def post_beacon(self, q):
        hdrs = self.cors()
        if hdrs is None:
            self.close_connection = True
            return self.error(HTTPStatus.FORBIDDEN, "origin not allowed")
        ct = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct not in ("application/json", "text/plain"):
            raise BadRequest("Content-Type must be text/plain or application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        try:
            _, body = self.body(2048, require_json=False)
            r = watch.beacon(body, self.client_addr())
        except BadRequest as e:
            return self.send(e.status, {"error": str(e)}, headers=hdrs)
        self.send(HTTPStatus.OK, r, headers=hdrs)

    def get_watch(self, q):
        try:
            n = int((q.get("days") or ["30"])[0])
        except ValueError:
            raise BadRequest("days must be a number")
        self.send(HTTPStatus.OK, watch.report(max(1, min(n, DAILY_DAYS))))

    def static(self, p):
        if p in ("", "/"):
            p = "/index.html"
        rel = os.path.normpath(p.lstrip("/"))
        if rel.startswith("..") or os.path.isabs(rel):
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        full = os.path.join(STATIC_DIR, rel)
        ext = os.path.splitext(full)[1]
        if ext not in STATIC_TYPES or not os.path.isfile(full):
            return self.error(HTTPStatus.NOT_FOUND, "not found")
        with open(full, "rb") as f:
            data = f.read()
        self.send(HTTPStatus.OK, data, STATIC_TYPES[ext])


def load_token() -> str:
    """TRACKER_TOKEN, else DATA_DIR/token, made at first start (never printed)."""
    if TOKEN:
        return TOKEN
    p = path_of("token")
    try:
        with open(p) as f:
            t = f.read().strip()
        if t:
            return t
    except FileNotFoundError:
        pass
    t = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t + "\n")
    print(f"made a new token in {p} (TRACKER_TOKEN is not set)", flush=True)
    return t


def main():
    global TOKEN
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        TOKEN = load_token()
    except OSError as e:
        print(f"warning: no TRACKER_TOKEN and could not make {path_of('token')} ({e}); "
              "snapshot uploads and closing requests are disabled", flush=True)
    try:
        snapshot.refresh()
    except (ValueError, OSError) as e:
        print(f"warning: could not load snapshot.json: {e}", flush=True)
    try:
        watch.load()
    except (ValueError, OSError) as e:
        print(f"warning: could not load the watch data: {e}", flush=True)
    if not watch.status["enabled"]:
        print("note: ERSATZTV_URL or ERSATZTV_API_KEY is not set; the ErsatzTV session poller is off, "
              "only viewer beacons count", flush=True)
    threading.Thread(target=watch.run, name="watch", daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print(f"retro-tv-tracker {VERSION} on :{PORT}, data in {DATA_DIR}, days in {WATCH_TZ}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

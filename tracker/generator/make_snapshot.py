#!/usr/bin/env python3
"""Build snapshot.json for the channel tracker and upload it.

Runs wherever it can reach ErsatzTV's database: the ErsatzTV host, or a PC
with ssh, docker or kubectl access to it. Python 3.9+, standard library only.

1. Takes a consistent copy of ErsatzTV's SQLite database without writing to
   it. Where python3 is available next to the database (the host, or inside
   the container) a one-shot opens it read-only and uses SQLite's online
   backup API; otherwise the database and its WAL are read with cat and the
   copy is checked (and the read retried) before use. Access is one of:
     file     a path on this machine (or on --ssh HOST)
     docker   docker exec into the ErsatzTV container
     kubectl  kubectl exec into the ErsatzTV pod (k3s: --kubectl "k3s kubectl")
   and any of them can run on another machine over ssh (--ssh HOST).
2. Resolves each channel's members the way ErsatzTV does: channel -> playout
   -> schedule -> schedule items -> smart collection -> search query. The
   query is evaluated here by a small evaluator for the common subset of
   ErsatzTV's Lucene syntax (field:term, field:"phrase", ranges, AND/OR/NOT,
   parentheses). A query outside that subset leaves the channel without
   members, unless an optional lineup file (--lineup) names its shows.
3. Cross-checks: every programme in the channel's current playout must be in
   the resolved member set; the result is stored per channel.
4. Reads the channel list and version from the ErsatzTV API (GET only).
5. PUTs the snapshot to the tracker with X-Tracker-Token.

Settings come from the command line, else the environment, else an env file
(default ~/.config/retro-tv-tracker/env; KEY=value lines). See tracker/README.md.
Secrets (ErsatzTV API key, tracker token) are read into memory and never
printed.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import json
import math
import os
import posixpath
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ENV_FILE = os.path.expanduser("~/.config/retro-tv-tracker/env")
DEFAULTS = {
    "ETV_DB_ACCESS": "file",                       # file | docker | kubectl
    "ETV_DB_PATH": "/config/ersatztv.sqlite3",     # inside the container for docker/kubectl
    "ETV_SSH": "",                                 # run the access command on this ssh host
    "ETV_DOCKER": "docker",                        # e.g. "sudo docker"
    "ETV_CONTAINER": "ersatztv",
    "ETV_KUBECTL": "kubectl",                      # e.g. "k3s kubectl" or "sudo k3s kubectl"
    "ETV_K8S_NAMESPACE": "ersatztv",
    "ETV_K8S_TARGET": "deploy/ersatztv",           # a pod, or deploy/<name>
}

# A "qualifying ad break": a chapter boundary where a mid-roll expression of
# the form "point > A and remaining_duration > B and last_mid_filler > C"
# would place a break. Default: the shows' rule in docs/tv.html.
DEFAULT_BREAK_RULE = "240,180,300"
BREAK = (240.0, 180.0, 300.0)   # set from --break-rule in main()

PLAYBACK_ORDER = {
    0: "None", 1: "Chronological", 2: "Random", 3: "Shuffle", 4: "Shuffle in order",
    5: "Multi-episode shuffle", 6: "Season, episode", 7: "Random rotation", 8: "Marathon",
}
FILLER_KIND = {0: "none", 1: "pre-roll", 2: "mid-roll", 3: "post-roll", 4: "tail", 5: "fallback"}
FILLER_MODE = {0: "none", 1: "duration", 2: "count", 3: "pad", 4: "random count"}

# The far half, when python3 is there: open read-only, back up to a temp
# file, stream it gzipped, delete the temp file.
REMOTE_COPY = r'''
import gzip, os, sqlite3, sys, tempfile
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
fd, tmp = tempfile.mkstemp(prefix="etv-tracker-", suffix=".sqlite3")
os.close(fd)
try:
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as f:
        sys.stdout.buffer.write(gzip.compress(f.read(), 3))
finally:
    os.remove(tmp)
'''


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Settings

def read_env_file(path: str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:].strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


class Settings(dict):
    """Command line > environment > env file > defaults."""

    def __init__(self, args, env_file):
        super().__init__(DEFAULTS)
        self.update({k: v for k, v in read_env_file(env_file).items() if v})
        for k in list(DEFAULTS) + ["TRACKER_URL", "TRACKER_TOKEN", "ERSATZTV_URL", "ERSATZTV_API_KEY"]:
            if os.environ.get(k):
                self[k] = os.environ[k]
        for k, v in vars(args).items():
            if k.isupper() and v is not None:
                self[k] = v


# --------------------------------------------------------------------------
# Fetching: run a command where the database is

class Source:
    def __init__(self, cfg: Settings):
        self.access = cfg["ETV_DB_ACCESS"]
        if self.access not in ("file", "docker", "kubectl"):
            raise SystemExit(f"ETV_DB_ACCESS must be file, docker or kubectl (not {self.access!r})")
        self.path = cfg["ETV_DB_PATH"]
        self.ssh = cfg["ETV_SSH"]
        if self.access == "docker":
            self.prefix = shlex.split(cfg["ETV_DOCKER"]) + ["exec", "-i", cfg["ETV_CONTAINER"]]
            where = f"container {cfg['ETV_CONTAINER']}"
        elif self.access == "kubectl":
            self.prefix = shlex.split(cfg["ETV_KUBECTL"]) + ["exec", "-i", "-n", cfg["ETV_K8S_NAMESPACE"],
                                                           cfg["ETV_K8S_TARGET"], "--"]
            where = f"{cfg['ETV_K8S_NAMESPACE']}/{cfg['ETV_K8S_TARGET']}"
        else:
            self.prefix = []
            where = "this machine" if not self.ssh else "the host"
        self.label = f"{self.path} in {where}" + (f" on {self.ssh}" if self.ssh else "")

    @property
    def local(self) -> bool:
        return self.access == "file" and not self.ssh

    def run(self, argv: list[str], stdin: bytes | None = None, check=True) -> bytes:
        cmd = self.prefix + argv
        if self.ssh:
            cmd = ["ssh", "-o", "BatchMode=yes", "-T", self.ssh, shlex.join(cmd)]
        r = subprocess.run(cmd, input=stdin, capture_output=True, timeout=600)
        if check and r.returncode != 0:
            raise SystemExit(f"{shlex.join(cmd[:8])}... failed ({r.returncode}): {r.stderr.decode(errors='replace')[:500]}")
        return r.stdout if r.returncode == 0 else b""

    def has_python(self) -> bool:
        out = self.run(["sh", "-c", "command -v python3 >/dev/null 2>&1 && echo yes || echo no"])
        return out.strip() == b"yes"

    def fetch_db(self, dest: str) -> str:
        """Copy the database to dest; returns how it was copied."""
        if self.local:
            src = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            dst = sqlite3.connect(dest)
            src.backup(dst)
            dst.close()
            src.close()
            return "SQLite backup API, read-only"
        if self.has_python():
            data = self.run(["python3", "-I", "-", self.path], stdin=REMOTE_COPY.encode())
            with open(dest, "wb") as f:
                f.write(gzip.decompress(data))
            return "SQLite backup API, read-only"
        # No python3 there: read the files. A checkpoint between the two reads
        # can leave a copy that fails the check; then read again.
        for attempt in range(1, 4):
            db = self.run(["cat", self.path])
            wal = self.run(["sh", "-c", 'if [ -f "$1-wal" ]; then cat "$1-wal"; fi', "sh", self.path])
            for suffix in ("-wal", "-shm"):
                if os.path.exists(dest + suffix):
                    os.remove(dest + suffix)
            with open(dest, "wb") as f:
                f.write(db)
            if wal:
                with open(dest + "-wal", "wb") as f:
                    f.write(wal)
            try:
                c = sqlite3.connect(dest)
                ok = c.execute("pragma quick_check").fetchone()[0] == "ok"
                c.execute("pragma wal_checkpoint(TRUNCATE)")
                c.execute("pragma journal_mode=DELETE")
                c.close()
            except sqlite3.DatabaseError:
                ok = False
            if ok:
                return f"file copy (no python3 there), checked, attempt {attempt}"
            log(f"  the copy failed SQLite's check (attempt {attempt}); reading again")
            time.sleep(2)
        raise SystemExit("could not get a consistent copy of the database")

    def read_text(self, path: str) -> str | None:
        try:
            if self.local:
                with open(path) as f:
                    return f.read()
            out = self.run(["cat", path], check=False)
            return out.decode() if out else None
        except (OSError, UnicodeDecodeError):
            return None


def fetch_api_key(cfg: Settings, src: Source) -> str | None:
    """ERSATZTV_API_KEY, else ApiKey from api-secrets.json next to the database."""
    if cfg.get("ERSATZTV_API_KEY"):
        return cfg["ERSATZTV_API_KEY"]
    raw = src.read_text(posixpath.join(posixpath.dirname(src.path), "api-secrets.json"))
    try:
        return json.loads(raw).get("ApiKey") if raw else None
    except (ValueError, AttributeError):
        return None


def api_get(base: str, path: str, key: str | None):
    req = urllib.request.Request(base.rstrip("/") + "/api" + path)
    if key:
        req.add_header("X-Etv-Api-Key", key)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------
# Query evaluation (subset of ErsatzTV's Lucene syntax)

STOP = set("a an and are as at be but by for if in into is it no not of on or such that the "
           "their then there these they this to was will with".split())
TOKEN_RE = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)


def analyze(text: str | None) -> list[tuple[int, str]]:
    """StandardAnalyzer-like: lowercase word tokens, stop words dropped, positions kept."""
    out = []
    for i, m in enumerate(TOKEN_RE.finditer((text or "").lower())):
        t = m.group(0).replace("’", "'")
        if t not in STOP:
            out.append((i, t))
    return out


class Unsupported(Exception):
    pass


ANALYZED = {"title", "show_title", "genre", "tag", "studio", "actor", "director", "plot",
            "library_name", "network", "writer"}
EXACT = {"type", "state", "season_number", "episode_number", "release_date", "year",
         "content_rating", "minutes", "height", "width"}

QTOKEN = re.compile(r'''\s*(?:
    (?P<lp>\() | (?P<rp>\)) |
    (?P<op>AND\b|OR\b|NOT\b|&&|\|\|) |
    (?P<mod>[+-])(?=[a-z_(]) |
    (?P<field>[a-z_]+):(?:
        "(?P<phrase>(?:[^"\\]|\\.)*)" |
        (?P<range>[\[{]\s*\S+\s+TO\s+\S+\s*[\]}]) |
        (?P<term>[^\s()"]+)
    ) |
    (?P<bad>\S+)
)''', re.X)


def tokenize_query(q: str):
    pos, out = 0, []
    while pos < len(q):
        m = QTOKEN.match(q, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group("lp"):
            out.append(("(",))
        elif m.group("rp"):
            out.append((")",))
        elif m.group("op"):
            op = {"&&": "AND", "||": "OR"}.get(m.group("op"), m.group("op"))
            out.append((op,))
        elif m.group("mod"):
            out.append(("NOT",) if m.group("mod") == "-" else ("+",))
        elif m.group("field"):
            f = m.group("field")
            if f not in ANALYZED and f not in EXACT:
                raise Unsupported(f"field {f}")
            if m.group("phrase") is not None:
                out.append(("phrase", f, m.group("phrase").replace('\\"', '"')))
            elif m.group("range"):
                r = m.group("range")
                mm = re.match(r"([\[{])\s*(\S+)\s+TO\s+(\S+)\s*([\]}])", r)
                out.append(("range", f, mm.group(2), mm.group(3), mm.group(1) == "[", mm.group(4) == "]"))
            else:
                t = m.group("term")
                if any(ch in t for ch in "*?~^"):
                    raise Unsupported(f"operator in {t}")
                out.append(("term", f, t))
        elif m.group("bad") and m.group("bad").strip():
            raise Unsupported(f"token {m.group('bad')}")
    return out


def parse_query(q: str):
    """The query as Lucene's classic parser reads it (ErsatzTV's, default operator OR).
    Each group, the whole query or one in parentheses, is a flat list of clauses, each
    required (+, or joined by AND), optional (plain, or joined by OR) or prohibited (- or
    NOT): a document matches when it has every required clause and no prohibited one, and,
    when nothing is required, at least one optional clause. So NOT never adds "everything
    else": `a NOT b` is a without b, and `a OR b AND NOT c` is b without c (AND makes b
    required, and a, still optional, no longer counts). A group of only prohibited clauses
    matches nothing in Lucene; it is reported as unsupported rather than guessed at.
    Tree: ("bool", must, should, must_not), or a single clause as it is."""
    toks = tokenize_query(q)
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def parse_group():
        nonlocal i
        clauses = []  # [occur, node]; occur is "must", "should" or "must_not"
        while True:
            t = peek()
            if t is None or t == (")",):
                break
            conj = None
            if t in (("AND",), ("OR",)):
                if not clauses:
                    raise Unsupported(f"{t[0]} at the start")
                conj = t[0]
                i += 1
            mod = None
            if peek() in (("NOT",), ("+",)):
                mod = peek()[0]
                i += 1
            node = parse_primary()
            # AND makes the clause before it required too, unless it is prohibited
            if conj == "AND" and clauses[-1][0] != "must_not":
                clauses[-1][0] = "must"
            if mod == "NOT":
                occur = "must_not"
            elif mod == "+" or conj == "AND":
                occur = "must"
            else:
                occur = "should"    # implicit OR (Lucene default operator)
            clauses.append([occur, node])
        if not clauses:
            raise Unsupported("empty query")
        if len(clauses) == 1 and clauses[0][0] != "must_not":
            return clauses[0][1]
        must = [n for o, n in clauses if o == "must"]
        should = [n for o, n in clauses if o == "should"]
        must_not = [n for o, n in clauses if o == "must_not"]
        if not must and not should:
            raise Unsupported("only NOT clauses (Lucene matches nothing)")
        return ("bool", must, should, must_not)

    def parse_primary():
        nonlocal i
        t = peek()
        if t is None:
            raise Unsupported("unexpected end")
        i += 1
        if t == ("(",):
            node = parse_group()
            if peek() != (")",):
                raise Unsupported("unbalanced parentheses")
            i += 1
            return node
        if t[0] in ("phrase", "term", "range"):
            return t
        raise Unsupported(f"unexpected {t}")

    tree = parse_group()
    if i != len(toks):
        raise Unsupported("unbalanced parentheses")
    return tree


def phrase_match(doc: list[tuple[int, str]], query: list[tuple[int, str]]) -> bool:
    if not query:
        return False
    base = query[0][0]
    rel = [(p - base, t) for p, t in query]
    at = {p: t for p, t in doc}
    for p, t in doc:
        if t == rel[0][1] and all(at.get(p + off) == tt for off, tt in rel[1:]):
            return True
    return False


def evaluate(node, doc) -> bool:
    kind = node[0]
    if kind == "bool":
        _, must, should, must_not = node
        if any(evaluate(n, doc) for n in must_not):
            return False
        if must:
            return all(evaluate(n, doc) for n in must)
        return any(evaluate(n, doc) for n in should)
    field = node[1]
    values = doc.get(field)
    if not values:
        return False
    if kind == "range":
        lo, hi, inc_lo, inc_hi = node[2], node[3], node[4], node[5]
        for v in values:
            a = (v >= lo) if inc_lo else (v > lo)
            b = (v <= hi) if inc_hi else (v < hi)
            if lo.isdigit() and hi.isdigit() and v.isdigit():
                a = int(v) >= int(lo) if inc_lo else int(v) > int(lo)
                b = int(v) <= int(hi) if inc_hi else int(v) < int(hi)
            if a and b:
                return True
        return False
    text = node[2]
    if field in EXACT:
        return any(v.lower() == text.lower() for v in values)
    q = analyze(text)
    if kind == "term" and len(q) == 1:
        return any(any(t == q[0][1] for _, t in v) for v in values)
    return any(phrase_match(v, q) for v in values)


# --------------------------------------------------------------------------
# Helpers

def span(s: str | None) -> float:
    """.NET TimeSpan text ([-][d.]hh:mm:ss[.fffffff]) to seconds."""
    if not s:
        return 0.0
    neg = s.startswith("-")
    s = s.lstrip("-")
    days = 0
    m = re.match(r"(?:(\d+)\.)?(\d+):(\d+):(\d+(?:\.\d+)?)$", s)
    if not m:
        return 0.0
    days = int(m.group(1) or 0)
    v = days * 86400 + int(m.group(2)) * 3600 + int(m.group(3)) * 60 + float(m.group(4))
    return -v if neg else v


MIRROR = 1  # Channel.PlayoutSource: 0 Generated (its own playout), 1 Mirror


def mirror_source(channels: dict, ch_id):
    """The channel whose playout channel ch_id plays: itself, or for a mirror (an HD
    twin: PlayoutSource Mirror, no playout of its own) its MirrorSourceChannelId,
    followed through a mirror of a mirror. None when the chain ends at a channel
    that is not there or comes round again. channels: Id -> row (a dict or
    sqlite3.Row); an ErsatzTV without mirrors has no such columns."""
    seen = set()
    while ch_id in channels and ch_id not in seen:
        seen.add(ch_id)
        ch = channels[ch_id]
        keys = ch.keys()
        if "PlayoutSource" not in keys or ch["PlayoutSource"] != MIRROR:
            return ch_id
        ch_id = ch["MirrorSourceChannelId"] if "MirrorSourceChannelId" in keys else None
    return None


def res_label(w: int | None, h: int | None) -> str:
    w, h = w or 0, h or 0
    if w >= 3000 or h >= 2000:
        return "4K"
    if w >= 1800 or h >= 1000:
        return "1080p"
    if w >= 1200 or h >= 700:
        return "720p"
    return "SD" if (w or h) else "?"


def parse_break_rule(s: str) -> tuple[float, float, float]:
    try:
        a, b, c = (float(x) for x in s.split(","))
        return a, b, c
    except ValueError:
        raise SystemExit("--break-rule must be three numbers: point,remaining_duration,last_mid_filler")


def break_rule_text() -> str:
    a, b, c = (f"{x:g}" for x in BREAK)
    return f"point > {a} and remaining_duration > {b} and last_mid_filler > {c}"


def breaks_for(chapter_starts: list[float], duration: float) -> int:
    min_point, min_remaining, min_gap = BREAK
    n, last = 0, 0.0
    for p in chapter_starts:
        if p > min_point and duration - p > min_remaining and p - last > min_gap:
            n += 1
            last = p
    return n


def size_fields(v: dict) -> dict:
    """minutes (rounded up, as ErsatzTV indexes it), height and width."""
    out = {"minutes": [str(math.ceil(v["dur"] / 60))] if v["dur"] else []}
    for k, f in (("h", "height"), ("w", "width")):
        out[f] = [str(v[k])] if v[k] else []
    return out


def ymd(s: str | None) -> str | None:
    if not s or s.startswith("0001"):
        return None
    return s[:10].replace("-", "")


# --------------------------------------------------------------------------
# Build

def build(db_path: str, lineup_path: str | None, api_channels, api_version, source_label: str = "") -> dict:
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = lambda sql, *a: c.execute(sql, a).fetchall()  # noqa: E731

    def multi(table, col):
        d = collections.defaultdict(list)
        for r in q(f"select {col} k, Name from {table} where {col} is not null order by Id"):
            if r["Name"] not in d[r["k"]]:
                d[r["k"]].append(r["Name"])
        return d

    genres_m, genres_s = multi("Genre", "MovieMetadataId"), multi("Genre", "ShowMetadataId")
    studios_m, studios_s = multi("Studio", "MovieMetadataId"), multi("Studio", "ShowMetadataId")
    directors_m = multi("Director", "MovieMetadataId")
    tags_o = multi("Tag", "OtherVideoMetadataId")

    # media versions, chapters
    ver = {}
    for r in q("select Id, coalesce(EpisodeId, MovieId, OtherVideoId) item, Duration, Width, Height from MediaVersion"):
        ver[r["item"]] = {"vid": r["Id"], "dur": span(r["Duration"]), "w": r["Width"], "h": r["Height"]}
    chap = collections.defaultdict(list)
    for r in q("select MediaVersionId v, StartTime s from MediaChapter order by MediaVersionId, StartTime"):
        chap[r["v"]].append(max(0.0, span(r["s"])))
    paths = {r["v"]: r["Path"] for r in q("select MediaVersionId v, Path from MediaFile")}
    state = {r["Id"]: r["State"] for r in q("select Id, State from MediaItem")}
    lib_of_item = {r["Id"]: r["Name"] for r in q(
        "select mi.Id, l.Name from MediaItem mi join LibraryPath lp on lp.Id = mi.LibraryPathId join Library l on l.Id = lp.LibraryId")}

    def media_stats(item_id):
        v = ver.get(item_id) or {"vid": None, "dur": 0.0, "w": None, "h": None}
        starts = sorted(set(chap.get(v["vid"], [])))
        nch = len(starts)
        inner = [s for s in starts if s > 1.0]
        return v, nch, breaks_for(inner, v["dur"])

    # documents for the query evaluator
    docs = {}
    movies = []
    for r in q("select m.Id, mm.Id mid, mm.Title, mm.Year, mm.ReleaseDate, mm.ContentRating, mm.SortTitle "
               "from Movie m join MovieMetadata mm on mm.MovieId = m.Id"):
        v, nch, br = media_stats(r["Id"])
        g = genres_m.get(r["mid"], [])
        rd = ymd(r["ReleaseDate"])
        docs[r["Id"]] = {"type": ["movie"], "title": [analyze(r["Title"])], "release_date": [rd] if rd else [],
                         "year": [str(r["Year"])] if r["Year"] else [], "genre": [analyze(x) for x in g],
                         "studio": [analyze(x) for x in studios_m.get(r["mid"], [])],
                         "director": [analyze(x) for x in directors_m.get(r["mid"], [])],
                         "content_rating": [r["ContentRating"]] if r["ContentRating"] else [],
                         "state": ["FileNotFound" if state.get(r["Id"]) == 1 else "Normal"],
                         "library_name": [analyze(lib_of_item.get(r["Id"]))], **size_fields(v)}
        p = paths.get(v["vid"]) or ""
        movies.append({"id": r["Id"], "t": r["Title"], "st": r["SortTitle"] or r["Title"], "y": r["Year"],
                       "r": r["ContentRating"], "g": g, "d": directors_m.get(r["mid"], [])[:2],
                       "m": round(v["dur"] / 60), "q": res_label(v["w"], v["h"]),
                       "wh": f"{v['w']}x{v['h']}" if v["w"] else None,
                       "ch": nch, "br": br, "f": p.rsplit("/", 1)[-1], "on": []})

    shows = {}
    for r in q("select s.Id, sm.Id mid, sm.Title, sm.Year, sm.ContentRating, sm.SortTitle "
               "from Show s join ShowMetadata sm on sm.ShowId = s.Id"):
        shows[r["Id"]] = {"id": r["Id"], "t": r["Title"], "st": r["SortTitle"] or r["Title"], "y": r["Year"],
                          "r": r["ContentRating"], "g": genres_s.get(r["mid"], []),
                          "studio": studios_s.get(r["mid"], [])[:2], "_mid": r["mid"]}
    episodes = {}
    for r in q("select e.Id, se.ShowId, se.SeasonNumber, em.Title, em.EpisodeNumber, em.ReleaseDate "
               "from Episode e join Season se on se.Id = e.SeasonId "
               "left join EpisodeMetadata em on em.EpisodeId = e.Id"):
        v, nch, br = media_stats(r["Id"])
        sh = shows.get(r["ShowId"])
        if not sh:
            continue
        episodes[r["Id"]] = {"show": r["ShowId"], "season": r["SeasonNumber"], "dur": v["dur"],
                             "ch": nch, "br": br, "q": res_label(v["w"], v["h"])}
        rd = ymd(r["ReleaseDate"])
        docs[r["Id"]] = {"type": ["episode"], "title": [analyze(r["Title"])], "show_title": [analyze(sh["t"])],
                         "season_number": [str(r["SeasonNumber"])],
                         "episode_number": [str(r["EpisodeNumber"])] if r["EpisodeNumber"] is not None else [],
                         "release_date": [rd] if rd else [], "genre": [analyze(x) for x in sh["g"]],
                         "content_rating": [sh["r"]] if sh["r"] else [],
                         "state": ["FileNotFound" if state.get(r["Id"]) == 1 else "Normal"],
                         "library_name": [analyze(lib_of_item.get(r["Id"]))], **size_fields(v)}
    for r in q("select o.Id, om.Id mid, om.Title from OtherVideo o join OtherVideoMetadata om on om.OtherVideoId = o.Id"):
        docs[r["Id"]] = {"type": ["other_video"], "title": [analyze(r["Title"])],
                         "tag": [analyze(x) for x in tags_o.get(r["mid"], [])],
                         "state": ["FileNotFound" if state.get(r["Id"]) == 1 else "Normal"],
                         "library_name": [analyze(lib_of_item.get(r["Id"]))]}

    # per-show library aggregates
    by_show = collections.defaultdict(list)
    for eid, e in episodes.items():
        by_show[e["show"]].append(e)

    def show_agg(eps):
        regular = [e for e in eps if e["season"] != 0]
        dur = sum(e["dur"] for e in eps)
        qs = collections.Counter(e["q"] for e in eps)
        return {"n": len(eps), "se": len({e["season"] for e in regular}),
                "sp": len(eps) - len(regular), "h": round(dur / 3600, 1),
                "m": round(dur / 60 / len(eps)) if eps else 0,
                "ch": sum(1 for e in eps if e["ch"] >= 2), "bre": sum(1 for e in eps if e["br"] > 0),
                "br": sum(e["br"] for e in eps), "q": qs.most_common(1)[0][0] if qs else "?"}

    for sid, sh in shows.items():
        sh.update(show_agg(by_show.get(sid, [])))
        sh["on"] = []

    # smart collections
    smart = {r["Id"]: {"name": r["Name"], "query": r["Query"]} for r in q("select * from SmartCollection")}
    resolved_cache = {}

    def resolve_smart(sc_id):
        if sc_id in resolved_cache:
            return resolved_cache[sc_id]
        sc = smart[sc_id]
        try:
            tree = parse_query(sc["query"])
            ids = {i for i, d in docs.items() if evaluate(tree, d)}
            res = (ids, "query", None)
        except Unsupported as e:
            res = (None, "unsupported", str(e))
        resolved_cache[sc_id] = res
        return res

    presets = {r["Id"]: dict(r) for r in q("select * from FillerPreset")}

    def preset_desc(pid, role):
        p = presets.get(pid)
        if not p:
            return None
        pool = None
        if p["SmartCollectionId"] in smart:
            ids, _, _ = resolve_smart(p["SmartCollectionId"])
            pool = {"collection": smart[p["SmartCollectionId"]]["name"], "items": len(ids) if ids is not None else None}
        return {"role": role, "name": p["Name"], "kind": FILLER_KIND.get(p["FillerKind"], str(p["FillerKind"])),
                "mode": FILLER_MODE.get(p["FillerMode"], str(p["FillerMode"])), "expression": p["Expression"],
                "padToMinutes": p["PadToNearestMinute"], "pool": pool}

    # Optional: {"channels": [{"number": "24", "shows": ["Show title", ...]}, ...]} for
    # channels whose query the evaluator cannot read.
    lineup = {}
    if lineup_path:
        with open(lineup_path) as f:
            for ch in json.load(f).get("channels", []):
                lineup[str(ch.get("number"))] = ch
    show_by_title = collections.defaultdict(list)
    for sid, sh in shows.items():
        show_by_title[sh["t"].casefold()].append(sid)

    mode_tables = {t: {r[0] for r in q(f"select Id from {t}")} for t in
                   ("ProgramScheduleOneItem", "ProgramScheduleMultipleItem", "ProgramScheduleDurationItem",
                    "ProgramScheduleFloodItem")}

    def mode_of(item_id):
        for t, s in mode_tables.items():
            if item_id in s:
                return t.replace("ProgramSchedule", "").replace("Item", "")
        return "?"

    mv_by_id = {m["id"]: m for m in movies}
    profiles = {r["Id"]: r["Name"] for r in q("select Id, Name from FFmpegProfile")}
    playouts = {r["ChannelId"]: dict(r) for r in q("select * from Playout")}
    enum_names = {}
    for r in q("select PlayoutId, json_extract(SchedulingContext, '$.Enumerator') e, count(*) n from PlayoutItem "
               "where FillerKind = 0 group by 1, 2 order by n"):
        if r["e"]:
            enum_names[r["PlayoutId"]] = r["e"]
    playout_items = collections.defaultdict(set)
    for r in q("select PlayoutId, MediaItemId from PlayoutItem where FillerKind = 0"):
        playout_items[r["PlayoutId"]].add(r["MediaItemId"])

    api_by_num = {}
    for a in api_channels or []:
        api_by_num[str(a.get("number"))] = a

    channel_rows = q("select * from Channel order by SortNumber, Number")
    channel_by_id = {ch["Id"]: ch for ch in channel_rows}
    schedules = {}

    def schedule_of(ch):
        """A channel's members and schedule, from its own playout."""
        if ch["Id"] in schedules:
            return schedules[ch["Id"]]
        pl = playouts.get(ch["Id"])
        items = q("select * from ProgramScheduleItem where ProgramScheduleId = ? order by \"Index\"",
                  pl["ProgramScheduleId"]) if pl else []
        member_ids, methods, notes, orders, roles, colls = set(), set(), [], [], [], []
        for it in items:
            orders.append(PLAYBACK_ORDER.get(it["PlaybackOrder"], str(it["PlaybackOrder"])))
            for col, role in (("PreRollFillerId", "pre-roll"), ("MidRollFillerId", "mid-roll"),
                              ("PostRollFillerId", "post-roll"), ("TailFillerId", "tail"),
                              ("FallbackFillerId", "fallback")):
                if it[col]:
                    d = preset_desc(it[col], role)
                    if d and d not in roles:
                        roles.append(d)
            sc_id = it["SmartCollectionId"]
            if sc_id:
                colls.append({"name": smart[sc_id]["name"], "query": smart[sc_id]["query"], "mode": mode_of(it["Id"])})
                ids, how, why = resolve_smart(sc_id)
                if ids is not None:
                    member_ids |= ids
                    methods.add("query")
                    continue
                notes.append(f"query not evaluated ({why})")
            else:
                notes.append(f"schedule item {it['Id']} is not a smart collection (type {it['CollectionType']})")
            lu = lineup.get(str(ch["Number"]))
            if lu:
                methods.add("lineup")
                for title in lu.get("shows", []):
                    for sid in show_by_title.get(title.casefold(), []):
                        member_ids |= {e for e, ep in episodes.items() if ep["show"] == sid and ep["season"] != 0}
        res = schedules[ch["Id"]] = (pl, member_ids, methods, notes, orders, roles, colls)
        return res

    channels = []
    for ch in channel_rows:
        mirror_of = None
        src_id = mirror_source(channel_by_id, ch["Id"])
        if src_id is None:
            pl, member_ids, methods, notes, orders, roles, colls = None, set(), set(), [], [], [], []
            notes.append("mirror of a channel that is not there (Mirror Source Channel)")
        else:
            pl, member_ids, methods, notes, orders, roles, colls = schedule_of(channel_by_id[src_id])
            notes, roles = list(notes), list(roles)
            if src_id != ch["Id"]:
                # An HD twin: no playout of its own, it plays its source's
                mirror_of = channel_by_id[src_id]["Number"]
                notes.insert(0, f"mirror of channel {mirror_of}: its members")
        if ch["FallbackFillerId"]:
            d = preset_desc(ch["FallbackFillerId"], "channel fallback")
            if d:
                roles.append(d)
        ep_ids = [i for i in member_ids if i in episodes]
        mv_ids = sorted(i for i in member_ids if i in mv_by_id)
        other = len(member_ids) - len(ep_ids) - len(mv_ids)
        kind = "shows" if ep_ids and not mv_ids else "movies" if mv_ids and not ep_ids else "mixed" if member_ids else "empty"

        members = []
        grouped = collections.defaultdict(list)
        for e in ep_ids:
            grouped[episodes[e]["show"]].append(episodes[e])
        for sid, eps in grouped.items():
            a = show_agg(eps)
            members.append({"type": "show", "id": sid, "t": shows[sid]["t"], **a})
            if mirror_of is None:
                shows[sid]["on"].append(ch["Number"])
        for mid in mv_ids:
            m = mv_by_id[mid]
            members.append({"type": "movie", "id": mid, "t": m["t"], "y": m["y"], "m": m["m"],
                            "ch": m["ch"], "br": m["br"], "q": m["q"]})
            if mirror_of is None:
                m["on"].append(ch["Number"])
        members.sort(key=lambda x: (shows[x["id"]]["st"] if x["type"] == "show" else mv_by_id[x["id"]]["st"]).casefold())

        n_items = len(ep_ids) + len(mv_ids)
        dur = sum(episodes[e]["dur"] for e in ep_ids) + sum(ver.get(m, {}).get("dur", 0) for m in mv_ids)
        chaptered = sum(1 for e in ep_ids if episodes[e]["ch"] >= 2) + sum(1 for m in mv_ids if mv_by_id[m]["ch"] >= 2)
        with_breaks = sum(1 for e in ep_ids if episodes[e]["br"] > 0) + sum(1 for m in mv_ids if mv_by_id[m]["br"] > 0)
        breaks = sum(episodes[e]["br"] for e in ep_ids) + sum(mv_by_id[m]["br"] for m in mv_ids)

        check = None
        if pl:
            on_air = playout_items.get(pl["Id"], set())
            check = {"playoutItems": len(on_air), "outsideMembers": len(on_air - member_ids)}
        order = enum_names.get(pl["Id"]) if pl else None
        a = api_by_num.get(str(ch["Number"]))
        channels.append({
            "id": ch["Id"], "number": ch["Number"], "name": ch["Name"], "group": ch["Group"],
            "enabled": bool(ch["IsEnabled"]), "kind": kind, "mirrorOf": mirror_of,
            "profile": profiles.get(ch["FFmpegProfileId"]),
            "order": order or (", ".join(dict.fromkeys(orders)) if orders else None),
            "presets": roles, "collections": colls,
            "membership": "+".join(sorted(methods)) or "none", "notes": notes,
            "counts": {"shows": len(grouped), "episodes": len(ep_ids), "movies": len(mv_ids), "other": other,
                       "items": n_items, "hours": round(dur / 3600, 1), "chaptered": chaptered,
                       "withBreaks": with_breaks, "breaks": breaks},
            "check": check, "inApi": a is not None if api_channels is not None else None,
            "members": members,
        })

    for sh in shows.values():
        sh.pop("_mid", None)
    show_list = sorted(shows.values(), key=lambda s: s["st"].casefold())
    movie_list = sorted(movies, key=lambda m: m["st"].casefold())
    for m in movie_list:
        if m["st"] == m["t"]:
            del m["st"]
    for s in show_list:
        if s["st"] == s["t"]:
            del s["st"]

    return {
        "schema": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "ersatztvVersion": api_version, "db": f"{source_label} (read-only copy)",
            "membership": "Smart-collection queries evaluated against the DB copy "
                          "(channel -> playout -> schedule items -> smart collection -> query)"
                          + ("; the lineup file only where a query cannot be evaluated." if lineup else "."),
            "breakRule": break_rule_text() + " (chapter boundaries, seconds)",
            "chaptered": "an episode or film with 2 or more chapters",
        },
        "channels": channels,
        "library": {"shows": show_list, "movies": movie_list},
    }


# --------------------------------------------------------------------------

def upload(snap_bytes: bytes, url: str, token: str) -> None:
    req = urllib.request.Request(url.rstrip("/") + "/api/snapshot", data=snap_bytes, method="PUT")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Tracker-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            log(f"uploaded: HTTP {r.status} {r.read()[:200].decode(errors='replace')}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload failed: HTTP {e.code} {e.read()[:200].decode(errors='replace')}")


def main() -> None:
    global BREAK
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 epilog="Settings not given here come from the environment or the env file.")
    ap.add_argument("--env-file", default=ENV_FILE, help=f"KEY=value settings (default {ENV_FILE})")
    g = ap.add_argument_group("where the ErsatzTV database is")
    g.add_argument("--access", dest="ETV_DB_ACCESS", choices=("file", "docker", "kubectl"),
                   help="file (default), docker or kubectl  [ETV_DB_ACCESS]")
    g.add_argument("--db-path", dest="ETV_DB_PATH",
                   help="the database, inside the container for docker/kubectl (default /config/ersatztv.sqlite3)  [ETV_DB_PATH]")
    g.add_argument("--ssh", dest="ETV_SSH", help="run the access on this ssh host (BatchMode)  [ETV_SSH]")
    g.add_argument("--docker", dest="ETV_DOCKER", help='the docker command (default docker; e.g. "sudo docker")  [ETV_DOCKER]')
    g.add_argument("--container", dest="ETV_CONTAINER", help="container name (default ersatztv)  [ETV_CONTAINER]")
    g.add_argument("--kubectl", dest="ETV_KUBECTL", help='the kubectl command (default kubectl; e.g. "k3s kubectl")  [ETV_KUBECTL]')
    g.add_argument("--namespace", dest="ETV_K8S_NAMESPACE", help="namespace (default ersatztv)  [ETV_K8S_NAMESPACE]")
    g.add_argument("--target", dest="ETV_K8S_TARGET", help="pod or deploy/<name> (default deploy/ersatztv)  [ETV_K8S_TARGET]")
    g.add_argument("--db", default=None, help="use this local DB copy instead of fetching one")
    g.add_argument("--keep-db", default=None, help="save the fetched DB copy here")
    g = ap.add_argument_group("the rest")
    g.add_argument("--etv-url", dest="ERSATZTV_URL", help="ErsatzTV's address, http://<server-ip>:8409  [ERSATZTV_URL]")
    g.add_argument("--no-api", action="store_true", help="skip the ErsatzTV API cross-check")
    g.add_argument("--lineup", default=None, help="optional JSON naming the shows of channels whose query cannot be evaluated")
    g.add_argument("--break-rule", default=DEFAULT_BREAK_RULE,
                   help=f"mid-roll rule as point,remaining,gap seconds (default {DEFAULT_BREAK_RULE})")
    g.add_argument("--out", default=None, help="also write the snapshot to this file")
    g.add_argument("--no-upload", action="store_true")
    g.add_argument("--url", dest="TRACKER_URL", help="tracker base URL  [TRACKER_URL]")
    args = ap.parse_args()
    cfg = Settings(args, args.env_file)
    BREAK = parse_break_rule(args.break_rule)

    t0 = time.time()
    src = None if args.db else Source(cfg)
    tmpdir = tempfile.mkdtemp(prefix="retro-tv-tracker-")
    db = args.db
    try:
        if not db:
            db = args.keep_db or os.path.join(tmpdir, "ersatztv.sqlite3")
            log(f"copying the ErsatzTV database: {src.label}...")
            how = src.fetch_db(db)
            log(f"  {os.path.getsize(db) / 1e6:.0f} MB in {time.time() - t0:.1f}s ({how})")
        api_channels = api_version = None
        if not args.no_api and cfg.get("ERSATZTV_URL"):
            key = fetch_api_key(cfg, src) if src else cfg.get("ERSATZTV_API_KEY")
            try:
                api_channels = api_get(cfg["ERSATZTV_URL"], "/channels", key)
                api_version = api_get(cfg["ERSATZTV_URL"], "/version", key)
            except Exception as e:  # noqa: BLE001
                log(f"warning: ErsatzTV API not reachable ({type(e).__name__})")
            del key
        elif not args.no_api:
            log("note: no ERSATZTV_URL; skipping the API cross-check")
        snap = build(db, args.lineup, api_channels, api_version, src.label if src else args.db)
    finally:
        if not args.db and not args.keep_db and db:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(db + suffix):
                    os.remove(db + suffix)
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    data = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode()
    lib = snap["library"]
    log(f"snapshot: {len(snap['channels'])} channels, {len(lib['shows'])} shows, {len(lib['movies'])} films, "
        f"{len(data) / 1e6:.1f} MB")
    for ch in snap["channels"]:
        c, k = ch["counts"], ch["check"] or {}
        log(f"  {ch['number']:>4} {ch['name'][:24]:24} {ch['kind']:6} {ch['membership']:6} "
            f"shows={c['shows']:<3} eps={c['episodes']:<5} films={c['movies']:<3} chaptered={c['chaptered']:<5} "
            f"withBreaks={c['withBreaks']:<5} playout outside={k.get('outsideMembers')}/{k.get('playoutItems')}"
            + (f"  notes={ch['notes']}" if ch["notes"] else ""))
    if args.out:
        with open(args.out, "wb") as f:
            f.write(data)
        log(f"wrote {args.out}")
    if not args.no_upload:
        url, token = cfg.get("TRACKER_URL"), cfg.get("TRACKER_TOKEN")
        if not url or not token:
            raise SystemExit(f"no TRACKER_URL/TRACKER_TOKEN (environment or {args.env_file}); --no-upload to skip")
        upload(data, url, token)
    log(f"done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

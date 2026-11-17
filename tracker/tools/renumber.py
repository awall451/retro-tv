#!/usr/bin/env python3
"""Move the tracker's watch history to new channel numbers.

Watch time is stored by channel number (watch-events.json, watch-daily.json in the
data folder). When channels are renumbered in ErsatzTV, their past minutes stay under
the old numbers; this rewrites them:

    renumber.py [--data-dir /data] [--apply] OLD=NEW ... [LO-HI=+N ...]

    24=124          channel 24's minutes go to 124
    101-199=+900    every channel from 101 to 199 moves up by 900 (101 -> 1001, ...)
    124=24          minutes kept under an HD twin's own number go to its channel

All pairs apply at once, so 1=2 2=1 swaps two channels. A number that gets minutes
from two channels on one day (or that already has some) gets their sum.

Without --apply it only says what would change. With --apply it first copies each
file it changes to <file>.bak-<time> in the same folder, then replaces it atomically.
Stop the tracker first: it keeps the recent history in memory and would write the old
numbers back on its next save. Standard library only; see tracker/README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile

CHANNEL_RE = re.compile(r"^\d{1,4}(\.\d{1,2})?$")
RANGE_RE = re.compile(r"^(\d{1,4})-(\d{1,4})=([+-])(\d{1,4})$")
FILES = ("watch-events.json", "watch-daily.json")


def parse_map(pairs: list[str]) -> dict[str, str]:
    """OLD=NEW and LO-HI=+N / LO-HI=-N into {old: new}."""
    out: dict[str, str] = {}

    def put(old, new):
        if not CHANNEL_RE.match(new) or new.startswith("0") and new != "0":
            raise ValueError(f"{old} would become {new}, not a channel number")
        if old in out and out[old] != new:
            raise ValueError(f"channel {old} is given two new numbers ({out[old]}, {new})")
        if old != new:
            out[old] = new

    for p in pairs:
        m = RANGE_RE.match(p.strip())
        if m:
            lo, hi, sign, n = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
            if lo > hi:
                raise ValueError(f"{p}: the range runs backwards")
            for c in range(lo, hi + 1):
                put(str(c), str(c + n if sign == "+" else c - n))
            continue
        old, sep, new = p.strip().partition("=")
        if not sep or not CHANNEL_RE.match(old) or not CHANNEL_RE.match(new):
            raise ValueError(f"{p!r}: expected OLD=NEW (e.g. 124=1024) or LO-HI=+N (e.g. 101-199=+900)")
        put(old, new)
    if len(set(out.values())) < len(out):
        dup = sorted({v for v in out.values() if list(out.values()).count(v) > 1})
        print(f"note: several channels go to {', '.join(dup)}: their minutes are added up", file=sys.stderr)
    return out


def merge_day(into: dict, rec: dict) -> None:
    """Add one channel's day record (s, hd, u, dev, h) into another."""
    for k in ("s", "hd", "u"):
        into[k] = into.get(k, 0) + rec.get(k, 0)
    dev = into.setdefault("dev", {})
    for d, v in (rec.get("dev") or {}).items():
        dev[d] = dev.get(d, 0) + v
    h = into.setdefault("h", [0] * 24)
    for i, v in enumerate((rec.get("h") or [])[:24]):
        h[i] += v


def remap_daily(daily: dict, mp: dict) -> tuple[dict, dict]:
    """watch-daily.json with the days' channel keys moved; and {old: (days, seconds)}."""
    moved: dict[str, list] = {}
    days = daily.get("days") if isinstance(daily, dict) else None
    if not isinstance(days, dict):
        return daily, moved
    new_days = {}
    for day, chans in days.items():
        out: dict = {}
        for c, rec in chans.items():
            nc = mp.get(c, c)
            if nc != c:
                m = moved.setdefault(c, [0, 0])
                m[0] += 1
                m[1] += rec.get("s", 0)
            if nc in out:
                merge_day(out[nc], rec)
            else:
                out[nc] = json.loads(json.dumps(rec)) if nc != c else rec
        new_days[day] = out
    return dict(daily, days=new_days), moved


def remap_events(events: list, mp: dict) -> tuple[list, int]:
    """watch-events.json with each event's channel moved; and how many changed. A
    session id ("<number>@<start>") is moved too, so it stays one session."""
    n = 0
    for e in events:
        if not isinstance(e, dict):
            continue
        changed = False
        c = str(e.get("c"))
        if c in mp:
            e["c"] = mp[c]
            changed = True
        sid = e.get("id")
        if isinstance(sid, str) and "@" in sid:
            raw, rest = sid.split("@", 1)
            if raw in mp:
                e["id"] = f"{mp[raw]}@{rest}"
                changed = True
        n += changed
    return events, n


def stage(path: str, data: bytes) -> str:
    """data written and synced to a temp file next to path; its name."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{os.path.basename(path)}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        os.remove(tmp)
        raise
    return tmp


def write_atomic(path: str, data: bytes) -> None:
    tmp = stage(path, data)
    try:
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def backup_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%dT%H%M%S")


def make_backup(path: str, stamp: str) -> str:
    """A copy of path as <path>.bak-<stamp> (-2, -3, ... if taken), created exclusively:
    an earlier backup is never overwritten."""
    n = 1
    while True:
        bak = f"{path}.bak-{stamp}" + (f"-{n}" if n > 1 else "")
        try:
            dst = open(bak, "xb")
        except FileExistsError:
            n += 1
            continue
        try:
            with dst, open(path, "rb") as src:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            shutil.copystat(path, bak)
        except BaseException:
            os.remove(bak)
            raise
        return bak


def apply_all(outputs: dict) -> dict:
    """Replace each file in {path: data} with its new contents, all or none: both new files
    are written and both backups taken before anything is replaced, and a file already
    replaced is put back from its backup if a later one fails. {path: backup}."""
    staged, baks, done = {}, {}, []
    try:
        for p, data in outputs.items():
            staged[p] = stage(p, data)
        stamp = backup_stamp()
        for p in outputs:
            baks[p] = make_backup(p, stamp)
        try:
            for p, tmp in staged.items():
                os.replace(tmp, p)
                done.append(p)
        except BaseException:
            for p in done:
                with open(baks[p], "rb") as f:
                    write_atomic(p, f.read())
            raise
    finally:
        for tmp in staged.values():
            if os.path.exists(tmp):
                os.remove(tmp)
    return baks


def run(data_dir: str, pairs: list[str], apply: bool, out=None) -> int:
    out = out or sys.stdout
    mp = parse_map(pairs)
    if not mp:
        print("nothing to renumber", file=out)
        return 0
    loaded = {}
    for name in FILES:
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                loaded[name] = json.loads(f.read())
    if not loaded:
        print(f"no watch history in {data_dir} ({', '.join(FILES)})", file=out)
        return 1

    results = {}
    daily_moved, n_events = {}, 0
    if "watch-daily.json" in loaded:
        results["watch-daily.json"], daily_moved = remap_daily(loaded["watch-daily.json"], mp)
    if "watch-events.json" in loaded and isinstance(loaded["watch-events.json"], list):
        results["watch-events.json"], n_events = remap_events(loaded["watch-events.json"], mp)

    for old in sorted(daily_moved, key=float):
        days, sec = daily_moved[old]
        print(f"  {old:>7} -> {mp[old]:<7} {days:>4} day(s), {sec / 60:,.0f} watched minutes", file=out)
    untouched = sorted(set(mp) - set(daily_moved), key=float)
    if untouched and len(untouched) <= 20:
        print(f"  no daily history under {', '.join(untouched)}", file=out)
    elif untouched:
        print(f"  no daily history under {len(untouched)} of the given numbers", file=out)
    print(f"  {n_events} raw event(s) of the last 14 days renumbered", file=out)
    if not daily_moved and not n_events:
        print("nothing stored under the old numbers: no change", file=out)
        return 0
    if not apply:
        print("dry run: nothing written (add --apply; stop the tracker first)", file=out)
        return 0

    outputs = {}
    for name, obj in results.items():
        if name == "watch-daily.json":
            data = json.dumps(obj, separators=(",", ":")).encode()
        else:
            data = json.dumps(obj, ensure_ascii=False, indent=1).encode()
        outputs[os.path.join(data_dir, name)] = data
    for p, bak in apply_all(outputs).items():
        print(f"wrote {p} (backup {os.path.basename(bak)})", file=out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.split("\n")[2:]))
    ap.add_argument("pairs", nargs="+", metavar="OLD=NEW", help="e.g. 124=1024, or 101-199=+900")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"),
                    help="the tracker's data folder (default $DATA_DIR or /data)")
    ap.add_argument("--apply", action="store_true", help="write the change (default: only show it)")
    args = ap.parse_args(argv)
    try:
        return run(args.data_dir, args.pairs, args.apply)
    except ValueError as e:
        ap.error(str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Retro TV theme (and power) service.

A tiny local web service on 127.0.0.1:8412 that the viewer talks to through
nginx (/pi/theme, /pi/power). The viewer posts its theme id whenever it
applies one; this records the choice in /data/retro-tv/theme and
points the Plymouth theme's images at the matching splash, so the next boot
shows it. Plymouth runs from the initramfs on Pi OS, so the initramfs is
rebuilt afterwards: once, at low priority, for the running kernel only, and
only after 20 s without further changes (flipping through themes used to
start one heavy rebuild per press and make the box crawl). The settings screen's
"Power off" row posts to /pi/power, and the box shuts down cleanly.

  POST /pi/theme   body: the theme id        -> 204
  GET  /pi/theme                             -> the current id
  POST /pi/power   body: "off" or "reboot"   -> 204, then systemctl poweroff / reboot

Root-only files are touched, so it runs as root (retro-tv-themed.service).
Only the viewer on this box reaches it: nginx listens on loopback alone.
"""
import glob
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

POWER = {"off": "poweroff", "reboot": "reboot"}
STATE_DIR = "/data/retro-tv"
STATE = os.path.join(STATE_DIR, "theme")
PLYMOUTH = "/usr/share/plymouth/themes/retro-tv"
SIZES = ("640", "720", "1080")


def known_themes() -> tuple:
    """The themes with a rendered boot splash (splash-<theme>-640.png); cable first."""
    names = set()
    for f in glob.glob(os.path.join(PLYMOUTH, "splash-*-640.png")):
        names.add(os.path.basename(f)[len("splash-"):-len("-640.png")])
    names.discard("cable")
    return ("cable",) + tuple(sorted(names))


THEMES = known_themes()
lock = threading.Lock()


def current() -> str:
    try:
        with open(STATE, encoding="utf-8") as f:
            value = f.read().strip()
        return value if value in THEMES else THEMES[0]
    except OSError:
        return THEMES[0]


def point_plymouth(theme: str) -> None:
    """current-<size>.png -> splash-<theme>-<size>.png, atomically."""
    for size in SIZES:
        target = f"splash-{theme}-{size}.png"
        link = os.path.join(PLYMOUTH, f"current-{size}.png")
        if not os.path.exists(os.path.join(PLYMOUTH, target)):
            continue
        tmp = link + ".tmp"
        if os.path.lexists(tmp):
            os.unlink(tmp)
        os.symlink(target, tmp)
        os.replace(tmp, link)


REBUILD_QUIET = 20.0            # seconds without a change before the initramfs is rebuilt
_rebuild_at = 0.0               # when the next rebuild is due (monotonic), 0 = none pending
_rebuild_lock = threading.Lock()
_rebuild_thread = None


def schedule_rebuild() -> None:
    """Rebuild the initramfs once things have been quiet for REBUILD_QUIET seconds."""
    global _rebuild_at, _rebuild_thread
    if not glob.glob("/boot/firmware/initramfs*"):
        return                  # Plymouth draws from the root filesystem here: nothing to do
    with _rebuild_lock:
        _rebuild_at = time.monotonic() + REBUILD_QUIET
        if _rebuild_thread is None or not _rebuild_thread.is_alive():
            _rebuild_thread = threading.Thread(target=_rebuild_worker, daemon=True)
            _rebuild_thread.start()


def _rebuild_worker() -> None:
    global _rebuild_at
    while True:
        with _rebuild_lock:
            due = _rebuild_at
        wait = due - time.monotonic()
        if wait > 0:
            time.sleep(wait)
            continue
        with _rebuild_lock:
            _rebuild_at = 0.0
        # Low priority, and only the kernel this Pi runs (-u alone does every installed one).
        subprocess.run(["nice", "-n", "19", "ionice", "-c", "3", "update-initramfs", "-u",
                        "-k", os.uname().release], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with _rebuild_lock:
            if not _rebuild_at:
                return          # nothing changed meanwhile


def set_theme(theme: str) -> bool:
    with lock:
        if theme == current() and all(
                os.path.lexists(os.path.join(PLYMOUTH, f"current-{s}.png")) for s in SIZES):
            return False
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE + ".tmp", "w", encoding="utf-8") as f:
            f.write(theme + "\n")
        os.replace(STATE + ".tmp", STATE)
        point_plymouth(theme)
    schedule_rebuild()
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        if self.path != "/pi/theme":
            return self.send_error(404)
        body = current().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/pi/power":
            return self.do_power()
        if self.path != "/pi/theme":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length") or 0)
        theme = self.rfile.read(min(length, 64)).decode("utf-8", "replace").strip()
        if theme not in THEMES:
            return self.send_error(400, "unknown theme")
        set_theme(theme)
        self.send_response(204)
        self.end_headers()

    def do_power(self):
        length = int(self.headers.get("Content-Length") or 0)
        action = self.rfile.read(min(length, 16)).decode("utf-8", "replace").strip()
        if action not in POWER:
            return self.send_error(400, "unknown action")
        self.send_response(204)
        self.end_headers()
        # Answer first, then act a moment later so the viewer gets its 204.
        threading.Timer(1.0, subprocess.run, args=(["systemctl", POWER[action]],),
                        kwargs={"check": False}).start()


if __name__ == "__main__":
    set_theme(current())          # make sure Plymouth points somewhere on first start
    HTTPServer(("127.0.0.1", 8412), Handler).serve_forever()

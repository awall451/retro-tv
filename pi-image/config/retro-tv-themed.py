#!/usr/bin/env python3
"""Retro TV theme (and power) service.

A tiny local web service on 127.0.0.1:8412 that the viewer talks to through
nginx (/pi/theme, /pi/power). The viewer posts its theme ("cable" or "vapor")
whenever it applies one; this records the choice in /data/retro-tv/theme and
points the Plymouth theme's images at the matching splash, so the next boot
shows it. If Plymouth runs from the initramfs on this system, the initramfs is
rebuilt in the background so the change gets in. The settings screen's
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
from http.server import BaseHTTPRequestHandler, HTTPServer

THEMES = ("cable", "vapor")
POWER = {"off": "poweroff", "reboot": "reboot"}
STATE_DIR = "/data/retro-tv"
STATE = os.path.join(STATE_DIR, "theme")
PLYMOUTH = "/usr/share/plymouth/themes/retro-tv"
SIZES = ("640", "720", "1080")
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


def rebuild_initramfs() -> None:
    # Only when the boot partition carries an initramfs (Plymouth then draws from it).
    if glob.glob("/boot/firmware/initramfs*"):
        subprocess.run(["update-initramfs", "-u"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    threading.Thread(target=rebuild_initramfs, daemon=True).start()
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

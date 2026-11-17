#!/usr/bin/env python3
"""Retro TV HDMI-CEC service: is the TV on?

For a box on an HDMI TV (DISPLAY_MODE=hdmi480). Composite has no CEC, and
setup.sh leaves this service off there. It uses cec-ctl (v4l-utils):

  - registers the box on the HDMI-CEC bus as a playback device ("Retro TV"),
  - asks the TV for its power status every CEC_POLL_SEC seconds (10) and
    listens to the bus, so a <Standby> from the TV is seen at once,
  - writes what it knows to /run/retro-tv/cec/state.json, which nginx serves
    to the viewer as /pi/cec:  {"power": "on" | "standby" | "unknown", ...}

The viewer (with its /pi/cec change, feat/idle-timeout) polls /pi/cec:
"standby" stops the stream at once (its standby screen, as after the sleep
timer), and "on" after "standby" resumes the channel. "unknown" (a TV that
does not answer, or a converter that does not pass CEC on) changes nothing.

With CEC=auto (the default) a TV that has not answered for a few minutes
is asked only every QUIET_POLL_S seconds (300): an HDMI-to-composite
converter usually drops CEC, and then nothing ever answers. Any message
from the TV on the bus, or an answer, brings back the normal pace. CEC=1
keeps the normal pace regardless.

CEC_KEYS=1 also lets the TV's remote drive the viewer: the kernel turns the
remote's <User Control Pressed> messages into key presses on its rc-cec
input device (RC passthrough), and setup.sh loads retro-tv-cec.toml for it,
which maps them to the keyboard keys the viewer knows. With CEC_KEYS unset
or 0 the passthrough is switched off (cec-ctl --no-rc-passthrough). TVs send
their remote's keys to the active source, so with CEC_KEYS=1 the box says it
is the active source when the service starts; on most TVs that also
switches the TV to the box's input.

Settings: CEC, CEC_DEVICE (default: the cec device of the connected HDMI
port), CEC_KEYS, CEC_POLL_SEC, CEC_OSD_NAME. setup.sh copies them from
/etc/retro-tv.env into /etc/retro-tv-cec.env, so the service (its own user,
retro-tv-cec) sees these and nothing else from the box's settings. The rc-cec
key map is loaded by udev through /etc/rc_maps.cfg (setup.sh triggers it),
not by this service: that needs root.

Untested on hardware so far: the parsing is unit-tested against cec-ctl's
output format (pi-image/tests/test_cec.py).
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

# The service's RuntimeDirectory (retro-tv/cec), so its own user can write it.
STATE = os.environ.get("CEC_STATE") or "/run/retro-tv/cec/state.json"   # CEC_STATE: for tests
STATE_DIR = os.path.dirname(STATE)
POLL_S = max(3.0, float(os.environ.get("CEC_POLL_SEC") or 10))
KEYS = os.environ.get("CEC_KEYS", "0") == "1"
AUTO = os.environ.get("CEC", "auto") != "1"     # auto: slow down while nothing answers
OSD_NAME = (os.environ.get("CEC_OSD_NAME") or "Retro TV")[:14]   # CEC allows 14 characters
UNKNOWN_AFTER = 3            # power queries without an answer before the state is "unknown"
QUIET_AFTER = 30             # polls with the TV silent (5 min at 10 s) before polling slows down
QUIET_POLL_S = 300.0         # the slow pace (CEC=auto only)
MIN_GAP_S = 2.0              # at least this long between two polls, however often the bus pokes

# cec-ctl's names for the power states (newer and older spellings), and the codes.
POWER_WORDS = {
    "on": "on", "to-on": "on", "in-transition-standby-to-on": "on",
    "standby": "standby", "to-standby": "standby", "in-transition-on-to-standby": "standby",
}
POWER_CODES = {0: "on", 1: "standby", 2: "on", 3: "standby"}
PWR_RE = re.compile(r"pwr-state:\s*([A-Za-z-]+)?\s*(?:\(0x([0-9a-fA-F]+)\))?")
MSG_RE = re.compile(r"Received from (.+?) to (.+?) \((\d+) to (\d+)\):\s*([A-Z0-9_]+)")
PA_RE = re.compile(r"Physical Address\s*:\s*([0-9a-fA-F])\.([0-9a-fA-F])\.([0-9a-fA-F])\.([0-9a-fA-F])")


def parse_power(text):
    """The last power state reported in cec-ctl output: "on", "standby" or None."""
    state = None
    for m in PWR_RE.finditer(text or ""):
        word, code = (m.group(1) or "").lower(), m.group(2)
        if word in POWER_WORDS:
            state = POWER_WORDS[word]
        elif code is not None and int(code, 16) in POWER_CODES:
            state = POWER_CODES[int(code, 16)]
    return state


def parse_message(line):
    """One monitor line -> (from logical address, opcode name), or None."""
    m = MSG_RE.search(line or "")
    return (int(m.group(3)), m.group(5)) if m else None


def is_header(line):
    """A monitor line that starts a message or event (its details are indented below it)."""
    text = (line or "").strip()
    return bool(text) and (not line[:1].isspace() or text.startswith(("Received ", "Transmit", "Event")))


def parse_phys_addr(text):
    """The adapter's physical address ("1.0.0.0"), or None when there is none (f.f.f.f)."""
    m = PA_RE.search(text or "")
    if not m:
        return None
    pa = ".".join(g.lower() for g in m.groups())
    return None if pa == "f.f.f.f" else pa


def pick_device(env=os.environ, drm="/sys/class/drm", dev="/dev"):
    """CEC_DEVICE, else the cec device of the HDMI port with a screen on it
    (HDMI-A-1 -> cec0, HDMI-A-2 -> cec1 on a Pi 4/5), else the first one."""
    if env.get("CEC_DEVICE"):
        return env["CEC_DEVICE"]
    for status in sorted(glob.glob(os.path.join(drm, "card*-HDMI-A-*", "status"))):
        try:
            with open(status, encoding="utf-8") as f:
                connected = f.read().strip() == "connected"
        except OSError:
            continue
        port = re.search(r"HDMI-A-(\d+)", status)
        cand = os.path.join(dev, f"cec{int(port.group(1)) - 1}")
        if connected and os.path.exists(cand):
            return cand
    found = sorted(glob.glob(os.path.join(dev, "cec[0-9]*")))
    return found[0] if found else None


class Tv:
    def __init__(self, device):
        self.device = device
        self.power = "unknown"
        self.since = time.time()
        self.misses = 0              # power queries unanswered since the last power answer
        self.quiet = 0               # polls since the TV last said anything (paces polling)
        self.seen = 0                # bus observations so far; a poll older than the last one is dropped
        self.sender = None           # logical address of the monitor's last message header
        self.last_poll = 0.0
        self.lock = threading.Lock()
        self.poll_now = threading.Event()

    def cec(self, *args, timeout=8):
        try:
            r = subprocess.run(["cec-ctl", "-d", self.device, "-s", *args], capture_output=True,
                               text=True, timeout=timeout, check=False)
            return r.stdout + r.stderr
        except (OSError, subprocess.SubprocessError) as e:
            return f"error: {e}"

    def set(self, power, why, seen=None):
        """Publish a power state. A poll passes the observation count from
        before its query: if the monitor has seen the TV since, the poll's
        answer is older than that and is dropped."""
        with self.lock:
            if seen is None:
                self.seen += 1
            elif seen != self.seen:
                return
            if power == self.power:
                return
            print(f"tv: {self.power} -> {power} ({why})", flush=True)
            self.power, self.since = power, time.time()
            self.write()

    def write(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        body = json.dumps({"power": self.power, "since": round(self.since), "device": self.device,
                           "keys": KEYS})
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, STATE)

    def register(self):
        args = ["--playback", "-o", OSD_NAME]
        if not KEYS:
            args.append("--no-rc-passthrough")
        print(self.cec(*args).strip()[-300:], flush=True)
        if KEYS:
            pa = parse_phys_addr(self.cec("-x"))
            if pa:
                self.cec("-t", "0", "--active-source", f"phys-addr={pa}")

    def poll(self):
        with self.lock:
            seen = self.seen
        out = self.cec("-t", "0", "--give-device-power-status")
        self.last_poll = time.monotonic()
        state = parse_power(out)
        if state:
            self.misses = self.quiet = 0
            self.set(state, "poll", seen)
        else:
            # Kept apart: other talk from the TV ends the quiet pace (quiet),
            # but says nothing about its power, so it does not hold off
            # "unknown" (misses).
            self.misses += 1
            self.quiet += 1
            if self.misses >= UNKNOWN_AFTER:
                self.set("unknown", "no answer", seen)
            if AUTO and self.quiet == QUIET_AFTER:
                print(f"tv: no answer for {QUIET_AFTER} polls, asking every {QUIET_POLL_S:.0f} s", flush=True)

    def interval(self):
        """Seconds to the next poll: slow while the TV has long been silent (CEC=auto)."""
        return QUIET_POLL_S if AUTO and self.quiet >= QUIET_AFTER else POLL_S

    def poller(self):
        while True:
            self.poll()
            self.poll_now.wait(self.interval())
            self.poll_now.clear()
            # However often the bus pokes, never query back to back.
            gap = MIN_GAP_S - (time.monotonic() - self.last_poll)
            if gap > 0:
                time.sleep(gap)

    def see(self, line):
        """One monitor line. A <Standby> from the TV is acted on at once, a
        power report from it is taken as it is (also the TV's answer to our
        own poll, which must not start another poll), and any other message
        from it (it woke up, it changed input) means a fresh look. Any
        message from the TV also ends the quiet pace (CEC=auto): it talks,
        so it is polled at the normal pace again; only a power report or
        <Standby> counts as an answer, though (misses). A pwr-state line belongs
        to the header above it, and counts only when that header is the
        TV's (logical address 0): an audio system in standby says nothing
        about the TV."""
        if is_header(line):
            msg = parse_message(line)
            self.sender = msg[0] if msg else None
            if msg and msg[0] == 0:
                if self.quiet >= QUIET_AFTER:
                    self.poll_now.set()      # it talks after all: back to the normal pace
                self.quiet = 0
                if msg[1] == "STANDBY":
                    self.misses = 0
                    self.set("standby", "TV sent standby")
                elif msg[1] != "REPORT_POWER_STATUS":
                    self.poll_now.set()
        elif "pwr-state" in line and self.sender == 0:
            state = parse_power(line)
            if state:
                self.misses = 0
                self.set(state, "report")

    def monitor(self):
        """Follow the bus (see see())."""
        while True:
            try:
                p = subprocess.Popen(["cec-ctl", "-d", self.device, "-s", "-m"], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
                self.sender = None
                for line in p.stdout:
                    self.see(line)
                p.wait()
            except OSError as e:
                print(f"monitor: {e}", flush=True)
            time.sleep(5)


def main():
    device = pick_device()
    if not device:
        print("no CEC device: nothing to do", flush=True)
        return 0
    tv = Tv(device)
    tv.write()
    tv.register()
    threading.Thread(target=tv.monitor, daemon=True).start()
    tv.poller()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Pull a stream with yt-dlp and pass it through as MPEG-TS over HTTP."""
import http.server
import json
import os
import re
import select
import signal
import subprocess
import threading
import time
import urllib.request

PORT = int(os.environ.get("RELAY_PORT", "8090"))
YTDLP = os.environ.get("YTDLP", "/media/tools/yt-dlp")
STREAMS = os.environ.get("STREAMS_FILE", "/relay/streams.json")
FIRST_BYTE_TIMEOUT = 60
# A film has no single stream with picture and sound at 720p, so take the best
# H.264 picture up to 720p plus the best sound, both as segmented playlists.
VOD_FORMAT = "bv[height<=720][protocol^=m3u8][vcodec^=avc]+ba[protocol^=m3u8]"
# YouTube's stream addresses expire after about six hours.
VOD_CACHE_SECONDS = 3 * 3600
VOD_CACHE_MAX = 200
VOD_CACHE = {}
VOD_LOCK = threading.Lock()
BASE = ["python3", YTDLP, "-q", "--no-warnings", "--no-cache-dir"]


def log(*parts):
    print(time.strftime("%F %T"), *parts, flush=True)


def command_for(path):
    match = re.fullmatch(r"/live/([a-z0-9-]+)", path)
    if match:
        with open(STREAMS) as handle:
            address = json.load(handle).get(match.group(1))
        if address:
            # A live stream comes as separate picture and sound playlists, and each
            # starts on its own 5-second segment. -copyts keeps their original
            # clocks through the join; without it the sound lands a whole segment
            # early on about half of all pulls.
            return BASE + [address, "--hls-use-mpegts", "--downloader-args", "ffmpeg_i:-copyts",
                           "-S", "res:720", "-o", "-"]
    return None


def fetch(address):
    with urllib.request.urlopen(address, timeout=30) as response:
        return response.read().decode()


def segments(playlist):
    """(duration, address) for every segment of a media playlist."""
    found, duration = [], None
    for line in playlist.splitlines():
        if line.startswith("#EXTINF:"):
            duration = line[8:].split(",")[0]
        elif line and not line.startswith("#") and duration is not None:
            found.append((duration, line))
            duration = None
    return found


def vod(video):
    """Picture and sound segment lists for one video, resolved with yt-dlp and cached."""
    with VOD_LOCK:
        cached = VOD_CACHE.get(video)
    if cached and time.time() - cached["at"] < VOD_CACHE_SECONDS:
        return cached
    address = "https://www.youtube.com/watch?v=" + video
    result = subprocess.run(BASE + ["-f", VOD_FORMAT, "-g", address], capture_output=True,
                            text=True, stdin=subprocess.DEVNULL, timeout=90)
    streams = result.stdout.split()
    if len(streams) != 2:
        log("/vod/" + video, "could not resolve:", result.stderr.strip()[-300:])
        return None
    picture, sound = segments(fetch(streams[0])), segments(fetch(streams[1]))
    if not picture or len(picture) != len(sound):
        log("/vod/" + video, "picture and sound differ:", len(picture), "and", len(sound), "segments")
        return None
    lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-PLAYLIST-TYPE:VOD", "#EXT-X-MEDIA-SEQUENCE:0",
             "#EXT-X-TARGETDURATION:%d" % (max(float(d) for d, _ in picture) + 1)]
    for number, (duration, _) in enumerate(picture):
        lines += ["#EXTINF:%s," % duration, "%s/%d.ts" % (video, number)]
    lines.append("#EXT-X-ENDLIST")
    entry = {"at": time.time(), "picture": picture, "sound": sound, "playlist": "\n".join(lines) + "\n"}
    now = time.time()
    with VOD_LOCK:
        for key in [k for k, e in VOD_CACHE.items() if now - e["at"] >= VOD_CACHE_SECONDS]:
            del VOD_CACHE[key]
        while len(VOD_CACHE) >= VOD_CACHE_MAX:
            del VOD_CACHE[min(VOD_CACHE, key=lambda k: VOD_CACHE[k]["at"])]
        VOD_CACHE[video] = entry
    log("/vod/" + video, "resolved,", len(picture), "segments")
    return entry


def vod_response(path):
    """(content type, body) for a video's playlist or one of its joined segments."""
    match = re.fullmatch(r"/vod/([A-Za-z0-9_-]{11})\.m3u8", path)
    if match:
        entry = vod(match.group(1))
        return ("application/vnd.apple.mpegurl", entry["playlist"].encode()) if entry else None
    match = re.fullmatch(r"/vod/([A-Za-z0-9_-]{11})/(\d+)\.ts", path)
    if not match:
        return None
    entry = vod(match.group(1))
    number = int(match.group(2))
    if not entry or number >= len(entry["picture"]):
        return None
    # Join one picture segment with its sound segment, keeping their clocks.
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", entry["picture"][number][1],
         "-i", entry["sound"][number][1], "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
         "-copyts", "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-"],
        capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    if result.returncode != 0 or not result.stdout:
        log(path, "join failed:", result.stderr.decode(errors="replace").strip()[-200:])
        return None
    return ("video/mp2t", result.stdout)


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def plain(self, status, text):
        body = (text + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = self.path.split("?")[0]
        if path.startswith("/vod/"):
            known = re.fullmatch(r"/vod/[A-Za-z0-9_-]{11}(\.m3u8|/\d+\.ts)", path)
            self.send_response(200 if known else 404)
            self.send_header("Content-Type", "video/mp2t" if path.endswith(".ts")
                             else "application/vnd.apple.mpegurl")
        else:
            self.send_response(200 if command_for(path) else 404)
            self.send_header("Content-Type", "video/mp2t")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self.plain(200, "ok")
        if path.startswith("/vod/"):
            try:
                answer = vod_response(path)
            except Exception as problem:
                log(path, "failed:", repr(problem)[:200])
                answer = None
            if not answer:
                return self.plain(404, "unknown or unavailable video")
            kind, body = answer
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the viewer went away mid-segment
            return
        command = command_for(path)
        if not command:
            return self.plain(404, "unknown stream")
        started = time.time()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        sent = 0
        try:
            ready, _, _ = select.select([process.stdout], [], [], FIRST_BYTE_TIMEOUT)
            chunk = os.read(process.stdout.fileno(), 65536) if ready else b""
            if not chunk:
                log(path, "no video within", int(time.time() - started), "s")
                return self.plain(502, "the source gave no video")
            log(path, "start, first video after", round(time.time() - started, 1), "s")
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.end_headers()
            while chunk:
                self.wfile.write(chunk)
                sent += len(chunk)
                ready, _, _ = select.select([process.stdout], [], [], FIRST_BYTE_TIMEOUT)
                if not ready:
                    log(path, "source quiet for", FIRST_BYTE_TIMEOUT, "s")
                    break
                chunk = os.read(process.stdout.fileno(), 65536)
            log(path, "source ended after", int(time.time() - started), "s")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            stop(process)
            log(path, "closed,", sent // 1048576, "MB in", int(time.time() - started), "s")


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    log("relay listening on", PORT)
    server.serve_forever()

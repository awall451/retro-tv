# The TV Guide Channel generator: renders the viewer's tvguide.html in a
# headless Chromium and encodes the picture and sound into a live HLS stream
# that ErsatzTV carries as a channel. See README.md in this folder.
#
# Debian's Chromium, Xvfb for a screen to draw on, PulseAudio for the promo
# channel's sound, ffmpeg to capture and encode, Python's http.server to hand
# the segments out. Runs as an ordinary user; Chromium's sandbox is off
# because the container has no user namespaces (the page is our own).
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      chromium xvfb ffmpeg pulseaudio pulseaudio-utils \
      fonts-liberation ca-certificates python3 tini procps \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 -s /bin/bash tvguide \
 && mkdir -p /out && chown tvguide:tvguide /out

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

USER tvguide
ENV HOME=/home/tvguide \
    VIEWER_URL=http://web:8080 \
    TVGUIDE_PROMO= \
    TVGUIDE_FPS=30 \
    TVGUIDE_BITRATE=1800k \
    TVGUIDE_PORT=8082
WORKDIR /home/tvguide
EXPOSE 8082
# Healthy once the playlist exists and keeps being rewritten.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python3 -c "import os,sys,time; p='/out/live.m3u8'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 30 else 1)"
ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]

# The TV Guide Channel generator

Turns the viewer's [TV Guide page](../README.md#the-tv-guide-channel-page) into a live stream, so
ErsatzTV can carry it as a channel and every device gets it like any other: the scrolling
listings of the late-1990s TV Guide Channel, with the promo channel playing in the top half,
as channel *N* in Kodi, on the Roku, in the browser and on the Pi box.

## How it works

One container, five small parts:

| Part | Job |
|---|---|
| Xvfb | a 640×480 screen nobody looks at |
| PulseAudio | a silent sink called `tv`; the browser plays the promo channel's sound into it |
| Chromium | `tvguide.html?tv&promo=…` from the viewer container, kiosk mode, full screen |
| ffmpeg | grabs the screen at 30 fps and the sink's monitor, encodes H.264 + AAC, writes HLS |
| http.server | hands the playlist and segments out at `http://<machine>:8412/live.m3u8` |

If any part dies the container exits and Docker restarts it. The output is plain HLS with 4 s
segments; ErsatzTV reads it as a remote stream and transcodes it into the channel's own
profile, so this stream only has to be clean, not small.

The page itself needs nothing new: it reads the listings through the viewer's `/iptv/` proxy,
so a channel added or renumbered in ErsatzTV shows up on the next scroll.

## Running it

In this folder's parent (`docker/`), with the viewer already running from `compose.yaml`:

```bash
docker compose --profile tvguide up -d --build
```

Settings in `.env` (see `.env.example`):

| Variable | Default | What |
|---|---|---|
| `TVGUIDE_PROMO` | empty | the channel whose stream plays in the top half; empty leaves it black |
| `TVGUIDE_PORT` | `8412` | where the stream is published on this machine |
| `TVGUIDE_BIND` | `127.0.0.1` | `0.0.0.0` when ErsatzTV runs in its own container or on another machine |
| `TVGUIDE_FPS` | `30` | frames per second of the generated stream |
| `TVGUIDE_BITRATE` | `1800k` | its video bitrate |

Check it: `curl http://127.0.0.1:8412/live.m3u8` lists segments, and `docker logs retro-tv-tvguide`
shows the page address and the encoder settings. `docker exec retro-tv-tvguide tail /tmp/ffmpeg.log`
(also `chromium.log`, `xvfb.log`, `pulse.log`) when something is wrong.

Cost: software rendering of a mostly static page plus one 640×480 encode is about one CPU core
on a desktop-class machine, less on x264's `veryfast` preset; memory under 1 GB.

## The ErsatzTV side

ErsatzTV's *remote streams* ([definition](https://ersatztv.org/docs/media/local/remotestreams/definition/),
[samples](https://ersatztv.org/docs/media/local/remotestreams/sample/)) take a URL that ffmpeg can
play directly. A remote stream library is a folder of `.yml` files; this one is the channel:

```yaml
# tvguide.yml
url: "http://<this machine>:8412/live.m3u8"
is_live: true
duration: 24:00:00
```

Then a channel for it (the Prevue Channel's own slot was low, so channel 1 or 2 suits it), a
schedule that plays this item all day, and a guide entry: the programme is simply "TV Guide
Channel". `is_live: true` is required: ErsatzTV must not try to work ahead on it. The address
must be reachable from where ErsatzTV runs: `127.0.0.1` only if ErsatzTV is on this machine's
host network; otherwise set `TVGUIDE_BIND=0.0.0.0` and use the machine's LAN address.

The top half wants a channel of its own to play: promos, commercials and infomercials, assembled
in ErsatzTV like the other channels, its number in `TVGUIDE_PROMO`. Until it exists any channel
number works as a stand-in. Do not point it at the TV Guide channel itself.

## Files

```
tvguide/
├── Dockerfile       Debian slim + Chromium, Xvfb, PulseAudio, ffmpeg
├── entrypoint.sh    starts the five parts and watches them
└── README.md        this page
```

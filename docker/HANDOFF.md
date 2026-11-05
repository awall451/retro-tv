# Handoff: retro TV guide web viewer (`docker/`)

**For:** the agent on the user's Linux laptop (Garuda, on the tailnet).
**From:** the Pi 4 / Batocera session that built the Kodi version of this guide.
**Date:** 2026-11-05.
**Status:** designed, not started. Nothing in `docker/` exists yet except this file and
`design/mockup.html`.

---

## 1. What the user wants

A **viewer** for the home ErsatzTV channels that opens in a web browser from anywhere on the
user's tailnet: open the URL → the retro TV guide appears → pick a show → it plays. It's the same
experience the user now has in Kodi on a Sony Trinitron, which they love, but reachable from a
laptop, desktop or phone.

The user's requirements, in their words and decisions so far:

1. **Docker / Docker Compose.** The whole viewer runs as a Compose project.
2. **Routed through Gantry so it's reachable on the tailnet.** The user reaches services on this
   laptop "anywhere through Gantry". This session never saw Gantry (see §9): find out how it
   works on the laptop before wiring anything, and fit into it rather than around it.
3. **Lives in its own directory, `docker/`,** in this repo (`retro-tv`). Everything for the viewer
   goes under `docker/`; don't scatter files elsewhere in the repo.
4. **The look:** the late-90s cable guide in [`design/mockup.html`](design/mockup.html). The user
   saw that mockup and said "I LOVE this first mockup".
5. **Behavior:** pressing select on a show goes **straight** into watching it. No pop-up in
   between. A details view is fine as a separate, optional action.
6. **The live picture keeps playing** in the guide's corner box while browsing. Going to the guide
   must never stop the show. The user also liked the idea of a smooth zoom between full screen and
   the box ("cool if possible, not required").
7. It's a **viewer only**: it reads from ErsatzTV and never changes anything there.
8. **Private:** tailnet only, and nothing personal in the repo (see §10).

### Decided against

| Option | Why not |
|---|---|
| Kodi itself in a container, shown in the browser through KasmVNC / noVNC | You'd watch a re-encoded video of a screen that's playing video: choppy motion, audio drift, heavy CPU on the laptop, poor on phones. Fine for menus, bad for TV. |
| Jellyfin or Plex Live TV pointed at ErsatzTV | Works today with no code, but it's their generic guide, not this look. Fine as a fallback if this project stalls. |

**Chosen:** a small web app. Static front end + a reverse proxy to ErsatzTV's read-only `/iptv/`
endpoints. The browser plays the streams itself (hardware decoding on the viewing device), and the
guide is drawn in HTML/CSS from ErsatzTV's XMLTV.

---

## 2. How the pieces fit

```
 browser (laptop / phone, on the tailnet)
    │  https://<gantry route>/
    ▼
 Gantry (the user's routing on the laptop: find out how it works)
    ▼
 docker compose: retro-tv-viewer
 ┌───────────────────────────────────────────────┐
 │ web: nginx or Caddy                           │
 │   /            → static app (HTML/CSS/JS)     │
 │   /iptv/...    → allowlisted proxy ───────────┼──► ErsatzTV  http://<server-ip>:8409
 │   (rewrites ErsatzTV's absolute URLs)         │     (home server, LAN; owned by another
 └───────────────────────────────────────────────┘      session: read only, never change it)
```

- ErsatzTV runs on the home server (a k3s pod). It already serves the channels to Kodi on the Pi.
  Its address is `<server-ip>:8409` on the home LAN. **Ask the user for the real address**; it's
  deliberately not in this repo. The laptop reaches it over the LAN at home and over the tailnet
  when away (check which route works; the server is also a tailnet node).
- One container is probably enough: nginx (or Caddy) serving the static app and proxying `/iptv/`.
  Add a second service only if you find a real need (for example, an XMLTV-to-JSON API; see §5.4).

---

## 3. ErsatzTV: what's actually there (verified 2026-11-05)

All read-only GETs. `S = http://<server-ip>:8409`.

| Path | Content-Type | What it is |
|---|---|---|
| `/iptv/channels.m3u` | `audio/x-mpegurl` | Channel list. `?mode=segmenter` makes every stream URL HLS (`/iptv/channel/<n>.m3u8?mode=segmenter`). |
| `/iptv/xmltv.xml` | `text/xml; charset=utf-8` | Guide data, about 1.4 MB for 16 channels × 2 days. Sends `Access-Control-Allow-Origin: *`. |
| `/iptv/channel/<n>.m3u8?mode=segmenter` | `application/vnd.apple.mpegurl` | **HLS master playlist (use this).** About 2 s to start. One variant: `BANDWIDTH=1953600, RESOLUTION=640x480, CODECS="avc1.4D4028,mp4a.40.2"`, pointing to `/iptv/session/<n>/live.m3u8`. |
| `/iptv/channel/<n>.m3u8` (no mode) | — | `302` → `/iptv/channel/<n>.ts` (the channels' default mode is MPEG-TS). |
| `/iptv/channel/<n>.ts` | MPEG-TS | What Kodi plays. Browsers can't play it natively (mpegts.js could). |
| `/iptv/session/<n>/...` | HLS | The live media playlist and segments behind the master playlist. |
| `/iptv/logos/gen?text=…` | image | Generated channel logos (text on a plain background). |
| `/iptv/artwork/posters/plex/<id>` and `/iptv/artwork/thumbnails/plex/<id>` | image | Posters and episode stills referenced by the XMLTV. |

**Important:** ErsatzTV writes **absolute URLs with its own LAN address** into the M3U, the HLS
master playlist (`http://<server-ip>:8409/iptv/session/1/live.m3u8`), and the XMLTV `icon`/`image`
elements. Through a proxy, those must not leak to the browser, or remote viewers will try to reach
the LAN address directly and fail. Two ways:

1. First test whether ErsatzTV builds those URLs from the request's `Host` header. Send the
   request through the proxy with `proxy_set_header Host $host` and `X-Forwarded-Host/Proto`, and
   see whether the URLs change.
2. If not, rewrite them in the proxy: nginx `sub_filter 'http://<server-ip>:8409/' '/';` with
   `sub_filter_once off; sub_filter_types application/vnd.apple.mpegurl audio/x-mpegurl text/xml;`
   and `proxy_set_header Accept-Encoding "";` (sub_filter can't edit compressed bodies). Or have
   the front end strip the origin from every URL it reads, but playlists fetched by hls.js still
   need the proxy fix, so do it in the proxy.

### 3.1 Channel list (M3U)

```
#EXTINF:0 tvg-id="C1.145.ersatztv.org" channel-id="…" channel-number="1" tvg-chno="1"
  tvg-name="Star Trek TNG" tvg-logo="http://<server-ip>:8409/iptv/logos/gen?text=Star+Trek+TNG"
  group-title="ErsatzTV", Star Trek TNG
http://<server-ip>:8409/iptv/channel/1.ts
```

- Key a channel by `tvg-id` (it matches `<channel id>` and `<programme channel>` in the XMLTV).
  Order and display by `tvg-chno`.
- **16 channels as of today:** 1 Star Trek TNG, 2 Toonami, 3 Sitcoms, 4 80s Action, 5 Cartoon
  Network, 6 Looney Tunes, 7 Family Channel, 8 Adult Swim, 9 Toonami HD, 10 Classic Sitcoms,
  11 Star Trek Films, 12 Non-Stop Action, 13 Platform 9¾, 14 Midnight Society, 15 Christmas
  Spirit, 16 Studio Ghibli. **Channels get added and rebuilt often** by the other session, so
  never hard-code them.
- Names can have non-ASCII characters (`Platform 9¾`). Handle UTF-8 throughout.

### 3.2 Guide data (XMLTV)

Root `<tv generator-info-name="ersatztv">`. Per channel:

```xml
<channel id="C1.145.ersatztv.org">
  <display-name>1 Star Trek TNG</display-name><display-name>1</display-name>
  <display-name>Star Trek TNG</display-name>
  <icon src="http://<server-ip>:8409/iptv/logos/gen?v=…&amp;text=Star+Trek+TNG"/>
</channel>
```

Per programme (an episode):

```xml
<programme start="20261105130000 -0500" stop="20261105140000 -0500" channel="C1.145.ersatztv.org">
  <title lang="en">Star Trek: The Next Generation</title>
  <sub-title lang="en">11001001</sub-title>
  <desc lang="en">Stardate: 41365.9. While undergoing repairs, …</desc>
  <category lang="en">Series</category> <category lang="en">Action</category> …
  <icon src="http://<server-ip>:8409/iptv/artwork/posters/plex/135570"/>
  <image type="poster" size="3">http://…/iptv/artwork/posters/plex/135570</image>
  <image type="still" orient="L" size="3">http://…/iptv/artwork/thumbnails/plex/135750</image>
  <episode-num system="onscreen">S01E14</episode-num>
  <episode-num system="xmltv_ns">0.13.0/1</episode-num>
  <rating><value>TV-PG</value></rating>
  <previously-shown/>
</programme>
```

Movies have no `sub-title` or `episode-num`, and add `<date>1984</date>`; the first category is
`Movie`. Counts across today's file: 1351 programmes, `desc` on 1338, `sub-title` on 1089,
`rating` on 1339, `date` on 262.

- **Times carry their own UTC offset** (`-0500`). Parse them to absolute instants and display in
  the **viewer's** local time zone. (Lesson: the Pi was left on Europe/Paris and the guide was six
  hours off.)
- Listings cover roughly now−1 day to now+2 days. Programmes are contiguous per channel (no gaps
  seen), but don't assume it: draw a gap as an empty "No information" cell.
- **Schedules change under you.** The other session rebuilds playouts, and today Toonami's next
  hour was reshuffled between two fetches. Re-fetch the XMLTV at least every 15 minutes, and also
  when the page regains focus. Use `If-Modified-Since`/`ETag` if ErsatzTV supports them (check).
- Very short programmes exist: Looney Tunes is a run of 6-minute shorts, and the Kodi guide turned
  them into "L… Loon… L…" slivers. Merge consecutive programmes with the same `title` into one
  cell for display (e.g. "Looney Tunes · 4 shorts"), and show the individual shorts in the details
  panel when highlighted. Never print a label in a cell too narrow for it.

---

## 4. The design (match the mockup)

Open [`design/mockup.html`](design/mockup.html) in a browser. It's drawn at **640×480**, the
Trinitron's real size. The Kodi version of the same screen is
[`../pi/kodi-skin/MyPVRGuide.xml`](../pi/kodi-skin/MyPVRGuide.xml) (same layout, coordinates ×3),
and the details pop-up is [`../pi/kodi-skin/DialogPVRInfo.xml`](../pi/kodi-skin/DialogPVRInfo.xml).

### 4.1 Layout (640×480 reference)

```
┌───────────────────────────────────────────────────────────────┐ y=0
│ ┌──────────────────────┐  Ch 1 · Star Trek TNG        (yellow) │
│ │                      │  Star Trek: The Next Generation (big) │
│ │  live picture of the │  "When the Bough Breaks"   (light blue)│
│ │  channel you're       │  3:00 – 4:00 PM · TV-PG               │
│ │  watching (4:3)      │  A planet that can cloak itself …     │
│ └──────────────────────┘  (description, wraps, 4–6 lines)     │ y≈200
├────────────┬───────────────┬───────────────┬──────────────────┤ y≈210
│ Thu 3:24 PM│ 3:00 PM       │ 3:30 PM       │ 4:00 PM          │ time bar
├────────────┼───────────────┴───────────────┼──────────────────┤
│1 Star Trek │ Star Trek: The Next Generation │ Star Trek: TNG   │ focused row
│2 Toonami   │ Initial D     │ Dragon Ball Z │ Dragon Ball Z    │
│ …          │               │               │                  │ 8 rows visible
└────────────┴───────────────┴───────────────┴──────────────────┘ y=480
```

- Preview box: about 256×192 at (8,8), 4:3, 2 px yellow frame, black inside.
- Details: right of the preview, from x≈272.
- Grid: from y≈210. Channel column 126 px, then 3 half-hour columns (90 minutes). Rows 27 px
  plus a 2 px black gap. 8 channel rows fill the screen; the rest scroll.
- **The time window starts on the current half hour** (3:24 PM → 3:00). Kodi couldn't do this
  reliably and showed slivers at the left edge. A browser can, so do it.

### 4.2 Colors and type

| Token | Hex | Used for |
|---|---|---|
| `--navy` | `#0a1240` | page background, text on yellow |
| `--program` | `#0f2a7a` | programme cells |
| `--channel` | `#1c3fa8` | channel-name cells |
| `--timebar` | `#5a7fe0` | half-hour header cells |
| `--yellow` | `#f2c200` | focus, preview frame, channel line, clock cell |
| `--soft` | `#cfe0ff` | episode name, description |
| `--white` | `#ffffff` | most text |
| `--gap` | `#000000` | 2 px lines between cells |

- Font: **Cabin Bold** (SIL Open Font License; same font as the CRT game menu and the Kodi guide).
  Self-host it in the image (Google Fonts has it). Description text can use Cabin Regular.
- Sizes at 640×480: grid and channel names 15 px, title 21 px, episode and time 16 px,
  description 14 px. Everything bold except the description.
- **2 px minimum** for any line or gap. The same page may one day be shown on the CRT, where
  1-pixel lines flicker. Cheap to respect, so respect it.
- Flat colors. No gradients, shadows, rounded corners or transparency: it's a 1997 cable guide.

### 4.3 Sizing on other screens (open question)

The mockup is 640×480. Ask the user which they prefer:

- **A. Keep the 4:3 layout and scale it** to fit the window (letterboxed). Most faithful; tiny on a
  phone held upright.
- **B. Responsive:** same parts and look, but the grid fills the width and shows more channels or
  more time on big screens, and the preview and details stack on narrow ones.

Suggested default if you can't ask: **B**, with the 4:3 proportions kept for the preview box, plus
a "TV mode" toggle (or `?tv=1`) that forces A for big screens.

### 4.4 States and interactions

| State | What's on screen | Select (Enter / click / A / Cross) | Back (Esc / Backspace / B / Circle) | Info (I / long-press / X / Square) |
|---|---|---|---|---|
| **Guide** | Grid, details of the highlighted show, preview box playing the current channel (or "Pick a show to watch" if none yet) | Tune to that channel and go **straight to full screen** | If a channel is playing: back to full screen. Otherwise nothing | Open **Details** |
| **Full screen** | The channel, filling the window (4:3 kept, black bars) | Show a small banner (channel, title, time, progress) for 4 s | Open the **Guide**; the show keeps playing in the box | Banner |
| **Details** | Big-text panel: channel, title, episode (S01E14 "Name"), time, rating, year/genres, poster, full description; **Watch now** button | Watch now: tune and go full screen | Close, back to Guide | Close |

Further rules:

- **Select on a show that's already over or not started yet:** tune to the channel anyway (it plays
  what's on now). Same as Kodi and real TV.
- **Up/Down** moves between channels and keeps the same *time position* (the start time of the
  focused cell). Kodi's grid sometimes jumped back to the "now" column on Down, and the user
  reported it as a bug, so don't reproduce it. **Left/Right** moves between programmes, scrolling
  the time window by half hours at the edges; don't go before "now − 30 min".
- **Channel up/down while full screen:** PageUp/PageDown, D-pad up/down, shoulder buttons, with a
  banner on each change.
- **Number entry:** typing digits jumps to that channel (nice to have).
- **Now-playing marker:** mark the channel you're watching in the channel column (Kodi drew its
  name in orange). Use a small yellow ▶ or yellow text, not a new color.
- **"Now" line:** optional thin (2 px) yellow line at the current time across the grid.
- **Clock cell:** day and time (`Thu 3:24 PM`), updated every minute; the grid re-aligns at each
  half hour.
- **Zoom transition (nice to have):** opening the guide shrinks the video from full screen into
  the preview box (about 350 ms ease-out) and back the other way on close. Use one `<video>`
  element that's moved and resized with a CSS transform (FLIP), never a second player. Re-creating
  the player would restart the stream and add the 2 s HLS start.
- **Audio:** keeps playing in the guide. Browsers block autoplay with sound until the user
  interacts; the first Select counts as a gesture. Start muted if you must and unmute on first
  input.
- **Remember** the last channel in `localStorage` and pre-highlight it next time, but don't
  auto-play it.

### 4.5 Input

- Keyboard: arrows, Enter, Esc/Backspace, I, PageUp/PageDown, digits.
- Mouse and touch: click/tap a cell = Select. Tap the preview = full screen. Swipe or scroll the
  grid. A visible ✕/back on Details. In full screen, a tap shows the banner and a back button.
- **Gamepad API** (the user uses a PS5 DualSense; also test an Xbox pad): standard mapping,
  `buttons[0]` A/Cross = Select, `[1]` B/Circle = Back, `[2]` X/Square = Info, D-pad
  `[12..15]`, `[4]/[5]` shoulders = channel down/up. Poll in `requestAnimationFrame`, with key
  repeat after about 400 ms. Pads appear only after the first button press on the page.
- Focus is always visible as a yellow cell; there's no hover-only UI.

---

## 5. Front end

### 5.1 Stack

Keep it small; the user didn't ask for a framework. Suggested: plain HTML + CSS + ES modules (or
Vite + TypeScript if you prefer), **hls.js** for playback (pin an exact version and vendor it into
the image rather than loading it from a CDN at runtime), no other runtime dependencies. Safari and
iOS play HLS natively: use `video.canPlayType('application/vnd.apple.mpegurl')` and fall back to
hls.js elsewhere.

### 5.2 Playback

- Tune: `GET /iptv/channel/<n>.m3u8?mode=segmenter` through the proxy, played via hls.js. Expect
  about 2 s before the first frame. Show the channel's name in the box meanwhile ("Tuning to 2
  Toonami…").
- **One stream at a time.** Each open stream is a live transcode on the home server. Only the
  channel being watched streams. Never preview the highlighted channel, and never preload others;
  the user explicitly prefers the box to keep showing what they're watching. Destroy the old
  hls.js instance before tuning to a new channel.
- Stop streaming when the tab is hidden for more than a few minutes (Page Visibility API), and
  resume when it's back, so a forgotten tab doesn't keep the server transcoding all night.
- hls.js live settings: keep the defaults and check `liveSyncDuration`; don't use low-latency mode
  (ErsatzTV isn't LL-HLS). On a fatal error, show "Channel unavailable, retrying…" and retry with
  backoff. ErsatzTV shows its own error card if a file fails, so you'll also see that in-picture.
- Video is 640×480 4:3. Keep the aspect (`object-fit: contain`), black bars.

### 5.3 Guide data

- Fetch `/iptv/channels.m3u` and `/iptv/xmltv.xml` through the proxy. Parse M3U lines by regex;
  parse the XMLTV with `DOMParser`. 1.4 MB parses fine in a browser; keep only now−30 min to
  now+24 h in memory.
- Index programmes by channel, sorted by start. The details panel and grid both read from that
  index.
- Refresh both every 15 minutes, on `visibilitychange`, and on a manual "R". Keep the focus on the
  same channel and time across a refresh.
- XMLTV image URLs are absolute LAN URLs. Rewrite them to `/iptv/...` relative paths, or rely on
  the proxy rewrite (§3).

### 5.4 Optional: a tiny API service

If parsing in the browser feels heavy on phones, add a small service (e.g. Python/FastAPI or Go)
in the Compose project that fetches the XMLTV, caches it, and serves `/api/guide?from=&hours=`
as compact JSON. **Not needed for v1.** Start without it.

---

## 6. Docker / Compose

Everything under `docker/`. Suggested layout:

```
docker/
├── HANDOFF.md            this file
├── README.md             how to run it, for the user (write this)
├── compose.yaml
├── .env.example          ERSATZTV_URL=http://<server-ip>:8409   (real .env is git-ignored)
├── web/
│   ├── Dockerfile        nginx:<pinned>-alpine + the built app + fonts + hls.js
│   ├── nginx.conf.template
│   └── app/              index.html, css/, js/, fonts/ (Cabin), vendor/hls.js
└── design/
    └── mockup.html       the approved design (keep it)
```

`compose.yaml` sketch (adapt to how Gantry expects services to be declared; see §9):

```yaml
services:
  web:
    build: ./web
    restart: unless-stopped
    environment:
      ERSATZTV_URL: ${ERSATZTV_URL}          # http://<server-ip>:8409, from .env
    # Bind to loopback or the Gantry network only. Never 0.0.0.0 on a public interface.
    ports:
      - "127.0.0.1:8088:80"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/healthz"]
      interval: 30s
```

`nginx.conf.template` essentials (nginx's image substitutes `${ERSATZTV_URL}` via envsubst):

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  location = /healthz { return 200 "ok\n"; }
  location / { try_files $uri $uri/ /index.html; }

  # Read-only allowlist. Anything else under /iptv/ or /api/ must 404.
  location ~ ^/iptv/(channels\.m3u|xmltv\.xml|channel/[0-9]+\.m3u8|session/|logos/|artwork/) {
    limit_except GET HEAD { deny all; }
    proxy_pass ${ERSATZTV_URL};
    proxy_http_version 1.1;
    proxy_set_header Accept-Encoding "";        # so sub_filter can rewrite
    proxy_buffering off;                        # live HLS
    sub_filter_types application/vnd.apple.mpegurl audio/x-mpegurl text/xml;
    sub_filter '${ERSATZTV_URL}/' '/';          # absolute LAN URLs → relative (see §3)
    sub_filter_once off;
  }
  location /iptv/ { return 404; }
  location /api/  { return 404; }                # ErsatzTV's admin API: never reachable
}
```

- Pin image versions (`nginx:1.27-alpine` or whatever is current and at least two weeks old).
- The `.ts` path isn't in the allowlist on purpose (use HLS). Add it only if you switch to mpegts.js.
- No secrets are needed: the `/iptv/` endpoints don't take a key. ErsatzTV's API key exists, but
  this viewer must not use it.

---

## 7. Security rules (non-negotiable)

1. **Never expose ErsatzTV's web UI or `/api/`.** It has no login, and its config holds a token
   with full access to the Plex account. Proxy only the allowlisted read-only `/iptv/` paths
   above.
2. **Tailnet only.** Through Gantry, to tailnet devices. No public internet exposure, no Funnel,
   no port forwarding.
3. **No changes to ErsatzTV or the home server.** Another session owns them. If the viewer needs
   something server-side (a CORS header, a new endpoint), write it down for the user to pass on.
4. No secrets, real addresses, MACs or personal names in the repo. Real values go in
   `docker/.env` (git-ignored; add `docker/.env` to the root `.gitignore`).

---

## 8. Milestones and acceptance

1. **Proxy proof:** Compose up; `curl` through the proxy returns the M3U and the XMLTV with no
   LAN addresses left in them; `/api/` and other `/iptv/` paths return 404; one channel plays in
   VLC or mpv from `http://localhost:8088/iptv/channel/1.m3u8?mode=segmenter`.
2. **Player:** a bare page plays a channel in Chrome and Firefox (hls.js) and Safari (native), and
   channel switching works without leaking streams. Check that the old session stops on the server
   side (ErsatzTV drops idle HLS sessions after a short timeout).
3. **Guide:** the grid from real data, aligned to the half hour, 15-minute refresh, keyboard and
   mouse navigation, details panel, now-playing marker, merged short programmes.
4. **Watching:** Select → full screen; Back → guide with the show still in the box; banner; channel
   up/down; Info → details with Watch now.
5. **Gamepad and touch.**
6. **Gantry:** reachable from another tailnet device (the user's phone) by its Gantry route;
   not reachable off the tailnet.
7. **Polish:** zoom transition, Cabin font, 2 px lines, empty and error states, `docker/README.md`.

**Done when** the user opens the Gantry URL on the laptop and on the phone, sees the guide, picks a
show with one press, watches it, goes back to the guide with the show still playing, and nothing
but the read-only `/iptv/` paths is reachable through it.

---

## 9. Open questions (ask the user or find out on the laptop)

1. **Gantry.** What is it, and how does a service get a route: Docker labels, a config file, a
   shared network, a Tailscale serve wrapper? Find its config on the laptop, look at an existing
   service that uses it, and follow that pattern exactly. This session never saw it.
2. **ErsatzTV's address** from the laptop: LAN IP at home, and does it also work over the tailnet
   when away? (The server is a tailnet node.) The viewer has to reach it both ways, or the user has
   to accept home-only.
3. **Layout:** fixed 4:3 scaled, or responsive (§4.3)?
4. Does ErsatzTV build its absolute URLs from the `Host` header (§3)? That decides the
   rewrite approach.
5. Later: move the Compose project to the home server? Fine as long as it stays in this repo's
   `docker/` and the server's owner agrees.

---

## 10. Repo conventions

- Repo: `retro-tv` (private). Branch `main`. Commit as the user's GitHub noreply identity (the
  repo-local git config on the Windows PC already does; set the same on the laptop).
- **Nothing personal in commits or files:** no home IPs (use `<server-ip>`, `<pi-ip>`), MACs, email
  addresses, machine or tailnet hostnames, or real names. Run a quick grep before each push.
- Line endings: `.gitattributes` forces LF for code and configs. Keep it that way.
- The Pi side (`pi/`, `tools/`, `docs/`) is maintained from another machine. Don't change it from
  here except to fix a link. Do update `README.md`'s folder table if you add something top-level.

## 11. Background, if useful

- `docs/tv.html`: how the ErsatzTV channels were built (server side, lineups, commercials,
  troubleshooting).
- `docs/display.html`, section "The retro TV guide (Trinitron)": the Kodi version, its controls,
  and the problems found (stale guide, empty guide for new channels, Circle stopping playback).
- `pi/kodi-skin/`: the Kodi screens this design came from.

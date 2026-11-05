# Web TV guide (to build)

A browser front end for the ErsatzTV channels: the same retro cable-style guide as Kodi's on
the Trinitron, so the channels can be watched from any device on the tailnet. It's a viewer only;
it never changes anything on the server.

## What it should do

- Open straight into the guide: navy grid, yellow highlight, 90 minutes across starting on the
  current half hour, channels down the left. Design: [`mockup.html`](mockup.html) (drawn at the
  Trinitron's 640×480; the Kodi version is [`../pi/kodi-skin/MyPVRGuide.xml`](../pi/kodi-skin/MyPVRGuide.xml)).
- Top left: the channel you're watching keeps playing in a framed box. Top right: details of the
  highlighted show (channel, title, episode, time, rating, description).
- Select a show (click, tap, Enter, or a gamepad's A/Cross) → that channel plays full screen.
  Back (Esc, Backspace, B/Circle) → the guide, with the show still playing in the box.
- A details view on request (Square/X or a long press), not on every select.
- Arrow keys, mouse, touch, and the browser Gamepad API (PS5 and Xbox pads).
- Size: decide with the user whether to keep the 640×480 layout scaled up, or lay it out to fill
  laptop and phone screens.

## Data (ErsatzTV, read-only)

`<server-ip>` is the ErsatzTV host on the home network; ask the user for it. Port 8409.

| URL | What |
|---|---|
| `/iptv/channels.m3u` | Channel list: `tvg-id`, `tvg-chno`, `tvg-name`, `tvg-logo`, stream URL `/iptv/channel/<n>.ts` |
| `/iptv/xmltv.xml` | Guide: `<programme channel start stop>` with `title`, `sub-title`, `desc`; times carry a UTC offset |
| `/iptv/channel/<n>.ts` | Live stream: MPEG-TS, H.264 + AAC, 640×480 4:3 |
| `/iptv/logos/gen?text=…` | Generated channel logos |

Browsers can't play raw MPEG-TS by themselves. Check whether ErsatzTV serves HLS for the same
channel (`/iptv/channel/<n>.m3u8`, possibly with `?mode=segmenter`) and use hls.js, or play
the `.ts` with mpegts.js. Opening a channel starts a live transcode on the server, so only open a
stream when the user actually watches; don't preload every channel.

As of 2026-11-05 there are 16 channels with two days of listings each.

## Deploy

Docker Compose on the user's Linux laptop (on Tailscale) for now; maybe the home
server later. A static page plus a small reverse proxy (nginx or Caddy) that forwards **only**
the four paths above to ErsatzTV. That also avoids CORS.

## Rules

- **Never expose ErsatzTV's web UI or `/api`.** It has no login, and its config holds a token with
  full access to the Plex account. Proxy only the read-only `/iptv/...` paths.
- Reachable over Tailscale only, not the public internet. The user mentioned "Gantry" for
  routing; find out what it is before wiring anything to it.
- Don't change ErsatzTV or its server; another session owns that side.
- No secrets, keys or home addresses in this repo; use placeholders and a local `.env`.

## Lessons from the Kodi version

- Reload the guide every 15 minutes or so: the server rebuilds schedules, and a stale guide shows
  the wrong show "on now".
- Show times in the viewer's local time zone (the Pi was once left on Europe/Paris).
- Very short programs (6-minute cartoons) make unreadable slivers in the grid; consider merging
  runs of the same title or hiding labels on narrow cells.
- Draw lines at least 2 px thick if it will ever be shown on the CRT.

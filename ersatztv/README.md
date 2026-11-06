# Building retro cable channels in ErsatzTV

How we run 36 round-the-clock "cable" channels on [ErsatzTV](https://ersatztv.org), with
commercials between and inside programmes, a TV guide, and an HD copy of every channel for
modern screens. It is written so you can do the same with your own library. Kodi on the Pi
watches these channels (see `../pi/`); so does the browser viewer (`../docker/`).

| File | What it is |
|---|---|
| `README.md` | This guide |
| `commercials/` | **The commercials**: 1,120 clips in 12 sets from the Internet Archive, the catalog of where each came from, and `build.py` to rebuild them. Start with `commercials/README.md` |
| `lineups.example.json` | Example channel lineups (a few of ours) |
| `build-queries.py` | Turns a lineups file into ErsatzTV smart collection queries |
| `check-chapters.py` | Lists episodes a commercial-break channel would drop (see "Chapter marks") |

Addresses are placeholders: `<server-ip>` is the machine running ErsatzTV (port 8409).

## Our setup

- **ErsatzTV 26.11** in a container, with an NVIDIA card for encoding (NVENC). Stay on 26.11 if
  you want the HD twins below: they need the Legacy streaming engine, which ErsatzTV says goes
  away in 26.12.
- **The library comes from a Plex server** (a friend's, shared with us). ErsatzTV reads Plex's
  catalogue and streams a file only while a channel showing it is watched; nothing is copied.
  Local folders and Jellyfin/Emby work the same way.
- **Commercials are a local library** of type Other Videos (see `commercials/README.md`).
- **One FFmpeg profile for every channel**, `CRT 640x480 NVENC`: NVENC, 640x480, scale and pad,
  H.264 high, 1500 kbps video (3000 buffer), AAC 128 kbps stereo 48 kHz, loudness normalization
  (LoudNorm, target -16), deinterlace on, B-frames off. Our main screen is a 4:3 CRT; widescreen
  programmes air letterboxed. A new channel defaults to the 1080p profile, so pick this one in
  the channel form.
- Channels are **MPEG-TS** on the **Next** streaming engine (the default in 26.11).
- Feeds for players: `http://<server-ip>:8409/iptv/channels.m3u` and `/iptv/xmltv.xml`. Kodi
  uses them through the IPTV Simple Client add-on.

ErsatzTV's API covers FFmpeg profiles, smart collections, playout resets and library scans.
Filler presets, schedules, channels and playouts are made in the web UI.

## Building a channel

1. **Smart collection** (Lists → Smart Collections, or `POST /api/collections/smart/new` with
   `{"name": …, "query": …}` and the API key in header `X-Etv-Api-Key`). Write the query by hand
   or keep lineups in a JSON file like `lineups.example.json` and run `build-queries.py`. Test
   every query first on `http://<server-ip>:8409/search?query=<url-encoded query>` and compare
   the count with what you expect.
2. **Schedule** (Scheduling → Schedules): one item, Start Type Dynamic, Collection Type Smart
   Collection, Playout Mode One, a playback order, and the commercial presets (see
   "Commercials in the schedule"). Orders we use: **Chronological** (episodes in order; for
   films, release order), **Shuffle In Order** (shows rotate, each in episode order),
   **Shuffle**.
3. **Channel** (Channels → Add Channel): number, name, group, the FFmpeg profile, MPEG-TS.
4. **Playout** (Playouts → Add): Classic Schedule, pointing at the schedule.

A playout is built from local midnight of the day it is created or reset, so a chronological
channel starts its first episode at midnight. After changing a collection or a schedule, reset
the playout: `POST /api/channels/<number>/playout/reset`.

**Story order** (Star Wars I to IX with the spin-offs in between; Middle-earth from The War of
the Rohirrim on) is neither release order nor alphabetical. Use a **playlist** (Lists →
Playlists): one item per film, Show In EPG ticked, and Collection Type Playlist in the schedule.

**Short programmes** (cartoon shorts of 7 minutes): Playout Mode **Duration**, 30 minutes, Tail
Mode Filler with a Tail preset. ErsatzTV plays shorts until the next will not fit, then fills
the rest of the half hour with commercials. A pad preset there would put 20 minutes of ads after
each short.

**Filling in forms in bulk.** Building 20 channels by hand is slow. The UI is Blazor with
MudBlazor controls; a script in the browser console can fill the forms: open a select with mouse
events (`mousedown`, `mouseup`, `click`) on its `.mud-input`, then click the option in
`.mud-popover-open .mud-list-item`; set a text field with the native value setter followed by
`input` and `change` events. Check every save afterwards.

## Smart collection queries

What we learned the hard way:

- **A quoted title also matches longer titles** (`"Police Story"` matches Police Story 2), so
  pair each film with its release year:
  `(title:"Police Story" AND release_date:[19850101 TO 19851231])`. `build-queries.py` does
  this. A film the server has no release date for matches no date range; match it on title only
  (year `null` in the lineups file).
- **Punctuation belongs inside the quotes**: `"Married... with Children"`, `"That '70s Show"`.
- **A quoted phrase with a stop word** ("in", "the", "of") or only part of a punctuated title
  matches nothing: `"Ghost in the Shell"` and `"Under Arrest"` returned zero. Use a part without
  stop words (`"Stand Alone Complex"`), single words joined with AND (`king AND hill`), or the
  whole title with its punctuation (`"You're Under Arrest!"`). Single words are not always safe
  either: `swat` matches SWAT Kats, `kats` does not.
- When a word comes up short, try a wildcard: `title:trek` found 7 of 13 Star Trek titles,
  `title:trek*` all 13.
- `NOT season_number:0` keeps specials out. A genre guard (`genre:animation`) keeps out
  live-action shows with the same title. `minutes:[45 TO 400]` keeps shorts and TV specials off
  a film channel.
- `NOT state:FileNotFound` on every collection of local files: a clip moved out of the folder
  otherwise stays in rotation until the trash is emptied.
- Smart collections update on their own when the library grows.

## Commercials in the schedule

Commercials are **filler presets** (Lists → Filler Presets) on a collection of clips, attached
to a schedule item. Three kinds matter:

- **Mid-Roll**: breaks inside a programme, at its **chapter marks**.
- **Post-Roll**: a block after each programme.
- **Fallback**: what plays if a gap cannot be filled otherwise.

and two modes:

- **Pad** (to the nearest 30 minutes): works out the ad time needed to reach the next :00 or
  :30 and spreads it over the breaks, so programmes start on the hour and half hour like real
  TV. A schedule item can hold only one Pad preset.
- **Duration**: a fixed length per break. Duration presets can be combined.

### Chapter marks

Breaks can only go where the file has a chapter mark. A **filler expression** on the Mid-Roll
preset picks which chapter ends become breaks: `point` is seconds into the programme,
`remaining_duration` seconds left, `last_mid_filler` seconds since the previous break.

| For | Expression |
|---|---|
| Shows | `point > 240 and remaining_duration > 180 and last_mid_filler > 300` (no break in the first 4 minutes or last 3, at most one every 5 minutes) |
| Films | `point > 600 and remaining_duration > 600 and last_mid_filler > 1200` (none in the first or last 10 minutes, at most one every 20) |
| A show whose only usable mark is right after a short cold open | `point > 150 and remaining_duration > 180 and last_mid_filler > 300` |

- **A file with no chapter marks gets all its ad time in one block after it.** That is fine for a
  film; for an hour-long episode it means about 14 minutes of ads at the end. If you would rather
  not, put unchaptered films on a channel without commercials.
- **A file whose chapter marks all fail the expression is dropped from the schedule, but its ad
  time stays**: we had 30-minute slots of nothing but bumpers. Lupin the 3rd has marks only at
  the opening and ending credits; Record of Lodoss War season 2 the same. Before putting a show
  on a channel with breaks, run `check-chapters.py` on it and exclude what it lists in the
  query.

### The two patterns we use

**Shows**: one Mid-Roll preset, **Pad** to the nearest 30 minutes, with the shows expression,
plus a Fallback preset on the same clips. Episodes start on :00 or :30 with three-minute-ish
breaks at the chapter marks.

**Films**: a Mid-Roll preset, **Duration 3 minutes**, with the films expression, plus a
Post-Roll preset, **Duration 6 minutes**. What airs:

- a film with chapter marks: 3-minute breaks inside it, then 6 minutes of ads before the next;
- a film without: one block of about 9 minutes after it.

Films then start at odd times, which is how film channels felt anyway.

**No commercials at all**: a schedule item with no presets; films run back to back.

## HD copies of every channel ("twins")

The CRT wants 640x480; a laptop or a big TV wants 1080p. Rather than a second set of channels in
every guide, each channel has a hidden **twin** that mirrors it in 1920x1080, and the browser
viewer's Quality setting switches to it.

- FFmpeg profile `HD 1920x1080 NVENC`: the CRT profile's settings at 1920x1080, 6000 kbps video
  (12000 buffer), 192 kbps audio.
- A twin (Channels → Add Channel): number = the channel's + 100, group `HD`, Playout Source
  **Mirror**, Mirror Source = the channel, offset 0, Show In EPG **off**, streaming engine
  **Legacy**, the HD profile. Every new channel needs its twin made by hand.
- **Mirrors only play on the Legacy engine** in 26.11 (on Next they show an error card,
  "failed to resolve the playout folder"). Check before upgrading.
- **A twin cannot be hidden from `channels.m3u` and still play.** Show In EPG off removes it from
  the guide only; disabling it makes the stream answer 404. Kodi therefore lists twins as extra
  channels unless it is told to skip group `HD` (we filter the list on the Pi).
- HD is heavy on the CPU: the Legacy engine scales on the CPU, and some sources (10-bit H.264)
  decode in software. **One HD stream used about 3.7 CPU cores** on our server, so give
  ErsatzTV about 4 cores per HD stream you expect to run at once.
- To swap two channels' numbers, edit each channel's Number through a spare number (16 → 9916,
  1 → 16, 9916 → 1), then the same for their twins; a twin follows its channel by id, not by
  number. Channels → Edit Channel Numbers renumbers by drag order, which is not what you want.

## Checking what a file looks like on air

`GET /api/troubleshoot/playback.m3u8?mediaItem=<id>&ffmpegProfile=<id>&streamingMode=4&seekSeconds=<n>`
(API key header; not in the API list) transcodes 30 seconds of one programme through a chosen
profile. Read the result with ffmpeg's `cropdetect`: 640x480 is full 4:3, 640x360 true
widescreen, 480x360 a 4:3 picture with bars baked into a wide file. `mediaItem` is the episode's
or movie's id in ErsatzTV's database.

## Limits we ran into

- **At most 8 channels can play at once on a consumer NVIDIA card**: each channel being watched
  is one NVENC session, and the driver allows 8. A ninth fails (`nvEncOpenEncodeSessionEx
  failed`) with an error card. A channel keeps running for about 90 seconds after its last
  viewer leaves (Next engine; Legacy about 30), so flipping quickly through many channels can
  fill the card. `GET /api/sessions` lists what is running.
- **Two-file rips ("cd1 / cd2") play only their first file**; the rest of the slot is an error
  card. Find them before building a film channel (in the database: `select Path from MediaFile
  where Path like '%cd1%'`) and leave them out.
- ErsatzTV scans one library at a time; a first scan of 3,400 films took about 30 minutes and of
  280 shows (12,000 episodes) about an hour.
- Two clips from the same set can land next to each other by chance; the shuffle has no rule
  against it.
- Programmes run at 23.976 fps and most commercials at 29.97, so the stream changes frame rate at
  each break. Kodi and browsers cope.

# Channels from live streams and YouTube

Most channels here play files from a media server. Two kinds do not:

- **Live channels**: free 24-hour news streams (NBC News NOW, ABC News Live, BBC News and so on),
  passed straight through.
- **Channels built from a YouTube channel's films**: each film is streamed from YouTube when it
  airs, with your own commercials between films. Nothing is downloaded or stored.

Both use ErsatzTV's *Remote Streams* library and a small relay service, `relay.py`.

Pulling video with `yt-dlp` is against YouTube's terms of service. This is for watching at home.

## Why a relay

ErsatzTV can run a command for a remote stream (`script:` in the stream file), and its
documentation shows `yt-dlp` used that way. On v26.11.6 and v26.12.0 that never starts: the
library scan runs in a separate program, which signs ErsatzTV's internal stream address with a
random key the main program does not have. The request answers "not found", the item is stored
with no picture, and the channel shows *video input is required*.

A remote stream given as a plain `url:` is read directly and works. So each stream file points
at the relay, and the relay does the pulling.

```
YouTube / broadcaster ──► relay.py ──► ErsatzTV remote stream (url:) ──► channel
```

## The relay

`relay.py` is one file with no dependencies beyond Python 3, `ffmpeg` and `yt-dlp`. It answers
two kinds of address:

| Address | What it returns |
|---|---|
| `/live/<name>` | The live stream listed under `<name>` in the stream list, as MPEG-TS. |
| `/vod/<id>.m3u8` | One YouTube video (by its 11-character id) as an ordinary segmented playlist. |

Settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `RELAY_PORT` | `8090` | Port to listen on. |
| `YTDLP` | `/media/tools/yt-dlp` | Path to the `yt-dlp` release file (run with `python3`). |
| `STREAMS_FILE` | `/relay/streams.json` | The stream list; see `streams.example.json`. Reread on every request. |

Run it anywhere ErsatzTV can reach and that can reach the internet. We run it as a small
deployment beside ErsatzTV, using ErsatzTV's own image (it already has `python3` and `ffmpeg`)
and reading `yt-dlp` from a shared volume. Keep it inside your network: only names in the
stream list and YouTube video ids are accepted, but it has no login.

Memory: allow about 150 MB per stream being pulled. A channel and its HD copy pull separately.

### Two things the relay does that matter

**Live sound stays in step.** YouTube sends a live stream's picture and sound as two separate
playlists in 5-second pieces. Joined naively, each starts on its own piece and their clocks are
dropped, so on about half of all pulls the sound runs exactly 5.0 seconds ahead of the picture.
The relay passes `-copyts` to the join, which keeps the original clocks.

**Films can be joined partway through.** A channel tuned in the middle of a film makes ErsatzTV
jump to that point. One long piped stream cannot jump: it is read from the start, and ErsatzTV
gives up after 30 seconds. YouTube's own playlist with separate picture and sound streams takes
20 to 30 seconds to jump under ErsatzTV's `+igndts` input option. So the relay serves a single
ordinary playlist and joins each picture segment with its sound segment when asked. A jump then
takes about 2 seconds anywhere in the film.

## A live channel

1. Add a line to the stream list: a short name and the stream's address. For YouTube use the
   channel's `/live` address, so it follows the broadcaster's current stream.
2. Put a stream file in the Remote Streams library folder. The file name is the guide title.

   ```yaml
   # NBC News NOW.yml
   url: "http://<relay>:8090/live/nbc-news-now"
   is_live: true
   duration: 24:00:00
   ```
3. Scan the library **while the stream is up**. ErsatzTV looks at the stream during the scan; if
   it is down, the item is stored empty and the channel fails until it is scanned again.
4. Make a smart collection for it: `type:remote_stream AND title:"NBC News NOW"`.
5. Build the channel as usual: a schedule with that one collection and no filler, a playout, the
   channel, and its HD copy.

The guide shows one all-day block with the channel's name. A live feed carries the broadcaster's
own advertising; your commercials cannot be inserted.

Some broadcasters end and restart their YouTube stream. If a channel keeps answering "not
currently live", look for the broadcaster's own site stream; `yt-dlp` supports many.

## A channel of films from a YouTube channel

`make-streams.py` turns a channel listing into stream files, in two steps so you can read and
edit the list in between.

```bash
yt-dlp --flat-playlist --print "%(id)s|%(duration)s|%(title)s" \
    https://www.youtube.com/@SomeChannel/videos > listing.txt

./make-streams.py list listing.txt films.tsv          # films an hour or longer, titles cleaned
# read films.tsv; set status to "skip" for anything unwanted, fix any title
./make-streams.py write films.tsv out/ --relay http://<relay>:8090
```

- `list` keeps videos between one hour and 2¼ hours, takes the film's name out of titles like
  `Hook sentence! | Ape vs Monster | Full Sci-Fi Movie`, and marks a film listed twice.
- `write` makes one `.yml` per kept row:

  ```yaml
  # Ape vs Monster.yml
  url: "http://<relay>:8090/vod/HKaLoC9Ms6U.m3u8"
  is_live: false
  duration: 01:28:07
  ```

Copy the files into a folder of their own inside the Remote Streams library (the folder name
becomes a tag), scan, and build the channel on `type:remote_stream AND tag:<folder>`.

The scan looks at every film once, a few seconds each. `asylum.tsv` is the list we air from
The Asylum Movie Channel.

**Commercials** go between films, not inside them: a streamed film has no break points. A
post-roll filler preset in *Pad* mode (to the next quarter hour) plus a fallback preset gives
films that start on :00, :15, :30 or :45 with a few minutes of ads between them.

## When it stops working

| Symptom | Cause | Fix |
|---|---|---|
| Every YouTube channel goes dark at once | YouTube changed something | Replace the `yt-dlp` file with the newest release. No restart needed. |
| One live channel shows the offline picture | The broadcaster moved or ended its stream | Update its address in the stream list. |
| One film fails | It was removed from YouTube | Mark it `skip` in the table, delete its `.yml`, scan. |
| *video input is required* on a new channel | The library was scanned while the stream was down | Touch the `.yml`, scan again, reset the playout. |

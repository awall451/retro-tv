# The channel tracker

A small web page next to the viewer for whoever looks after the channels: what is on each
channel, what in the library is on no channel at all, which channels people actually watch,
and a queue of changes to make ("move this film to channel 24", "a new Saturday-morning
channel with these shows"). Anyone at home can queue a change; whoever runs the server
applies it in ErsatzTV and marks it done.

Like the viewer it changes nothing on the server. It reads a snapshot of ErsatzTV's channels
and library that a script builds from ErsatzTV's database, and, if given the API key, asks
ErsatzTV which channels are running.

```
generator/make_snapshot.py ──PUT snapshot──► retro-tv-tracker container ◄── browser (the page)
  reads ErsatzTV's database read-only          ├─ /       the page               ▲
  (file, docker exec, kubectl exec, ssh)       ├─ /api/   snapshot, queue, stats │ watch beacons
                                               └─ polls ErsatzTV /api/sessions   │
                                                                              viewer (TRACKER_URL)
```

## Screens

| Tab | What |
|---|---|
| **Channels** | Every channel as a tile or a row: kind (shows, films, mixed), size in hours, how many episodes and films have chapter marks and can take an ad break, its schedule (smart collections and their queries, playback order, filler presets), and its watch time. A channel's page lists its shows and films. |
| **TV**, **Movies** | The whole library, with search, filters (channel, "not on any channel", genre, decade, resolution, chapters and ad breaks), sorting, and which channels each title is on. Select titles to queue a change. |
| **Popular** | The most watched channels (today, 7 days, 30 days) with a sparkline per channel, the busiest hours, the split by device, who is watching now, and the channels nobody watched in 30 days. |
| **Queue** | The pending changes, planned channels and free-text notes, and the done ones with what was done. |

The page has a light and a dark look and works on a phone. It loads no fonts or scripts from
elsewhere.

## Run it

Needs the viewer's `docker/` folder set up (`.env` with `ERSATZTV_URL`; see
[`../docker/README.md`](../docker/README.md)). In `docker/`:

```bash
docker compose --profile tracker up -d --build
```

Then open <http://localhost:8413>. It shows "no snapshot yet" until the generator has run
once (below).

Settings in `docker/.env` (all optional; see `.env.example`):

| Variable | Default | What |
|---|---|---|
| `TRACKER_PORT` | `8413` | where the page is published on this machine |
| `TRACKER_BIND` | `127.0.0.1` | where that port is open; `0.0.0.0` for every device on the network (no login), or put a proxy in front, as for the viewer |
| `TRACKER_TOKEN` | made at first start | the token for uploading snapshots and closing requests. Empty: a random one is written to the data volume; read it with `docker exec retro-tv-tracker cat /data/token` |
| `ERSATZTV_API_KEY` | empty | ErsatzTV's API key (`/config/api-secrets.json` on the server). With it and `ERSATZTV_URL`, the tracker polls ErsatzTV's running channels (below). Without, only the viewer's beacons count |
| `TRACKER_TZ` | `UTC` | the time zone for "today" and the hours chart, e.g. `America/New_York` |
| `TRACKER_URL` | empty | not the tracker's own setting: the viewer's. Where browsers reach the tracker, e.g. `http://<this-machine-ip>:8413`. Set, the viewer sends watch beacons |
| `TRACKER_ORIGINS` | empty | the addresses browsers open the viewer at, e.g. `http://<this-machine-ip>:8410`, separated by spaces or `;`. Beacons from any other page are refused. `http://localhost` and `http://127.0.0.1` on any port (the viewer on this machine, the Retro TV box) are always allowed |
| `TRACKER_DEVICES` | empty | names for devices, by the address the tracker sees: `<pi-ip>=Retro TV box;<laptop-ip>=Laptop` |
| `TRACKER_TV_LABEL` | empty | one name for every viewer in TV mode (`?tv`), when addresses do not tell devices apart (behind NAT or a proxy that hides them) |
| `TRACKER_TRUST_PROXY` | off | `1` when a reverse proxy sits in front: the address comes from its `X-Forwarded-For` |

Data lives in the Docker volume `retro-tv-tracker-data`: the snapshot, the queue, planned
channels, the watch statistics and the token. Every write goes to a temp file, is synced and
renamed. The container runs as uid 10001 with a read-only root filesystem and no capabilities.

Keep it on your own network or VPN, like the viewer. There is no login: anyone who can open the
page can queue and delete pending requests; only the token can upload a snapshot or close a
request.

## The snapshot generator

`generator/make_snapshot.py` builds the snapshot and uploads it. Run it again whenever the
channels change; it takes 10 to 30 seconds. Python 3.9 or newer, nothing to install. It runs
anywhere that can reach ErsatzTV's database:

```bash
# ErsatzTV in Docker on this machine
python3 tracker/generator/make_snapshot.py --access docker --container ersatztv

# ErsatzTV in Docker on another machine, over ssh (the docker group, or "sudo docker")
python3 tracker/generator/make_snapshot.py --ssh <server> --access docker --docker "sudo docker"

# ErsatzTV on Kubernetes (k3s): deploy/ersatztv in namespace ersatztv, as in docs/tv.html
python3 tracker/generator/make_snapshot.py --access kubectl --kubectl "k3s kubectl"

# The database file itself (on this machine, or on --ssh <server>)
python3 tracker/generator/make_snapshot.py --access file --db-path /path/to/config/ersatztv.sqlite3

# Build only, upload nothing
python3 tracker/generator/make_snapshot.py ... --no-upload --out /tmp/snapshot.json
```

Every option can also be set in the environment or in `~/.config/retro-tv-tracker/env`
(`KEY=value` lines; `--env-file` for another). Keep that file private (`chmod 600`): it holds
the token.

| Setting | Option | Default |
|---|---|---|
| `TRACKER_URL` | `--url` | the tracker, e.g. `http://localhost:8413` |
| `TRACKER_TOKEN` | | the tracker's token (above) |
| `ERSATZTV_URL` | `--etv-url` | ErsatzTV, `http://<server-ip>:8409`, for the cross-check against its API. Empty: skipped |
| `ERSATZTV_API_KEY` | | the API key; empty: read from `api-secrets.json` next to the database, if it can |
| `ETV_DB_ACCESS` | `--access` | `file`, `docker` or `kubectl` |
| `ETV_DB_PATH` | `--db-path` | `/config/ersatztv.sqlite3` (inside the container for docker and kubectl) |
| `ETV_SSH` | `--ssh` | empty; a host: run the access there (`ssh -o BatchMode=yes`) |
| `ETV_DOCKER`, `ETV_CONTAINER` | `--docker`, `--container` | `docker`, `ersatztv` |
| `ETV_KUBECTL`, `ETV_K8S_NAMESPACE`, `ETV_K8S_TARGET` | `--kubectl`, `--namespace`, `--target` | `kubectl`, `ersatztv`, `deploy/ersatztv` |

What it does:

1. **Copies the database without writing to it.** Where `python3` exists next to the
   database, a one-shot opens it read-only and takes a consistent copy with SQLite's backup
   API. Where it does not (ErsatzTV's image may have no Python), it reads the database and its
   write-ahead log with `cat`, checks the copy with SQLite's `quick_check` and reads again if a
   checkpoint got in between. Nothing is written in the container but SQLite's usual reader
   bookkeeping.
2. **Works out each channel's shows and films** the way ErsatzTV does: channel, playout,
   schedule items, smart collection, search query. The query is evaluated by a small evaluator
   for the common part of ErsatzTV's search syntax: `field:term`, `field:"phrase"`, `[a TO b]`
   ranges (open at either end with `*`: `release_date:[* TO 19891231]`), AND / OR / NOT / `+` / `-` and parentheses (read as Lucene's classic parser reads
   them: `a NOT b` is a without b, and `a OR b AND NOT c` is b without c). The fields and
   their matching follow ErsatzTV's search index (v26.11.6):
   - text, split on spaces and lowercased, nothing dropped: `title`, `genre`, `tag`, `studio`,
     `actor`, `director`, `writer`, `country`, `library_name`, and for episodes their show's
     `show_title`, `show_genre`, `show_tag`, `show_studio`, `show_network`. Punctuation stays
     on its word, so `title:it` finds "It", and `show_title:"Cowboy Bebop"` also matches
     "Cowboy Bebop (2021)", but `show_title:trek` does not find "Star Trek: Voyager" (its word
     is `trek:`), in ErsatzTV either;
   - `plot`: words, lowercased, English stop words dropped (Lucene's StandardAnalyzer);
   - exact, case and all: `type`, `state`, `content_rating`, `show_content_rating`,
     `release_date` (yyyymmdd), `tag_full`. So `content_rating:R` but not `content_rating:r`;
   - whole numbers: `season_number`, `episode_number`, `minutes`, `seconds`, `height`, `width`,
     `chapters`, from every version of a file (a film in 720p and 1080p matches either height).

   An episode's `genre`, `tag` and the rest are its own; its show's are the `show_*` fields
   (`type:episode AND genre:comedy` needs comedy episodes, `show_genre:comedy` a comedy show),
   and an episode has no `content_rating` of its own. A range on a text or exact field compares
   the words as text, its bounds lowercased, as Lucene does (`release_date:[1988 TO 1989]`
   takes all of 1988). A query with anything else (wildcards such as `trek*`, fields such as
   `language` or `video_codec`, `year` (ErsatzTV has no such field, so it matches nothing
   there), `network` (shows only), a clause of only stop words, a group of only NOT clauses,
   which matches nothing in Lucene) and schedule items that are not smart collections are not
   evaluated: that channel shows no members and a note saying why, as does a query the
   evaluator fails on. A query that filters
   on a field some of the items it could match never have (other videos, such as news tapes,
   usually have no genre and no date, so `genre:news` or a `release_date` range cannot match
   them, in ErsatzTV either) gets a note saying so, as does a query that matches nothing. An HD
   twin (Playout Source **Mirror**, no playout of its own) shows the members of the channel it
   mirrors, and the library lists both numbers on each of those titles.
3. **Checks the result** against the channel's current playout: every scheduled programme
   should be a member. The channel page shows the count that is not (`check.outsideMembers`),
   which flags a query the evaluator read differently from ErsatzTV.
4. **Counts chapters and ad breaks**: per episode and film, its chapter marks and how many
   would take a mid-roll break under `--break-rule` (default `240,180,300`, the shows' rule in
   [docs/tv.html](../docs/tv.html): `point > 240 and remaining_duration > 180 and
   last_mid_filler > 300`).
5. **Reads the channel list and version** from ErsatzTV's API (GET only), then PUTs the
   snapshot to the tracker.

Genres, ratings, directors and resolution come from ErsatzTV's own copy of the media server's
metadata; Plex, Jellyfin or Emby are not asked.

Optional: for channels whose query cannot be evaluated, `--lineup <file>` names their shows
by title, as `{"channels": [{"number": "24", "shows": ["Show title", "..."]}]}`; those
channels are then marked `membership: "lineup"`.

## The queue

Pick titles on the TV or Movies tab and queue **add** (to a channel), **remove** (from one),
**move** (between two) or a **note**. A target can be a planned channel, made on the Queue tab
with a name, an optional number and a kind. Each request stores the titles and their
ErsatzTV ids (`Show.Id`, `Movie.Id`), checked against the snapshot. A mirror (HD twin) has no
schedule of its own, so a request naming one is stored against the channel it mirrors (with
`"via"` keeping the number asked for), and the page's **From** starts at the source channel.

Whoever runs the server applies the requests in ErsatzTV (usually by changing a smart
collection's query and resetting the playout; see [docs/tv.html](../docs/tv.html)) and closes
them with the token:

```bash
T=http://localhost:8413
curl -s "$T/api/requests?format=text"                    # the queue as plain text
curl -s -X PATCH -H "X-Tracker-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"applied","result":"added to ch24, playout reset"}' "$T/api/requests/5"
```

Then run the generator again so the page shows the new lineup. The plain-text export is meant
to be read by a person, a script or an AI assistant that does the applying.

## Watch statistics

Two sources, neither perfect:

1. **Beacons from the viewer.** With `TRACKER_URL` set in the viewer's `.env`, each browser
   says which channel it is playing: once a tune settles, every minute and on leaving (see
   [Watch beacons](../docker/README.md#watch-beacons)). This counts per device.
2. **ErsatzTV's running channels.** With `ERSATZTV_API_KEY` set, a thread reads ErsatzTV's
   `GET /api/sessions` every 30 seconds. A session is one running channel, shared by everyone
   watching it, with when it started and when a client last fetched from it. It says nothing
   about who: every player that plays ErsatzTV directly (the Roku app, Kodi, VLC) counts as
   one device, **direct**.

How they are combined, per channel:

- A beacon claims its channel from 30 s before its first to 60 s after its last heartbeat.
  ErsatzTV's time inside a claim is dropped, so a browser is never counted twice.
- Channels a beacon reports as warming up (fast flipping) are claimed for a moment and count
  for nobody. ErsatzTV sessions shorter than 20 s are dropped (probes, flips).
- What is left of ErsatzTV's time counts once, as **direct**. A Roku on the same channel as a
  browser at the same time is not counted.
- Heartbeats from one browser less than 150 s apart join into one stretch. Two devices with
  the same name on one channel at once count once.
- HD twins (group `HD`, number + 100; `TRACKER_HD_OFFSET` for another offset) count toward
  their channel, with the HD share kept.
- **Unattended time.** A viewer that sends `idle` (seconds since the last key press) and
  `idleAfter` (its sleep timer) in its beacons gets the minutes past that point kept apart as
  unattended: not watch time, not in the rankings. The viewer in this repo sends these while
  its sleep timer is on; the tracker works without them (`TRACKER_IDLE_MIN`, default 90 minutes, is the
  threshold when only `idle` is sent).

Limits: a channel left playing to an empty room counts as watched; a direct player is only
seen while ErsatzTV is fetched from; a browser tab that is closed without a goodbye (a crash,
a pulled plug) keeps counting until its last heartbeat plus a minute.

**What is kept.** Per beacon: channel, device name, HD or not, start and end. Not stored: IP
addresses, the browser's random id (kept in memory only, hashed, to join heartbeats),
programme titles. Raw stretches are kept 14 days (`watch-events.json`), daily totals per
channel, device and hour 400 days (`watch-daily.json`).

**Beacon checks.** Only from `TRACKER_ORIGINS` and localhost; at most 2 KB; `text/plain` or
`application/json` (plain text needs no CORS preflight); the channel must be in the snapshot;
at most 20 a minute per browser, 60 per address and 600 in all. A beacon can only add watch
time.

## Known limits

- The query evaluator assumes ErsatzTV's default operator is OR (Lucene's default, and
  ErsatzTV's); a query read with AND as the default would resolve differently.
- The evaluator mirrors ErsatzTV v26.11.6's search index (fields, analyzers, item types). A
  query that relies on something it does not model (shows as items, the `collection`, language
  and codec fields, ...) gets a note instead of members. The plot analyzer is an approximation
  of Lucene's StandardAnalyzer (word boundaries differ on some punctuation). The playout check
  (`check.outsideMembers`) shows any difference.
- Where the database is read without Python next to it (the `cat` fallback), the copy of the
  database and its write-ahead log can be inconsistent if a checkpoint lands between the two
  reads, and `quick_check` does not always catch it. A follow-up will stream a proper backup
  instead.
- The ErsatzTV API key (`X-Etv-Api-Key`) and the tracker token (`X-Tracker-Token`) travel in
  clear over `http://` URLs. The tracker is meant for a trusted home network; beyond that, put
  ErsatzTV and the tracker behind https (a TLS proxy) or a VPN. A URL given as `https://` is
  used as https.
- A new channel gets no watch time from the viewer until the snapshot is generated again: its
  beacons are refused (ErsatzTV's own sessions still count, as **direct**), and its HD twin is
  not recognised.
- History is kept by channel number. Renumbering channels in ErsatzTV leaves their past
  minutes under the old numbers until they are moved (below).

## Renumbering channels

`tools/renumber.py` moves stored watch time (`watch-events.json`, `watch-daily.json`) to new
channel numbers. It is in the image as `/app/renumber.py`. Stop the tracker first (it keeps
the recent history in memory and would write the old numbers back), look at the dry run, then
apply:

```bash
cd docker
docker compose --profile tracker stop tracker
docker compose --profile tracker run --rm --no-deps tracker python3 -I /app/renumber.py 24=124 25=125
docker compose --profile tracker run --rm --no-deps tracker python3 -I /app/renumber.py 24=124 25=125 --apply
docker compose --profile tracker start tracker
```

Pairs are `OLD=NEW`, or a range `LO-HI=+N` (`101-199=+900`); all apply at once, so `1=2 2=1`
swaps. Channels moved onto one number have their minutes added up. `--apply` first copies each
file it changes to `<file>.bak-<time>` in the data folder (a new name, `-2`, `-3`, ... if one
is taken: a backup is never overwritten), and changes both files or neither. Without Docker:
`python3 tools/renumber.py --data-dir <folder> ...`.

HD twins are counted under their channel's own number, so moving the twins (from number + 100
to + 1000, say) moves no history: set `TRACKER_HD_OFFSET=1000` (or `100,1000` while both
exist) and regenerate the snapshot. The dry run shows whether anything was kept under a twin's
own number (from before the snapshot listed it); `124=24` folds such minutes into channel 24.

## API

| Method | Path | Token | What |
|---|---|---|---|
| GET | `/healthz` | | `{"ok": true}` when the data folder is writable |
| GET | `/api/snapshot` | | the current snapshot (gzip, ETag) |
| PUT | `/api/snapshot` | yes | replace the snapshot |
| GET | `/api/requests` | | all requests; `?status=pending`; `?format=text` |
| POST | `/api/requests` | | queue a request |
| GET | `/api/requests/{id}` | | one request |
| PATCH | `/api/requests/{id}` | for status and result | `{"status": "applied"\|"rejected", "result": "..."}`; editing the note of a pending request needs none |
| DELETE | `/api/requests/{id}` | unless pending | delete a request |
| GET, POST | `/api/planned` | | planned channels: `{"name", "number"?, "kind"?: shows\|movies\|mixed, "note"?}` |
| DELETE | `/api/planned/{id}` | | delete one (refused while a pending request targets it) |
| GET | `/api/meta` | | version, snapshot time, pending count |
| GET | `/api/watch?days=30` | | watch seconds per day and channel, who is on now, poller state |
| POST | `/api/watch/beacon` | | a viewer's beacon (CORS) |

The token goes in the header `X-Tracker-Token`. POST, PUT and PATCH need
`Content-Type: application/json`. A request:

```json
{"action": "move", "items": [{"type": "movie", "id": 89}], "from": "201", "channel": "24", "note": "why"}
```

`action` is `add` (needs `channel`), `remove` (needs `from`), `move` (both) or `note` (text
and/or items, optional `channel`). A channel is a number (`"24"`) or a planned channel
(`{"planned": 1}`).

## Without Docker

```bash
cd tracker
python3 -m unittest discover -s tests                   # the tests, about 3 s
DATA_DIR=/tmp/tracker-data PORT=8413 python3 app/server.py
```

## Files

```
tracker/
├── Dockerfile            pinned Python (Alpine), no packages but tzdata
├── app/server.py         the API, the poller and the static files (standard library only)
├── app/static/           the page: plain HTML, CSS and JavaScript, no build step
├── generator/make_snapshot.py   builds and uploads the snapshot
├── tools/renumber.py     moves watch history to new channel numbers
└── tests/                API and counting rules (against a fake ErsatzTV), generator
```

## Troubleshooting

| Seen | Cause and fix |
|---|---|
| "no snapshot yet: run the generator" | Run `generator/make_snapshot.py` (above). |
| Upload fails with 403 | Wrong token. `docker exec retro-tv-tracker cat /data/token`, or set `TRACKER_TOKEN`. |
| Popular stays empty although people watch | No beacons and no poller. Check `TRACKER_URL` in the viewer's `.env` (`curl <viewer>/config.json` shows a `tracker` key; the viewer's log says why when it skipped one), `TRACKER_ORIGINS` (the browser's console shows a CORS error otherwise), and `poller.lastError` in `curl <tracker>/api/watch`. |
| Beacons refused from an `https://` viewer | The tracker must be `https://` too (browsers block plain-HTTP requests from a secure page): put it behind the same proxy. |
| Every device is "browser (desktop)" | Fine: names come from `TRACKER_DEVICES`. Behind a proxy, also set `TRACKER_TRUST_PROXY=1`. |
| A channel shows no members and a note | Its query uses search syntax the generator does not evaluate (see above). |

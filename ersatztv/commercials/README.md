# Commercials for retro channels

The commercials, trailers and bumpers that play between programmes on our ErsatzTV channels:
**1,838 clips in 24 sets, plus two small news sets, all from the Internet Archive**, with a record of where every clip came
from, how it was cut, and what we threw out and why. `build.py` rebuilds any set on your machine
from that record.

This folder holds **no video**. It lists public Internet Archive addresses; `build.py` downloads
from there. Who owns the rights to old commercials is often unclear: the Archive hosts them, we
link to them, and what you do with them is up to you.

## The sets

| Set | Clips | What | Source on the Archive |
|---|---|---|---|
| `80s` | 122 | Late-80s / early-90s ads and station bumpers from Cleveland TV (WUAB 43, WEWS 5) | `commercialpack1` |
| `90s` | 118 | 90s ads, about 30 s each | `Collectionof90sCommercials` |
| `toonami` | 123 | Toonami show intros and promos (the promo reels split into single promos) | `Toonami-Bumpers`, `toonami-promos` |
| `christmas` | 21 | Christmas ads, 70s to 90s, 14 s to 4 min | `yt-PL059E38785A0BB5F6` |
| `reels8486` | 197 | US TV ads recorded off air, October 1984 to December 1986, cut into single ads | 12 items `October1984Commercials` … `December91986Commercials` |
| `games80s` | 92 | Video game and home computer ads, 1977–1989 (Atari, Activision, Coleco, Commodore, IBM, NES) | collection `computercommercials`, `640x480_videogame_commercials` |
| `trailers80s` | 44 | Trailers for 1982–86 films | collection `movie_trailers` |
| `horror` | 54 | Classic horror trailers, 1920–1970 | collection `movie_trailers` |
| `romcom` | 22 | Romantic comedy trailers, 1984–2012 | collection `movie_trailers` |
| `fifties` | 153 | 1950s TV ads (cigarettes, beer, detergent, gasoline, toothpaste…), cut into single ads | `misc1950s-*`, Prelinger `ClassicT1948` I–VIII, `Televisi1960` |
| `ads2000s` | 28 | 2000s ads, cut into single ads | `2000sCommercials`, `a-bunch-of-2000s-commercials-720p` |
| `starwars` | 146 | Kenner toy ads 1978–85, Micro Machines, 1977–83 tie-ins, 1997–99 Pepsi / Taco Bell / Episode I spots | single `youtube-*` items, `star-wars-kenner-toy-commercials-trailers-and-more` |
| `marvel` | 42 | Spider-Man 2 TV spots and tie-ins (2004), Marvel Transformers comic ads, a 1981 Marvel Comics ad, Spider-Man toy and game ads | `spider-man-2-commercials`, `transformers-marvel-comics-commercials-upscaled-60fps`, single items |
| `cars` | 25 | Car ads: 1950s–60s classics, 80s Toyota and Chevrolet, 2000s European ads | `Classic_Car_Commercials_From_The_50s_and_60s_1993_Moon_River_Tape`, `top-10-car-commercials`, single items |
| `scifi` | 110 | SCI FI Channel breaks 1996–2005: promos, "IF" idents, Sci Fi Friday, and the ads that ran with them | `capture-a-*` "Sci-Fi Channel commercials", `sci-fi-channel-i-am-sci-fi-promos`, `sci-fi-channel-idents-and-bumpers-compiliation` |
| `discovery` | 41 | Discovery Channel promos (1999), History Channel promos (1999, 2003), a Mail Call promo (2002) | `1999DiscoveryChannelPromos` (1, 2), `February1999HistoryChannelPromos`, `22January2003HistoryChannelPromos`, `history-channel-mail-call-promo-usa-2002` |
| `comedycentral` | 148 | Comedy Central breaks 1995–2002: promos (The Man Show, TV Funhouse, The Daily Show, Crank Yankers) and period ads; 2004 promos | `capture-a-*` "Comedy Central commercials", `2000-comedy-cntrl`, `comedy-central-commercials-july-5-2002`, `MNN-002_*` |
| `wb` | 132 | WB network breaks 1998–2002: Charmed and Dawson's Creek promos, Michigan J. Frog, period ads | `Commercials_The_WB_WBNE_New_Haven_Connecticut_1998`, `capture-a-*` "WB commercials" |
| `drivein` | 14 | Drive-in snack bar ads and intermission reels | `SnackBar*` items, `Drive-inSnackBarAd`, `1953_Movie_Trailers_Intermission_*`, `Commercials39` |
| `sixties` | 13 | Early-1960s daytime ads (Ivory Snow, Dash, Carnation, Camay) | `Early1960sDaytimeCommercials` |
| `seventies` | 36 | Early-1970s ads | `0649_Early_1970s_Television_Commercials_*`, `usa-vintage-commercials`, `abcearly1970scommercials` |
| `ads2010s` | 6 | Late-2000s / early-2010s ads | `jingles-from-your-childhood-2000s2010s-nostalgic-commercials-parts-1-and-2` |
| `apple` | 102 | Apple ads: 1984, iMac colours, iPod silhouettes, Get a Mac (US and UK), iPhone 4 and iCloud | `AppleAds`, `apple_getamac`, `apple_ipoditunes`, `apple-1984`, `apple-colors`, single items |
| `travel` | 49 | Travel Channel breaks (2005, 2007) and 1958–65 airline ads (Eastern, Northwest Orient) | `capture-a-537`, `capture-a-557`, `EasternAirlines1965` (+ ads 2–4), `northwestorient1958` |
| `cnn` (news) | 12 | CNN's launch day (1 June 1980, four parts) and CNN Headline News recordings, 1985–1997, whole tapes | `CNN_pt._1_6-1-1980` … `pt._4`, `headline-news-*`, `capture-a-*` "CNN Headline News" |
| `newsreels` (news) | 31 | Universal Newsreel stories, 1933–1964: flights, rockets, sport, ceremonies (nothing on wars or disasters) | collection `universal_newsreels` |

`python3 build.py OUT --list` prints the same with download sizes. The full build downloads
about 20 GB and keeps about 13 GB.

What we pair them with: 80s shows get `80s`, 90s shows `90s`; Stranger Things gets
`reels8486` + `games80s` + `trailers80s`; horror films get `horror` + `fifties`; black-and-white
classics and The Twilight Zone get `fifties`; romantic comedies get `romcom` + `ads2000s` + `90s`;
Star Wars films get `starwars` + `90s`.
The sets added on 2026-11-08 go with channels of the same name (MCU films get `marvel`, Fast & Furious
`cars`, a Sci-Fi channel `scifi`, and so on); `sixties` and `fifties` go between drama episodes,
`seventies` with 70s crime films and drive-in movies.

**Quality bar for the 2026-11-08 sets.** Ordinary soft VHS stays. Thrown out: burned-in watermarks
and running timecode (two Periscope Film uploads, 97 pieces), VHS tracking noise over the whole
picture, VCR on-screen displays, black or title-card pieces, pieces over about two minutes, and
software demo videos that never aired. Two sources were mislabelled (one "2000s/2010s ads" item is
Steamboat Willie).

## Rebuilding a set

Needs Python 3.8 or newer, `curl`, and `ffmpeg` / `ffprobe`. Nothing to install from pip.

```bash
python3 build.py ~/commercials --list              # what there is
python3 build.py ~/commercials fifties starwars    # build two sets
python3 build.py ~/commercials                     # build everything
```

You get one folder per set (`~/commercials/fifties/` …) ready for ErsatzTV, plus
`_downloads/` (the originals, which you can delete afterwards) and `_rejected/` (what we threw
out, with `REASONS.tsv` saying why). It is safe to stop and run again: finished downloads and
clips are kept, and a part-finished download resumes.

## The catalog

Two tab-separated files, readable in any spreadsheet:

**`sources.tsv`**: one row per file downloaded (680).

| Column | Meaning |
|---|---|
| `set` | which set it belongs to (also the folder name) |
| `file` | the name it is saved under |
| `url` | the Internet Archive download address |
| `md5`, `bytes` | the Archive's checksum and size, to check the download |
| `process` | `copy`, `fit`, `split`, or `toonami` / `christmas` (a clean-up script in `fixes/`) |
| `status` | `on air`; `on air: N clips` for a reel; `rejected`; `replaced or parked by its clean-up script`; `not used`; `not kept` (a duplicate) |
| `reason` | why it was rejected |
| `archive_title` | the Archive item's title |

**`clips.tsv`**: one row per clip that came out (1,120 on air, 90 rejected).

| Column | Meaning |
|---|---|
| `set`, `clip` | set and clip file name; a piece cut from a reel is named `<reel>_<piece number>_<seconds>s.mp4` |
| `from` | the downloaded file it came from (`sources.tsv`, column `file`) |
| `status` | `on air` or `rejected` |
| `reason` | why it was rejected |
| `label` | what the ad is, where we wrote it down. Read off one frame, so it names the brand or the toy only where it was legible; most pieces have no label yet |

## How the sets were made, and how to make your own

1. **Find sources.** Search the Internet Archive for `commercials 1985`, `TV spots`, a brand or a
   toy line. Two kinds are useful: **single clips** (one ad per file) and **reels** (an hour of
   ads recorded off air, back to back). Reels give the most authentic mix but must be cut up.
   Prefer files at 640x480 or better; 4:3 originals look best on a CRT. Watch for "featurette"
   items in the trailer collections: many are the Trailers From Hell versions, a director talking
   over the trailer.
2. **Download** and check the md5 (the Archive lists one for every file at
   `https://archive.org/metadata/<item>`).
3. **Cut and shape.** `split` cuts a reel in the middle of every black gap (ffmpeg `blackdetect`)
   and drops pieces under 8 seconds (station bumpers, fragments). Pieces over about 130 s are
   usually two or more ads with no black between them; we rejected those. `fit` crops a 4:3
   picture that sits inside a wide frame, so it does not air with bars on all four sides. Clips
   that are really widescreen are left alone and air letterboxed.
4. **Look at every clip.** `python3 build.py sheet ~/commercials/fifties fifties.jpg` makes a
   contact sheet (one frame per clip, eight across) and a `.txt` with the names in the same order.
   We rejected: commentary versions, an interview filed as a trailer, trailers with nudity,
   games from 1990 on in an 80s set, a 1950s ad that looked like a racial caricature, slate
   cards, and fragments. Everything is in `clips.tsv` and `sources.tsv` with its reason.
5. **Record it.** Add your sources to `sources.tsv` and your rejects to `clips.tsv`, so the
   next person gets your review work too.

Bigger hand-made fixes live in `fixes/`: `fix-toonami.py` splits the Toonami promo reels at cut
points checked by eye and repairs 24 clips whose 4:3 picture was boxed or stretched;
`fix-christmas.py` crops one boxed ad, trims an uploader's title cards and a film countdown off
two others, and drops a postage-stamp-sized copy and a widescreen duplicate. `build.py` runs them for you.

## Loading them into ErsatzTV

1. Put the set folders under one folder and add it to ErsatzTV as a local library of type
   **Other Videos**. ErsatzTV turns each sub-folder name into a **tag**, so a clip in `fifties/`
   gets the tag `fifties`.
2. Make a **smart collection** per mix, for example
   `type:other_video AND (tag:horror OR tag:fifties) AND NOT state:FileNotFound`.
   `NOT state:FileNotFound` keeps a clip off the air once you move it out of the folder (ErsatzTV
   keeps such items in collections until the trash is emptied).
3. Make **filler presets** on that collection and attach them to a schedule. What we use, and
   why, is in [`../README.md`](../README.md), "Commercials in the schedule".
4. After adding clips: scan the library, wait for the scan to finish, then reset the channel's
   playout. A reset that runs before the scan has finished does not see the new clips.

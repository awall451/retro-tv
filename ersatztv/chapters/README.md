# Chapter marks: where the commercial breaks go

ErsatzTV can only cut to commercials at a **chapter mark**. An episode whose file has no
chapters gets all of its ad time in one block at the end: about 8 minutes after a 22-minute
cartoon, 17 after a 43-minute drama. An episode with chapters gets the same time as three or
four short breaks, like the broadcast it came from.

Shows made for commercial TV fade to black and go silent where the ads were.
[`add-chapters.py`](add-chapters.py) finds those moments and writes them into the files as
chapters. It never re-encodes, and without `--write` it changes nothing.

It runs **where the files are** (the Plex server), not on the ErsatzTV machine: finding the
breaks means reading every episode once.

## Needs

Python 3.8 or newer, `ffmpeg` and `ffprobe`. `mkvpropedit` (package `mkvtoolnix`) is strongly
recommended: with it an MKV is edited in place in under a second; without it every file is
copied once.

## Use

```bash
# 1. Report only. Nothing is changed. Read chapters-report.tsv afterwards.
./add-chapters.py "/path/to/Show Name"

# 2. Check a few episodes by eye: open one at the times in the report. Each should be a fade
#    to black between scenes, not the middle of one.

# 3. Write them.
./add-chapters.py --write --jobs 4 "/path/to/Show Name"
```

| File type | What `--write` does |
|---|---|
| MKV, with `mkvpropedit` | Edits the chapter list in place. The file is otherwise untouched |
| MKV without it, MP4, M4V, MOV | Copies every stream into a new file with the chapters, checks the copy (same streams, same length, chapters present), then swaps it in. `--keep-original` leaves the old file beside it as `.orig` |
| AVI, OGM and others | Cannot hold chapters. Reported and left alone, unless `--convert-to-mkv`: then the streams are copied into an `.mkv` with the chapters and the old file is removed (kept with `--keep-original`). The file name changes, so the media server sees a new file |

A file that already has usable chapters is skipped. Chapters that lie past the end of the file
(seen in some rips) count as damage and are replaced. An episode where no break qualifies is
left as it is. Run it again any time: finished files are skipped.

## What counts as a break

The picture is black for at least a quarter of a second **while** the sound is silent; at
least 4 min 10 s into the episode and 3 min 20 s before its end; breaks at least 5 min 30 s
apart; at most one per 8 minutes of running time (two in a half-hour show, five in an hour
one). The longest black-and-silent moments win. The limits match this project's mid-roll
presets (`point > 240 and remaining_duration > 180 and last_mid_filler > 300`, see the
[main guide](../README.md)) with a margin, so a chapter the script writes is one ErsatzTV will
use. Every limit is an option (`--help`).

**It suits shows made for commercial television.** Streaming originals and BBC-style
documentaries have no ad breaks; there the script finds nothing, or finds an ordinary fade
between scenes. Look at the report before writing those, or leave them out.

## Afterwards

1. The media server has to notice the chapters. In Plex: the show's **⋯ → Analyze** (or
   "Refresh Metadata"); chapters then appear in the episode's info.
2. In ErsatzTV: scan the library again, check with `../check-chapters.py "Show Name"` that
   no episode would be dropped, then reset the playouts of the channels that carry the show.

## Tested

On generated test episodes (MKV, MP4 and AVI, with real break points and with decoys: black
without silence, silence without black, breaks too early and too late, chapters past the end
of the file). The in-place `mkvpropedit` path follows its documented chapter format and was
not run here. The thresholds are the usual ones for broadcast fades; a show with dark scenes
and quiet moments may need `--black 0.5`, and one with music over its fades `--ignore-sound`.

"""Clean up the Toonami filler folder after build.py has filled it.

build.py runs this (see ../README.md, "Toonami"). It does
three things to <out>/toonami and never removes a file:

1. Re-encodes clips whose picture is the wrong shape for a 4:3 TV into
   640x480 copies named *_43.mp4:
   - CROP: a 4:3 picture boxed inside a 16:9 frame (bars left and right,
     which become bars on all four sides on a CRT).
   - SQZ: a 4:3 picture stretched to 16:9, squeezed back.
2. Splits the "..._Promos.mp4" reels (several promos for one show glued
   end to end, 45-200 s each) into one file per promo, so a break no longer
   plays the same show's promo three or four times in a row. Cut points
   are where a black frame and silence coincide, found with ffmpeg
   blackdetect / silencedetect and checked by eye.
3. Moves the originals it replaced to <out>/_rejected/toonami, plus
   one exact duplicate, one content-warning card that is not an ad, and
   two near-identical 15 s Batman variants (to .../toonami-extra).

Indexes are positions in the sorted listing of the 92 files that
build.py downloads. Safe to re-run only on a freshly fetched folder.
"""
import os
import re
import subprocess

OUT = os.environ.get("KIT_OUT", ".")  # build.py sets this to its output folder
SRC = os.path.join(OUT, "toonami")
STAGE = os.path.join(OUT, "_staging", "toonami")
PARK = os.path.join(OUT, "_rejected", "toonami")
EXTRA = os.path.join(OUT, "_rejected", "toonami-extra")

CROP = "crop=960:720:160:0,scale=640:480,setsar=1"
SQZ = "scale=640:480,setsar=1"
# Reels with grey side bars and a watermark in the right-hand bar.
BOX = "crop=960:720:159:0,scale=640:480,setsar=1"
# One reel segment is a 4:3 picture boxed inside the 720x480 frame.
BOX480 = "crop=640:480:40:0,setsar=1"

WHOLE = {i: CROP for i in (7, 8, 14, 28, 29, 31, 42, 52, 53, 59, 66, 67, 68)}
WHOLE.update({i: SQZ for i in (15, 16, 17, 18, 20, 58, 61, 62, 63, 90, 91)})

# index: [(filter, start s, end s), ...]
REELS = {
    73: [(SQZ, 0.13, 89.96), (SQZ, 90.39, 150.08), (SQZ, 150.78, 165.23)],
    74: [(SQZ, 0.0, 89.89), (SQZ, 90.56, 120.32), (SQZ, 121.25, 136.2)],
    75: [(BOX, 0.17, 59.53), (BOX, 60.2, 89.43), (BOX, 90.3, 104.77),
         (BOX, 105.13, 119.67), (BOX, 120.37, 134.9)],
    76: [(SQZ, 1.17, 29.7), (SQZ, 30.87, 99.4), (SQZ, 105.06, 130.34),
         (SQZ, 131.21, 151.3), (BOX480, 153.94, 181.97)],
    77: [(BOX, 0.27, 30.0), (BOX, 30.47, 45.13)],
    78: [(SQZ, 0.23, 59.97), (SQZ, 60.53, 90.23), (SQZ, 90.6, 105.47)],
    79: [(SQZ, 0.0, 89.94), (SQZ, 90.64, 150.3), (SQZ, 150.83, 164.25),
         (SQZ, 164.59, 180.65)],
    80: [(SQZ, 0.1, 59.69), (SQZ, 60.26, 89.96), (SQZ, 90.52, 104.8)],
    81: [(SQZ, 0.0, 13.07), (SQZ, 16.23, 135.83), (SQZ, 137.33, 166.27)],
    82: [(SQZ, 0.2, 29.13), (SQZ, 30.3, 89.29), (SQZ, 89.89, 118.92),
         (SQZ, 119.45, 149.15), (SQZ, 149.52, 163.76), (SQZ, 164.3, 194.06)],
    83: [(SQZ, 0.0, 59.83), (SQZ, 60.33, 89.88), (SQZ, 90.5, 104.58)],
    84: [(SQZ, 0.0, 59.88), (SQZ, 60.31, 90.28)],
    85: [(SQZ, 0.0, 59.77), (SQZ, 60.52, 90.4)],
    86: [(SQZ, 0.13, 59.43), (SQZ, 59.99, 89.69), (SQZ, 90.26, 104.84)],
    87: [(SQZ, 0.2, 119.82), (SQZ, 120.45, 149.88), (SQZ, 150.25, 164.7)],
}

# Parked without a replacement.
PARK_ONLY = [
    # Same two-minute promo as the first segment of the Tenchi reel.
    "Tenchi_Muyo-Toonami_-_Tenchi_Muyo_2_Minute_Promo_1080p_HD_.mp4",
    # A content-warning card with a crisis hotline, not a bumper.
    "Paranoia_Agent_Intro-Toonami_-_Paranoia_Agent-_Happy_Family_Planning_Disclaimers.mp4",
]
# Same 15 s spot as Promo-Batman-03 with a different end card.
HELD_BACK = ["Promo-Batman-04_15s.mp4", "Promo-Batman-05_15s.mp4"]


def encode(src, vf, dst, start=None, end=None):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", "%.3f" % start, "-to", "%.3f" % end]
    cmd += ["-i", src, "-vf", vf, "-r", "30000/1001",
            "-c:v", "libx264", "-crf", "17", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-ar", "48000", "-ac", "2", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)


def main():
    files = sorted(os.listdir(SRC))
    if len(files) != 92:
        raise SystemExit("expected the 92 fetched files, found %d" % len(files))
    for d in (STAGE, PARK, EXTRA):
        os.makedirs(d, exist_ok=True)

    replaced = []
    for i, vf in sorted(WHOLE.items()):
        name = files[i - 1]
        encode(os.path.join(SRC, name), vf,
               os.path.join(STAGE, os.path.splitext(name)[0] + "_43.mp4"))
        replaced.append(name)
    for i, segments in sorted(REELS.items()):
        name = files[i - 1]
        show = re.sub(r"^Toonami_(-_)?|_Promos\.mp4$", "", name)
        for n, (vf, start, end) in enumerate(segments, 1):
            out = "Promo-%s-%02d_%ds.mp4" % (show, n, round(end - start))
            encode(os.path.join(SRC, name), vf, os.path.join(STAGE, out),
                   start, end)
        replaced.append(name)

    # Only after every encode has succeeded: park originals, bring in copies.
    for name in replaced + PARK_ONLY:
        os.rename(os.path.join(SRC, name), os.path.join(PARK, name))
    for name in HELD_BACK:
        os.rename(os.path.join(STAGE, name), os.path.join(EXTRA, name))
    for name in sorted(os.listdir(STAGE)):
        os.rename(os.path.join(STAGE, name), os.path.join(SRC, name))
    print("library now holds", len(os.listdir(SRC)), "clips")


if __name__ == "__main__":
    main()

"""Clean up the Christmas filler folder after the clips have been fetched.

build.py runs this once <out>/christmas holds the 23
files listed in sources.tsv. It never removes a file: what it replaces or drops is
moved to <out>/_rejected/christmas, outside the library.

- Cap'n Crunch: a 4:3 picture boxed inside a 3:2 frame, cropped to the
  picture.
- Coca-Cola "Classic Christmas 90's": the uploader's intro and outro
  cards are trimmed off.
- McDonald's 1975: the film leader (countdown) is trimmed off.
- Parked without a replacement: a 160x120 Coca-Cola Santa spot (too
  small to watch) and a 30 s widescreen copy of the Budweiser ad that is
  already here in 4:3.

The 54-minute "Retro Christmas Toy Commercials" reel is listed in
sources.tsv as "not used" and build.py does not fetch it: it is
black-and-white toy advertising from the 1950s and 60s with nothing
Christmas on screen.
"""
import os
import subprocess

OUT = os.environ.get("KIT_OUT", ".")  # build.py sets this to its output folder
SRC = os.path.join(OUT, "christmas")
STAGE = os.path.join(OUT, "_staging", "christmas")
PARK = os.path.join(OUT, "_rejected", "christmas")

# name: (video filter or None, start s, end s, output name)
JOBS = {
    "Cap_n_Crunch_Christmas_Crunch_Cereal_1997_Commercial.mkv":
        ("crop=426:326:54:24,scale=640:480,setsar=1", None, None,
         "Cap_n_Crunch_Christmas_Crunch_Cereal_1997_Commercial_43.mp4"),
    "Coca_Cola_Classic_Christmas_90_s_TVC.mkv":
        ("fade=in:st=0:d=0.5,fade=out:st=56.0:d=0.5", 10.8, 67.3,
         "Coca_Cola_Classic_Christmas_90_s_TVC_trim.mp4"),
    "McDonalds_Merry_Christmas_World_1975.mkv":
        (None, 12.45, 72.47, "McDonalds_Merry_Christmas_World_1975_trim.mp4"),
}
PARK_ONLY = [
    "Coca_Cola_Christmas_Commercial_old.mkv",
    "Retro_Budweiser_Christmas_Commercial.mkv",
]


def encode(src, vf, start, end, dst):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", "%.3f" % start, "-to", "%.3f" % end]
    cmd += ["-i", src]
    if vf:
        cmd += ["-vf", vf]
    if start is not None:
        cmd += ["-af", "afade=in:st=0:d=0.3"]
    cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-ar", "48000", "-ac", "2", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)


def main():
    for d in (STAGE, PARK):
        os.makedirs(d, exist_ok=True)
    for name, (vf, start, end, out) in JOBS.items():
        encode(os.path.join(SRC, name), vf, start, end, os.path.join(STAGE, out))
    # Only after every encode has succeeded: park originals, bring in copies.
    for name in list(JOBS) + PARK_ONLY:
        os.rename(os.path.join(SRC, name), os.path.join(PARK, name))
    for name in sorted(os.listdir(STAGE)):
        os.rename(os.path.join(STAGE, name), os.path.join(SRC, name))
    print("library now holds", len(os.listdir(SRC)), "clips")


if __name__ == "__main__":
    main()

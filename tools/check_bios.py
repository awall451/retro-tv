"""Check BIOS files against Batocera's own checksum list.

Usage: python3 check_bios.py <folder>
Each file in <folder> (top level only) is matched by MD5 against
/usr/share/batocera/datainit/bios/readme.txt and reported as:
  GOOD      matches a known-good dump; shows where Batocera expects it
  MISMATCH  the name is one Batocera uses, but the contents are a different dump
  UNKNOWN   not a file Batocera looks for
"""
import hashlib
import os
import re
import sys

README = "/usr/share/batocera/datainit/bios/readme.txt"


def load_list():
    by_md5, by_name, system = {}, {}, None
    for raw in open(README, errors="replace").read().splitlines():
        line = raw.strip()
        m = re.match(r"^([0-9a-f]{32})?\s*(bios/\S.*)$", line)
        if m:
            md5, path = m.group(1), m.group(2).strip()
            by_name.setdefault(os.path.basename(path).lower(), []).append((md5, path, system))
            if md5:
                by_md5.setdefault(md5, []).append((path, system))
        elif line.endswith(":"):
            system = line[:-1]
    return by_md5, by_name


def main():
    folder = sys.argv[1]
    by_md5, by_name = load_list()
    for f in sorted(os.listdir(folder)):
        full = os.path.join(folder, f)
        if not os.path.isfile(full):
            continue
        md5 = hashlib.md5(open(full, "rb").read()).hexdigest()
        if md5 in by_md5:
            paths = sorted({p for p, _ in by_md5[md5]})
            print(f"GOOD      {f:22} -> {', '.join(paths)}  [{by_md5[md5][0][1]}]")
        elif f.lower() in by_name:
            exp = by_name[f.lower()]
            wanted = [e[0] for e in exp if e[0]]
            print(f"MISMATCH  {f:22} md5 {md5}; expected {wanted or 'no md5 listed'} for {exp[0][1]}  [{exp[0][2]}]")
        else:
            print(f"UNKNOWN   {f:22} md5 {md5}")


if __name__ == "__main__":
    main()

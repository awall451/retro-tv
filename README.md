# retro-tv

A 90s living room on a Raspberry Pi 4 and a Sony Trinitron: retro games on Batocera 43.1, a
shared Plex library, and round-the-clock ErsatzTV channels with a cable-style TV guide. The Pi
switches from the controller between a flat HDMI TV and the 4:3 Trinitron.

**Start with the guide: [docs/index.html](docs/index.html)** (open it in a browser), also
published privately at <https://claude.ai/artifact/V1V4L9BL9b557rc5xS4qQt>. It covers
flashing the card, the SSD, SSH, the game library, shader benchmarks, the two display profiles,
Kodi's retro guide, the live-TV server, and troubleshooting.

| Folder | What's in it |
|---|---|
| `docs/` | The HTML guide |
| `tools/` | Scripts run from the PC or copied to the Pi: flashing, importing, BIOS check, benchmarks |
| `pi/display-profiles/` | The HDMI / Trinitron profile switcher and its helpers |
| `pi/kodi-skin/` | Kodi's retro TV guide and show details screens, and the live-TV controller map |
| `pi/scripts/` | Batocera launch hooks (`/userdata/system/scripts/`) |
| `pi/shaders/` | Shader sets and the Trinitron CRT presets |
| `pi/snapshots/` | Sanitized copies of the Pi's config files |
| `docker/` | The browser TV guide viewer (Docker Compose): start with `docker/README.md` |
| `roku-tv/` | A Roku app for the channels (home network): start with `roku-tv/README.md` |
| `pi-image/` | The second Pi: a box that boots straight into the viewer on a CRT, with an IR remote. Design, config and build script: start with `pi-image/README.md` |
| `tools/render-splash/` | Renders the viewer's splash scenes to PNG for the Roku app and the Pi's boot screen |
| `ersatztv/` | How the channels are built in ErsatzTV, and the commercials between programmes (catalog of 1,120 clips + a script to rebuild them): start with `ersatztv/README.md` |

Addresses are placeholders: `<pi-ip>` is the Pi on the home network and `<server-ip>` the
server running ErsatzTV (port 8409). Fill them in locally.

Not in this repo: ROMs, BIOS files, box art, SSH keys, the ScreenScraper login, and anything
from the ErsatzTV server's config (`.gitignore` blocks the first ones).

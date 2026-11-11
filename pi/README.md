# The Batocera Pi: games, Plex and live TV on a Sony Trinitron

<p align="center">
  <a href="../README.md">Home</a> &nbsp;·&nbsp;
  <a href="../docker/README.md">Browser app</a> &nbsp;·&nbsp;
  <b>Batocera Pi</b> &nbsp;·&nbsp;
  <a href="../pi-image/README.md">Retro TV box</a> &nbsp;·&nbsp;
  <a href="../roku-tv/README.md">Roku</a> &nbsp;·&nbsp;
  <a href="../ersatztv/README.md">ErsatzTV channels</a>
</p>

One Raspberry Pi 4 running Batocera 43.1 that plays retro games and a shared Plex library, and
watches the ErsatzTV channels in Kodi through a late-90s cable-style guide. From the controller it
switches between a flat HDMI TV and a 4:3 Sony Trinitron.

This page is the short version. **The full guide is the HTML in [`docs/`](../docs/index.html)**
(open `docs/index.html` in a browser; also published privately as a
[Claude artifact](https://claude.ai/artifact/V1V4L9BL9b557rc5xS4qQt)). It records every step, so
the whole setup can be rebuilt from a blank card.

| Guide page | Covers |
|---|---|
| [Base setup](../docs/setup.html) | Flash the card, move storage to the SSD, SSH key, fixed address, Argon fan, BIOS files |
| [Game library](../docs/library.html) | Import ROMs and art from an Onion (Miyoo Mini) backup, PS1 discs and playlists, scraping gaps |
| [Shaders](../docs/shaders.html) | Every shader benchmarked on the Pi and which ones were picked |
| [HDMI and Trinitron](../docs/display.html) | The two display profiles, the converter, overscan, CRT-readable menus, Kodi's retro guide |
| [Live TV channels](../docs/tv.html) | ErsatzTV from the Pi's side: tuning in with IPTV Simple, the server in brief |
| [Reference](../docs/reference.html) | Every file and script, the gotchas, troubleshooting, rebuilding in order |

<p align="center"><img src="../docs/img/readme/game-dkc2-1080.jpg" alt="Donkey Kong Country 2 under the Trinitron shader" width="100%"></p>
<p align="center"><sub>Donkey Kong Country 2 on the flat TV, through the <code>trinitron-hdmi</code> shader: aperture-grille mask, a little curvature.</sub></p>

<table><tr><td align="center"><img src="../docs/img/readme/es-snes-1080.jpg" width="400"><br><sub>The system carousel (Carbon theme, HDMI profile)</sub></td><td align="center"><img src="../docs/img/readme/es-grid-snes-1080.jpg" width="400"><br><sub>313 SNES games with box art</sub></td><td align="center"><img src="../docs/img/readme/bcc-game-1080.jpg" width="400"><br><sub>Batocera's Control Center over a running game</sub></td></tr></table>

<table><tr><td align="center"><img src="../docs/img/readme/game-smw-1080.jpg" width="400"><br><sub>Super Mario World</sub></td><td align="center"><img src="../docs/img/readme/game-sonic2-1080.jpg" width="400"><br><sub>Sonic the Hedgehog 2</sub></td><td align="center"><img src="../docs/img/readme/game-crash-1080.jpg" width="400"><br><sub>Crash Bandicoot (PlayStation)</sub></td></tr></table>

## What the finished system does

- 1,075 games across SNES, NES, Mega Drive, Game Boy, GBC, GBA and PlayStation, imported from a
  Miyoo Mini (Onion) backup with its box art.
- Two display profiles, picked from the **Ports** menu: a 16:9 HDMI TV with a Trinitron-style
  CRT shader, or the real Trinitron through an HDMI-to-composite converter at 640×480 with no
  shaders, overscan margins and a CRT-legible menu. Either profile gives a picture on either TV.
- Kodi with the live channels (ErsatzTV on the home server) and on-demand Plex (PM4K), both
  following the active display profile.
- Storage on a 1 TB SSD, SSH by key, an Argon ONE case with its fan service on.

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi 4 Model B, 8 GB | Wired Ethernet, address pinned by a DHCP reservation |
| Argon ONE M.2 case | The shell is the heatsink; fan and power button on an I2C board at `0x1a` |
| 1 TB M.2 SATA SSD | `/userdata` lives here (a `batocera` folder, picked by UUID in `batocera-boot.conf`) |
| 32 GB microSD | Holds Batocera |
| Dingsun HDMI-to-composite converter | Only for the Trinitron; outputs 480i, NTSC switch, USB powered |
| PS5 DualSense | Bluetooth; the PS button is the hotkey |

## Setting it up, in order

1. **Flash** the Batocera bcm2711 image with [`tools/flash-sd.ps1`](../tools/flash-sd.ps1)
   (elevated PowerShell). It refuses system disks and anything but a 28–33 GB USB card, writes the
   image, then reads the card back and compares SHA-256.
2. **SSH by key**: `ssh-keygen -t ed25519`, append the public key to `/userdata/system/.ssh/authorized_keys`
   on the Pi (root's home is on the SSD, so it survives updates). Use the IP, not `batocera.local`.
3. **Move `/userdata` to the SSD**: ext4 the drive, copy the card's `/userdata` into a `batocera`
   folder on it, set `sharedevice=DEV <UUID>` in `/boot/batocera-boot.conf`, reboot, check with
   `findmnt /userdata`.
4. **Argon fan and button**: `dtparam=i2c_arm=on`, `dtparam=i2c-1=on` in `config.txt` and
   `system.power.switch=ARGONONE` in `batocera.conf`.
5. **BIOS files**: [`tools/check_bios.py`](../tools/check_bios.py) checks MD5s against Batocera's list.
6. **Game library**: stage each Onion system folder on the SSD, then
   [`tools/import_onion.py`](../tools/import_onion.py) (cartridge systems: ROMs, fully validated
   PNG art, `gamelist.xml`) and [`tools/import_onion_psx.py`](../tools/import_onion_psx.py)
   (cue + tracks, one `.m3u` per multi-disc game). Scrape only what is missing afterwards.
7. **Shaders and profiles**: copy `pi/shaders/configs/*` to `/userdata/shaders/configs/`,
   `pi/shaders/crt/*.glslp` to `/userdata/shaders/crt/`, `pi/display-profiles/*` to
   `/userdata/system/display-profiles/`, its `ports/*` to `/userdata/roms/ports/`, `pi/kodi-skin/*`
   to `/userdata/system/display-profiles/kodi-skin/`, `pi/scripts/*` to `/userdata/system/scripts/`.
   Every `.sh` must be executable on the Pi, the two Ports entries included; a copy from Windows
   drops the bit, so finish with
   `chmod +x /userdata/system/display-profiles/*.sh /userdata/roms/ports/*.sh /userdata/system/scripts/*.sh`.
   Run `apply.sh hdmi` once.
8. **Live TV**: enable IPTV Simple Client in Kodi and point it at
   `http://<server-ip>:8409/iptv/channels.m3u` and `/iptv/xmltv.xml`. Switching to either profile
   then applies the Kodi settings below.

The [Reference](../docs/reference.html) page has the same list with every file name.

## The two display profiles

Pick **Display: HDMI TV (16:9)** or **Display: Sony Trinitron (4:3 CRT)** in Ports. The profile
rewrites a complete set of video, theme, Control Center, Kodi and Plex settings, backs up what it
changes, and reboots (about 30 s).

| | HDMI TV | Trinitron |
|---|---|---|
| Output | Best mode up to 1080p | `max-640x480`, 60 Hz |
| Overscan margins (kernel `video=`) | None | left 13, right 27, top 0, bottom 20 px |
| Shader set | `trinitron-hdmi`: crt-pi with an aperture-grille mask, horizontal curvature; LCD looks for handhelds | `trinitron-crt`: none; the tube draws the real thing |
| Menu theme | Stock Carbon | Carbon CRT: bold, white, bigger titles (1-pixel strokes flicker on 480i) |
| Control Center | Stock | Compact 12 px bold layout that fits 640 px |
| Kodi skin | Estuary Retro: the retro TV guide, channel banner and show details laid out for 16:9 | Estuary CRT: the same screens on the 4:3 canvas, plus every font bold and 1.5× |
| Plex (PM4K) quality | Original | 480p, 1.5 Mbps (software decoding) |

<table><tr><td align="center"><img src="../docs/img/readme/es-snes-1080.jpg" width="600"><br><sub>HDMI profile: 1080p, stock Carbon</sub></td><td align="center"><img src="../docs/img/readme/es-snes-640.png" width="600"><br><sub>Trinitron profile: 640×480, Carbon CRT (bold, bigger, no thin strokes)</sub></td></tr></table>

<table><tr><td align="center"><img src="../docs/img/readme/es-grid-snes-640.png" width="400"><br><sub>The SNES grid at 640×480</sub></td><td align="center"><img src="../docs/img/readme/bcc-game-640.png" width="400"><br><sub>The compact Control Center, 12 px bold, fits 640 px</sub></td><td align="center"><img src="../docs/img/trinitron-shader-zoom.png" width="400"><br><sub>The Trinitron shader on a flat TV, 3× zoom</sub></td></tr></table>

Why 640×480: square pixels on a 4:3 tube, 480 lines is exactly twice a 240-line game, and the
converter gets its native line count instead of a blurry 1080p-to-480i downscale. The Pi's own
composite port is not an option on Batocera (unsupported since the move to Wayland). Overscan
margins are hardware DRM properties set on the kernel command line from
`display-profiles/crt-margins.conf`; tune them with the test pattern in
[HDMI and Trinitron](../docs/display.html).

## Kodi and the channels

- **The retro guide** ([`kodi-skin/MyPVRGuide.xml`](kodi-skin/MyPVRGuide.xml)): navy and yellow,
  the show you are watching in a framed box, the highlighted show's details beside it, and the
  grid below (8 channels by 90 minutes on the 4:3 set, by 2½ hours at 16:9). Home → TV opens it.
  Show details ([`kodi-skin/DialogPVRInfo.xml`](kodi-skin/DialogPVRInfo.xml)) get big bold text
  and a Watch now button. The files in `kodi-skin/` use Estuary's 4:3 canvas (1920×1440, 3× the
  real pixels); `kodi-skin/hdmi/` holds the same screens for 16:9 at 1080p.
- **Channel banner** ([`kodi-skin/crt-banner.xml`](kodi-skin/crt-banner.xml), `hdmi/banner.xml`):
  on a channel change or Info. Two sizes: a compact strip along the bottom of the screen like
  the browser app's (default), or a large panel with the description and what's next.
- **Settings** ([`kodi-skin/Custom_1150_RetroSettings.xml`](kodi-skin/Custom_1150_RetroSettings.xml)):
  Triangle/Y, or S on a keyboard, in the guide or while watching. Theme (Cable or Vaporwave, the
  browser app's two palettes; Vaporwave sets titles in Audiowide), Quality (Standard or HD) and
  the banner size. Theme and banner change at once; Quality applies when the guide opens next.
  Every colour in the screens is a skin variable ([`kodi-skin/retro-variables.xml`](kodi-skin/retro-variables.xml)),
  which is what lets one setting recolour everything.
- **Standard and HD.** The server gives every channel an HD twin (number + 100, group `HD`).
  Kodi loads every group; the guide opens on the `ErsatzTV` group or the `HD` group according
  to the Quality setting, so channel up/down stays within the set you picked. In HD the numbers
  read 101 and up (Kodi's labels cannot subtract 100). Group names are constants at the top of
  `make_kodi_skin.sh`, which reads each group's PVR client id from Kodi's TV database to build
  the `pvr://channels/tv/<group>@<id>/` paths the guide is opened with; before the groups exist
  (first run) Home → TV opens the guide on its last group.
  The HD grid needs the server to list each twin in its XMLTV (in ErsatzTV: Show In EPG on, see
  [HD copies of every channel](../ersatztv/README.md#hd-copies-of-every-channel-twins)); a twin
  without it plays but has an empty row.
- **Controller** ([`kodi-skin/livetv-controller.xml`](kodi-skin/livetv-controller.xml)): Cross/A
  pauses or switches to the highlighted channel; Circle/B opens the guide with the show still
  playing (hold to stop); Square/X shows controls or details; Triangle/Y opens Settings.
- **Settings for both profiles** ([`display-profiles/kodi_tv_settings.py`](display-profiles/kodi_tv_settings.py)):
  Select switches channel instead of opening details, the guide reloads every 15 minutes, IPTV
  Simple loads every channel group, and the controller map is installed.
- **Launch hook** in `/userdata/system/scripts/`:
  [`scripts/kodi-fullscreen-fix.sh`](scripts/kodi-fullscreen-fix.sh), which toggles full screen
  once after Kodi opens because sway first places the window 19 px low.
- The converter does not pass HDMI-CEC, so the controller drives Kodi on the Trinitron, not a
  TV remote.

<table><tr><td align="center"><img src="../docs/img/readme/kodi-guide-640.png" width="600"><br><sub>The retro guide: the show you are watching in the box, the highlighted show beside it</sub></td><td align="center"><img src="../docs/img/readme/kodi-details-640.png" width="600"><br><sub>Show details, big and bold for the tube</sub></td></tr></table>

<table><tr><td align="center"><img src="../docs/img/readme/kodi-banner-640.png" width="400"><br><sub>The channel banner on a channel change</sub></td><td align="center"><img src="../docs/img/readme/kodi-guide-office-640.png" width="400"><br><sub>Moving around the grid</sub></td><td align="center"><img src="../docs/img/readme/kodi-watching-640.png" width="400"><br><sub>Watching: no overlay at all</sub></td></tr></table>

<p align="center"><sub>The same screens on a 16:9 TV, from the HDMI profile's Estuary Retro:</sub></p>

<table><tr><td align="center"><img src="../docs/img/readme/kodi-guide-1080.jpg" width="400"><br><sub>The guide at 1080p: 8 channels by 2½ hours</sub></td><td align="center"><img src="../docs/img/readme/kodi-details-1080.jpg" width="400"><br><sub>Show details</sub></td><td align="center"><img src="../docs/img/readme/kodi-banner-1080.jpg" width="400"><br><sub>The compact channel banner</sub></td></tr></table>

<table><tr><td align="center"><img src="../docs/img/readme/kodi-settings-1080.jpg" width="600"><br><sub>Settings: theme, Standard/HD, banner size</sub></td><td align="center"><img src="../docs/img/readme/kodi-guide-vapor-1080.jpg" width="600"><br><sub>The Vaporwave theme, Audiowide titles</sub></td></tr></table>

## What is in this folder

| Path | Installed on the Pi as |
|---|---|
| `display-profiles/apply.sh hdmi\|crt` | `/userdata/system/display-profiles/apply.sh`: applies a profile, backs up, logs to `logs/display-profile.log`, reboots |
| `display-profiles/ports/` | The two Ports menu entries (`/userdata/roms/ports/`) |
| `display-profiles/crt-margins.conf` | The Trinitron's overscan margins |
| `display-profiles/make_crt_theme.sh` | Builds the Carbon CRT theme (`/userdata/themes/es-theme-carbon-crt`) |
| `display-profiles/make_bcc_compact_css.py`, `make_bcc_layout.py` | Control Center stylesheet and layout |
| `display-profiles/make_kodi_skin.sh` + `kodi-skin/` | Builds and enables the retro Kodi skin: `crt` (4:3, big bold fonts; screens in `kodi-skin/`) or `hdmi` (16:9; screens in `kodi-skin/hdmi/`). Stops cleanly and falls back to stock Estuary if a Batocera update changed Estuary |
| `display-profiles/kodi_tv_settings.py` | Kodi live-TV settings (every channel group loaded, the server's channel numbers, guide refresh) and the controller map |
| `display-profiles/overscan-test.png` | The margin test pattern (bands 8 px apart) |
| `scripts/` | `/userdata/system/scripts/`: Batocera's per-launch hooks |
| `shaders/configs/trinitron-hdmi`, `trinitron-crt` | `/userdata/shaders/configs/`: the two shader sets |
| `shaders/crt/trinitron.glslp`, `trinitron-flat.glslp` | `/userdata/shaders/crt/`: crt-pi tuned for a Trinitron, curved and flat |
| `snapshots/` | Sanitized copies of `batocera.conf`, `batocera-boot.conf`, `cmdline.txt`, `config.txt`, `crt-margins.conf`, `es_settings.cfg` (2026-11-05, Trinitron profile) |

Copy files over with `scp -i ~/.ssh/<key> <file> root@<pi-ip>:<path>`.

## Troubleshooting, the short list

| Problem | Fix |
|---|---|
| No picture on the Trinitron | Converter powered and on NTSC, TV on the Video input, Pi booted with the converter already on |
| Picture rolls or is black and white | Converter on PAL; switch to NTSC |
| Edges cut off | Re-measure with the test pattern, edit `crt-margins.conf`, run the Trinitron entry again |
| Wrong profile | Pick the other Ports entry; both work on either TV |
| Controller won't connect | Airplane mode: `batocera-planemode disable`, then `/etc/init.d/S32bluetooth restart` |
| New channels with an empty guide | Close Kodi, move `Database/Epg16.db` and IPTV Simple's two cache files aside, start Kodi |
| Channels renumbered on the server, Kodi keeps old numbers | Close Kodi, move `Database/TV*.db` and `Database/Epg*.db` aside, start Kodi: it imports the list again |
| `/userdata` on the card, not the SSD | `findmnt /userdata`; check `sharedevice=DEV <UUID>` and `lsblk -f` |

More, with the reasons, in [Reference](../docs/reference.html).

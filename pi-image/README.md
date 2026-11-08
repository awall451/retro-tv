# Retro TV box: the Pi image

<p align="center">
  <a href="../README.md">Home</a> &nbsp;·&nbsp;
  <a href="../docker/README.md">Browser app</a> &nbsp;·&nbsp;
  <a href="../pi/README.md">Batocera Pi</a> &nbsp;·&nbsp;
  <b>Retro TV box</b> &nbsp;·&nbsp;
  <a href="../roku-tv/README.md">Roku</a> &nbsp;·&nbsp;
  <a href="../ersatztv/README.md">ErsatzTV channels</a>
</p>

A Raspberry Pi 4 that boots straight into the Retro TV guide on a CRT, with an IR remote. No
Batocera, no Kodi: the box runs the browser viewer from `../docker/web/app` full screen, served by
its own web server, with a boot splash in the chosen theme. This folder holds everything about
that box: the design, the configuration, the script that builds it, and later the image recipe.

**Status:** step 1 works. On 2026-11-07 a stock Pi OS Lite card plus `setup.sh` booted into the
guide at 640×480 on the Sylvania through the HDMI converter, with no cursor and no phantom
display. Still to check on the tube: the margins, the boot splash, the remote (receiver not
here yet), sound. Decisions below are settled unless marked open.

<table><tr><td align="center"><img src="../docs/img/readme/tv-guide-playing-cable.png" width="600"><br><sub>What the box shows: the guide at 640×480, a show playing in the box</sub></td><td align="center"><img src="../docs/img/readme/poe-hat.jpg" width="600"><br><sub>The official PoE+ HAT: one cable for power and network</sub></td></tr></table>

<table><tr><td align="center"><img src="config/plymouth/retro-tv/splash-cable-640.png" width="400"><br><sub>Boot splash, Cable theme (640×480)</sub></td><td align="center"><img src="config/plymouth/retro-tv/splash-vapor-640.png" width="400"><br><sub>Boot splash, Vaporwave theme</sub></td></tr></table>

## The box

| Part | What we have |
|---|---|
| Computer | Raspberry Pi 4 Model B, 2 GB, with the official PoE+ HAT (power and network over one cable; its fan is run by the firmware) |
| Card | 16 GB microSD (the system needs about 3 GB) |
| Screen | 12-inch Sylvania CRT, composite input |
| Video out | For now: HDMI at 640×480 into the HDMI-to-composite converter (same as the Trinitron). Later: the Pi's own composite jack, 720×480i, once the 4-pole cable arrives |
| Remote | A Media Center (MCE) USB IR receiver (on order); a universal remote programmed for the Sylvania's power and volume and for the box |
| Controller | PS5 pad over Bluetooth, optional |
| Network | Wired, through the PoE switch; the ErsatzTV server is on the home network |

## Decisions

- **Base system: Raspberry Pi OS Lite, 64-bit** (current release). It has the Pi's video drivers,
  Chromium with hardware H.264 decoding, Plymouth, and `apt`. A fully custom Buildroot system was
  considered and kept as a possible later step; Pi OS gets us there in days, not weeks.
- **The viewer runs on the box itself.** nginx serves `docker/web/app` and proxies `/iptv/` to
  ErsatzTV, using the very same `docker/web/nginx.conf.template` as the laptop container (only
  the port and root differ). Reasons: the box never shows a browser error page (if the server is
  down, the guide's own "Can't reach the TV server" message appears, in the theme's style); no
  dependency on the laptop being up; and the viewer's theme can be read by the box (below).
- **Kiosk: `cage` + Chromium.** `cage` is a Wayland compositor that shows exactly one window, full
  screen, no desktop, no cursor. Chromium runs in kiosk mode with sound allowed from the start
  (the "press a key for sound" problem does not exist here) and its profile on a writable data
  area so the theme and other settings survive reboots. The page is `http://127.0.0.1:8410/?tv`:
  the plain 640×480 layout.
- **Boot splash: Plymouth, in the current theme.** The Pi's rainbow square and the scrolling boot
  text are turned off. Plymouth shows the theme's splash (the little television, or the sunset) as
  a still, from the same scene code as the viewer and the Roku app, rendered by
  `tools/render-splash`. Then the viewer's own animated splash takes over as the guide loads.
- **The theme follows the viewer's setting.** The viewer posts its theme to `/pi/theme` whenever
  it is applied (on every start and on every change). On the box, nginx passes that to a small
  local service (`retro-tv-themed.py`), which records the choice and points Plymouth's images at
  the matching splash, so the *next* boot already matches. Anywhere else (laptop, phone) the
  request answers 404 and is ignored.
- **Composite video from the Pi itself** is the end state: Pi OS can drive the 3.5 mm jack
  (Batocera could not). The jack also carries the sound. Until the cable arrives, HDMI at
  640×480 through the converter, exactly like the Trinitron setup, with the same kind of
  kernel margin settings for overscan. Switching between the two is one line in the box's
  config file.
- **IR: a USB MCE receiver, decoded by Linux.** The kernel's `mceusb` driver decodes the remote;
  a key map of ours (`config/rc_keymaps/retro-tv-mce.toml`) turns its buttons into the plain
  keyboard keys the viewer already understands (arrows, Enter, Escape, Page Up/Down, digits,
  I, S, M, R). No wiring, no soldering, and the receiver can sit on top of the TV. The official
  PoE+ HAT covers the GPIO header, which is why a USB receiver rather than a 3-wire module.
  Many MCE receivers also have IR *emitter* jacks: a later step can let the box switch the TV
  on and off itself.
- **TV power and volume stay with the TV.** A universal remote with "punch-through" sends power
  and volume to the Sylvania and everything else to the box. The box's own power button on the
  remote is for later (blank the picture, stop the stream); the Pi cannot be switched on by IR.
  Power from fully off: the PoE switch's port (if it is managed) or the plug.
- **Read-only system, writable data.** The root filesystem is mounted read-only with an overlay,
  so pulling the plug can never corrupt the card. A separate writable area (`/data`) holds the
  Chromium profile (the viewer's settings), the theme choice, Bluetooth pairings and logs.
- **Tailscale is optional, off by default.** With it on, and a subnet route for the home network
  advertised by something at home, the box works anywhere with ordinary Wi-Fi or a hotspot (not
  behind a hotel sign-in page: there is no browser to click through).
- **Two build steps.** First a provisioning script (`setup.sh`) that turns a stock Pi OS Lite card
  into the box, so every piece can be tried on the real Pi and CRT. Then `pi-gen` wraps that same
  script into a flashable image: write it to a card and the box is finished.

## How it starts

1. Power (PoE) → firmware → kernel. Boot text is hidden; Plymouth draws the theme's splash.
2. nginx starts with the viewer and the ErsatzTV proxy. The theme service starts.
3. `cage` starts on the console as user `tv` and launches Chromium in kiosk mode on the viewer.
4. The viewer shows its own animated splash while it loads the listings, then the guide.
5. The IR receiver's key map is loaded when the receiver is seen (`ir-keytable`), so the remote
   works from the first screen.

About 20–25 seconds from power to guide on a Pi 4, to be measured.

## Files

```
pi-image/
├── README.md                      this file
├── setup.sh                       turns a fresh Pi OS Lite into the box; run again after changes
└── config/
    ├── retro-tv.env.example       the box's settings: server address, display mode, margins, Tailscale
    ├── retro-tv-kiosk.sh          starts Chromium in kiosk mode on the viewer (run by cage)
    ├── retro-tv.service           systemd: cage on the console as user tv
    ├── retro-tv-themed.py         the theme service behind /pi/theme (records the choice, updates Plymouth)
    ├── retro-tv-themed.service    systemd unit for it
    ├── nginx-pi.conf              the Pi-only additions to the viewer's nginx config (/pi/)
    ├── plymouth/retro-tv/         the boot splash theme: script, config, and the rendered scenes
    └── rc_keymaps/retro-tv-mce.toml   MCE remote buttons → the viewer's keys
```

The splash pictures in `config/plymouth/retro-tv/` are generated, not drawn by hand:
`node tools/render-splash/render.mjs` (from the repo root, after `npm install` in that folder)
renders both themes at 640×480 (HDMI), 720×480 (composite, non-square pixels) and 1920×1080, and
the Roku app's icons, from `docker/web/app/js/splash.js`. Re-run it when the scenes change.

## Building the box, step 1: a stock card plus `setup.sh`

1. **Flash** Raspberry Pi OS Lite (64-bit) with Raspberry Pi Imager. In its settings: hostname
   `retro-tv`, user `tv` with a password of your choice, SSH on with public-key login only, and
   paste the public key for the box (kept out of the repo; the private half lives on the
   maintainer's PC). Wi-Fi is not needed on PoE.
2. **Boot** it on the network, then from the PC: `ssh tv@retro-tv.local`.
3. **Get the repo** onto it (`git clone` of the GitHub repo, or `rsync` from the PC) and run
   `sudo pi-image/setup.sh`. The first run copies `config/retro-tv.env.example` to
   `/etc/retro-tv.env` and stops so you can fill in the ErsatzTV address and the display mode;
   run it again and it does everything else, then reboots into the guide.
4. **Tune the picture** on the CRT with the margins in `/etc/retro-tv.env` (a bigger number
   pulls the picture in from that edge), `sudo pi-image/setup.sh`, reboot.

`setup.sh` is written to be safe to run repeatedly: it installs what is missing, rewrites the
files it owns, and leaves the rest alone.

## Step 2: the image (`pi-gen`)

Later. A `pi-gen` stage that runs `setup.sh` inside the image build, plus the read-only overlay
and the `/data` partition, produces `retro-tv-<date>.img.xz`. Building needs a Linux machine
(the Garuda laptop, or WSL on the PC) and about 30 minutes. Until then, step 1 gives a working
box, just not a one-file one.

## Display details

- **HDMI 640×480 (now):** `video=HDMI-A-1:640x480@60D` on the kernel command line plus the
  margins (`margin_left=…` and so on), the same mechanism the Trinitron uses. The converter
  makes 480i from it.
- **Composite (later):** `dtoverlay=vc4-kms-v3d,composite` and `enable_tvout=1` in
  `config.txt`, and `video=Composite-1:720x480@60ie` on the command line (NTSC). The picture is
  720×480 with non-square pixels; the viewer's `?tv` layout is 640×480 and is stretched to fit,
  which is what a 4:3 CRT expects. Margins work the same way.
- The 12-inch tube is small: text that reads fine on the 19-inch Trinitron may need a size
  bump. The viewer's design units make that a CSS change.

## The remote

- **Receiver:** any "Windows Media Center" USB IR receiver (Linux driver `mceusb`). Those with
  two 3.5 mm emitter jacks can later control the TV too.
- **Key map:** `config/rc_keymaps/retro-tv-mce.toml` maps the standard MCE remote codes:
  arrows → arrows, OK → Enter, Back/Clear → Escape, Guide → Escape (the viewer's "back" toggles
  guide and picture), Info → I, Channel +/− → Page Up/Down, digits → digits, Mute → M, the
  green Windows button → S (settings), Record → R (reload listings). Power and volume are left
  to the TV. `ir-keytable` loads it through `/etc/rc_maps.cfg` whenever the receiver appears.
- **Any other remote** can be used once its codes are known: `ir-keytable -t` prints what the
  receiver sees while you press buttons, and the map is a text file.
- **Universal remote:** program the TV device with the Sylvania's codes and the box as a
  "Media Center PC" (or learn the MCE remote's codes), with volume and power punched through to
  the TV.

## Learned on the first boot

- **Pi OS Lite is Debian 13 (Trixie)** here; the packages are `chromium` and `cage` (0.3.1, a
  Raspberry Pi build), both in the standard repository. The whole install takes about 4 minutes.
- **The compositor picks the display's preferred mode, not the kernel's.** `cage` (wlroots)
  started the converter at its preferred 1280×720 whatever `video=` said. The kiosk script
  now sets the mode from inside the session with `wlr-randr` before starting Chromium; the
  kernel line still carries the mode and the margins (the margins are connector properties the
  compositor leaves alone).
- **Never write `@60D` in `video=`.** The `D` suffix means "force this connector on". With it,
  the empty HDMI port 1 became a phantom 1024×768 display, and `cage` spread the screen across
  both. Plain `@60`, and the mode is given for both HDMI ports so either one can be used. The
  same goes for `hdmi_force_hotplug=1`, which is not needed: the converter presents an EDID.
- **The CEC devices are the "mouse".** Each HDMI port has a CEC remote-control input that
  libinput classes as keyboard + pointer, and a pointer makes `cage` draw a cursor in the middle
  of the screen. A udev rule hides them (and game pads) from libinput; with no input devices
  left, wlroots refuses to start unless `WLR_LIBINPUT_NO_DEVICES=1` is set, so the service sets
  it. The viewer also hides the pointer in `?tv` mode.
- **Imager's user has no passwordless `sudo` on this image.** A line in `/etc/sudoers.d/` gives
  it, as every stock Pi OS has; `setup.sh` needs root.
- **Boot to SSH is about 25 s.**
- **Margins on the 12-inch Sylvania through the converter: left 19, right 21, top 10,
  bottom 6** (the Trinitron's were 13/27/0/20). Tuned with the test pattern: `PAGE=overscan` in
  `/etc/retro-tv.env`, `sudo pi-image/setup.sh`, reboot, and adjust until the white 0 px frame
  is just visible on every side; then `PAGE=guide`. The margins take a reboot; the page only a
  `systemctl restart retro-tv`.
- **Sound defaulted to the headphone jack.** PipeWire picks the 3.5 mm jack as the default
  output, so the converter got silence. The kiosk script now makes the HDMI output the default
  at full volume (the jack in composite mode, where it carries the sound).

## Open items

- Confirm sound through the converter while a channel plays; the boot splash; the IR receiver
  when it arrives.
- Whether Plymouth on Pi OS runs from the initramfs (then a theme change also regenerates it in
  the background, which the theme service already does if it finds one).
- A "standby" action for the remote's power button: blank the picture and stop the stream, in
  the viewer. Needs a small viewer change.
- The box controlling the TV through an IR emitter (power on with the box, off at standby).
- Tailscale: install, sign in from a phone, accept the home subnet route; a settings-screen
  switch for it would need the box to expose a second local endpoint like `/pi/theme`.
- Font sizes on the 12-inch tube.

## Conventions

Nothing personal in this folder: the server address lives only in `/etc/retro-tv.env` on the
box (and in the git-ignored `pi-image/retro-tv.env` if kept locally). SSH keys never enter the
repo.

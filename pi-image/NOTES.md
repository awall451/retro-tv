# Retro TV box: build log

Working notes for this particular box, kept apart from the [README](README.md) so that page
stays a description anyone can use. Newest first.

## 2026-11-09: no network at all, then composite

- Moved to the TV on Wi-Fi only and the 3.5 mm composite cable: no picture (expected, the box
  was still in `hdmi480` mode) and no SSH. The router saw its Wi-Fi address but 5 of 6 packets
  were lost: 5 GHz at the TV spot, with the PoE HAT over the antenna and the tube beside it. A
  power cycle made it worse: the only Wi-Fi profile was gone and the box booted with no network
  at all. (The kernel's "orphan cleanup" line is printed after clean reboots too, so it proves
  nothing; the lost profile and the pulled plug are the facts.)
- Written and installed: `retro-tv-net.sh` with its restore unit (profiles rebuilt from Imager's
  `network-config` at every boot) and the minute check behind `/pi/net`; the viewer's settings
  screen gained a read-only Network row.
- The two network names here take the same password; the 2.4 GHz one is `WIFI_EXTRA_SSID` and
  is preferred. At the switch: 2.4 GHz 68–74%, 5 GHz 71%, 0% loss on either. Yesterday's
  "no network after pinning the band" is explained: the Imager profile was for the 5 GHz name,
  which does not exist on 2.4 GHz.
- Display mode switched to `composite` (`DISPLAY_MODE` in `/etc/retro-tv.env`, then `setup.sh`).
  At the TV, on Wi-Fi only and the 3.5 mm cable: no picture at first although the kernel showed
  `Composite-1` connected and a `grim` capture under cage showed the guide being scanned out.
  The cable is a camcorder-type (J&D "for Sony Handycam") TRRS lead, which puts the video on the
  **red** plug when used on a Pi; red into the TV's video jack and the guide appeared.
- Margins re-tuned once the viewer was stretched (which exposed the edges the 40 px bars had
  hidden). The test pattern turned out to have been unstyled all along (CSP), fixed with
  `overscan.css`, but reading its photos still misled: a first guess of 29/31/18/14 left the
  sides cut and put bars top and bottom. Judged on the guide itself instead, one reboot at a
  time: left 45, right 37, **top 10 and bottom 6 unchanged**. Channel numbers and the cog are
  fully on screen with no bar on either side.
- Seen on the tube: the guide had a thin black bar at each side (the viewer laid out 640 wide
  inside the 720-pixel anamorphic picture); a widescreen show with "Fill the screen" had none.
  Fixed the same day: the kiosk passes `&screen=4:3` in composite mode and the viewer stretches
  the whole page by 720/640 (`body` transform), so the layout, the picture box, the banner and
  the splash all come out 4:3 on the tube.
- Wi-Fi at the TV spot on 2.4 GHz: 60–69% signal, 0% loss over 240 pings to the router from the
  box, and the watchdog has logged 0% on every check. The 5 GHz link in the same place lost 5 of
  6 packets yesterday. That closes the "Channel unavailable" story for this location.
- Trying the themes from the TV made the box laggy for minutes: every change ran
  `update-initramfs -u` immediately (both kernels, normal priority), and quick presses stacked
  them. Debounced to one low-priority rebuild per quiet 20 s, running kernel only; measured
  ~15 s for a burst of four changes, load back to normal.
- Boot splashes rendered for all nine themes (the other session's theme picker had seven new
  ones with only the viewer's animated splash). `fonts.py` unpacks the viewer's WOFF2 fonts to
  TTF for resvg; the theme service now accepts any theme that has a splash file. The box's
  current theme is Vaporwave; with no remote yet, that is what the tube shows at boot.
- Added the settings screen's **Power off** row (`/pi/power` through `retro-tv-themed.py`,
  two presses, then `systemctl poweroff`); tested end to end with the `reboot` action. The
  settings list is now six rows on the box, so a compact layout kicks in under 540 px of height.

## 2026-11-07: first boot

- A stock Raspberry Pi OS Lite card (Debian 13, Trixie) plus `setup.sh` booted into the guide at
  640×480 on the 12-inch set, through the HDMI-to-composite converter borrowed from the Batocera
  Pi. No cursor, no phantom display. Picture and sound confirmed on the tube.
- Packages in the standard repository: `chromium`, `cage` 0.3.1 (a Raspberry Pi build). The
  whole install took about 4 minutes; boot to SSH is about 25 s.
- Margins on this set through the converter: left 19, right 21, top 10, bottom 6 (the
  Trinitron's on the Batocera Pi are 13/27/0/20). Tuned with `PAGE=overscan`.
- Imager's user had no passwordless `sudo` on this image; added by hand under `/etc/sudoers.d/`.
- Sound first came out of the headphone jack (PipeWire's default); the kiosk script now selects
  HDMI.
- Everything under "Things that bit" in the README was found on this boot.

## 2026-11-08: "Channel unavailable" every minute

- The box had been running on Wi-Fi (no Ethernet link). The 5 GHz link lost 26–40% of packets to
  the gateway in ~30 s holes about once a minute; nginx returned 504 on `live.m3u8` (connect
  timeout) and the viewer showed "Channel unavailable, retrying…". The server was fine (a probe
  from the PC had zero failures).
- Disabling Wi-Fi power saving (`802-11-wireless.powersave 2` on the NetworkManager connection)
  did not change the loss. Pinning the connection to 2.4 GHz (`band bg`) and rebooting left the
  box with no network at all; recovered by plugging Ethernet in, then the pin was removed.
- Now on Ethernet (1 Gb/s, default route `eth0`), Wi-Fi left configured as a fallback with power
  saving off.

## Hardware in this build

- Pi 4 Model B, 2 GB, official PoE+ HAT, 16 GB card, wired through the PoE switch.
- 12-inch CRT with composite input, fed by the converter for now (shared with the Batocera Pi,
  so only one of the two is on the tube at a time).
- 4-pole 3.5 mm composite cable: a camcorder-type lead (video on the red plug on a Pi). The MCE USB
  IR receiver: on order.
- Universal remote to be programmed for the TV's power and volume and for the box.

## Open items

- Plymouth boot splash: not yet confirmed on the tube (seen over HDMI only).
- Sound on the composite jack: not yet confirmed on the tube.
- The IR receiver when it arrives: `ir-keytable -t` to check the codes, then the key map.
- Whether Plymouth on Pi OS runs from the initramfs (then a theme change also regenerates it in
  the background, which the theme service already does if it finds one).
- Standby action, IR emitter to the TV, Tailscale sign-in, font sizes on the 12-inch tube: see
  "Not yet" in the README.
- Step 2 (`pi-gen`): build machine is a Linux laptop or WSL.

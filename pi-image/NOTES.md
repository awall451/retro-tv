# Retro TV box: build log

Working notes for this particular box, kept apart from the [README](README.md) so that page
stays a description anyone can use. Newest first.

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

## Hardware in this build

- Pi 4 Model B, 2 GB, official PoE+ HAT, 16 GB card, wired through the PoE switch.
- 12-inch CRT with composite input, fed by the converter for now (shared with the Batocera Pi,
  so only one of the two is on the tube at a time).
- 4-pole 3.5 mm composite cable and the MCE USB IR receiver: on order.
- Universal remote to be programmed for the TV's power and volume and for the box.

## Open items

- Plymouth boot splash: not yet confirmed on the tube (seen over HDMI only).
- The Pi's composite output (720×480i) when the cable arrives: mode line, margins, sound on the
  jack.
- The IR receiver when it arrives: `ir-keytable -t` to check the codes, then the key map.
- Whether Plymouth on Pi OS runs from the initramfs (then a theme change also regenerates it in
  the background, which the theme service already does if it finds one).
- Standby action, IR emitter to the TV, Tailscale sign-in, font sizes on the 12-inch tube: see
  "Not yet" in the README.
- Step 2 (`pi-gen`): build machine is a Linux laptop or WSL.

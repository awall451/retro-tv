# Retro TV for Roku

The ErsatzTV channels on a Roku, with the same look as the browser viewer (`../docker/`):
full-screen live TV and a channel bar along the bottom. It talks to ErsatzTV directly, so it
works on the home network only (a Roku cannot join a tailnet).

**What it has:** the guide grid with the picture in the corner box, show details, settings, the
channel bar while watching, Standard/HD, and the two themes with their splash screens. Not here,
on purpose: the viewer's fast-flipping warm-up, "Fill the screen" and typing a channel number (a
Roku remote has no digits).

| Remote | In the guide | Watching |
|---|---|---|
| Arrows | Move the highlight (Up from the top row reaches the settings cog) | Up / Down change channel; Left / Right pick a button on the channel bar |
| OK | Watch the highlighted channel | Show the channel bar, or press its highlighted button |
| Play / Pause | Show details | Sound on / off |
| Replay or `*` | Settings | |
| Rewind / Fast-forward | Page through channels | Channel down / up |
| Back | Back to the picture (or leave the app) | Back to the guide |

**Settings** (Replay or `*`): **Theme** (Cable or Vaporwave: the whole guide recolours at once and
the new theme's splash plays for two seconds), **Quality** (Standard or HD; HD needs the channel's
twin, see `../ersatztv/README.md`), and the **TV server** address. They are kept on the Roku, so
each Roku has its own.

On first start it asks for the ErsatzTV address (`<server-ip>:8409`). It remembers that and the
last channel watched. If the server stops answering, the guide's message says how to change the
address (Replay).

**The splash.** Roku shows the app's start-up picture itself, and that one is fixed at install:
the Cable television. The app then shows the current theme's splash for two seconds over the
loading guide (the Cable one continues the start-up picture without a cut; Vaporwave is the
sunset over the grid). Both are stills of the scenes the browser viewer draws, rendered from
`../docker/web/app/js/splash.js`.

## Installing it on your Roku (sideloading)

No Roku account or store review is needed for your own Roku.

1. **Developer mode.** On the Roku remote press **Home ×3, Up ×2, Right, Left, Right, Left,
   Right**. Accept the agreement, choose a password, and let it restart. The screen shows the
   Roku's address (`http://<roku-ip>`).
2. **Install.** From this folder:
   ```bash
   ROKU_IP=<roku-ip> ROKU_DEV_PASSWORD=<password> ./install.sh
   ```
   or put the two lines in `roku-tv/.env` (git-ignored) and run `./install.sh`. It zips the app
   and uploads it; "Install Success" means it is on the Roku and starts at once. Re-run it after
   every change.
   Without the script: open `http://<roku-ip>` in a browser, sign in as `rokudev`, upload
   `out/retro-tv.zip`, press Install.
3. **Debug output.** `telnet <roku-ip> 8085` shows the app's log and any BrightScript error with
   its line number.

Only one sideloaded app can be on a Roku at a time; installing replaces it.

## Files

| Path | What |
|---|---|
| `manifest` | App name, version, icons |
| `source/main.brs` | Opens the screen |
| `components/MainScene.*` | Video, channel bar, remote keys, settings in the registry |
| `components/ChannelsTask.*` | Reads `/iptv/channels.m3u` from ErsatzTV |
| `images/` | Icons and splash screen: the viewer's Cable splash (the little television), rendered from `../docker/web/app/js/splash.js` |
| `install.sh` | Zip and sideload |

Streams are ErsatzTV's HLS (`/iptv/channel/<n>.m3u8?mode=segmenter`), the same ones the
browser viewer plays. HD plays channel number + 100 when the server has that twin.

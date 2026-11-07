# Retro TV for Roku

The ErsatzTV channels on a Roku, with the same look as the browser viewer (`../docker/`):
full-screen live TV and a channel bar along the bottom. It talks to ErsatzTV directly, so it
works on the home network only (a Roku cannot join a tailnet).

**Status: first version.** Channel up/down, the channel bar, Standard/HD. Programme names, the
TV guide grid, show details and settings come next.

| Remote | Does |
|---|---|
| Up / Down (or Fast-forward / Rewind) | Channel up / down |
| OK | Show or hide the channel bar |
| `*` | Switch between Standard and HD (HD needs the channel's twin, see `../ersatztv/README.md`) |
| Back | Leave |

On first start it asks for the ErsatzTV address (`<server-ip>:8409`). It remembers that, the
last channel and the quality on the Roku. To change the address later, enter an address that
does not answer: the error message offers to change it. (A settings screen comes later.)

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
| `images/` | Icons and splash screen (navy and yellow, like the viewer) |
| `install.sh` | Zip and sideload |

Streams are ErsatzTV's HLS (`/iptv/channel/<n>.m3u8?mode=segmenter`), the same ones the
browser viewer plays. HD plays channel number + 100 when the server has that twin.

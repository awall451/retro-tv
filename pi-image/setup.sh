#!/usr/bin/env bash
# Retro TV box: turn a fresh Raspberry Pi OS Lite (64-bit) into the box, or
# bring an existing one up to date. Run as root on the Pi, from a checkout of
# the repo:
#     sudo pi-image/setup.sh
# Safe to run again: it installs what is missing and rewrites the files it
# owns (marked as such) and nothing else. pi-gen will run this same script
# when the image is built (README, step 2).
#
# Run on the first box (Pi 4, Sylvania CRT through an HDMI-to-composite
# converter); what that boot taught is in the README.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
CFG=/etc/retro-tv.env
APP=/usr/share/retro-tv/app
DATA=/data
BOOT=/boot/firmware
[ -d "$BOOT" ] || BOOT=/boot

log() { printf '\n== %s\n' "$*"; }
[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0" >&2; exit 1; }

# ---- settings -----------------------------------------------------------------
if [ ! -f "$CFG" ]; then
    install -m 600 "$HERE/config/retro-tv.env.example" "$CFG"
    echo "Wrote $CFG from the example. Set ERSATZTV_URL and DISPLAY_MODE there, then run this again."
    exit 2
fi
chmod 644 "$CFG"            # the kiosk script (user tv) reads the display mode from it; nothing secret in it
set -a; . "$CFG"; set +a
: "${ERSATZTV_URL:?set ERSATZTV_URL in $CFG}"
case "$ERSATZTV_URL" in *'<'*) echo "ERSATZTV_URL in $CFG is still the placeholder" >&2; exit 2;; esac
DISPLAY_MODE=${DISPLAY_MODE:-hdmi480}
MARGIN_LEFT=${MARGIN_LEFT:-0}; MARGIN_RIGHT=${MARGIN_RIGHT:-0}
MARGIN_TOP=${MARGIN_TOP:-0}; MARGIN_BOTTOM=${MARGIN_BOTTOM:-0}
TAILSCALE=${TAILSCALE:-0}
case "$DISPLAY_MODE" in hdmi480|composite) ;; *) echo "DISPLAY_MODE must be hdmi480 or composite" >&2; exit 2;; esac

# ---- packages -----------------------------------------------------------------
log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
pkgs=(cage wlr-randr nginx-light plymouth plymouth-themes ir-keytable python3 python3-yaml rsync bluez pipewire-audio)
if apt-cache show chromium >/dev/null 2>&1; then pkgs+=(chromium); else pkgs+=(chromium-browser); fi
apt-get install -y -q --no-install-recommends "${pkgs[@]}"

# ---- the tv user and the writable data area ------------------------------------
log "user tv, $DATA"
id tv >/dev/null 2>&1 || useradd -m -s /bin/bash tv       # Imager normally made it already
usermod -aG video,render,input,audio tv
mkdir -p "$DATA/chromium" "$DATA/retro-tv"
chown -R tv:tv "$DATA/chromium"
loginctl enable-linger tv

# ---- the viewer, served by this box ---------------------------------------------
# The same files and nginx rules as the laptop container (docker/web); only the
# port, the root and the ErsatzTV address are filled in, and /pi/ is added.
log "viewer -> $APP, nginx on 127.0.0.1:8410"
mkdir -p "$APP"
rsync -a --delete "$REPO/docker/web/app/" "$APP/"
cp "$HERE"/config/www/* "$APP/"          # the box's own pages (the overscan test pattern)
# The site is the template with its closing brace taken off and the include put
# in before it. It is built aside and the old one kept, so a template that no
# longer ends the way this expects cannot leave nginx unable to start.
SITE=/etc/nginx/sites-available/retro-tv
sed -e 's|listen 8080;|listen 127.0.0.1:8410;|' \
    -e "s|root /usr/share/nginx/html;|root $APP;|" \
    -e "s|\${ERSATZTV_URL}|$ERSATZTV_URL|g" \
    "$REPO/docker/web/nginx.conf.template" |
    awk '{ line[NR] = $0 }
         END { n = NR
               while (n > 0 && line[n] ~ /^[[:space:]]*$/) n--          # blank lines at the end
               if (n == 0 || line[n] !~ /^[[:space:]]*}[[:space:]]*$/) exit 1
               for (i = 1; i < n; i++) print line[i]
               print ""; print "  include /etc/nginx/retro-tv-pi.conf;"; print "}" }' > "$SITE.new" ||
    { rm -f "$SITE.new"; echo "docker/web/nginx.conf.template does not end with a closing brace" >&2; exit 1; }
[ -f "$SITE" ] && cp -p "$SITE" "$SITE.prev"
mv -f "$SITE.new" "$SITE"
chmod 644 "$SITE"
install -m 644 "$HERE/config/nginx-pi.conf" /etc/nginx/retro-tv-pi.conf
ln -sf "$SITE" /etc/nginx/sites-enabled/retro-tv
rm -f /etc/nginx/sites-enabled/default
if ! nginx -t; then
    [ -f "$SITE.prev" ] && mv -f "$SITE.prev" "$SITE"
    echo "nginx rejected the new site; the previous one is back in place" >&2
    exit 1
fi
rm -f "$SITE.prev"
systemctl enable nginx
systemctl restart nginx

# ---- the kiosk and the theme service ----------------------------------------------
log "services"
install -m 755 "$HERE/config/retro-tv-kiosk.sh" /usr/local/bin/retro-tv-kiosk.sh
install -m 755 "$HERE/config/retro-tv-themed.py" /usr/local/bin/retro-tv-themed.py
install -m 644 "$HERE/config/retro-tv.service" /etc/systemd/system/retro-tv.service
install -m 644 "$HERE/config/retro-tv-themed.service" /etc/systemd/system/retro-tv-themed.service
# Network keeper: Wi-Fi profiles restored from the boot partition, a check every minute.
install -m 755 "$HERE/config/retro-tv-net.sh" /usr/local/bin/retro-tv-net.sh
install -m 644 "$HERE/config/retro-tv-net-restore.service" "$HERE/config/retro-tv-net-check.service" \
    "$HERE/config/retro-tv-net-check.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable retro-tv-themed.service retro-tv.service retro-tv-net-restore.service retro-tv-net-check.timer
/usr/local/bin/retro-tv-net.sh restore
systemctl start retro-tv-net-check.timer
systemctl disable getty@tty1.service >/dev/null 2>&1 || true
systemctl set-default graphical.target

# ---- boot splash -------------------------------------------------------------------
log "plymouth theme"
mkdir -p /usr/share/plymouth/themes/retro-tv
install -m 644 "$HERE"/config/plymouth/retro-tv/* /usr/share/plymouth/themes/retro-tv/
systemctl restart retro-tv-themed.service        # points current-*.png at the chosen theme
plymouth-set-default-theme -R retro-tv           # -R: also rebuild the initramfs, if there is one

# ---- IR remote and game controllers --------------------------------------------------
log "IR key map, input rules"
mkdir -p /etc/rc_keymaps
install -m 644 "$HERE/config/rc_keymaps/retro-tv-mce.toml" /etc/rc_keymaps/
grep -q retro-tv-mce /etc/rc_maps.cfg 2>/dev/null || printf '*\trc-rc6-mce\tretro-tv-mce.toml\n' >> /etc/rc_maps.cfg
# Game controllers are read by the viewer itself (the browser's gamepad
# support); the compositor must not treat them as pointers, or it draws a cursor.
install -m 644 "$HERE/config/udev/90-retro-tv-input.rules" /etc/udev/rules.d/
udevadm control --reload
udevadm trigger --subsystem-match=input || true

# ---- display --------------------------------------------------------------------------
# Kernel command line: the video mode with the CRT margins, no boot text, no
# cursor. config.txt: no rainbow square; composite output when asked for.
log "display: $DISPLAY_MODE (margins L$MARGIN_LEFT R$MARGIN_RIGHT T$MARGIN_TOP B$MARGIN_BOTTOM)"
CMD=$BOOT/cmdline.txt
CONF=$BOOT/config.txt
cp -n "$CMD" "$CMD.before-retro-tv" 2>/dev/null || true
cp -n "$CONF" "$CONF.before-retro-tv" 2>/dev/null || true
margins="margin_left=$MARGIN_LEFT,margin_right=$MARGIN_RIGHT,margin_top=$MARGIN_TOP,margin_bottom=$MARGIN_BOTTOM"
# Both HDMI ports get the mode, so the cable can be in either.
case "$DISPLAY_MODE" in
    hdmi480)   video="video=HDMI-A-1:640x480@60,$margins video=HDMI-A-2:640x480@60,$margins" ;;   # no "D": that would force an empty port on
    composite) video="video=Composite-1:720x480@60ie,$margins" ;;
esac
line=$(tr -d '\n' < "$CMD" | sed -E 's/ ?(video=[^ ]+|quiet|splash|plymouth\.ignore-serial-consoles|logo\.nologo|consoleblank=[0-9]+|vt\.global_cursor_default=[0-9]+)//g')
printf '%s %s quiet splash plymouth.ignore-serial-consoles logo.nologo consoleblank=0 vt.global_cursor_default=0\n' "$line" "$video" | tr -s ' ' > "$CMD"

python3 - "$CONF" "$DISPLAY_MODE" <<'PY'
import re, sys
path, mode = sys.argv[1:3]
text = open(path, encoding="utf-8").read()
# the KMS overlay line gets the composite parameter, or loses it
want = "dtoverlay=vc4-kms-v3d,composite" if mode == "composite" else "dtoverlay=vc4-kms-v3d"
text, n = re.subn(r"^dtoverlay=vc4-kms-v3d.*$", want, text, flags=re.M)
if n == 0:
    text = text.rstrip("\n") + "\n" + want + "\n"
# our own block, replaced whole
text = re.sub(r"\n# >>> retro-tv.*?# <<< retro-tv\n", "\n", text, flags=re.S)
# No hdmi_force_hotplug: it makes an empty HDMI port look connected, and the
# compositor then spreads the screen across a phantom output and the real one.
block = ["# >>> retro-tv (written by pi-image/setup.sh)", "disable_splash=1"]
if mode == "composite":
    block.append("enable_tvout=1")
block.append("# <<< retro-tv")
open(path, "w", encoding="utf-8").write(text.rstrip("\n") + "\n" + "\n".join(block) + "\n")
PY

# ---- Tailscale (optional) ------------------------------------------------------------
if [ "$TAILSCALE" = 1 ] && ! command -v tailscale >/dev/null 2>&1; then
    log "tailscale"
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "Sign in once with: sudo tailscale up --accept-routes"
fi

log "done"
echo "Reboot to start the box:  sudo reboot"
echo "Logs: journalctl -u retro-tv -u retro-tv-themed -u nginx"

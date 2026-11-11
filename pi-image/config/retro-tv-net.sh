#!/bin/bash
# Retro TV box: keep the network up on a headless Pi. Two jobs, run as root.
#
#   retro-tv-net.sh restore   At boot, before NetworkManager. Makes sure the Wi-Fi
#                             networks from Imager's settings (network-config on the
#                             boot partition) exist as NetworkManager profiles, and
#                             adds WIFI_EXTRA_SSID from /etc/retro-tv.env, if set, as
#                             a preferred network with the same password. Nothing is
#                             touched when the profiles are already there.
#   retro-tv-net.sh check     Every minute (retro-tv-net-check.timer). Writes what the
#                             box is connected through to /run/retro-tv/net.json, which
#                             the viewer shows on its settings screen (/pi/net). On
#                             Wi-Fi it pings the gateway: after two failed checks the
#                             radio is reconnected, after six the box reboots. If the
#                             network is still gone after that reboot, the next one
#                             waits 30 minutes and every later one two hours, so a
#                             router that is off overnight costs a few reboots, not
#                             one every ten minutes.
#
# Why: NetworkManager keeps its profiles in files it rewrites whenever a network
# connects. One box lost its only Wi-Fi profile to a power cut during such a
# rewrite and came up with no network at all, with nothing on screen to say so.
# The boot partition is FAT and is not rewritten, so it is the durable source.
set -u
NC=/boot/firmware/network-config
[ -f "$NC" ] || NC=/boot/network-config
PROFILES=/etc/NetworkManager/system-connections
STATE_DIR=/run/retro-tv
STATUS=$STATE_DIR/net.json
FAILS=$STATE_DIR/net.fails
REBOOTS=/data/retro-tv/net.reboots     # watchdog reboots in a row; on disk, so it outlives them
WIFI_EXTRA_SSID=
[ -r /etc/retro-tv.env ] && . /etc/retro-tv.env

log() { logger -t retro-tv-net "$*"; echo "$*"; }

restore() {
    [ -f "$NC" ] || { log "no $NC; nothing to restore"; return 0; }
    python3 - "$NC" "$PROFILES" "$WIFI_EXTRA_SSID" <<'PY'
import os, sys, uuid
import yaml

nc, profiles, extra = sys.argv[1:4]
cfg = yaml.safe_load(open(nc)) or {}
wifis = (cfg.get("network") or {}).get("wifis") or {}
aps = {}
for iface in wifis.values():
    for ssid, data in (iface.get("access-points") or {}).items():
        psk = (data or {}).get("password")
        if psk:
            aps[ssid] = psk
if not aps:
    print("retro-tv-net: no Wi-Fi networks in", nc)
    sys.exit(0)

# The extra network takes the first network's password and is tried first.
wanted = [(ssid, psk, 0) for ssid, psk in aps.items()]
if extra and extra not in aps:
    wanted.append((extra, next(iter(aps.values())), 10))

def keyfile(name, ssid, psk, prio):
    return "\n".join([
        "[connection]", "id=%s" % name, "uuid=%s" % uuid.uuid5(uuid.NAMESPACE_DNS, "retro-tv:" + ssid),
        "type=wifi", "interface-name=wlan0", "autoconnect=true", "autoconnect-priority=%d" % prio, "",
        "[wifi]", "mode=infrastructure", "ssid=%s" % ssid, "powersave=2", "",
        "[wifi-security]", "key-mgmt=wpa-psk", "psk=%s" % psk, "",
        "[ipv4]", "method=auto", "route-metric=600", "",
        "[ipv6]", "method=auto", "addr-gen-mode=default", "",
    ])

os.makedirs(profiles, mode=0o755, exist_ok=True)
made = 0
for i, (ssid, psk, prio) in enumerate(wanted):
    name = "retro-tv-wifi-%d" % (i + 1)
    path = os.path.join(profiles, name + ".nmconnection")
    if os.path.exists(path):
        continue
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(keyfile(name, ssid, psk, prio))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    made += 1
    print("retro-tv-net: restored Wi-Fi profile %s for %r" % (name, ssid))
if made:
    fd = os.open(profiles, os.O_RDONLY)
    os.fsync(fd)
    os.close(fd)
    os.system("nmcli connection reload >/dev/null 2>&1")
PY
}

write_status() {   # path ssid band signal loss fails
    mkdir -p "$STATE_DIR"; chmod 755 "$STATE_DIR"
    printf '{"path":"%s","ssid":"%s","band":"%s","signal":%s,"loss":%s,"fails":%s,"time":%s}\n' \
        "$1" "${2//\"/\\\"}" "$3" "${4:-null}" "${5:-null}" "${6:-0}" "$(date +%s)" > "$STATUS.tmp"
    chmod 644 "$STATUS.tmp"; mv -f "$STATUS.tmp" "$STATUS"
}

check() {
    local dev gw fails=0 ssid="" freq=0 signal="" band="" lost=""
    dev=$(ip -o route show default 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i == "dev") print $(i + 1); exit }')
    gw=$(ip -o route show default 2>/dev/null | awk '{ for (i = 1; i <= NF; i++) if ($i == "via") print $(i + 1); exit }')
    [ -f "$FAILS" ] && fails=$(cat "$FAILS")
    if [ -z "$dev" ]; then
        write_status none "" "" null null "$fails"
        fails=$((fails + 1)); echo "$fails" > "$FAILS"
        log "no default route (check $fails)"
        if [ "$fails" -ge 2 ]; then nmcli radio wifi off; sleep 2; nmcli radio wifi on; fi
    elif [ "$dev" != wlan0 ]; then
        write_status wired "" "" null 0 0
        echo 0 > "$FAILS"
        [ -e "$REBOOTS" ] && rm -f "$REBOOTS"
        return 0
    else
        # the active network, from the last scan (no new scan: it would stall the stream)
        IFS=: read -r ssid freq signal <<< "$(nmcli -t -f ACTIVE,SSID,FREQ,SIGNAL dev wifi list --rescan no 2>/dev/null | awk -F: '$1 == "yes" { print $2 ":" $3 ":" $4; exit }')"
        freq=${freq% MHz}
        case "$freq" in 2*) band="2.4 GHz" ;; 5*) band="5 GHz" ;; 6*) band="6 GHz" ;; *) band="" ;; esac
        lost=$(ping -I wlan0 -c 5 -i 0.3 -W 1 "$gw" 2>/dev/null | grep -oE '[0-9]+% packet loss' | cut -d% -f1)
        [[ "$lost" =~ ^[0-9]+$ ]] || lost=100
        if [ "$lost" -ge 100 ]; then
            fails=$((fails + 1)); echo "$fails" > "$FAILS"
            write_status wifi "$ssid" "$band" "${signal:-null}" "$lost" "$fails"
            log "Wi-Fi $ssid ($band, ${signal:-?}%): gateway unreachable (check $fails)"
            if [ "$fails" -eq 2 ] || [ "$fails" -eq 4 ] || [ $((fails % 10)) -eq 0 ]; then
                log "reconnecting the radio"
                nmcli device disconnect wlan0 >/dev/null 2>&1; sleep 2; nmcli device connect wlan0 >/dev/null 2>&1
            fi
        else
            [ "$fails" -gt 0 ] && log "Wi-Fi $ssid ($band, ${signal:-?}%): back, $lost% loss"
            [ $(( $(date +%M) % 10 )) -eq 0 ] && log "Wi-Fi $ssid ($band, ${signal:-?}%), $lost% loss to the gateway"
            write_status wifi "$ssid" "$band" "${signal:-null}" "$lost" 0
            echo 0 > "$FAILS"
            [ -e "$REBOOTS" ] && rm -f "$REBOOTS"
            return 0
        fi
    fi
    # Six failed minutes in a row, and not just booted: start over. A reboot that
    # did not bring the network back is not worth repeating every ten minutes, so
    # the wait grows: 6 minutes, then 30, then 120 for every one after.
    local reboots=0 limit=6
    [ -f "$REBOOTS" ] && reboots=$(cat "$REBOOTS" 2>/dev/null)
    [[ "$reboots" =~ ^[0-9]+$ ]] || reboots=0
    case "$reboots" in 0) limit=6 ;; 1) limit=30 ;; *) limit=120 ;; esac
    if [ "$fails" -ge "$limit" ] && [ "$(cut -d. -f1 /proc/uptime)" -ge 600 ]; then
        log "no network for $fails minutes: rebooting (reboot $((reboots + 1)) in a row)"
        echo 0 > "$FAILS"
        mkdir -p "${REBOOTS%/*}" && echo $((reboots + 1)) > "$REBOOTS" && sync
        systemctl reboot
    fi
}

case "${1:-}" in
    restore) restore ;;
    check)   check ;;
    *) echo "usage: $0 restore|check" >&2; exit 2 ;;
esac

# Watch beacons (see docker/README.md, "Watch beacons"). TRACKER_URL, where
# browsers reach the channel tracker, becomes
#  - "tracker": {"url": "<origin>"} in /config.json, for js/beacon.js, and
#  - <origin> in the Content-Security-Policy's connect-src.
# Unset or empty: neither, and the viewer sends no beacons.
#
# TRACKER_URL=https://tracker.example   (scheme, host, optional port; no path)
#
# Sourced by ../config.envsh; the rules for a piece are at its top.

_tracker_url=${TRACKER_URL:-}
while :; do
  case $_tracker_url in */) _tracker_url=${_tracker_url%/} ;; *) break ;; esac
done
if [ -n "$_tracker_url" ]; then
  # Only the characters an origin can have: this rules out a second line,
  # quotes, spaces and backslashes before the shape is checked (grep would
  # pass a value of which any one line matches), so nothing here can break
  # /config.json or the CSP header.
  case $_tracker_url in
    *[!]A-Za-z0-9.:/[-]*) _tracker_ok= ;;
    *) _tracker_ok=1 ;;
  esac
  if [ -n "$_tracker_ok" ] && grep -Eq '^https?://([A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(:[0-9]{1,5})?$' <<_TRACKER_EOF
$_tracker_url
_TRACKER_EOF
  then
    _tracker_url=$(printf '%s' "$_tracker_url" | tr 'A-Z' 'a-z')
    config_set tracker "{\"url\": \"$_tracker_url\"}"
    csp_connect "$_tracker_url"
    echo "tracker: watch beacons go to $_tracker_url" >&2
  else
    echo "tracker: skipped TRACKER_URL: not a plain http(s)://host[:port]" >&2
  fi
fi
unset _tracker_url _tracker_ok

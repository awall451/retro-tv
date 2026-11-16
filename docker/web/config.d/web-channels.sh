# Web channels (see docker/README.md, "Web channels"): WEB_CHANNELS ->
#  - "webChannels" in /config.json, the channel number -> page URL map
#    js/web.js reads, and
#  - the CSP's frame-src, one origin (scheme, host, port) per site.
#
# WEB_CHANNELS="192=https://weather.example/?kiosk=true;193=https://cam.example/"
# Entries are separated by ";" or white space. A URL must start with
# http:// or https://, or be a path on the viewer itself starting with a
# single "/" (WEB_CHANNELS="7=/tvguide.html?tv&promo=7"; frame-src 'self'
# already covers it). It must be plain ASCII without control characters,
# quotes, backslashes, < or > (percent-encode them), so it goes into the
# JSON as it is. A site's host must be a name or an IPv4 address: a frame
# policy cannot name an IPv6 address ([fd00::7]), so give the site a host
# name. A bad entry is skipped with a warning; a channel listed twice keeps
# the last one, and only the sites of the entries kept reach frame-src.
#
# The awk prints "frame <origin>" lines and one "json <object>" line.

_wc_out=$(
  WEB_CHANNELS=${WEB_CHANNELS:-} LC_ALL=C awk '
    function warn(msg) { printf "web-channels: %s\n", msg > "/dev/stderr" }
    function bad(num) { warn("skipped channel " num ": not a plain http(s) URL or /path") }
    BEGIN {
      k = 0
      n = split(ENVIRON["WEB_CHANNELS"], entries, /[;[:space:]]+/)
      for (i = 1; i <= n; i++) {
        e = entries[i]
        if (e == "") continue
        eq = index(e, "=")
        num = substr(e, 1, eq - 1); url = substr(e, eq + 1)
        if (eq < 2 || num !~ /^[0-9]+(\.[0-9]+)?$/) {
          shown = e; gsub(/[^!-~]/, "?", shown)
          warn("skipped \"" shown "\": not <channel number>=<url>"); continue
        }
        # Anything JSON would need escaped (and anything that is not plain
        # ASCII) is left out, so one bad entry cannot spoil the whole file.
        if (url == "" || url ~ /[^!-~]/ || url ~ /["\\<>'\'']/) { bad(num); continue }
        if (url ~ /^\/([^\/]|$)/) {
          origin = ""                       # a page on the viewer itself: self
        } else {
          if (!match(url, /^[Hh][Tt][Tt][Pp][Ss]?:\/\/[^\/?#]+/)) { bad(num); continue }
          origin = tolower(substr(url, 1, RLENGTH))
          if (origin ~ /^https?:\/\/\[/) {
            warn("skipped channel " num ": a frame policy cannot allow an IPv6 address (" origin "); use a host name for it")
            continue
          }
          if (origin !~ /^https?:\/\/[a-z0-9.-]+(:[0-9]+)?$/) { warn("skipped channel " num ": odd host in " origin); continue }
        }
        if (num in page) warn("channel " num " is listed twice; the last one wins")
        else order[++k] = num
        page[num] = url; site[num] = origin
      }
      # The sites come from the map as it ends up, so a replaced entry
      # leaves nothing behind in frame-src.
      json = ""; origins = " "
      for (i = 1; i <= k; i++) {
        num = order[i]
        json = json (json == "" ? "" : ", ") "\"" num "\": \"" page[num] "\""
        if (site[num] != "" && !index(origins, " " site[num] " ")) {
          origins = origins site[num] " "
          print "frame " site[num]
        }
      }
      if (k) {
        print "json {" json "}"
        printf "web-channels: %d channel(s), frames allowed from self%s\n", k, substr(origins, 1, length(origins) - 1) > "/dev/stderr"
      }
    }'
) || _wc_out=

while IFS= read -r _wc_line; do
  case $_wc_line in
    'frame '*) csp_frame "${_wc_line#frame }" ;;
    'json '*) config_set webChannels "${_wc_line#json }" ;;
  esac
done <<EOF
$_wc_out
EOF
unset _wc_out _wc_line

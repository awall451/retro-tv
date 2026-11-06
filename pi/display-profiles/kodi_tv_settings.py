#!/usr/bin/env python3
"""Live-TV settings for Kodi, the same in both display profiles. Kodi must not be running
(it rewrites these files when it exits). Run by apply.sh; safe to run again.

- epg.selectaction = 1: Select (Cross / A) on a show in the guide switches straight to the
  channel. Square opens the show details instead (keymaps/livetv-controller.xml).
- epg.epgupdate = 15: Kodi asks for new guide data every 15 minutes (default 120).
- IPTV Simple reloads the channel list and guide from ErsatzTV every 15 minutes
  (m3uRefreshMode 1 = repeated), so a rebuilt schedule shows up within 15 minutes.
- installs the live-TV controller keymap.
- hides the server's HD twins (channels 101+, group "HD", made for the browser viewer): IPTV
  Simple loads only the channel groups named in a custom groups file, and this script writes
  that file as "every group in ErsatzTV's channel list except HD". A normal channel put in a
  new group is therefore still shown; only the HD group is left out.

With --groups it only refreshes the groups file. /userdata/system/scripts/kodi-channel-groups.sh
runs it that way at every Kodi launch, so a new group on the server shows at the next launch.
"""
import html, os, re, shutil, sys, urllib.request

KODI = "/userdata/system/.kodi/userdata"
HERE = "/userdata/system/display-profiles"
IPTV = os.path.join(KODI, "addon_data/pvr.iptvsimple/instance-settings-1.xml")
GROUPS_FILE = os.path.join(KODI, "addon_data/pvr.iptvsimple/channelGroups/customTVGroups-retro-tv.xml")
HIDDEN_GROUPS = {"HD"}


def set_settings(path, values):
    if not os.path.exists(path):
        print("skip (missing): %s" % path)
        return
    text = open(path, encoding="utf-8").read()
    for key, value in values.items():
        new = '<setting id="%s">%s</setting>' % (key, value)
        pattern = r'<setting id="%s"(?: [^>]*)?(?:/>|>[^<]*</setting>)' % re.escape(key)
        text, n = re.subn(pattern, new, text)
        if n == 0:  # not written yet: add it before the closing tag
            text = re.sub(r'(\s*)</settings>\s*$', r'\1    %s\1</settings>\n' % new, text)
    open(path, "w", encoding="utf-8").write(text)
    print("set %s in %s" % (", ".join("%s=%s" % kv for kv in values.items()), path))


def server_groups():
    """Group names in ErsatzTV's channel list, or None if the server can't be read."""
    m = re.search(r'<setting id="m3uUrl"[^>]*>([^<]+)<', open(IPTV, encoding="utf-8").read())
    if not m:
        return None
    try:
        with urllib.request.urlopen(html.unescape(m.group(1)), timeout=5) as r:
            m3u = r.read().decode("utf-8", "replace")
    except Exception as e:
        print("channel list not readable (%s)" % e)
        return None
    groups = set()
    for value in re.findall(r'group-title="([^"]*)"', m3u):
        groups.update(g.strip() for g in value.split(";") if g.strip())  # IPTV Simple splits on ;
    return groups


def write_groups():
    """Custom groups file = every server group except HIDDEN_GROUPS; mode = custom groups."""
    if not os.path.exists(IPTV):
        print("skip (missing): %s" % IPTV)
        return
    groups = server_groups()
    if groups is None:
        if os.path.exists(GROUPS_FILE):
            print("kept %s" % GROUPS_FILE)
            return
        groups = {"ErsatzTV"}  # first run with the server down: ErsatzTV's default group
    keep = sorted(groups - HIDDEN_GROUPS)
    os.makedirs(os.path.dirname(GROUPS_FILE), exist_ok=True)
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        f.write("<!-- Written by display-profiles/kodi_tv_settings.py: every group in ErsatzTV's\n"
                "     channel list except %s. Rewritten at every Kodi launch. -->\n"
                "<customChannelGroups>\n" % ", ".join(sorted(HIDDEN_GROUPS)))
        for g in keep:
            f.write("  <channelGroupName>%s</channelGroupName>\n" % html.escape(g))
        f.write("</customChannelGroups>\n")
    print("channel groups shown: %s" % ", ".join(keep))
    set_settings(IPTV, {
        "tvGroupMode": "2",  # custom groups
        "customTvGroupsFile": "special://userdata/addon_data/pvr.iptvsimple/channelGroups/"
                              + os.path.basename(GROUPS_FILE)})


write_groups()
if "--groups" in sys.argv:
    sys.exit(0)

set_settings(os.path.join(KODI, "guisettings.xml"),
             {"epg.selectaction": "1", "epg.epgupdate": "15"})
set_settings(IPTV, {"m3uRefreshMode": "1", "m3uRefreshIntervalMins": "15"})

os.makedirs(os.path.join(KODI, "keymaps"), exist_ok=True)
shutil.copy(os.path.join(HERE, "kodi-skin/livetv-controller.xml"),
            os.path.join(KODI, "keymaps/livetv-controller.xml"))
print("installed keymaps/livetv-controller.xml")

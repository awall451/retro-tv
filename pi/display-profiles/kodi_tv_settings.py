#!/usr/bin/env python3
"""Live-TV settings for Kodi, the same in both display profiles. Kodi must not be running
(it rewrites these files when it exits). Run by apply.sh; safe to run again.

- epg.selectaction = 1: Select (Cross / A) on a show in the guide switches straight to the
  channel. Square opens the show details instead (keymaps/livetv-controller.xml).
- epg.epgupdate = 15: Kodi asks for new guide data every 15 minutes (default 120).
- IPTV Simple reloads the channel list and guide from ErsatzTV every 15 minutes
  (m3uRefreshMode 1 = repeated), so a rebuilt schedule shows up within 15 minutes.
- installs the live-TV controller keymap.
- loads every channel group from ErsatzTV (tvGroupMode 0), the server's HD twins (channels
  1001+, group "HD") included, and shows the server's channel numbers. The retro skin's guide opens on the Standard or the HD group
  from its Quality setting (make_kodi_skin.sh); Kodi's own channel list shows both.
"""
import os, re, shutil

KODI = "/userdata/system/.kodi/userdata"
HERE = "/userdata/system/display-profiles"
IPTV = os.path.join(KODI, "addon_data/pvr.iptvsimple/instance-settings-1.xml")
GROUPS_FILE = os.path.join(KODI, "addon_data/pvr.iptvsimple/channelGroups/customTVGroups-retro-tv.xml")


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


set_settings(IPTV, {"tvGroupMode": "0"})  # all groups
if os.path.exists(GROUPS_FILE):
    os.remove(GROUPS_FILE)
    print("removed %s (every group is loaded now)" % GROUPS_FILE)

set_settings(os.path.join(KODI, "guisettings.xml"),
             {"epg.selectaction": "1", "epg.epgupdate": "15",
              # channel numbers as the server sends them (the HD twins are 1001+), not Kodi's own count
              "pvrmanager.usebackendchannelnumbers": "true"})
set_settings(IPTV, {"m3uRefreshMode": "1", "m3uRefreshIntervalMins": "15"})

os.makedirs(os.path.join(KODI, "keymaps"), exist_ok=True)
shutil.copy(os.path.join(HERE, "kodi-skin/livetv-controller.xml"),
            os.path.join(KODI, "keymaps/livetv-controller.xml"))
print("installed keymaps/livetv-controller.xml")

#!/bin/sh
# Wallpaper library (fw-wallpaper, Settings → Appearance): create ~/Pictures/Wallpapers and, when an old
# ~/.config/hypr/wallpaper.jpg exists (else the first library picture) and none is current yet, adopt it and render the desktop/lock images
# (~/.config/fw13/theme/desktop.jpg, lock.jpg) that hyprpaper/hyprlock read. No desktop needed (CI container):
# fw13.wallpaper.init() restarts and reloads nothing. With no picture, those images stay absent and
# hyprpaper/hyprlock show plain colours. Skipped when the module is missing; never fails the apply.
python3 -c '
import os, sys
sys.path.insert(0, os.path.expanduser("~/.local/lib"))
try:
    from fw13 import wallpaper
except ImportError:
    sys.exit(0)
init = getattr(wallpaper, "init", None)
if callable(init):
    err = init()
    if err:
        print("wallpaper-init:", err, file=sys.stderr)
' || true
exit 0

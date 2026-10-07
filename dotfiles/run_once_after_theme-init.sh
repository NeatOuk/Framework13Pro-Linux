#!/bin/sh
# Theme (Settings → Appearance): colours follow the wallpaper (matugen) or stay Tokyo Night.
# chezmoi seeds ~/.config/fw13/theme/ with Tokyo Night (create_ files), so a desktop is not needed here
# (CI container). Only make sure the store names a source: fw13.theme.init() sets "tokyo-night" if unset
# and never reloads apps. Skipped when that function is missing; never fails the apply.
python3 -c '
import os, sys
sys.path.insert(0, os.path.expanduser("~/.local/lib"))
try:
    from fw13 import theme
except ImportError:
    sys.exit(0)
init = getattr(theme, "init", None)
if callable(init):
    init()
' || true
exit 0

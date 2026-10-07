#!/bin/sh
# GTK and Qt apps follow the desktop palette (fw13.theme, Settings → Appearance).
# fw13.theme.init() writes ~/.config/fw13/theme/{gtk3.css,gtk4.css,qt6ct-colors.conf} from the current palette
# (not chezmoi seeds: an install already following the wallpaper must not start with Tokyo Night GTK/Qt colours;
# for that case all files are rewritten from the stored palette below) and the "fw13" GTK theme
# (~/.local/share/themes/fw13: adw-gtk3 + our colours). ~/.config/qt6ct/qt6ct.conf (chezmoi) points at the Qt file.
# Hyprland session only (the files and keys below are per user, so GNOME/KDE sessions would see them too):
#   ~/.config/gtk-4.0/gtk.css @imports gtk4.css, only if that file is absent or already ours (a user's own
#   gtk.css is left alone, the note is printed); GSettings gtk-theme=fw13 / color-scheme, only with a D-Bus
#   session bus (never in CI), after saving the values they replace (fw13.theme.restore_gtk() puts them back).
# Run from another desktop, these wait for the first Hyprland login (fw13.theme.session_start()).
# Never fails the apply; skipped when fw13.theme is missing.
python3 -c '
import os, sys
sys.path.insert(0, os.path.expanduser("~/.local/lib"))
try:
    from fw13 import theme
except ImportError:
    sys.exit(0)
if not callable(getattr(theme, "session_start", None)):
    sys.exit(0)
note = theme.init()
if theme.state()["source"] != "tokyo-night":
    theme.write(theme.palette(), apply=False)
if note:
    print("gtk-qt-theme:", note)
if os.environ.get("DBUS_SESSION_BUS_ADDRESS") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
    note = theme.apply_gtk(refresh=False)
    if note:
        print("gtk-qt-theme:", note)
' || true
exit 0

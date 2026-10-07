"""Default apps and launcher clean-up for the Hyprland session (no GTK).

GNOME's own apps stay installed (rule 3a: the GNOME session on the same account keeps them) but are hidden from the
launcher inside Hyprland: each gets a copy of its .desktop entry with NoDisplay=true in a Hyprland-only data dir,
~/.local/share/fw13/hyprland/applications, which ~/.config/uwsm/env-hyprland puts first in XDG_DATA_DIRS for the
Hyprland session only (fuzzel ignores NotShowIn/OnlyShowIn, so entries meant for other desktops, such as
"GNOME Settings", are hidden the same way). NoDisplay only hides menu entries: the apps still open files. GNOME's viewers
still open files: defaults go in ~/.config/hyprland-mimeapps.list, which freedesktop/GIO read only when
XDG_CURRENT_DESKTOP is Hyprland (GNOME keeps its own defaults). Thunar opens folders, Chromium opens web links.

Run at every Hyprland start (autostart.lua) and by chezmoi when this file changes, so a package update or a newly
installed GNOME app is picked up; files we wrote carry MARK and are rewritten, anything else is the user's and is
left alone. A default the user picks themselves (Thunar "Open With → Set as default", written to
~/.config/mimeapps.list by GIO) wins: that type is left out of our list from the next run on.

  python3 -m fw13.defaultapps          apply (quiet)
  python3 -m fw13.defaultapps --show   apply and print what was hidden and which defaults were set
"""
import os
import sys

MARK = "X-FW13-Generated=true"
HEAD = "# Written by fw13.defaultapps at Hyprland login (GNOME apps hidden in Hyprland only). Do not edit:"
SYSTEM_DIRS = ["/usr/local/share/applications", "/usr/share/applications"]
USER_DIR = os.path.expanduser("~/.local/share/applications")           # the user's own entries (all desktops)
HYPR_DATA = os.path.expanduser("~/.local/share/fw13/hyprland")            # in XDG_DATA_DIRS for Hyprland only
HYPR_DIR = os.path.join(HYPR_DATA, "applications")
CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
MIMEAPPS = os.path.join(CONFIG, "hyprland-mimeapps.list")
USER_MIMEAPPS = os.path.join(CONFIG, "mimeapps.list")

# Hidden in Hyprland: every org.gnome.* app, plus GNOME Workstation helpers that only make sense in GNOME.
HIDE_PREFIXES = ("org.gnome.",)
HIDE_IDS = {"org.freedesktop.MalcontentControl.desktop", "rygel-preferences.desktop"}

# (desktop id, MIME types or None = the app's own MimeType= list). Earlier entries win a type.
WEB = ["x-scheme-handler/http", "x-scheme-handler/https", "x-scheme-handler/about", "x-scheme-handler/unknown",
       "text/html", "application/xhtml+xml"]
DEFAULTS = [
    ("thunar.desktop", ["inode/directory"]),
    ("chromium-browser.desktop", WEB),
    ("org.gnome.Loupe.desktop", None),       # pictures
    ("org.gnome.Papers.desktop", None),      # PDF, comics, DjVu
    ("org.gnome.TextEditor.desktop", None),  # text
    ("org.gnome.Showtime.desktop", None),    # video
    ("org.gnome.Decibels.desktop", None),    # music
]


def find(desktop_id):
    """Path of the system .desktop file for `desktop_id` (our own hidden copies don't count), or None."""
    for d in SYSTEM_DIRS:
        p = os.path.join(d, desktop_id)
        if os.path.isfile(p):
            return p
    return None


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def entry_value(text, key):
    """Value of `key` in the [Desktop Entry] group (not Desktop Action groups)."""
    group = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            group = s
        elif group == "[Desktop Entry]" and s.startswith(key + "="):
            return s.split("=", 1)[1]
    return None


def ours(path):
    text = read(path)
    return text is not None and MARK in text


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".fw13-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def hidden_copy(text):
    """The system entry with NoDisplay=true (inside [Desktop Entry]) and our marker."""
    out, group, done = [], None, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            if group == "[Desktop Entry]" and not done:
                out += ["NoDisplay=true", MARK]
                done = True
            group = s
        elif group == "[Desktop Entry]" and s.startswith("NoDisplay="):
            continue  # replaced
        out.append(line)
    if not done:
        out += ["NoDisplay=true", MARK]
    return f"{HEAD} rerun at next login\n" + "\n".join(out) + "\n"


def desktops(value):
    return {v for v in (value or "").split(";") if v}


def should_hide(desktop_id, text):
    """org.gnome.* apps and GNOME helpers, plus anything not meant for Hyprland (fuzzel doesn't filter those)."""
    if entry_value(text, "NoDisplay") == "true" or entry_value(text, "Hidden") == "true":
        return False  # not in any launcher already
    only = desktops(entry_value(text, "OnlyShowIn"))
    if only and "Hyprland" not in only:
        return True
    if "Hyprland" in desktops(entry_value(text, "NotShowIn")):
        return True
    return desktop_id.startswith(HIDE_PREFIXES) or desktop_id in HIDE_IDS


def system_ids():
    ids = set()
    for d in SYSTEM_DIRS:
        try:
            ids.update(n for n in os.listdir(d) if n.endswith(".desktop"))
        except OSError:
            pass
    return sorted(ids)


def hide_apps():
    """Write NoDisplay copies into the Hyprland-only data dir; drop stale ones. Returns the ids hidden now."""
    hidden = []
    for desktop_id in system_ids():
        if os.path.exists(os.path.join(USER_DIR, desktop_id)) and not ours(os.path.join(USER_DIR, desktop_id)):
            continue  # the user's own entry (higher priority than ours anyway): theirs decides
        text = read(find(desktop_id) or "")
        if text is None or not should_hide(desktop_id, text):
            continue
        dst = os.path.join(HYPR_DIR, desktop_id)
        new = hidden_copy(text)
        if read(dst) != new:
            write(dst, new)
        hidden.append(desktop_id)
    for d in (HYPR_DIR, USER_DIR):  # ours, not rewritten now: stale (app removed or taken off the list).
        try:                       # USER_DIR: copies an earlier version wrote there (NotShowIn, ignored by fuzzel)
            for n in os.listdir(d):
                p = os.path.join(d, n)
                if n.endswith(".desktop") and ours(p) and (d == USER_DIR or n not in hidden):
                    os.remove(p)
        except OSError:
            pass
    return hidden


def user_defaults():
    """MIME types the user chose themselves in ~/.config/mimeapps.list [Default Applications]."""
    text = read(USER_MIMEAPPS) or ""
    types, group = set(), None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            group = s
        elif group == "[Default Applications]" and "=" in s and not s.startswith("#"):
            types.add(s.split("=", 1)[0].strip())
    return types


def set_defaults():
    """Write ~/.config/hyprland-mimeapps.list; returns {type: desktop id}."""
    if os.path.exists(MIMEAPPS) and HEAD not in (read(MIMEAPPS) or ""):
        return {}  # the user's own Hyprland list: leave it
    mine = user_defaults()
    chosen = {}
    for desktop_id, types in DEFAULTS:
        path = find(desktop_id)
        text = read(path) if path else None
        if text is None:
            continue  # not installed (KDE, Minimal…): no default for it
        if types is None:
            types = [t for t in (entry_value(text, "MimeType") or "").split(";") if t]
        for t in types:
            if t not in chosen and t not in mine:
                chosen[t] = desktop_id
    body = f"{HEAD} your own choices go in mimeapps.list and win from the next login\n[Default Applications]\n"
    body += "".join(f"{t}={a};\n" for t, a in sorted(chosen.items()))
    if read(MIMEAPPS) != body:
        write(MIMEAPPS, body)
    return chosen


def main(argv):
    hidden = hide_apps()
    chosen = set_defaults()
    if "--show" in argv:
        print(f"Hidden in Hyprland ({len(hidden)}): " + ", ".join(h.removesuffix(".desktop") for h in hidden))
        by_app = {}
        for t, a in chosen.items():
            by_app.setdefault(a, []).append(t)
        for a, ts in by_app.items():
            print(f"{a}: {len(ts)} types (e.g. {', '.join(sorted(ts)[:4])})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Desktop colours: Tokyo Night, or a palette generated from the wallpaper with matugen.

The base configs (hypr theme.lua, hyprlock.conf, waybar style.css, fuzzel.ini, mako, kitty.conf) hold no colours;
they include the files this module writes into ~/.config/fw13/theme/. chezmoi seeds those once (create_) with
render(TOKYO_NIGHT), so a fresh install looks the same as before.

GTK and Qt apps follow too (read at app start; GTK 3 also live, see apply_gtk()):
  gtk3.css / gtk4.css   libadwaita named colours (@define-color; gtk4.css also the --*-color variables). GTK 3 and
                        plain GTK 4 apps get them through the "fw13" GTK theme in ~/.local/share/themes/fw13, which
                        is adw-gtk3[-dark] plus gtk3.css/gtk4.css; libadwaita apps ignore GTK themes and read
                        ~/.config/gtk-4.0/gtk.css, which @imports gtk4.css (only when that file is ours, see
                        link_gtk()).
  qt6ct-colors.conf     qt6ct colour scheme; ~/.config/qt6ct/qt6ct.conf points at it and ~/.config/uwsm/env-hyprland
                        sets QT_QPA_PLATFORMTHEME=qt6ct for the Hyprland session only (new Qt apps after re-login).
These three are not chezmoi seeds: ensure_files() (init(), run_once) writes them from the current palette, so an
upgrade of a wallpaper-following install does not start out with Tokyo Night GTK/Qt colours.

Other desktops on the same account (Fedora Workstation/KDE bases, CLAUDE.md 3a): gtk-theme and color-scheme
(org.gnome.desktop.interface, dconf) and ~/.config/gtk-4.0/gtk.css are per user, not per session. So they are only
set from a Hyprland session, the values they replace are saved first (store key GTK_SAVED), and session_end() /
restore_gtk() put them back and remove our gtk-4.0/gtk.css; session_start() re-applies at the next Hyprland login
(`python3 -m fw13.theme session-start|session-end`). Until a session_end() runs (e.g. after a crash), GNOME shows
the fw13 GTK theme and our light/dark choice; KDE resets gtk-theme itself at Plasma login.

State lives in fw13.store under "theme":
  {"source": "tokyo-night" | "wallpaper", "mode": "dark" | "light", "type": "scheme-tonal-spot",
   "wallpaper": path, "palette": {...last generated}}
Palette values are "#rrggbb" ("shadow" is "#rrggbbaa"); "ansi" is the 16 terminal colours.
"""
import colorsys
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import store
from .hypr import lua

DIR = os.path.expanduser("~/.config/fw13/theme")
SOURCES = ("tokyo-night", "wallpaper")
MODES = ("dark", "light")
TYPES = ("scheme-tonal-spot", "scheme-content", "scheme-expressive", "scheme-vibrant", "scheme-neutral",
         "scheme-monochrome", "scheme-fidelity", "scheme-rainbow", "scheme-fruit-salad")
DEFAULT_TYPE = "scheme-tonal-spot"

TOKYO_NIGHT = {
    "bg": "#1a1b26", "bg_dim": "#16161e",
    "surface": "#1f2335", "surface2": "#292e42", "surface3": "#3b4261",
    "fg": "#a9b1d6", "fg_bright": "#c0caf5", "fg_dim": "#565f89", "muted": "#414868",
    "accent": "#7aa2f7", "accent2": "#bb9af7",
    "ok": "#9ece6a", "warn": "#e0af68", "bad": "#f7768e",
    "border": "#7aa2f7", "shadow": "#1a1a1aee",
    "ansi": ["#15161e", "#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6",
             "#414868", "#ff7a93", "#b9f27c", "#ff9e64", "#7da6ff", "#bb9af7", "#0db9d7", "#c0caf5"],
}
ROLES = tuple(k for k in TOKYO_NIGHT if k != "ansi")


# ---- colour maths -------------------------------------------------------------------------------------------

def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(min(max(v, 0.0), 1.0) * 255):02x}" for v in rgb)


def _lum(c):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    """WCAG 2 contrast ratio (1–21)."""
    a, b = sorted((_lum(fg[:7]), _lum(bg[:7])), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _hsl(c):
    h, li, s = colorsys.rgb_to_hls(*_rgb(c))
    return h * 360, s, li


def _from_hsl(h, s, li):
    return _hex(colorsys.hls_to_rgb((h % 360) / 360, li, s))


def ensure(fg, bg, ratio):
    """`fg` with its HSL lightness moved away from `bg` until contrast(fg, bg) >= ratio (or it can't go further)."""
    if contrast(fg, bg) >= ratio:
        return fg
    h, s, li = _hsl(fg)
    step = 0.01 if _lum(bg) < 0.18 else -0.01  # dark background: lighten; light: darken
    out = fg
    while 0.0 <= li <= 1.0 and contrast(out, bg) < ratio:
        li += step
        out = _from_hsl(h, s, min(max(li, 0.0), 1.0))
    return out


# Minimum contrast against bg for each role that is read as text or as an accent line. muted (inactive
# workspace numbers, inactive borders) is meant to recede: 2 keeps it about as visible as Tokyo Night's (1.9);
# matugen's light outline_variant is ~1.6 without it.
MIN_CONTRAST = {"fg": 4.5, "fg_bright": 4.5, "accent": 3, "accent2": 3, "ok": 4.5, "warn": 4.5, "bad": 4.5,
                "border": 3, "muted": 2}


def adjust(p):
    """A copy of palette `p` meeting MIN_CONTRAST against p["bg"]. Only for matugen palettes: Tokyo Night is
    shipped as is."""
    out = dict(p)
    for role, ratio in MIN_CONTRAST.items():
        out[role] = ensure(out[role], out["bg"], ratio)
    return out


def _harmonize(c, toward, limit=15.0):
    """Rotate the hue of `c` toward `toward` by half the difference, at most `limit` degrees (Material-style)."""
    h, s, li = _hsl(c)
    d = (_hsl(toward)[0] - h + 180) % 360 - 180
    return _from_hsl(h + max(-limit, min(limit, d / 2)), s, li)


def _hue_near(c, hue, tol):
    h, s, _ = _hsl(c)
    return s > 0.2 and abs((h - hue + 180) % 360 - 180) <= tol


def _dark(p):
    return _lum(p["bg"]) < 0.18


def _on(c, p):
    """Text colour for a fill of `c`: the palette's bg or fg_bright, whichever reads better."""
    return max((p["bg"], p["fg_bright"]), key=lambda t: contrast(t, c))


def _shade(c, d):
    """`c` with its HSL lightness moved by `d` (-1..1)."""
    h, s, li = _hsl(c)
    return _from_hsl(h, s, min(max(li + d, 0.0), 1.0))


# ---- matugen ------------------------------------------------------------------------------------------------

def _matugen(path, mode, scheme_type):
    cmd = ["matugen", "image", path, "--dry-run", "--json", "hex", "-m", mode, "--prefer", "saturation",
           "-t", scheme_type]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                           env={**os.environ, "NO_COLOR": "1"})
    except FileNotFoundError:
        raise RuntimeError("matugen is not installed") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("matugen took too long") from None
    if r.returncode:
        # First line is the cause (e.g. a decode error); a panic's backtrace hint follows it.
        lines = [ln.strip() for ln in r.stderr.splitlines() if ln.strip()]
        if any("unexpected argument" in ln for ln in lines):  # Fedora's matugen 3.x
            raise RuntimeError("matugen 4 or newer is needed (install.sh installs it from the Hyprland COPR)")
        raise RuntimeError(lines[0][:200] if lines else "matugen failed")
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise RuntimeError("matugen returned no colours") from None


def _ansi_base16(b16, p, mode):
    """ANSI from matugen's base16 if it reads like a terminal scheme on our bg, else None.

    matugen's base16 is sampled from the image (base00 is often a mid-tone, base08 rarely red), so this is
    mostly a guard; the usual result is the Tokyo Night hues below.
    """
    try:
        c = {k: b16[k][mode]["color"] for k in ("base00", "base03", "base05", "base07", "base08", "base0a",
                                                 "base0b", "base0c", "base0d", "base0e")}
    except (KeyError, TypeError):
        return None
    hues = (("base08", 0, 30), ("base0b", 120, 45), ("base0a", 50, 30), ("base0d", 220, 40))
    if contrast(c["base00"], p["bg"]) > 1.25 or contrast(c["base05"], p["bg"]) < 4.5:
        return None
    if any(contrast(c[k], p["bg"]) < 4.5 for k in ("base08", "base0a", "base0b", "base0c", "base0d", "base0e")):
        return None
    if not all(_hue_near(c[k], hue, tol) for k, hue, tol in hues):
        return None
    six = [c[k] for k in ("base08", "base0b", "base0a", "base0d", "base0e", "base0c")]
    return [c["base00"], *six, c["base05"], c["base03"], *six, c["base07"]]


def _ansi(p):
    """Tokyo Night's hues, harmonised toward the accent and made readable on bg; black/white from the palette."""
    tn = TOKYO_NIGHT["ansi"]
    black = p["bg_dim"] if _lum(p["bg"]) < 0.18 else p["surface3"]
    out = [black] + [None] * 6 + [p["fg"], p["fg_dim"]] + [None] * 6 + [p["fg_bright"]]
    for i in list(range(1, 7)) + list(range(9, 15)):
        out[i] = ensure(_harmonize(tn[i], p["accent"]), p["bg"], 4.5)
    out[8] = ensure(out[8], p["bg"], 3)
    return out


def from_wallpaper(path, mode="dark", scheme_type=DEFAULT_TYPE):
    """Palette for `path` (jpg/png/jxl) via matugen. Raises RuntimeError with a short message on failure."""
    mode = mode if mode in MODES else "dark"
    scheme_type = scheme_type if scheme_type in TYPES else DEFAULT_TYPE
    data = _matugen(path, mode, scheme_type)
    try:
        m = {k: v[mode]["color"] for k, v in data["colors"].items()}
        p = {
            "bg": m["surface"], "bg_dim": m["surface_container_lowest"],
            "surface": m["surface_container"], "surface2": m["surface_container_high"],
            "surface3": m["surface_container_highest"],
            "fg": m["on_surface_variant"], "fg_bright": m["on_surface"], "fg_dim": m["outline"],
            "muted": m["outline_variant"],
            "accent": m["primary"], "accent2": m["tertiary"], "bad": m["error"], "border": m["primary"],
            "shadow": m["shadow"] + ("ee" if mode == "dark" else "66"),
        }
    except (KeyError, TypeError):
        raise RuntimeError("matugen output is missing colours") from None
    # Material has no success/warning roles: Tokyo Night's green/yellow, hue nudged toward the accent.
    p["ok"] = _harmonize(TOKYO_NIGHT["ok"], p["accent"])
    p["warn"] = _harmonize(TOKYO_NIGHT["warn"], p["accent"])
    p = adjust(p)
    p["ansi"] = _ansi_base16(data.get("base16") or {}, p, mode) or _ansi(p)
    return p


# ---- state --------------------------------------------------------------------------------------------------

def state():
    t = store.get("theme")
    t = t if isinstance(t, dict) else {}
    return {"source": t.get("source") if t.get("source") in SOURCES else "tokyo-night",
            "mode": t.get("mode") if t.get("mode") in MODES else "dark",
            "type": t.get("type") if t.get("type") in TYPES else DEFAULT_TYPE,
            "wallpaper": t.get("wallpaper"), "palette": t.get("palette")}


def _valid(p):
    return (isinstance(p, dict) and all(isinstance(p.get(k), str) and p[k].startswith("#") for k in ROLES)
            and isinstance(p.get("ansi"), list) and len(p["ansi"]) == 16)


def palette():
    """The palette in use: the last generated one when following the wallpaper, else Tokyo Night."""
    s = state()
    if s["source"] == "wallpaper" and _valid(s["palette"]):
        return s["palette"]
    return dict(TOKYO_NIGHT)


# ---- rendering ----------------------------------------------------------------------------------------------

def _h(c):
    return c.lstrip("#")[:6]


def _a(c, alpha="ff"):
    return _h(c) + alpha


def _hypr_values(p):
    """Hyprland colour strings; keys are what looknfeel.lua reads as theme.*."""
    shadow = p["shadow"].lstrip("#")
    return {"accent": f"rgb({_h(p['accent'])})", "magenta": f"rgb({_h(p['accent2'])})",
            "bg": f"rgb({_h(p['bg'])})", "muted": f"rgb({_h(p['muted'])})",
            "shadow": f"rgba({shadow if len(shadow) == 8 else shadow + 'ee'})"}


HEAD = "Written by fw13.theme (Settings → Appearance). Changes here are replaced."


def _gtk_colors(p):
    """libadwaita / adw-gtk3 named colours for palette `p` (same roles as fw-settings' own ui_theme)."""
    dark = _dark(p)

    def text(c):  # standalone coloured text (links, warning labels) on window and view backgrounds
        return ensure(ensure(c, p["bg"], 4.5), p["bg_dim"], 4.5)
    raised = p["surface2"] if dark else p["bg_dim"]  # popovers/dialogs: lighter than the window in both modes
    c = {}
    for name, role in (("accent", "accent"), ("destructive", "bad"), ("success", "ok"), ("warning", "warn"),
                       ("error", "bad")):
        c[f"{name}_bg_color"] = p[role]
        c[f"{name}_fg_color"] = _on(p[role], p)
        c[f"{name}_color"] = text(p[role])
    c.update({
        "window_bg_color": p["bg"], "window_fg_color": p["fg"],
        "view_bg_color": p["bg_dim"], "view_fg_color": p["fg_bright"],
        "headerbar_bg_color": p["surface"], "headerbar_fg_color": p["fg_bright"],
        "headerbar_border_color": p["fg_bright"], "headerbar_backdrop_color": p["bg"],
        "sidebar_bg_color": p["bg_dim"], "sidebar_fg_color": p["fg"],
        "sidebar_backdrop_color": p["bg_dim"], "sidebar_border_color": p["surface2"],
        "secondary_sidebar_bg_color": p["bg"], "secondary_sidebar_fg_color": p["fg"],
        "secondary_sidebar_backdrop_color": p["bg"], "secondary_sidebar_border_color": p["surface2"],
        "card_bg_color": p["surface"] if dark else p["bg_dim"], "card_fg_color": p["fg_bright"],
        "popover_bg_color": raised, "popover_fg_color": p["fg_bright"],
        "dialog_bg_color": raised, "dialog_fg_color": p["fg_bright"],
        "thumbnail_bg_color": raised, "thumbnail_fg_color": p["fg_bright"],
        "borders": p["surface3"], "unfocused_borders": p["surface2"],
    })
    return {k: v[:7] for k, v in c.items()}


def _gtk_css(p, variables):
    lines = [f"/* {HEAD} */"] + [f"@define-color {k} {v};" for k, v in _gtk_colors(p).items()]
    if variables:  # libadwaita >= 1.6 styles with CSS variables; the named colours above are only aliases there
        lines += [":root {"] + [f"  --{k.replace('_', '-')}: {v};" for k, v in _gtk_colors(p).items()
                                if k.endswith("_color")] + ["}"]
    return "\n".join(lines) + "\n"


# QPalette::ColorRole order, as in qt6ct's colour schemes (/usr/share/qt6ct/colors/*.conf): 21 entries per line.
QT_ROLES = ("WindowText", "Button", "Light", "Midlight", "Dark", "Mid", "Text", "BrightText", "ButtonText",
            "Base", "Window", "Shadow", "Highlight", "HighlightedText", "Link", "LinkVisited", "AlternateBase",
            "NoRole", "ToolTipBase", "ToolTipText", "PlaceholderText")


def _qt_scheme(p):
    """qt6ct colour scheme text. Window/WindowText/Base/Highlight (what Citadel and most Qt apps paint with)
    are bg/fg/surface/accent; Light..Mid are bevel shades of Button for the Fusion style."""
    dark = _dark(p)
    button = p["surface2"]
    active = {
        "WindowText": p["fg"], "Button": button,
        "Light": _shade(button, 0.15), "Midlight": _shade(button, 0.07),
        "Dark": _shade(button, -0.15), "Mid": _shade(button, -0.07),
        "Text": p["fg_bright"], "BrightText": p["fg_bright"] if dark else p["bg_dim"], "ButtonText": p["fg_bright"],
        "Base": p["surface"], "Window": p["bg"], "Shadow": "#000000",
        "Highlight": p["accent"], "HighlightedText": _on(p["accent"], p),
        "Link": ensure(p["accent"], p["surface"], 4.5), "LinkVisited": ensure(p["accent2"], p["surface"], 4.5),
        "AlternateBase": p["surface2"], "NoRole": p["bg"],
        "ToolTipBase": p["surface2"], "ToolTipText": p["fg_bright"], "PlaceholderText": p["fg_dim"],
    }
    disabled = dict(active)
    for role in ("WindowText", "Text", "ButtonText", "HighlightedText", "BrightText"):
        disabled[role] = p["fg_dim"]
    disabled["Highlight"] = p["surface3"]

    def line(colors):
        return ", ".join("#ff" + _h(colors[r]) for r in QT_ROLES)
    return (f"; {HEAD}\n[ColorScheme]\n"
            f"active_colors={line(active)}\n"
            f"disabled_colors={line(disabled)}\n"
            f"inactive_colors={line(active)}\n")


def render(p):
    """{filename in ~/.config/fw13/theme: text} for palette `p`."""
    v = _hypr_values(p)
    hypr = (f"-- {HEAD}\n-- Read by ~/.config/hypr/theme.lua (falls back to Tokyo Night if this file breaks).\n"
            "return {\n" + "".join(f'  {k:<7} = "{c}",\n' for k, c in v.items()) + "}\n")
    waybar = (f"/* {HEAD} */\n"
              f"@define-color bg {p['bg']};\n"
              f"@define-color fg {p['fg']};\n"
              f"@define-color accent {p['accent']};\n"
              f"@define-color muted {p['muted']};\n"
              f"@define-color red {p['bad']};\n"
              f"@define-color yellow {p['warn']};\n")
    fuzzel = (f"# {HEAD}\n[colors]\n"
              f"background={_a(p['bg'], 'f2')}\n"
              f"text={_a(p['fg'])}\n"
              f"match={_a(p['accent'])}\n"
              f"selection={_a(p['surface2'])}\n"
              f"selection-text={_a(p['fg_bright'])}\n"
              f"selection-match={_a(p['accent'])}\n"
              f"border={_a(p['border'])}\n")
    mako = (f"# {HEAD}\n"
            f"background-color={p['bg']}\n"
            f"text-color={p['fg']}\n"
            f"border-color={p['border']}\n"
            "[urgency=critical]\n"
            f"border-color={p['bad']}\n")
    kitty = [f"# {HEAD}",
             f"background {p['bg']}",
             f"foreground {p['fg']}",
             f"selection_background {p['surface2']}",
             f"cursor {p['fg_bright']}"]
    for i in range(8):
        kitty += [f"color{i:<2} {p['ansi'][i]}", f"color{i + 8:<2} {p['ansi'][i + 8]}"]
    hyprlock = (f"# {HEAD}\n"
                f"$fw_base = rgba({_a(p['bg'])})\n"
                f"$fw_inner = rgba({_a(p['bg'], 'cc')})\n"
                f"$fw_outer = rgba({_a(p['accent'])})\n"
                f"$fw_text = rgba({_a(p['fg_bright'])})\n"
                f"$fw_check = rgba({_a(p['ok'])})\n"
                f"$fw_fail = rgba({_a(p['bad'])})\n"
                f"$fw_clock = rgba({_a(p['fg'])})\n")
    return {"hypr.lua": hypr, "waybar.css": waybar, "fuzzel.ini": fuzzel, "mako": mako,
            "kitty.conf": "\n".join(kitty) + "\n", "hyprlock.conf": hyprlock,
            "gtk3.css": _gtk_css(p, variables=False), "gtk4.css": _gtk_css(p, variables=True),
            "qt6ct-colors.conf": _qt_scheme(p)}


# ---- GTK theme + user gtk.css -------------------------------------------------------------------------------

GTK_THEME = "fw13"
GTK_THEME_DIR = os.path.expanduser("~/.local/share/themes/" + GTK_THEME)
GTK_MARK = "/* fw13: written by fw13.theme. Delete this line to keep your own copy of this file. */"
SYSTEM_THEMES = "/usr/share/themes"  # adw-gtk3 / adw-gtk3-dark (adw-gtk3-theme, packages/96-theme.txt)
GTK_SAVED = "theme_gtk_saved"  # fw13.store key: the gtk-theme / color-scheme apply_gtk() replaced


def _in_hyprland():
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def gtk_base(p):
    """The adw-gtk3 variant the fw13 GTK theme is built on, by the palette's lightness."""
    return "adw-gtk3-dark" if _dark(p) else "adw-gtk3"


def gtk_base_installed(p):
    """True if the base theme for `p` is installed. Without it the fw13 theme's @import fails and GTK 3 apps
    would lose all widget styling, so apply_gtk() never selects fw13 then."""
    return os.path.isfile(os.path.join(SYSTEM_THEMES, gtk_base(p), "gtk-3.0", "gtk.css"))


def render_gtk_theme(p):
    """{path in GTK_THEME_DIR: text}: the "fw13" GTK theme, adw-gtk3[-dark] (by the palette's lightness) with
    our colours on top. It is a theme rather than ~/.config/gtk-3.0/gtk.css because GTK 3 loads the user gtk.css
    once per process, while a theme is re-parsed (with its @imports) whenever gtk-theme changes."""
    base = gtk_base(p)
    out = {"index.theme": f"# {HEAD}\n[Desktop Entry]\nType=X-GNOME-Metatheme\nName={GTK_THEME}\n"
                          f"Comment=adw-gtk3 with the fw13 palette (~/.config/fw13/theme)\n\n"
                          f"[X-GNOME-Metatheme]\nGtkTheme={GTK_THEME}\n"}
    for ver, colours in (("gtk-3.0", "gtk3.css"), ("gtk-4.0", "gtk4.css")):
        css = (f"/* {HEAD} */\n"
               f'@import url("file://{SYSTEM_THEMES}/{base}/{ver}/gtk.css");\n'
               f'@import url("file://{os.path.join(DIR, colours)}");\n')
        # gtk-dark.css is loaded instead when an app asks for a dark variant: same palette either way.
        out[f"{ver}/gtk.css"] = out[f"{ver}/gtk-dark.css"] = css
    return out


def _user_gtk_css():
    """~/.config/gtk-4.0/gtk.css (read by every GTK 4 app at start, libadwaita ones included)."""
    return os.path.expanduser("~/.config/gtk-4.0/gtk.css"), (
        f"{GTK_MARK}\n/* libadwaita apps ignore GTK themes; this gives them the fw13 palette at start. */\n"
        f'@import url("file://{os.path.join(DIR, "gtk4.css")}");\n')


def _read(path):
    """File text, None if absent; OSError/UnicodeDecodeError if unreadable."""
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def link_gtk():
    """Make ~/.config/gtk-4.0/gtk.css @import our gtk4.css, unless the user has their own file there (one
    without GTK_MARK), which is left alone. Returns None or a short note saying why nothing was written.

    Only from a Hyprland session: the file is read by GTK 4 apps in every session, so installing from GNOME/KDE
    must not recolour their libadwaita apps (session_start() links it at the next Hyprland login, session_end()
    removes it). GTK 3 needs no user gtk.css (the fw13 theme carries the colours); one there with colours would
    even pin them, since GTK 3 never re-reads it."""
    path, text = _user_gtk_css()
    if not _in_hyprland():
        return None
    try:
        cur = _read(path)
    except (OSError, UnicodeDecodeError):
        return f"{path} is not readable; GTK 4 apps keep their own colours"
    if cur is not None and GTK_MARK not in cur:
        return f"{path} is yours, left as is; libadwaita apps keep their colours (@import {DIR}/gtk4.css to opt in)"
    if cur != text:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic(path, text)
    return None


def unlink_gtk():
    """Remove ~/.config/gtk-4.0/gtk.css if it is ours (has GTK_MARK)."""
    path, _ = _user_gtk_css()
    try:
        cur = _read(path)
        if cur is not None and GTK_MARK in cur:
            os.unlink(path)
    except (OSError, UnicodeDecodeError):
        pass


def _write_gtk_theme(p, only_missing=False):
    written = []
    for rel, text in render_gtk_theme(p).items():
        path = os.path.join(GTK_THEME_DIR, rel)
        if only_missing and os.path.isfile(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic(path, text)
        written.append(os.path.join("themes", GTK_THEME, rel))
    return written


def _atomic(path, text):
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ensure_files():
    """Write any missing generated file from the current palette (mako refuses to start when its include is
    missing). Existing files are left alone."""
    os.makedirs(DIR, exist_ok=True)
    p = palette()
    missing = {n: t for n, t in render(p).items() if not os.path.isfile(os.path.join(DIR, n))}
    for name, text in missing.items():
        _atomic(os.path.join(DIR, name), text)
    return sorted(missing) + _write_gtk_theme(p, only_missing=True)


def write(p, apply=True):
    """Write every generated file for `p` (atomically), the fw13 GTK theme and (if ours, under Hyprland) the
    GTK 4 user gtk.css, then reload running apps unless apply=False."""
    os.makedirs(DIR, exist_ok=True)
    for name, text in render(p).items():
        _atomic(os.path.join(DIR, name), text)
    _write_gtk_theme(p)
    link_gtk()
    if apply:
        reload(p)


def _quiet(*cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _gsettings_get(key):
    try:
        r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key], capture_output=True,
                           text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip().strip("'") if r.returncode == 0 else None


def _gsettings_set(key, value):
    _quiet("gsettings", "set", "org.gnome.desktop.interface", key, value)


def _save_gtk(theme_name, scheme):
    """Remember the gtk-theme / color-scheme apply_gtk() is about to replace (once: a saved pair is kept until
    restore_gtk() uses it, so a second apply does not save our own values)."""
    if theme_name == GTK_THEME or isinstance(store.get(GTK_SAVED), dict):
        return
    try:
        store.set(GTK_SAVED, {"gtk-theme": theme_name, "color-scheme": scheme})
    except OSError:
        pass


def apply_gtk(p=None, refresh=True):
    """Point GTK at the fw13 theme and the palette's light/dark (org.gnome.desktop.interface gtk-theme and
    color-scheme). Under Hyprland GTK 3/4 read these from GSettings (dconf) directly, and libadwaita apps get
    color-scheme through xdg-desktop-portal-gtk, so no settings.ini is needed (GSettings would override it).
    Returns None or a short note.

    Only inside a Hyprland session (never in CI or from another desktop). The keys are per user, so GNOME sees
    them too: the values replaced are saved first (GTK_SAVED) and restore_gtk() puts them back.
    gtk-theme is set to fw13 only when its adw-gtk3 base is installed (else GTK 3 apps would be unstyled).
    refresh: if gtk-theme is already fw13, switch it to plain adw-gtk3 and back so running GTK 3 apps re-parse
    the theme and its @imports; GTK compares names, so setting the same name again does nothing, and the short
    pause keeps apps from reading both writes as one (they read the key when the change signal arrives).
    """
    if not _in_hyprland() or not shutil.which("gsettings"):
        return None
    p = p or palette()
    dark = _dark(p)
    want = "prefer-dark" if dark else "prefer-light"
    current = _gsettings_get("gtk-theme")
    if current is None:
        return None  # no GSettings schema / dconf: nothing to set
    scheme = _gsettings_get("color-scheme")
    _save_gtk(current, scheme)
    if scheme != want:
        _gsettings_set("color-scheme", want)
    if not gtk_base_installed(p):
        if current == GTK_THEME:  # fw13 without its base is unstyled: back to what was there before
            saved = store.get(GTK_SAVED)
            prev = saved.get("gtk-theme") if isinstance(saved, dict) else None
            _gsettings_set("gtk-theme", prev if prev and prev != GTK_THEME else "Adwaita")
        return f"{gtk_base(p)} is not installed (adw-gtk3-theme); GTK 3 apps keep their theme"
    if current == GTK_THEME:
        if not refresh:
            return None
        _gsettings_set("gtk-theme", gtk_base(p))
        time.sleep(0.4)
    _gsettings_set("gtk-theme", GTK_THEME)
    return None


def restore_gtk():
    """Undo apply_gtk() and link_gtk(): put back the saved gtk-theme / color-scheme (gtk-theme only while it is
    still ours) and remove our ~/.config/gtk-4.0/gtk.css. Safe to call anywhere; a no-op if nothing is saved."""
    unlink_gtk()
    saved = store.get(GTK_SAVED)
    if not isinstance(saved, dict) or not shutil.which("gsettings"):
        return
    if _gsettings_get("gtk-theme") == GTK_THEME:
        prev = saved.get("gtk-theme")
        if prev and prev != GTK_THEME:
            _gsettings_set("gtk-theme", prev)
        else:
            _quiet("gsettings", "reset", "org.gnome.desktop.interface", "gtk-theme")
    if saved.get("color-scheme") in ("default", "prefer-dark", "prefer-light"):
        _gsettings_set("color-scheme", saved["color-scheme"])
    try:
        data = store.load()
        data.pop(GTK_SAVED, None)
        store.save(data)
    except OSError:
        pass


def session_start():
    """At Hyprland login: missing files, the GTK 4 user gtk.css and gtk-theme/color-scheme (another desktop or
    a session_end() may have reset them). Returns a note or None."""
    try:
        ensure_files()
    except OSError:
        pass
    notes = [n for n in (link_gtk(), apply_gtk(refresh=False)) if n]
    return "; ".join(notes) or None


def session_end():
    """At Hyprland logout: hand the shared GTK settings back to other desktops (restore_gtk())."""
    restore_gtk()


def reload(p=None):
    """Make running apps pick up the files; each step is a no-op when the app isn't running.

    fuzzel and hyprlock read their config at start, so they need nothing. GTK 3 apps recolour through
    apply_gtk(); GTK 4 (libadwaita) and Qt apps read their colours at start.
    """
    p = p or palette()
    try:
        ensure_files()
    except OSError:
        pass
    _quiet("pkill", "-SIGUSR2", "-x", "waybar")  # re-reads style.css (and its @import)
    if shutil.which("makoctl"):
        _quiet("makoctl", "reload")
    _quiet("pkill", "-SIGUSR1", "-x", "kitty")  # every kitty re-reads kitty.conf incl. includes
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        v = {k: f'"{c}"' for k, c in _hypr_values(p).items()}
        try:
            lua("hl.config({ general = { col = { "
                f"active_border = {{ colors = {{ {v['accent']}, {v['magenta']} }}, angle = 45 }}, "
                f"inactive_border = {v['muted']} }} }}, "
                f"decoration = {{ shadow = {{ color = {v['shadow']} }} }} }})")
        except OSError:
            pass
    apply_gtk(p)


def init():
    """Record Tokyo Night as the source if nothing is stored yet, put back any missing generated file (chezmoi
    seeds most of them; gtk3.css/gtk4.css/qt6ct-colors.conf are only written here, from the current palette; a
    deleted one would stop mako starting) and the fw13 GTK theme, and link the GTK 4 user gtk.css (see
    link_gtk(); its note is returned). Reloads nothing, so it is safe without a desktop (install, CI)."""
    data = store.load()
    if not isinstance(data.get("theme"), dict):
        data["theme"] = state()
        store.save(data)
    ensure_files()
    return link_gtk()


def set_source(source, mode=None, scheme_type=None, wallpaper=None):
    """Follow `source` ("tokyo-night" or "wallpaper"), store the choice, write the files and apply them.

    Unspecified options keep their stored value; the wallpaper defaults to ~/.config/hypr/wallpaper.jpg.
    Returns None, or an error message. The store is saved first; if writing the files then fails, the old
    store entry is put back, so the choice shown always matches the files (a file may be half-way only if
    that restore fails too).
    """
    if source not in SOURCES:
        return f"Unknown theme source {source}"
    s = state()
    s["source"] = source
    s["mode"] = mode if mode in MODES else s["mode"]
    s["type"] = scheme_type if scheme_type in TYPES else s["type"]
    if source == "wallpaper":
        from .hyprsettings import WALLPAPER
        path = wallpaper or WALLPAPER
        if not os.path.isfile(path):
            return "No wallpaper set"
        try:
            p = from_wallpaper(path, s["mode"], s["type"])
        except RuntimeError as e:
            return f"Could not read colours from the wallpaper: {e}"
        s["wallpaper"] = path
        s["palette"] = p
    else:
        p = dict(TOKYO_NIGHT)
    data = store.load()
    old = data.get("theme")
    data["theme"] = s
    try:
        store.save(data)
    except OSError as e:
        return f"Could not save the theme: {e}"
    try:
        write(p, apply=False)
    except OSError as e:
        data["theme"] = old
        if old is None:
            data.pop("theme")
        try:
            store.save(data)
            write(palette(), apply=False)
        except OSError:
            pass
        return f"Could not write the theme files: {e}"
    reload(p)
    return None


if __name__ == "__main__":  # python3 -m fw13.theme session-start|session-end (Hyprland login/logout hooks)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "session-start":
        msg = session_start()
        if msg:
            print("fw13.theme:", msg, file=sys.stderr)
    elif cmd == "session-end":
        session_end()
    else:
        sys.exit("usage: python3 -m fw13.theme session-start|session-end")

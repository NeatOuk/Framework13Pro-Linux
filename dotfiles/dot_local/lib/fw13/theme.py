"""Desktop colours: Tokyo Night, or a palette generated from the wallpaper with matugen.

The base configs (hypr theme.lua, hyprlock.conf, waybar style.css, fuzzel.ini, mako, kitty.conf, ghostty) hold no colours;
they include the files this module writes into ~/.config/fw13/theme/. chezmoi seeds those once (create_) with
render(TOKYO_NIGHT), so a fresh install looks the same as before.

GTK and Qt apps follow too (read at app start; GTK 3 also live, see apply_gtk()):
  gtk3.css / gtk4.css   libadwaita named colours (@define-color; gtk4.css also the --*-color variables). GTK 3 and
                        plain GTK 4 apps get them through the "fw13" GTK theme in ~/.local/share/themes/fw13, which
                        is adw-gtk3[-dark] plus gtk3.css/gtk4.css; libadwaita apps ignore GTK themes and read
                        ~/.config/gtk-4.0/gtk.css, which @imports gtk4.css (only when that file is ours, see
                        link_gtk()).
  ghostty               Ghostty colours; ~/.config/ghostty/config includes it (optional: "?" path).
  qt6ct-colors.conf     qt6ct colour scheme; ~/.config/qt6ct/qt6ct.conf points at it and ~/.config/uwsm/env-hyprland
                        sets QT_QPA_PLATFORMTHEME=qt6ct for the Hyprland session only (new Qt apps after re-login).
  fcitx5-theme.conf     fcitx5 classic UI theme; ~/.local/share/fcitx5/themes/fw13/theme.conf links to it
                        (link_fcitx()) and classicui.conf selects it in Hyprland sessions (apply_fcitx()).
These are not chezmoi seeds: ensure_files() (init(), run_once) writes them from the current palette, so an
upgrade of a wallpaper-following install does not start out with Tokyo Night GTK/Qt/Ghostty colours.

Apps with their own settings files, changed only from a Hyprland session:
  Chromium   GTK mode (extensions.theme.system_theme) once per profile at login, unless the user chose a theme
             (chromium_gtk()); it then takes its colours from the fw13 GTK theme. GNOME's Chromium too (Adwaita).
             Opt-in switch (store CHROMIUM_FORCE) replaces a chosen theme with GTK mode at every login (_chromium_force()).
  VS Code    on by default, switch in Settings → Appearance (store VSCODE_ON): theme-scoped workbench.colorCustomizations, removed at logout.
Terminal tools (btop's TTY theme, fzf --color=16, bat's ansi theme) use kitty's 16 colours: nothing to write.

Other desktops on the same account (Fedora Workstation/KDE bases, CLAUDE.md 3a): gtk-theme and color-scheme
(org.gnome.desktop.interface, dconf) and ~/.config/gtk-4.0/gtk.css are per user, not per session. So they are only
set from a Hyprland session, the values they replace are saved first (store key GTK_SAVED), and session_end() /
restore_gtk() put them back and remove our gtk-4.0/gtk.css (the same for fcitx5's Theme and the VS Code block);
session_start() re-applies at the next Hyprland login (`python3 -m fw13.theme session-start|session-end`). Until
a session_end() runs (e.g. after a crash), GNOME shows the fw13 GTK theme and our light/dark choice; KDE resets
gtk-theme itself at Plasma login.

State lives in fw13.store under "theme":
  {"source": "tokyo-night" | "wallpaper", "mode": "dark" | "light", "type": "scheme-tonal-spot",
   "wallpaper": path, "palette": {...last generated}}
Palette values are "#rrggbb" ("shadow" is "#rrggbbaa"); "ansi" is the 16 terminal colours.
"""
import colorsys
import contextlib
import fcntl
import hashlib
import json
import os
import re
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

FONT = "font"  # fw13.store key: one font for the bar, menus, notifications, lock screen, panels and terminals
DEFAULT_FONT = "JetBrains Mono"


def _font_ok(name):
    """A family name safe to write into every config format (no quotes, newlines or separators)."""
    return isinstance(name, str) and re.fullmatch(r"\w[\w .+&-]{0,63}", name) is not None


def fonts():
    """Installed monospace font families, sorted: the font also drives the terminals, so it has to be fixed-width."""
    try:
        out = subprocess.run(["fc-list", ":spacing=mono", "family"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    names = {line.split(",")[0].strip() for line in out.splitlines()}
    return sorted({n for n in names if _font_ok(n) and "Emoji" not in n} | {DEFAULT_FONT}, key=str.lower)


def font():
    name = store.get(FONT)
    return name if _font_ok(name) else DEFAULT_FONT


def set_font(name):
    """Store `name`, rewrite every generated file and reload the apps. Returns None or an error message."""
    if name not in fonts():
        return f"Font not installed: {name}"
    old = store.get(FONT)
    store.set(FONT, name)
    try:
        write(palette())
    except OSError as e:
        store.set(FONT, old)  # the choice shown must match the files
        return f"Could not write the theme files: {e}"
    return None


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


def _fcitx_theme(p):
    """fcitx5 classic UI theme (candidate popup and its menu), laid out like fcitx5's default-dark. The page and
    menu images are links to default-dark's (link_fcitx()). No [AccentColorField]: with it, fcitx5 would paint
    those parts in the desktop portal's accent colour instead of ours."""
    sel, on_sel = p["accent"], _on(p["accent"], p)
    lines = [f"# {HEAD}", "[Metadata]", "Name=fw13", "Version=1", "Author=fw13",
             "Description=fw13 palette (Settings → Appearance)", "ScaleWithDPI=True", ""]

    def margins(section, n):
        return [f"[{section}]", f"Left={n}", f"Right={n}", f"Top={n}", f"Bottom={n}", ""]
    lines += ["[InputPanel]", f"NormalColor={p['fg_bright']}", f"HighlightCandidateColor={on_sel}",
              f"HighlightColor={p['accent']}", f"HighlightBackgroundColor={p['surface2']}",
              "PageButtonAlignment=Last Candidate", ""]
    lines += margins("InputPanel/TextMargin", 5) + margins("InputPanel/ContentMargin", 2)
    lines += ["[InputPanel/Background]", f"Color={p['bg']}", f"BorderColor={p['border']}", "BorderWidth=2", ""]
    lines += margins("InputPanel/Background/Margin", 2)
    lines += ["[InputPanel/Highlight]", f"Color={sel}", ""] + margins("InputPanel/Highlight/Margin", 5)
    for name, img in (("PrevPage", "prev.svg"), ("NextPage", "next.svg")):
        lines += [f"[InputPanel/{name}]", f"Image={img}", "",
                  f"[InputPanel/{name}/ClickMargin]", "Left=5", "Right=5", "Top=4", "Bottom=4", ""]
    lines += ["[Menu]", f"NormalColor={p['fg_bright']}", f"HighlightCandidateColor={on_sel}", ""]
    lines += ["[Menu/Background]", f"Color={p['bg']}", f"BorderColor={p['border']}", "BorderWidth=2", ""]
    lines += margins("Menu/Background/Margin", 2) + margins("Menu/ContentMargin", 2)
    lines += ["[Menu/CheckBox]", "Image=radio.svg", "", "[Menu/SubMenu]", "Image=arrow.svg", ""]
    lines += ["[Menu/Highlight]", f"Color={sel}", ""] + margins("Menu/Highlight/Margin", 5)
    lines += ["[Menu/Separator]", f"Color={p['muted']}", ""] + margins("Menu/TextMargin", 5)
    return "\n".join(lines)


def render(p):
    """{filename in ~/.config/fw13/theme: text} for palette `p`."""
    v = _hypr_values(p)
    f = font()
    hypr = (f"-- {HEAD}\n-- Read by ~/.config/hypr/theme.lua (falls back to Tokyo Night if this file breaks).\n"
            "return {\n" + "".join(f'  {k:<7} = "{c}",\n' for k, c in v.items()) + "}\n")
    waybar = (f"/* {HEAD} */\n"
              f"@define-color bg {p['bg']};\n"
              f"@define-color fg {p['fg']};\n"
              f"@define-color accent {p['accent']};\n"
              f"@define-color muted {p['muted']};\n"
              f"@define-color red {p['bad']};\n"
              f"@define-color yellow {p['warn']};\n"
              f'* {{ font-family: "{f}", "Font Awesome 6 Free", "Font Awesome 6 Brands", "Noto Sans Khmer", sans-serif; }}\n')
    fuzzel = (f"# {HEAD}\n[main]\nfont={f}:size=12,Font Awesome 6 Free:size=12\n[colors]\n"
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
            f"progress-color=over #{_a(p['accent'], '66')}\n"
            f"font={f} 11\n"  # fw-osd volume/brightness bar, text stays readable
            "[urgency=critical]\n"
            f"border-color={p['bad']}\n")
    kitty = [f"# {HEAD}",
             f"font_family {f}",
             f"background {p['bg']}",
             f"foreground {p['fg']}",
             f"selection_background {p['surface2']}",
             f"cursor {p['fg_bright']}"]
    for i in range(8):
        kitty += [f"color{i:<2} {p['ansi'][i]}", f"color{i + 8:<2} {p['ansi'][i + 8]}"]
    ghostty = [f"# {HEAD}",
               f"font-family = {f}",
               f"background = {p['bg']}",
               f"foreground = {p['fg']}",
               f"selection-background = {p['surface2']}",
               f"selection-foreground = {p['fg_bright']}",
               f"cursor-color = {p['fg_bright']}"]
    ghostty += [f"palette = {i}={p['ansi'][i]}" for i in range(16)]
    hyprlock = (f"# {HEAD}\n"
                f"$fw_font = {f}\n"
                f"$fw_base = rgba({_a(p['bg'])})\n"
                f"$fw_inner = rgba({_a(p['bg'], 'cc')})\n"
                f"$fw_outer = rgba({_a(p['accent'])})\n"
                f"$fw_text = rgba({_a(p['fg_bright'])})\n"
                f"$fw_check = rgba({_a(p['ok'])})\n"
                f"$fw_fail = rgba({_a(p['bad'])})\n"
                f"$fw_clock = rgba({_a(p['fg'])})\n")
    return {"hypr.lua": hypr, "waybar.css": waybar, "fuzzel.ini": fuzzel, "mako": mako,
            "kitty.conf": "\n".join(kitty) + "\n", "ghostty": "\n".join(ghostty) + "\n", "hyprlock.conf": hyprlock,
            "gtk3.css": _gtk_css(p, variables=False), "gtk4.css": _gtk_css(p, variables=True),
            "qt6ct-colors.conf": _qt_scheme(p), "fcitx5-theme.conf": _fcitx_theme(p),
            "framework-logo.svg": _framework_logo(p, 18), "framework-logo@2x.svg": _framework_logo(p, 36)}


# Framework's gear mark (Framework Computer's trademark; path from Simple Icons, CC0, source frame.work), drawn by the
# bar's launcher button (waybar style.css background-image) in the accent colour. The one non-Font-Awesome icon,
# by the user's choice. Written at exactly the size the bar shows (18 px, 36 px for scale-2 surfaces) and picked with
# -gtk-scaled() in style.css: GTK resamples CSS background images with a cheap filter, which makes any other size look
# jagged or soft (fractional scaling draws the bar at scale 2).
FRAMEWORK_LOGO = (
    "M23.186 9.07 21.41 8.019a2.78 2.78 0 0 1-1.344-2.391V3.523c0-.431-.19-.837-.516-1.108A11.965 11.965 "
    "0 0 0 16.317.493a1.356 1.356 0 0 0-1.193.091L13.347 1.64a2.622 2.622 0 0 1-2.688 0L8.882.584a1.348 1"
    ".348 0 0 0-1.194-.09 11.93 11.93 0 0 0-3.231 1.918 1.44 1.44 0 0 0-.516 1.108v2.104c0 .986-.51 1.897"
    "-1.344 2.392L.823 9.068c-.363.215-.61.588-.675 1.013A12.24 12.24 0 0 0 0 12.001c0 .651.048 1.292.145"
    " 1.916.065.425.312.801.675 1.016l1.774 1.052a2.78 2.78 0 0 1 1.344 2.392v2.104c0 .431.191.837.516 1."
    "108.965.8 2.054 1.452 3.231 1.919.393.155.831.124 1.194-.091l1.777-1.055a2.622 2.622 0 0 1 2.688 0l1"
    ".777 1.055c.363.215.804.246 1.193.091a11.973 11.973 0 0 0 3.232-1.92 1.44 1.44 0 0 0 .516-1.107v-2.1"
    "04a2.78 2.78 0 0 1 1.344-2.392l1.774-1.052c.363-.215.61-.588.675-1.016.094-.624.145-1.265.145-1.916 "
    "0-.652-.048-1.293-.145-1.917a1.41 1.41 0 0 0-.67-1.013zM12.003 19.41c-3.981 0-7.21-3.317-7.21-7.407s"
    "3.229-7.406 7.21-7.406c3.98 0 7.21 3.316 7.21 7.406s-3.23 7.407-7.21 7.407z"
)


def _framework_logo(p, px):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="0 0 24 24">'
            f'<path fill="#{_h(p["accent"])}" d="{FRAMEWORK_LOGO}"/></svg>\n')


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


def _atomic(path, text, mode=0o644):
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _atomic_user(path, text):
    """_atomic() for a file of another app (settings.json, classicui.conf, Chromium's Preferences): through a
    symlink to its target (the user may keep it in a dotfiles repo) and keeping the file's mode."""
    path = os.path.realpath(path)
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _atomic(path, text, mode=mode)


# Lines a generated file must hold; one of ours (HEAD on top) written before a line was added is rewritten by
# ensure_files() (written only on a palette change otherwise, so an existing install would never get it).
REQUIRED = {"mako": ("progress-color=", "font="), "fuzzel.ini": ("font=",), "waybar.css": ("font-family",),
            "hyprlock.conf": ("$fw_font",)}


def _outdated(name):
    text = _read_quiet(os.path.join(DIR, name))
    return (name in REQUIRED and text is not None and HEAD in text.split("\n", 1)[0]
            and any(line not in text for line in REQUIRED[name]))


def ensure_files():
    """Write any missing generated file from the current palette (mako refuses to start when its include is
    missing), and any of ours that lacks a line added since (REQUIRED). Other existing files are left alone."""
    os.makedirs(DIR, exist_ok=True)
    p = palette()
    missing = {n: t for n, t in render(p).items()
               if not os.path.isfile(os.path.join(DIR, n)) or _outdated(n)}
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
    chromium_policy(p, signal=apply)
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


# ---- fcitx5 candidate popup ---------------------------------------------------------------------------------

FCITX_THEME = "fw13"
FCITX_THEME_DIR = os.path.expanduser("~/.local/share/fcitx5/themes/" + FCITX_THEME)
FCITX_IMAGES = "/usr/share/fcitx5/themes/default-dark"  # prev/next/radio/arrow.svg (fcitx5-data)
FCITX_CONF = os.path.expanduser("~/.config/fcitx5/conf/classicui.conf")
FCITX_KEYS = ("Theme", "DarkTheme")  # classic UI: theme for a light / dark desktop (UseDarkTheme)
FCITX_SAVED = "theme_fcitx_saved"  # fw13.store key: the classicui.conf values apply_fcitx() replaced


def link_fcitx():
    """Make ~/.local/share/fcitx5/themes/fw13/ a theme: theme.conf → our fcitx5-theme.conf, images → fcitx5's
    default-dark ones. Links only (they follow every palette change); a real file there is left alone."""
    links = {"theme.conf": os.path.join(DIR, "fcitx5-theme.conf")}
    for img in ("prev.svg", "next.svg", "radio.svg", "arrow.svg"):
        if os.path.isfile(os.path.join(FCITX_IMAGES, img)):
            links[img] = os.path.join(FCITX_IMAGES, img)
    try:
        os.makedirs(FCITX_THEME_DIR, exist_ok=True)
        for name, target in links.items():
            path = os.path.join(FCITX_THEME_DIR, name)
            if os.path.islink(path):
                if os.readlink(path) == target:
                    continue
                os.unlink(path)
            elif os.path.lexists(path):
                continue
            os.symlink(target, path)
    except OSError:
        pass


def _ini_top(text, key):
    """Value of a top-level (before any [section]) `key=` line in fcitx5 config `text`, None if absent."""
    for line in (text or "").splitlines():
        if line.strip().startswith("["):
            break
        k, sep, v = line.partition("=")
        if sep and k.strip() == key:
            return v.strip()
    return None


def _ini_set_top(text, values):
    """`text` with the top-level keys in `values` set (value None: line removed), other lines kept as they are."""
    lines = (text or "").splitlines()
    end = next((i for i, ln in enumerate(lines) if ln.strip().startswith("[")), len(lines))
    head, seen = [], set()
    for line in lines[:end]:
        k, sep, _ = line.partition("=")
        if sep and k.strip() in values:
            seen.add(k.strip())
            if values[k.strip()] is not None:
                head.append(f"{k.strip()}={values[k.strip()]}")
            continue
        head.append(line)
    head += [f"{k}={v}" for k, v in values.items() if k not in seen and v is not None]
    out = head + lines[end:]
    return "\n".join(out) + "\n" if out else ""


def _read_quiet(path):
    try:
        return _read(path)
    except (OSError, UnicodeDecodeError):
        return None


def apply_fcitx():
    """Point fcitx5's classic UI (Theme and DarkTheme in ~/.config/fcitx5/conf/classicui.conf) at the fw13 theme
    and reload fcitx5. Only inside Hyprland: the file is per user, so the values replaced are saved first
    (FCITX_SAVED) and restore_fcitx() puts them back at logout, like apply_gtk(). Returns None or a short note."""
    if not _in_hyprland():
        return None
    link_fcitx()
    try:
        cur = _read(FCITX_CONF)
    except (OSError, UnicodeDecodeError):
        return f"{FCITX_CONF} is not readable; the input method popup keeps its theme"
    old = {k: _ini_top(cur, k) for k in FCITX_KEYS}
    if all(v == FCITX_THEME for v in old.values()):
        return None
    saved = store.get(FCITX_SAVED)
    if isinstance(saved, dict):  # left over (no session_end(), e.g. a crash): keep what was picked since then
        new = {**saved, **{k: v for k, v in old.items() if v != FCITX_THEME}}
    else:  # values that are already ours are not worth saving: restore removes them
        new = {"exists": cur is not None, **{k: (None if v == FCITX_THEME else v) for k, v in old.items()}}
    if new != saved:
        try:
            store.set(FCITX_SAVED, new)
        except OSError:
            return "Could not save the input method theme; left as is"
    try:
        _atomic_user(FCITX_CONF, _ini_set_top(cur, {k: FCITX_THEME for k in FCITX_KEYS}))
    except OSError as e:
        return f"Could not set the input method theme: {e}"
    _quiet("fcitx5-remote", "--check", "-r")
    return None


def restore_fcitx():
    """Undo apply_fcitx(): Theme/DarkTheme back to the saved values while they are still ours (one the user
    picked in fcitx5's settings meanwhile is kept), and remove classicui.conf if we created it and it holds
    nothing else. Safe anywhere; a no-op if nothing is saved."""
    saved = store.get(FCITX_SAVED)
    if not isinstance(saved, dict):
        return
    try:
        cur = _read(FCITX_CONF)
        if cur is not None:
            back = {k: saved.get(k) for k in FCITX_KEYS if _ini_top(cur, k) == FCITX_THEME}
            text = _ini_set_top(cur, back) if back else cur
            if not saved.get("exists") and not text.strip() and not os.path.islink(FCITX_CONF):
                os.unlink(FCITX_CONF)
            elif text != cur:
                _atomic_user(FCITX_CONF, text)
    except (OSError, UnicodeDecodeError):
        return
    try:
        data = store.load()
        data.pop(FCITX_SAVED, None)
        store.save(data)
    except OSError:
        pass


# ---- Chromium GTK mode --------------------------------------------------------------------------------------

CHROMIUM_DIR = os.path.expanduser("~/.config/chromium")
CHROMIUM_DONE = "theme_chromium_gtk"  # fw13.store key: profile dirs chromium_gtk() has handled (once each)
CHROMIUM_FORCE = "chromium_gtk_force"  # fw13.store key: the Appearance switch (off by default): replaces a theme
#                                        the user chose with GTK mode, at every login while Chromium is closed
CHROMIUM_HINT = "theme_chromium_hint"  # fw13.store key: True when the setting was protected (Appearance hint)


def _chromium_running():
    """True if Chromium (any profile of ~/.config/chromium) is running, or we cannot tell."""
    try:
        r = subprocess.run(["pgrep", "-x", "chromium-browse"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        if r.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        return True
    lock = os.path.join(CHROMIUM_DIR, "SingletonLock")
    if not os.path.lexists(lock):
        return False
    try:  # "<hostname>-<pid>": live if that pid exists on this host
        host, _, pid = os.readlink(lock).rpartition("-")
    except OSError:
        return True
    return host != os.uname().nodename or not pid.isdigit() or os.path.exists(f"/proc/{pid}")


def _mac_protected(path):
    """True if Chromium keeps a MAC for extensions.theme in the prefs file `path` (protection.macs, nested or
    dotted); editing a protected value would make Chromium reset it and warn about settings changed outside."""
    try:
        with open(path) as f:
            macs = json.load(f).get("protection", {}).get("macs", {})
    except FileNotFoundError:
        return False
    except (OSError, ValueError, AttributeError):
        return True
    if not isinstance(macs, dict):
        return False
    ext = macs.get("extensions")
    return ((isinstance(ext, dict) and "theme" in ext)
            or any(k.startswith("extensions.theme") for k in macs))


def _chromium_profiles():
    return [n for n in sorted(os.listdir(CHROMIUM_DIR)) if n not in ("System Profile", "Guest Profile")
            and os.path.isfile(os.path.join(CHROMIUM_DIR, n, "Preferences"))]


def _chromium_own(theme, browser_theme):
    """True if the user chose a theme: GTK/Classic (system_theme), a theme extension, or a colour (any
    browser.theme key but the light/dark color_scheme: user_color[2], color_variant[2], is_grayscale[2],
    follows_system_colors, saved_local_theme, ...)."""
    return ("system_theme" in theme or bool(theme.get("id"))
            or any(k not in ("color_scheme", "color_scheme2") for k in browser_theme))


def _chromium_theme(prefs):
    """(data, extensions.theme, browser.theme) of a Preferences file; TypeError/AttributeError if it is not that
    shape, OSError/ValueError if unreadable."""
    with open(prefs) as f:
        data = json.load(f)
    theme = data.setdefault("extensions", {}).setdefault("theme", {})
    browser_theme = data.get("browser", {}).get("theme", {})
    if not isinstance(theme, dict) or not isinstance(browser_theme, dict):
        raise TypeError(prefs)
    return data, theme, browser_theme


def _chromium_hint_needed():
    """True while a profile still has the protected setting unset (the Appearance hint stays until then)."""
    for name in _chromium_profiles():
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            _data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if not _chromium_own(theme, browser_theme) and (
                _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences"))):
            return True
    return False


def chromium_gtk():
    """Chromium in GTK mode (its colours from the fw13 GTK theme, see apply_gtk()): set
    extensions.theme.system_theme = 1 in each profile's Preferences, once per profile, only when the key is not
    there (a theme the user chose, incl. a theme extension or colour, is never overridden), Chromium is not
    running (it rewrites Preferences on exit) and the value is not MAC-protected. Only inside Hyprland.
    Returns None or a short note."""
    if not _in_hyprland():
        return None
    if store.get(CHROMIUM_HINT) and not (os.path.isdir(CHROMIUM_DIR) and _chromium_hint_needed()):
        _drop(CHROMIUM_HINT)  # GTK chosen in Chromium meanwhile, or the profile is gone
    if not os.path.isdir(CHROMIUM_DIR):
        return None
    if store.get(CHROMIUM_FORCE):
        return _chromium_force()
    done = store.get(CHROMIUM_DONE)
    done = done if isinstance(done, list) else []
    todo = [n for n in _chromium_profiles() if n not in done]
    if not todo:
        return None
    if _chromium_running():
        return "Chromium is running; GTK mode is set at the next login"
    notes = []
    for name in todo:
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError):
            continue  # unreadable now: try again next login
        except (TypeError, AttributeError):
            done.append(name)  # not the shape we know: left alone
            continue
        if _chromium_own(theme, browser_theme):
            done.append(name)  # the user's own choice
            continue
        if _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences")):
            try:
                store.set(CHROMIUM_HINT, True)
            except OSError:
                pass
            notes.append("Chromium protects its theme setting; choose GTK in Chromium's Settings → Appearance")
            done.append(name)
            continue
        theme["system_theme"] = 1  # ui::SystemTheme::kGtk
        try:
            _atomic_user(prefs, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        except OSError as e:
            notes.append(f"Could not set Chromium's GTK mode: {e}")
            continue
        done.append(name)
    try:
        store.set(CHROMIUM_DONE, done)
    except OSError:
        pass
    return "; ".join(dict.fromkeys(notes)) or None


CHROMIUM_POLICY = os.path.join(DIR, "chromium-policy.json")  # /etc/chromium/policies/managed/fw13-theme.json links here


CHROMIUM_POLICY_LINK = "/etc/chromium/policies/managed/fw13-theme.json"  # made by install.sh (root)


def _chromium_browsers():
    """PIDs of running Chromium browser processes (not its zygote/renderer children)."""
    try:
        r = subprocess.run(["pgrep", "-x", "chromium-browse"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for pid in r.stdout.split():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"--type=" not in f.read():
                    out.append(int(pid))
        except (OSError, ValueError):
            pass
    return out


def chromium_policy(p, signal=True):
    """Chromium's BrowserThemeColor policy from the palette's accent, so a running Chromium follows the colours:
    Chromium builds its whole palette from that one seed and re-reads policies on SIGHUP. Only with the Appearance
    switch (CHROMIUM_FORCE) on; switched off, the file is emptied (the symlink in /etc/chromium/policies/managed
    stays valid, root made it once). Nothing happens unless the switch is on or the /etc link exists (then the
    file is kept as "{}", so Chromium never reads a dangling link)."""
    on = bool(store.get(CHROMIUM_FORCE))
    if not on and not os.path.exists(CHROMIUM_POLICY) and not os.path.islink(CHROMIUM_POLICY_LINK):
        return
    text = json.dumps({"BrowserThemeColor": p["accent"]} if on else {}) + "\n"
    try:
        with open(CHROMIUM_POLICY) as f:
            if f.read() == text:
                return
    except OSError:
        pass
    try:
        _atomic(CHROMIUM_POLICY, text)
    except OSError:
        return
    if signal and _in_hyprland():
        for pid in _chromium_browsers():
            try:
                os.kill(pid, 1)  # SIGHUP: reload policies
            except OSError:
                pass


def _chromium_gtk_wanted(theme, browser_theme):
    """True if a profile still differs from the state the BrowserThemeColor policy needs: Chromium's own theme
    (system_theme 0, not GTK mode, which would take its colours from GTK and ignore the policy seed), no theme
    extension, no colour theme, and the light/dark mode following the system (color_scheme/color_scheme2 absent
    or 0), so the frame takes the fw13 theme's dark or light."""
    return (theme.get("system_theme") not in (None, 0) or bool(theme.get("id"))
            or any(v != 0 for v in browser_theme.values()))


def _chromium_force():
    """The Appearance switch is on: every profile ends up in GTK mode, replacing a theme or colour the user chose
    in Chromium, and a fixed Light/Dark mode (that is what the switch is for). Same limits as chromium_gtk(): Chromium closed (it rewrites
    Preferences on exit), value not MAC-protected, Hyprland only. Returns None or a short note."""
    todo = []
    for name in _chromium_profiles():
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if _chromium_gtk_wanted(theme, browser_theme):
            todo.append((name, prefs, data, theme, browser_theme))
    if not todo:
        return None
    if _chromium_running():
        return "Chromium is running; the theme is set at the next login"
    notes = []
    for name, prefs, data, theme, browser_theme in todo:
        if _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences")):
            notes.append("Chromium protects its theme setting; the policy colour may not apply")
            continue
        theme.pop("id", None)
        theme["system_theme"] = 0  # ui::SystemTheme::kDefault: colours come from the policy seed, not GTK
        browser_theme.clear()  # colour theme keys and a fixed Light/Dark mode: the mode follows the system
        try:
            _atomic_user(prefs, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        except OSError as e:
            notes.append(f"Could not set Chromium's theme: {e}")
    return "; ".join(dict.fromkeys(notes)) or None


def set_chromium(on):
    """The Settings → Appearance switch for Chromium: store it, then apply (the theme is replaced by GTK mode
    now if Chromium is closed, else at the next login). Switching off only stops forcing: the theme that was
    replaced is not restored. Returns None or a note."""
    try:
        store.set(CHROMIUM_FORCE, bool(on))
    except OSError as e:
        return f"Could not save the setting: {e}"
    chromium_policy(palette())
    if not on:
        return None
    if not _in_hyprland():
        return "Chromium follows the theme in Hyprland sessions"
    if not os.path.isdir(CHROMIUM_DIR):
        return None
    return chromium_gtk()


# ---- VS Code (on by default, switch in Settings → Appearance) ----------------------------------------------------------------

VSCODE_SETTINGS = os.path.expanduser("~/.config/Code/User/settings.json")
VSCODE_ON = "vscode_theme"  # fw13.store key: the switch (on by default: store.DEFAULTS)
VSCODE_APPLIED = "theme_vscode_applied"  # fw13.store key: {"key": scope, "hash": of the block we wrote}
# VS Code's own default themes (theme ids; 1.140: "Dark 2026"/"Light 2026" default, "Dark Modern"/"Light Modern"
# the previous ones, migrated from "Default Dark Modern"). The colours are scoped to them, so a theme the user
# picked keeps its own colours. Syntax colours stay the theme's, hence only the themes matching the palette's mode.
VSCODE_THEMES = {"dark": ("Dark 2026", "Dark Modern"), "light": ("Light 2026", "Light Modern")}


def _vscode_scope(p):
    return "".join(f"[{t}]" for t in VSCODE_THEMES["dark" if _dark(p) else "light"])


def _vscode_colors(p):
    """workbench.colorCustomizations for palette `p`: window chrome, editor background and the terminal."""
    sel = p["surface2"]
    c = {
        "focusBorder": p["accent"], "foreground": p["fg"], "descriptionForeground": p["fg_dim"],
        "editor.background": p["bg"], "editor.foreground": p["fg_bright"],
        "editor.lineHighlightBackground": p["surface"], "editor.selectionBackground": p["surface3"],
        "editorLineNumber.foreground": p["fg_dim"], "editorLineNumber.activeForeground": p["fg_bright"],
        "editorCursor.foreground": p["fg_bright"], "editorWidget.background": p["surface"],
        "editorGroupHeader.tabsBackground": p["bg_dim"], "editorGroup.border": p["surface2"],
        "tab.activeBackground": p["bg"], "tab.activeForeground": p["fg_bright"], "tab.activeBorderTop": p["accent"],
        "tab.inactiveBackground": p["bg_dim"], "tab.inactiveForeground": p["fg_dim"], "tab.border": p["bg_dim"],
        "titleBar.activeBackground": p["bg_dim"], "titleBar.activeForeground": p["fg"],
        "titleBar.inactiveBackground": p["bg_dim"], "titleBar.inactiveForeground": p["fg_dim"],
        "activityBar.background": p["bg_dim"], "activityBar.foreground": p["fg_bright"],
        "activityBar.inactiveForeground": p["fg_dim"], "activityBar.activeBorder": p["accent"],
        "activityBarBadge.background": p["accent"], "activityBarBadge.foreground": _on(p["accent"], p),
        "sideBar.background": p["bg_dim"], "sideBar.foreground": p["fg"],
        "sideBarSectionHeader.background": p["bg_dim"],
        "statusBar.background": p["bg_dim"], "statusBar.foreground": p["fg"],
        "statusBar.noFolderBackground": p["bg_dim"], "statusBar.debuggingBackground": p["warn"],
        "statusBar.debuggingForeground": _on(p["warn"], p),
        "panel.background": p["bg"], "panel.border": p["surface2"],
        "panelTitle.activeBorder": p["accent"], "panelTitle.activeForeground": p["fg_bright"],
        "list.activeSelectionBackground": sel, "list.activeSelectionForeground": p["fg_bright"],
        "list.inactiveSelectionBackground": p["surface"], "list.hoverBackground": p["surface"],
        "list.focusOutline": p["accent"], "list.highlightForeground": p["accent"],
        "input.background": p["surface"], "input.foreground": p["fg_bright"], "input.border": p["surface3"],
        "dropdown.background": p["surface"], "dropdown.foreground": p["fg_bright"],
        "quickInput.background": p["surface"], "quickInput.foreground": p["fg_bright"],
        "button.background": p["accent"], "button.foreground": _on(p["accent"], p),
        "button.hoverBackground": _shade(p["accent"], 0.05 if _dark(p) else -0.05),
        "badge.background": p["accent"], "badge.foreground": _on(p["accent"], p),
        "progressBar.background": p["accent"], "textLink.foreground": ensure(p["accent"], p["bg"], 4.5),
        "errorForeground": p["bad"], "editorError.foreground": p["bad"], "editorWarning.foreground": p["warn"],
        "terminal.background": p["bg"], "terminal.foreground": p["fg"],
        "terminalCursor.foreground": p["fg_bright"], "terminal.selectionBackground": sel,
    }
    names = ("Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White")
    for i, n in enumerate(names):
        c[f"terminal.ansi{n}"] = p["ansi"][i]
        c[f"terminal.ansiBright{n}"] = p["ansi"][i + 8]
    return {k: v[:7] for k, v in c.items()}


def _hash(block):
    return hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def _vscode_lock():
    """One VS Code settings change at a time: the Settings page switch (a thread per flip) and a theme change
    (reload(), maybe in another process) would otherwise interleave read-modify-write and lose the record."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or DIR, "fw13-vscode.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:  # a new open file per caller: flock also excludes other threads of this process
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _vscode_load():
    """(settings dict, text, None) or (None, None, note); text is the file as read (None if missing). A missing
    or empty file is {}; JSONC (comments, trailing commas) is left alone, since rewriting it as JSON would drop
    the user's comments."""
    try:
        text = _read(VSCODE_SETTINGS)
    except (OSError, UnicodeDecodeError):
        return None, None, "VS Code's settings.json is not readable; left as is"
    if text is None or not text.strip():
        return {}, text, None
    try:
        data = json.loads(text)
    except ValueError:
        return None, None, ("VS Code's settings.json has comments or trailing commas; left as is "
                            "(VS Code keeps its colours)")
    if not isinstance(data, dict):
        return None, None, "VS Code's settings.json is not a JSON object; left as is"
    cc = data.get("workbench.colorCustomizations", {})
    if not isinstance(cc, dict):
        return None, None, "VS Code's workbench.colorCustomizations is not an object; left as is"
    return data, text, None


def _vscode_dump(data, text):
    """JSON in the file's own layout: its indent (tab or n spaces; VS Code's default 4 for a new file), \\u
    escapes if it used them, its final newline."""
    m = re.search(r"\n([ \t]+)\S", text or "")
    indent = (("\t" if m.group(1)[0] == "\t" else len(m.group(1))) if m else 4)
    ascii_only = bool(text) and "\\u" in text and text.isascii()
    out = json.dumps(data, indent=indent, ensure_ascii=ascii_only)
    return out + "\n" if not text or text.endswith("\n") else out


def _vscode_save(data, cc, text):
    if cc:
        data["workbench.colorCustomizations"] = cc
    else:
        data.pop("workbench.colorCustomizations", None)
    _atomic_user(VSCODE_SETTINGS, _vscode_dump(data, text))


def _drop(key):
    try:
        data = store.load()
        data.pop(key, None)
        store.save(data)
    except OSError:
        pass


def _apply_vscode(p):
    if not store.get(VSCODE_ON) or not _in_hyprland():
        return None
    if not os.path.isfile(VSCODE_SETTINGS) and not shutil.which("code"):
        return None
    p = p or palette()
    data, text, note = _vscode_load()
    if note:
        return note
    cc = dict(data.get("workbench.colorCustomizations", {}))
    key, block = _vscode_scope(p), _vscode_colors(p)
    applied = store.get(VSCODE_APPLIED)
    applied = applied if isinstance(applied, dict) and isinstance(applied.get("key"), str) else None
    if applied and applied["key"] in cc:
        if _hash(cc[applied["key"]]) != applied.get("hash"):
            return "VS Code's theme colours were edited by hand; left as is"
        if applied["key"] != key:
            del cc[applied["key"]]  # the palette changed mode: the other default themes now
    if key in cc and not (applied and applied["key"] == key):
        return f"VS Code's settings.json has its own colours for {key}; left as is"
    if cc.get(key) == block and applied and applied.get("hash") == _hash(block):
        return None
    cc[key] = block
    record = {"key": key, "hash": _hash(block)}
    if applied and "was" in applied:
        record["was"] = applied["was"]
    elif not applied and (text is None or not text.strip()):
        record["was"] = text  # None: no file before us (restore removes it again), "": an empty one
    try:  # remember the block first: a block in the file without a record would look like the user's own
        store.set(VSCODE_APPLIED, record)
        _vscode_save(data, cc, text)
    except OSError as e:
        if applied:
            store.set(VSCODE_APPLIED, applied)
        else:
            _drop(VSCODE_APPLIED)
        return f"Could not write VS Code's settings: {e}"
    return None


def _restore_vscode():
    applied = store.get(VSCODE_APPLIED)
    if not isinstance(applied, dict) or not isinstance(applied.get("key"), str):
        return None
    data, text, note = _vscode_load()
    if note:
        return note  # the record stays: removed once the file is readable JSON again
    cc = dict(data.get("workbench.colorCustomizations", {}))
    key = applied["key"]
    if key in cc and _hash(cc[key]) == applied.get("hash"):
        del cc[key]
        try:
            if not cc and data.keys() <= {"workbench.colorCustomizations"} and "was" in applied:
                if applied["was"] is None:  # we created the file and it holds nothing else
                    if not os.path.islink(VSCODE_SETTINGS):
                        os.unlink(VSCODE_SETTINGS)
                else:
                    _atomic_user(VSCODE_SETTINGS, applied["was"])
            else:
                _vscode_save(data, cc, text)
        except OSError as e:
            return f"Could not write VS Code's settings: {e}"
    _drop(VSCODE_APPLIED)
    return None


def apply_vscode(p=None):
    """Give VS Code's default themes the palette: one theme-scoped block in workbench.colorCustomizations of
    ~/.config/Code/User/settings.json (VS Code recolours live). Only with the switch on (VSCODE_ON) and inside
    Hyprland; restore_vscode() removes the block at logout. The block's hash is kept in the store: once it was
    edited by hand, or the user has their own block for that scope, it is left alone. The file keeps its
    layout (_vscode_dump()). Returns None or a note."""
    try:
        with _vscode_lock():
            return _apply_vscode(p)
    except OSError as e:
        return f"Could not write VS Code's settings: {e}"


def restore_vscode():
    """Remove the block apply_vscode() wrote (unless it was edited by hand: then it is the user's now), and the
    file itself if we created it and nothing else is in it. Safe anywhere; a no-op if nothing was applied.
    Returns None or a note."""
    try:
        with _vscode_lock():
            return _restore_vscode()
    except OSError as e:
        return f"Could not write VS Code's settings: {e}"


def set_vscode(on):
    """The Settings → Appearance switch: store it, then apply or remove the colours. Under the lock the stored
    value decides, so quick flips (each in its own thread) end in the state of the last one stored. Returns None
    or a note."""
    try:
        with _vscode_lock():
            store.set(VSCODE_ON, bool(on))
            if store.get(VSCODE_ON):
                return _apply_vscode(None) or (None if _in_hyprland()
                                               else "VS Code follows the theme in Hyprland sessions")
            return _restore_vscode()
    except OSError as e:
        return f"Could not save the setting: {e}"


# ---- Hyprland session ---------------------------------------------------------------------------------------

def session_start():
    """At Hyprland login: missing files, the GTK 4 user gtk.css and gtk-theme/color-scheme (another desktop or
    a session_end() may have reset them), the fcitx5 theme, Chromium's GTK mode (once per profile) and the
    VS Code colours (if switched on). Returns a note or None."""
    try:
        if "mako" in ensure_files() and shutil.which("makoctl"):
            _quiet("makoctl", "reload")  # mako may be up already (D-Bus activated before this service)
    except OSError:
        pass
    link_fcitx()
    notes = [n for n in (link_gtk(), apply_gtk(refresh=False), apply_fcitx(), chromium_gtk(), apply_vscode())
             if n]
    return "; ".join(notes) or None


def session_end():
    """At Hyprland logout: hand the shared settings back to other desktops (GTK, fcitx5, VS Code)."""
    restore_vscode()
    restore_fcitx()
    restore_gtk()


def reload(p=None):
    """Make running apps pick up the files; each step is a no-op when the app isn't running.

    fuzzel and hyprlock read their config at start, so they need nothing. GTK 3 apps recolour through
    apply_gtk(); GTK 4 (libadwaita) apps read their colours at start. Qt apps on qt6ct (Citadel) recolour a few
    seconds after _nudge_qt6ct().
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
    _quiet("pkill", "-SIGUSR2", "-x", "ghostty")  # Ghostty (1.2+) reloads its config incl. config-file
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
    _nudge_qt6ct()
    if _in_hyprland() and _ini_top(_read_quiet(FCITX_CONF), "Theme") == FCITX_THEME:
        _quiet("fcitx5-remote", "--check", "-r")  # re-reads the fw13 theme (theme.conf links to our file)
    apply_vscode(p)


def _nudge_qt6ct():
    """Running Qt apps on qt6ct re-read their palette when something in ~/.config/qt6ct/ is replaced (it watches
    the directory, not our colour file), so replace qt6ct.conf with itself."""
    path = os.path.expanduser("~/.config/qt6ct/qt6ct.conf")
    try:
        text = _read(path)
        if text is not None:
            _atomic(path, text)
    except (OSError, UnicodeDecodeError):
        pass


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
    link_fcitx()
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

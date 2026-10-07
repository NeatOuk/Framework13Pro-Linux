"""Desktop colours: Tokyo Night, or a palette generated from the wallpaper with matugen.

The base configs (hypr theme.lua, hyprlock.conf, waybar style.css, fuzzel.ini, mako, kitty.conf) hold no colours;
they include the files this module writes into ~/.config/fw13/theme/. chezmoi seeds those once (create_) with
render(TOKYO_NIGHT), so a fresh install looks the same as before.

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
            "kitty.conf": "\n".join(kitty) + "\n", "hyprlock.conf": hyprlock}


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
    missing = {n: t for n, t in render(palette()).items() if not os.path.isfile(os.path.join(DIR, n))}
    for name, text in missing.items():
        _atomic(os.path.join(DIR, name), text)
    return sorted(missing)


def write(p, apply=True):
    """Write every generated file for `p` (atomically), then reload running apps unless apply=False."""
    os.makedirs(DIR, exist_ok=True)
    for name, text in render(p).items():
        _atomic(os.path.join(DIR, name), text)
    if apply:
        reload(p)


def _quiet(*cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def reload(p=None):
    """Make running apps pick up the files; each step is a no-op when the app isn't running.

    fuzzel and hyprlock read their config at start, so they need nothing.
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


def init():
    """Record Tokyo Night as the source if nothing is stored yet, and put back any missing generated file
    (chezmoi seeds them; a deleted one would stop mako starting). Reloads nothing, so it is safe without a
    desktop (install, CI)."""
    data = store.load()
    if not isinstance(data.get("theme"), dict):
        data["theme"] = state()
        store.save(data)
    ensure_files()


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

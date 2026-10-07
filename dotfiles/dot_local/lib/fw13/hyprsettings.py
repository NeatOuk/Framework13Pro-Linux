"""Appearance + Input overrides: Settings owns ~/.config/hypr/settings.lua (one hl.config call).

Values live in fw13.store under "hypr" as {"general.gaps_in": 8, ...}; only keys the user changed are written,
so looknfeel.lua / input.lua stay in charge of everything else. A new file is checked with
`Hyprland --verify-config` on a temp copy of ~/.config/hypr first; an unknown key would fail the whole config.
That check runs the user's whole Lua config, so top-level side effects in local.lua (hl.exec_cmd, os.execute) would
run too; it is done only when a key is added, not on every slider move (values are typed by KEYS).
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time

from . import store
from .hypr import hypr, lua, q

DIR = os.path.expanduser("~/.config/hypr")
PATH = os.path.join(DIR, "settings.lua")
WALLPAPER = os.path.join(DIR, "wallpaper.jpg")  # hyprpaper.conf and hyprlock.conf read this path
# Every key must exist in /usr/share/hypr/stubs/hl.meta.lua (dots = nesting in the Lua table).
KEYS = {
    "general.gaps_in": int,
    "general.gaps_out": int,
    "general.border_size": int,
    "input.touchpad.natural_scroll": bool,
    "input.touchpad.tap_to_click": bool,
    "input.touchpad.disable_while_typing": bool,
    "input.touchpad.scroll_factor": float,
    "input.sensitivity": float,
    "input.repeat_rate": int,
    "input.repeat_delay": int,
    "input.kb_layout": str,
}
# Used only when Hyprland can't be asked (not running): the shipped looknfeel.lua / input.lua values.
FALLBACK = {
    "general.gaps_in": 5, "general.gaps_out": 10, "general.border_size": 2,
    "input.touchpad.natural_scroll": True, "input.touchpad.tap_to_click": True,
    "input.touchpad.disable_while_typing": True, "input.touchpad.scroll_factor": 0.4,
    "input.sensitivity": 0.0, "input.repeat_rate": 40, "input.repeat_delay": 250, "input.kb_layout": "us",
}
_lock = threading.Lock()
_layouts = None


def overrides():
    v = store.get("hypr")
    return {k: v[k] for k in v if k in KEYS} if isinstance(v, dict) else {}


def running(key):
    """Current value from Hyprland (`hyprctl -j getoption`), or the fallback."""
    try:
        o = json.loads(hypr("-j", "getoption", key.replace(".", ":")))
    except ValueError:
        return FALLBACK[key]
    for field in ("bool", "int", "float", "str"):
        if field in o:
            return KEYS[key](o[field])
    if "css" in o:  # gaps: "5 5 5 5" (top right bottom left) — we only set all sides alike
        try:
            return int(o["css"].split()[0])
        except (IndexError, ValueError):
            pass
    return FALLBACK[key]


def get(key):
    return overrides().get(key, running(key))


def _lua_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{round(v, 3):g}"
    if isinstance(v, int):
        return str(v)
    return q(v)


def _table(tree, indent):
    pad = "  " * indent
    out = []
    for k in sorted(tree):
        v = tree[k]
        if isinstance(v, dict):
            out.append(f"{pad}{k} = {{\n{_table(v, indent + 1)}{pad}}},\n")
        else:
            out.append(f"{pad}{k} = {_lua_value(v)},\n")
    return "".join(out)


def call(values):
    """The hl.config({...}) statement for `values` ("" when empty)."""
    if not values:
        return ""
    tree = {}
    for key, v in values.items():
        *parents, leaf = key.split(".")
        node = tree
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = v
    return "hl.config({\n" + _table(tree, 1) + "})\n"


def render(values=None):
    values = overrides() if values is None else values
    head = ("-- Written by fw-settings (Settings → Appearance / Input). Change values there; manual edits are "
            "replaced.\n-- Only settings changed in the app are here; looknfeel.lua and input.lua hold the rest.\n"
            "-- Adding a setting runs `Hyprland --verify-config`, which executes top-level Lua: in local.lua, start "
            "programs only\n-- inside hl.on(\"hyprland.start\", ...) or a binding.\n")
    return head + call(values)


def verify(text):
    """None if Hyprland accepts the config with `text` as settings.lua, else the error text."""
    if not os.path.exists(os.path.join(DIR, "hyprland.lua")):
        return "~/.config/hypr/hyprland.lua not found"
    with tempfile.TemporaryDirectory(prefix="fw-settings-") as tmp:
        cfg, run = os.path.join(tmp, "cfg"), os.path.join(tmp, "run")
        os.makedirs(run, mode=0o700)
        shutil.copytree(DIR, os.path.join(cfg, "hypr"), symlinks=True)
        with open(os.path.join(cfg, "hypr", "settings.lua"), "w") as f:
            f.write(text)
        main = os.path.join(cfg, "hypr", "hyprland.lua")
        with open(main) as f:
            src = f.read()
        if 'require("settings")' not in src:  # older hyprland.lua: still check the new file parses
            with open(main, "a") as f:
                f.write('\nrequire("settings")\n')
        env = {**os.environ, "XDG_CONFIG_HOME": cfg, "XDG_RUNTIME_DIR": run}
        try:
            r = subprocess.run(["Hyprland", "--verify-config", "-c", main], env=env,
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"Could not check the config: {e}"
        lines = [ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
        if lines and lines[-1] == "config ok":
            return None
        if "Config parsing result:" in "\n".join(lines):
            lines = lines[["Config parsing result:" in ln for ln in lines].index(True) + 1:]
        msg = "\n".join(lines[-5:]) or "Hyprland rejected the config"
        return msg.replace(os.path.join(cfg, "hypr"), "~/.config/hypr")


def write(changes=None, reset=False):
    """Merge `changes` (value None = back to default), check, save and apply. Returns None or an error."""
    with _lock:
        old = overrides()
        new = {} if reset else dict(old)
        for k, v in (changes or {}).items():
            if k not in KEYS:
                return f"Unknown setting {k}"
            if v is None:
                new.pop(k, None)
            else:
                new[k] = KEYS[k](v)
        text = render(new)
        if set(new) - set(old) or not os.path.exists(PATH):
            try:
                err = verify(text)
            except OSError as e:
                err = f"Could not check the config: {e}"
            if err:
                return err
        try:
            _save(text, new)
        except OSError as e:
            return f"Could not save: {e}"
        if set(old) - set(new):
            # A key went back to default: only a reload brings back looknfeel.lua / input.lua's value.
            hypr("reload")
        elif new and not lua(call(new)):
            return "Saved, but Hyprland did not apply it live (it will at next login)"
        return None


def _save(text, new):
    """Store first, then settings.lua: if we are cut off in between, the next write renders the file again."""
    os.makedirs(DIR, exist_ok=True)
    os.makedirs(os.path.dirname(store.PATH), exist_ok=True)
    data = store.load()
    data["hypr"] = new
    # Own temp name: store.save's fixed settings.json.tmp may be in use by a page on the main thread.
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=os.path.dirname(store.PATH))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, store.PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".lua", dir=DIR)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def reset():
    return write(reset=True)


def layouts():
    """XKB layout names known to localectl (cached)."""
    global _layouts
    if _layouts is None:
        try:
            out = subprocess.run(["localectl", "list-x11-keymap-layouts"], capture_output=True,
                                 text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        _layouts = set(out.split())
    return _layouts


def check_layout(text):
    """(normalised "us,de", None) or (None, error)."""
    parts = [p.strip() for p in text.split(",")]
    if not text.strip() or not all(parts):
        return None, "Enter a layout, e.g. us or us,de"
    known = layouts()
    bad = [p for p in parts if known and p not in known]
    if bad:
        return None, f"Unknown layout: {', '.join(bad)}"
    return ",".join(parts), None


def wallpaper():
    return WALLPAPER if os.path.isfile(WALLPAPER) else None


def set_wallpaper(src):
    """Store `src` as ~/.config/hypr/wallpaper.jpg (converted to JPEG if needed) and restart hyprpaper.

    hyprpaper 0.8 has no reload IPC we can rely on (`hyprctl hyprpaper` answers "Invalid request"), so restart it.
    Returns None or an error.
    """
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    info = GdkPixbuf.Pixbuf.get_file_info(src)
    if not info or info[0] is None:
        return "Not an image GTK can read"
    os.makedirs(DIR, exist_ok=True)
    tmp = WALLPAPER + ".tmp"
    try:
        if info[0].get_name() == "jpeg":
            shutil.copyfile(src, tmp)
        else:
            pb = GdkPixbuf.Pixbuf.new_from_file(src)
            pb = pb.apply_embedded_orientation() or pb
            if pb.get_has_alpha():  # JPEG has no alpha: flatten onto the theme background
                from .theme import palette
                w, h = pb.get_width(), pb.get_height()
                flat = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
                flat.fill(int(palette()["bg"].lstrip("#")[:6] + "ff", 16))
                pb.composite(flat, 0, 0, w, h, 0, 0, 1, 1, GdkPixbuf.InterpType.NEAREST, 255)
                pb = flat
            pb.savev(tmp, "jpeg", ["quality"], ["95"])
        os.replace(tmp, WALLPAPER)
    except (OSError, GLib.Error) as e:
        if os.path.exists(tmp):
            os.unlink(tmp)
        return f"Could not save the wallpaper: {e}"
    subprocess.run(["pkill", "-x", "hyprpaper"])
    for _ in range(20):  # let the old one release the layer surface first
        if subprocess.run(["pgrep", "-x", "hyprpaper"], capture_output=True).returncode:
            break
        time.sleep(0.1)
    subprocess.Popen(["uwsm", "app", "--", "hyprpaper"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None

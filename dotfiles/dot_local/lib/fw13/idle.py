"""Idle timeouts (dim → lock → screen off → suspend): Settings → Power owns ~/.config/hypr/hypridle.conf.

Values live in fw13.store (idle_dim, idle_lock, idle_screen_off, idle_suspend; seconds, 0 = never) and are
rendered into hypridle's own (hyprlang) config, then hypridle is restarted. Screen on/off uses the Lua
dispatcher — `hyprctl dispatch dpms off` is rejected since the Hyprland config moved to Lua.
Dim and screen off hold auto-brightness (`fw-autobrightness pause` / `resume`, a no-op when it isn't running) so the
dim isn't taken for a manual change; `resume` runs after the brightness is restored.
"""
import os
import signal
import subprocess

from . import store

PATH = os.path.expanduser("~/.config/hypr/hypridle.conf")
KEYS = ("idle_dim", "idle_lock", "idle_screen_off", "idle_suspend")
DEFAULTS = {"idle_dim": 150, "idle_lock": 300, "idle_screen_off": 330, "idle_suspend": 900}
CHOICES = [0, 60, 120, 180, 300, 600, 900, 1800, 3600]  # seconds; 0 = never
DPMS = 'hyprctl dispatch \'hl.dsp.dpms({ action = "%s" })\''
AUTO = "fw-autobrightness"


def get():
    data = store.load()
    return {k: int(data.get(k, DEFAULTS[k])) for k in KEYS}


def label(seconds):
    if not seconds:
        return "Never"
    return f"{seconds // 3600} h" if seconds >= 3600 else f"{seconds // 60} min"


def render(v):
    out = ["# Written by fw-settings (Settings → Power → Screen & sleep). Edit there; manual edits are replaced.",
           "general {",
           "  lock_cmd = pidof hyprlock || hyprlock",
           "  before_sleep_cmd = loginctl lock-session",
           f"  after_sleep_cmd = {DPMS % 'on'}",
           "}"]
    if v["idle_dim"]:
        out += ["listener {            # dim", f"  timeout = {v['idle_dim']}",
                f"  on-timeout = {AUTO} pause; brightnessctl -s set 10%",
                f"  on-resume = brightnessctl -r; {AUTO} resume", "}"]
    if v["idle_lock"]:
        out += ["listener {            # lock", f"  timeout = {v['idle_lock']}",
                "  on-timeout = loginctl lock-session", "}"]
    if v["idle_screen_off"]:
        out += ["listener {            # screen off", f"  timeout = {v['idle_screen_off']}",
                f"  on-timeout = {AUTO} pause; {DPMS % 'off'}", f"  on-resume = {DPMS % 'on'}; {AUTO} resume", "}"]
    if v["idle_suspend"]:
        out += ["listener {            # suspend", f"  timeout = {v['idle_suspend']}",
                "  on-timeout = systemctl suspend", "}"]
    return "\n".join(out) + "\n"


def write(values=None, restart=True):
    v = {**get(), **(values or {})}
    data = store.load()
    data.update(v)
    store.save(data)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    text = render(v)
    try:
        with open(PATH) as f:
            same = f.read() == text
    except OSError:
        same = False
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, PATH)
    # unchanged file: no restart (chezmoi's run_once + run_onchange scripts both call this on a first apply)
    pids = _running() if restart and not same else []
    if pids:
        for p in pids:
            try:
                os.kill(p, signal.SIGTERM)
            except OSError:
                pass
        subprocess.Popen(["uwsm", "app", "--", "hypridle"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return v


def _running():
    """hypridle pids of this HOME only: a chezmoi dry-run into a temp HOME must not restart the session's one."""
    home = os.path.expanduser("~").encode()
    out = subprocess.run(["pgrep", "-x", "hypridle"], capture_output=True, text=True).stdout.split()
    pids = []
    for p in out:
        try:
            with open(f"/proc/{p}/environ", "rb") as f:
                if b"HOME=" + home in f.read().split(b"\0"):
                    pids.append(int(p))
        except (OSError, ValueError):
            pass
    return pids

"""Idle timeouts (dim → lock → screen off → suspend), separately when plugged in and on battery: Settings → Power
owns ~/.config/hypr/hypridle.conf.

Values live in fw13.store (idle_dim, idle_lock, idle_screen_off, idle_suspend = plugged in; the same keys with
"_battery" = on battery; seconds, 0 = never). A battery value that was never set follows the plugged-in one, so
existing settings keep working. hypridle can't tell the power source, so each listener calls `fw-idle <action>
ac|battery`, which acts only on that source (one listener without a guard when both timeouts are equal).
Dim and screen off hold auto-brightness (`fw-autobrightness pause` / `resume`, inside fw-idle) so the dim isn't taken
for a manual change. hypridle is restarted after a change.
"""
import os
import signal
import subprocess

from . import store

PATH = os.path.expanduser("~/.config/hypr/hypridle.conf")
AC_KEYS = ("idle_dim", "idle_lock", "idle_screen_off", "idle_suspend")
BAT = "_battery"
KEYS = AC_KEYS + tuple(k + BAT for k in AC_KEYS)
DEFAULTS = {"idle_dim": 150, "idle_lock": 300, "idle_screen_off": 330, "idle_suspend": 900}
CHOICES = [0, 60, 120, 180, 300, 600, 900, 1800, 3600]  # seconds; 0 = never
DPMS = 'hyprctl dispatch \'hl.dsp.dpms({ action = "%s" })\''
# key → (fw-idle action on timeout, on resume)
ACTIONS = {"idle_dim": ("dim", "undim"), "idle_lock": ("lock", None),
           "idle_screen_off": ("screen-off", "screen-on"), "idle_suspend": ("suspend", None)}


def get():
    data = store.load()
    v = {k: int(data.get(k, DEFAULTS[k])) for k in AC_KEYS}
    v.update({k + BAT: int(data.get(k + BAT, v[k])) for k in AC_KEYS})
    return v


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
    for key, (act, back) in ACTIONS.items():
        ac, bat = v[key], v[key + BAT]
        for secs, when in ([(ac, "")] if ac == bat else [(ac, " ac"), (bat, " battery")]):
            if secs:
                out += [f"listener {{            # {act}{when or ' (both)'}", f"  timeout = {secs}",
                        f"  on-timeout = fw-idle {act}{when}"]
                if back:
                    out.append(f"  on-resume = fw-idle {back}")
                out.append("}")
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

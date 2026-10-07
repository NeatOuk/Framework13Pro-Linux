"""Talking to Hyprland with a Lua config: dispatchers and settings are Lua, not hyprlang strings."""
import json
import subprocess


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def hypr(*args):
    return sh("hyprctl", *args)


def hj(what):
    """`hyprctl -j <what>` parsed; [] on error."""
    try:
        return json.loads(hypr("-j", what) or "[]")
    except ValueError:
        return []


def q(v):
    """A Lua string literal (a JSON string is one)."""
    return json.dumps(str(v))


def dispatch(expr):
    """`hyprctl dispatch 'hl.dsp.…'`."""
    return hypr("dispatch", expr)


def lua(*statements):
    """`hyprctl eval` — replaces `hyprctl keyword` / `--batch`. Returns True on "ok"."""
    return hypr("eval", "\n".join(statements)).strip() == "ok"

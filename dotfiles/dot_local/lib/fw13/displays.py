"""Monitors (arrange, refresh rate, scale) and laptop brightness — no GTK here.

Layouts are applied with `hyprctl eval 'hl.monitor(...)'` and saved to ~/.config/hypr/displays.lua
(required by hyprland.lua), one line per monitor keyed by description, so a monitor keeps its place
whatever port or dock it's plugged into.
"""
import json
import os
import re
import subprocess

from .hypr import hj, lua, sh

SAVED = os.path.expanduser("~/.config/hypr/displays.lua")
# Only scales that divide the monitor's size evenly are offered (see Mon.scales). On the Framework 13 panel
# (2880x1920) the even ones near 1.7 / 1.8 / 1.9 are 12/7, 16/9 and 1.875 / 1.92.
SCALES = [1, 1.2, 1.25, 4 / 3, 1.5, 1.6, 5 / 3, 12 / 7, 1.75, 16 / 9, 1.8, 1.875, 1.92, 2, 2.4, 2.5, 3]


class Mon:
    def __init__(self, m):
        self.name, self.desc = m["name"], m["description"]
        self.w, self.h, self.rr = m["width"], m["height"], m["refreshRate"]
        self.x, self.y, self.scale = m["x"], m["y"], m["scale"]
        self.transform = m["transform"]
        # refresh rates this monitor offers at its current resolution, e.g. "2560x1440@120.00Hz"
        res = f"{self.w}x{self.h}@"
        self.rates = sorted({float(md[len(res):].rstrip("Hz")) for md in m.get("availableModes", [])
                             if md.startswith(res)} or {self.rr}, reverse=True)
        self.rr = min(self.rates, key=lambda r: abs(r - self.rr))  # 119.999 → the 120.00 mode

    @property
    def lw(self):  # logical size (rotated outputs swap)
        return round((self.h if self.transform % 2 else self.w) / self.scale)

    @property
    def lh(self):
        return round((self.w if self.transform % 2 else self.h) / self.scale)

    def scales(self):
        ok = [s for s in SCALES if abs(self.w / s - round(self.w / s)) < 0.01
              and abs(self.h / s - round(self.h / s)) < 0.01]
        if not any(abs(s - self.scale) < 0.001 for s in ok):
            ok.append(self.scale)
        return sorted(ok)

    def rule(self):
        """One hl.monitor() call (Lua config); also what displays.lua stores, one per line."""
        q = json.dumps  # a JSON string is a valid Lua string literal
        r = (f"hl.monitor({{ output = {q('desc:' + self.desc)}, mode = {q(f'{self.w}x{self.h}@{self.rr:.2f}')}, "
             f"position = {q(f'{self.x}x{self.y}')}, scale = {self.scale:.6g}")
        return r + (f", transform = {self.transform} }})" if self.transform else " })")

    def snapshot(self):
        return (self.x, self.y, self.scale, self.rr)


def read_monitors():
    return [Mon(m) for m in hj("monitors") if not m.get("disabled")]


def overlaps(a, ax, ay, b):
    return ax < b.x + b.lw and b.x < ax + a.lw and ay < b.y + b.lh and b.y < ay + a.lh


def snap(m, mons):
    """Move m to the closest spot touching another monitor edge-to-edge without overlapping."""
    others = [o for o in mons if o is not m]
    if not others:
        m.x = m.y = 0
        return
    th = 0.08 * max(m.lw, m.lh)  # align edges when this close
    best = None
    for o in others:
        for side in ("left", "right", "above", "below"):
            if side in ("left", "right"):
                x = o.x - m.lw if side == "left" else o.x + o.lw
                y = min(max(m.y, o.y - m.lh + 1), o.y + o.lh - 1)
                for a in (o.y, o.y + o.lh - m.lh):  # align tops / bottoms
                    if abs(y - a) < th:
                        y = a
            else:
                y = o.y - m.lh if side == "above" else o.y + o.lh
                x = min(max(m.x, o.x - m.lw + 1), o.x + o.lw - 1)
                for a in (o.x, o.x + o.lw - m.lw):  # align left / right edges
                    if abs(x - a) < th:
                        x = a
            if any(overlaps(m, x, y, p) for p in others):
                continue
            d = (x - m.x) ** 2 + (y - m.y) ** 2
            if best is None or d < best[0]:
                best = (d, x, y)
    if best:
        m.x, m.y = round(best[1]), round(best[2])


def normalise(mons):
    if mons:
        dx, dy = min(m.x for m in mons), min(m.y for m in mons)
        for m in mons:
            m.x, m.y = m.x - dx, m.y - dy


def apply(mons):
    return lua(*(m.rule() for m in mons))


def save(mons):
    """Rewrite our lines; keep lines for monitors that aren't connected right now."""
    descs = {m.desc for m in mons}
    kept = []
    try:
        for line in open(SAVED):
            s = line.strip()
            d = re.search(r'output = "desc:((?:[^"\\]|\\.)*)"', s) if s.startswith("hl.monitor(") else None
            if d:
                if json.loads(f'"{d.group(1)}"') not in descs:
                    kept.append(s)
    except OSError:
        pass
    with open(SAVED, "w") as f:
        f.write("-- Written by fw-display-panel / fw-settings (Display → Apply → Keep).\n"
                "-- One line per monitor, matched by description. Delete a line to return it to the default.\n")
        for line in kept + [m.rule() for m in mons]:
            f.write(line + "\n")


# --- brightness (built-in panel) ------------------------------------------------------------------
def has_backlight():
    return os.path.isdir("/sys/class/backlight") and bool(os.listdir("/sys/class/backlight"))


def get_brightness():
    try:
        return int(sh("brightnessctl", "-m").split(",")[3].rstrip("%"))
    except (IndexError, ValueError):
        return 50


def set_brightness(pct):
    subprocess.Popen(["brightnessctl", "-q", "set", f"{int(pct)}%"])

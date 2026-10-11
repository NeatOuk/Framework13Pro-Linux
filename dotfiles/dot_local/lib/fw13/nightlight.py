"""Night light (hyprsunset) and its schedule.

Store: `nightlight_temp` (K), `nightlight_schedule` "off" (default) / "sun" (sunset to sunrise, from the weather
place's forecast, fw13.weather; FALLBACK offline or without a city) / "custom" (`nightlight_from`/`nightlight_to`,
"HH:MM"). `python3 -m fw13.nightlight tick` (fw-nightlight.timer, every 5 min) switches only at a change-over: the
wanted state is kept in store `nightlight_applied` {session, on}, so a manual SUPER+N wins until the next one; a new
Hyprland session applies the schedule once. During Zen (fw-profile) the change-over goes into what leaving Zen restores.
"""
import datetime
import os
import subprocess
import sys

from . import store

FALLBACK = ("19:00", "06:30")
SCHEDULES = {"off": "Off", "sun": "Sunset to sunrise", "custom": "Custom times"}


def on():
    return subprocess.run(["pgrep", "-x", "hyprsunset"], capture_output=True).returncode == 0


def switch(want, temp=None):
    """Start (restart with `temp`) or stop hyprsunset."""
    subprocess.run(["pkill", "-x", "hyprsunset"])
    if want:
        t = int(temp or store.get("nightlight_temp") or 4000)
        subprocess.Popen(["uwsm", "app", "--", "hyprsunset", "-t", str(t)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def minutes(hhmm):
    """'19:05' → 1145; ValueError on anything else."""
    h, m = (int(x) for x in hhmm.strip().split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(hhmm)
    return h * 60 + m


def window():
    """(start, end) as "HH:MM" for the current schedule, or None when off."""
    mode = store.get("nightlight_schedule")
    if mode == "custom":
        return store.get("nightlight_from") or FALLBACK[0], store.get("nightlight_to") or FALLBACK[1]
    if mode == "sun":
        from . import weather
        try:
            sun = weather.sun_today()
        except Exception:  # noqa: BLE001 — any lookup trouble: the fixed times
            sun = None
        if sun:
            return tuple(datetime.datetime.fromtimestamp(t).strftime("%H:%M") for t in sun)
        return FALLBACK
    return None


def wanted(start, end, now):
    """Night light on at `now` (minutes since midnight) for a start→end window that may cross midnight."""
    s, e = minutes(start), minutes(end)
    return s <= now < e if s <= e else now >= s or now < e


def tick():
    session = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    w = window()
    if not session or not w:
        return
    t = datetime.datetime.now()
    try:
        want = wanted(*w, t.hour * 60 + t.minute)
    except ValueError:  # a bad custom time: leave it alone
        return
    last = store.get("nightlight_applied") or {}
    if last.get("session") == session and last.get("on") == want:
        return  # no change-over since the last one: a manual toggle stays
    store.set("nightlight_applied", {"session": session, "on": want})
    saved = store.get("profile_saved")
    if store.get("profile") == "zen" and store.get("profile_session") == session and isinstance(saved, dict):
        store.set("profile_saved", {**saved, "nightlight": want})  # Zen keeps it on; leaving Zen follows the schedule
    elif want != on():
        switch(want)


def reset():
    """Schedule changed: apply it at the next tick even without a change-over."""
    store.set("nightlight_applied", None)


def test():
    assert minutes("06:30") == 390 and minutes(" 0:00") == 0
    for bad in ("24:00", "7", "ab:cd", "12:60"):
        try:
            minutes(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert wanted("19:00", "06:30", minutes("23:00")) and wanted("19:00", "06:30", minutes("03:00"))
    assert not wanted("19:00", "06:30", minutes("12:00")) and not wanted("19:00", "06:30", minutes("06:30"))
    assert wanted("19:00", "06:30", minutes("19:00"))
    assert wanted("13:00", "15:00", minutes("14:00")) and not wanted("13:00", "15:00", minutes("15:00"))
    print("ok")


if __name__ == "__main__":
    {"tick": tick, "test": test}[sys.argv[1] if len(sys.argv) > 1 else "tick"]()

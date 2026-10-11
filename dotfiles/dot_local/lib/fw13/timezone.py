"""Automatic time zone (Settings → System → Time zone, store `timezone_auto`, off by default).

`python3 -m fw13.timezone watch` (user service fw-timezone, Hyprland only; GNOME has its own switch) checks at
start, when NetworkManager reaches full connectivity and every 6 h: location from GeoClue2 (desktop id
fw13-timezone, let in without an agent by /etc/geoclue/conf.d/90-fw13-timezone.conf), the zone of that place from
Open-Meteo (timezone=auto), then timedate1 SetTimezone without a prompt. If polkit wants a password, it only
notifies. `check` prints what it would set and changes nothing; `test` runs the self-check.
"""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import notify, store, weather  # noqa: E402

APP = "fw-timezone"
GC = "org.freedesktop.GeoClue2"
TD = "org.freedesktop.timedate1"
CITY = 4  # GClueAccuracyLevel: the zone needs no more than the city
EVERY = 6 * 3600
NM_GLOBAL = 70  # NM_STATE_CONNECTED_GLOBAL


def _props(bus, path, iface, *names):
    return [bus.call_sync(GC, path, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (iface, n)),
                          None, Gio.DBusCallFlags.NONE, 5000, None).unpack()[0] for n in names]


def locate(timeout=30):
    """(lat, lon) from GeoClue2, or None (no fix in time, service off or not allowed)."""
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    client = bus.call_sync(GC, "/org/freedesktop/GeoClue2/Manager", GC + ".Manager", "CreateClient", None,
                           GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
    iface = GC + ".Client"
    for name, value in (("DesktopId", GLib.Variant("s", APP)), ("RequestedAccuracyLevel", GLib.Variant("u", CITY))):
        bus.call_sync(GC, client, "org.freedesktop.DBus.Properties", "Set", GLib.Variant("(ssv)", (iface, name, value)),
                      None, Gio.DBusCallFlags.NONE, 5000, None)
    found, loop = [], GLib.MainLoop()

    def updated(_c, _s, _p, _i, _sig, params):
        found.append(params.unpack()[1])
        loop.quit()
    sub = bus.signal_subscribe(GC, iface, "LocationUpdated", client, None, Gio.DBusSignalFlags.NONE, updated)
    try:
        bus.call_sync(GC, client, iface, "Start", None, None, Gio.DBusCallFlags.NONE, 10000, None)
        GLib.timeout_add_seconds(timeout, loop.quit)
        loop.run()
        if not found:
            return None
        lat, lon = _props(bus, found[0], GC + ".Location", "Latitude", "Longitude")
        return lat, lon
    finally:
        bus.signal_unsubscribe(sub)
        bus.call_sync(GC, "/org/freedesktop/GeoClue2/Manager", GC + ".Manager", "DeleteClient",
                      GLib.Variant("(o)", (client,)), None, Gio.DBusCallFlags.NONE, 5000, None)


def zone_for(lat, lon):
    """IANA zone of a place ("Asia/Phnom_Penh") from Open-Meteo; raises on network errors."""
    zone = weather._get(weather.FORECAST, {"latitude": lat, "longitude": lon, "timezone": "auto",
                                           "forecast_days": 1, "current": "is_day"}).get("timezone", "")
    return zone if valid(zone) else None


def valid(zone):
    return bool(zone) and "/" in zone and ".." not in zone and os.path.isfile(f"/usr/share/zoneinfo/{zone}")


def current():
    return os.path.realpath("/etc/localtime").partition("/zoneinfo/")[2]


def set_zone(zone):
    """True when timedated took it; False when polkit wants a password (no prompt from a background service)."""
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    try:
        bus.call_sync(TD, "/org/freedesktop/timedate1", TD, "SetTimezone", GLib.Variant("(sb)", (zone, False)),
                      None, Gio.DBusCallFlags.NONE, 10000, None)
        return True
    except GLib.Error as e:
        if "InteractiveAuthorizationRequired" in e.message or "AccessDenied" in e.message:
            return False
        raise


def wanted():
    """(zone, current): the zone for where we are, or (None, current) without a location."""
    pos = locate()
    return (zone_for(*pos) if pos else None), current()


def tick():
    if not store.get("timezone_auto"):
        return
    try:
        zone, now = wanted()
    except (GLib.Error, OSError, ValueError) as e:  # offline, GeoClue refused or an odd answer: next time
        print(f"timezone: {e}", file=sys.stderr)
        return
    if not zone or zone == now:
        return
    if set_zone(zone):
        notify.send(APP, f"Time zone changed to {zone}", f"Was {now}", icon="preferences-system-time")
    else:
        notify.send(APP, f"You seem to be in {zone}", f"The time zone is {now}: changing it needs a password "
                    "(Settings → System → Time zone).", icon="preferences-system-time")


def watch():
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    pending = []

    def soon(delay=15):  # one check shortly after the last trigger
        for src in pending:
            GLib.source_remove(src)
        pending[:] = [GLib.timeout_add_seconds(delay, lambda: (pending.clear(), tick()) and False)]

    def nm(_c, _s, _p, _i, _sig, params):
        if params.unpack()[0] == NM_GLOBAL:
            soon()
    bus.signal_subscribe("org.freedesktop.NetworkManager", "org.freedesktop.NetworkManager", "StateChanged",
                         "/org/freedesktop/NetworkManager", None, Gio.DBusSignalFlags.NONE, nm)
    GLib.timeout_add_seconds(EVERY, lambda: soon(0) or True)
    soon(30)
    GLib.MainLoop().run()


def selftest():
    assert valid("Asia/Phnom_Penh") and valid("America/Argentina/Buenos_Aires")
    assert not valid("") and not valid("UTC") and not valid("../etc/passwd") and not valid("Mars/Olympus")
    assert current() and "/" in current()
    print("ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    if cmd == "test":
        selftest()
    elif cmd == "check":
        pos = locate()
        print("location:", pos)
        zone = zone_for(*pos) if pos else None
        print(f"current: {current()}  would set: {zone if zone and zone != current() else 'nothing'}")
    elif cmd == "enabled":
        sys.exit(0 if notify.in_hyprland() else 1)
    elif cmd == "watch":
        watch()
    else:
        tick()

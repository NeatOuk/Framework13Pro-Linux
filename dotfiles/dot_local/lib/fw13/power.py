"""Battery (UPower), power profiles (power-profiles-daemon or tuned-ppd) and the charge limit — Gio D-Bus.

Same sources as the bar's fw-power-panel; powerprofilesctl isn't installed with tuned-ppd, so D-Bus is used.
"""
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

UP = "org.freedesktop.UPower"
PP = "org.freedesktop.UPower.PowerProfiles"
PP_PATH = "/org/freedesktop/UPower/PowerProfiles"
STATES = {1: "Charging", 2: "On battery", 3: "Empty", 4: "Fully charged", 5: "Plugged in · not charging",
          6: "On battery"}
TECH = {1: "lithium-ion", 2: "lithium-polymer", 3: "LiFePO4"}


def _bus():
    return Gio.bus_get_sync(Gio.BusType.SYSTEM)


def _call(dest, path, iface, method, args=None, reply=None):
    try:
        res = _bus().call_sync(dest, path, iface, method, args, GLib.VariantType(reply) if reply else None,
                               Gio.DBusCallFlags.NONE, 3000, None)
        return res.unpack() if res else None
    except GLib.Error:
        return None


def battery_path():
    devs = _call(UP, "/org/freedesktop/UPower", UP, "EnumerateDevices", None, "(ao)")
    return next((d for d in (devs or [[]])[0] if "battery_BAT" in d), None)


def battery():
    """Dict of UPower Device properties for the first battery, or None (desktop / no UPower)."""
    path = battery_path()
    if not path:
        return None
    props = _call(UP, path, "org.freedesktop.DBus.Properties", "GetAll",
                  GLib.Variant("(s)", ("org.freedesktop.UPower.Device",)), "(a{sv})")
    return dict(props[0], _path=path) if props else None


def set_charge_limit(enabled):
    path = battery_path()
    return path is not None and _call(UP, path, "org.freedesktop.UPower.Device", "EnableChargeThreshold",
                                      GLib.Variant("(b)", (enabled,))) is not None


def profiles():
    """(available profile names, active) or ([], None) without a power-profiles service."""
    def get(prop):
        r = _call(PP, PP_PATH, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (PP, prop)), "(v)")
        return r[0] if r else None
    avail = get("Profiles") or []
    order = ["performance", "balanced", "power-saver"]
    names = [p for p in order if any(a.get("Profile") == p for a in avail)]
    return names, get("ActiveProfile")


def set_profile(name):
    return _call(PP, PP_PATH, "org.freedesktop.DBus.Properties", "Set",
                 GLib.Variant("(ssv)", (PP, "ActiveProfile", GLib.Variant("s", name)))) is not None


def duration(seconds):
    m = int(seconds) // 60
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"

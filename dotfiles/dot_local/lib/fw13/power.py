"""Battery (UPower), power profiles (power-profiles-daemon or tuned-ppd) and the charge limit — Gio D-Bus.

Same sources as the bar's fw-power-panel; powerprofilesctl isn't installed with tuned-ppd, so D-Bus is used.
tuning() is a read-only look at what the profile actually set (sysfs + tuned's active profile); it never writes.
`python3 -m fw13.power tuning` prints it for the bash panel.
"""
import glob
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from . import store  # noqa: E402

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


WARN_CHOICES = (("20,10,5", "20, 10 and 5 %"), ("10,5", "10 and 5 %"), ("off", "Off"))  # store battery_warn


def warn_levels():
    """Low-battery warning levels (fw-battery-warn), from store `battery_warn`; default 20, 10 and 5 %."""
    v = store.get("battery_warn") or WARN_CHOICES[0][0]
    return tuple(int(x) for x in v.split(",")) if v != "off" else ()


def duration(seconds):
    m = int(seconds) // 60
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


# --- Tuning readout (read-only) -------------------------------------------------
CPU = "/sys/devices/system/cpu"


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip() or None
    except OSError:
        return None


def tuning():
    """What the power profile set, as a dict; every key is optional (missing when the system doesn't expose it).

    driver, pstate_mode (amd-pstate active/passive/guided), epp, epp_choices, boost (bool), platform_profile,
    platform_choices, abm (amdgpu panel_power_savings 0–4 on the internal panel), tuned (/etc/tuned/active_profile).
    """
    pol = f"{CPU}/cpufreq/policy0"
    t = {"driver": _read(f"{pol}/scaling_driver"), "pstate_mode": _read(f"{CPU}/amd_pstate/status"),
         "epp": _read(f"{pol}/energy_performance_preference"), "tuned": _read("/etc/tuned/active_profile")}
    t["epp_choices"] = (_read(f"{pol}/energy_performance_available_preferences") or "").split() or None
    boost = _read(f"{pol}/boost") or _read(f"{CPU}/cpufreq/boost")  # amd-pstate per policy; acpi-cpufreq global
    t["boost"] = boost == "1" if boost in ("0", "1") else None
    # Legacy ACPI file first; kernels ≥ 6.14 also have the platform-profile class (same value).
    prof = _read("/sys/firmware/acpi/platform_profile")
    choices = _read("/sys/firmware/acpi/platform_profile_choices")
    if prof is None:
        for d in sorted(glob.glob("/sys/class/platform-profile/platform-profile-*")):
            prof, choices = _read(f"{d}/profile"), _read(f"{d}/choices")
            if prof:
                break
    t["platform_profile"], t["platform_choices"] = prof, (choices or "").split() or None
    for f in sorted(glob.glob("/sys/class/drm/card*-eDP-*/amdgpu/panel_power_savings")):
        v = _read(f)
        if v and v.isdigit():
            t["abm"] = int(v)
            break
    return {k: v for k, v in t.items() if v is not None}


def tuning_rows(t=None):
    """[(title, value, hint or None)] for display; empty when nothing is readable."""
    t = tuning() if t is None else t
    rows = []
    if "driver" in t:
        rows.append(("CPU driver", t["driver"] + (f" · {t['pstate_mode']} mode" if "pstate_mode" in t else ""), None))
    if "epp" in t:
        rows.append(("Energy preference", t["epp"],
                     " · ".join(t["epp_choices"]) if "epp_choices" in t else None))
    if "boost" in t:
        rows.append(("CPU boost", "on" if t["boost"] else "off", None))
    if "platform_profile" in t:
        rows.append(("Platform profile", t["platform_profile"],
                     " · ".join(t["platform_choices"]) if "platform_choices" in t else None))
    if "abm" in t:
        rows.append(("Panel power savings", f"level {t['abm']} of 4" if t["abm"] else "off",
                     "amdgpu ABM: dims the backlight and boosts contrast to save power"))
    if "tuned" in t:
        rows.append(("tuned profile", t["tuned"], None))
    return rows


def main(argv):
    if argv[:1] == ["tuning"]:
        for title, value, _hint in tuning_rows():
            print(f"{title} · {value}")
        return 0
    print("usage: python3 -m fw13.power tuning", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Bluetooth through BlueZ on the system bus (org.bluez ObjectManager) — Gio D-Bus, no bluetoothctl parsing.

Every call is synchronous and safe from a worker thread; actions return (ok, message).
Pairing PINs/passkeys are answered by the running agent (blueman-applet), not here.
"""
import shutil
import subprocess
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
BATTERY = "org.bluez.Battery1"
PROPS = "org.freedesktop.DBus.Properties"

# BlueZ Icon property (freedesktop icon names) → Font Awesome 6 Free glyph
ICONS = {
    "audio-headset": "", "audio-headphones": "",    # headphones
    "audio-card": "", "audio-speakers": "",         # volume-high
    "input-mouse": "",                                    # computer-mouse
    "input-keyboard": "",                                 # keyboard
    "input-gaming": "",                                   # gamepad
    "input-tablet": "",                                   # tablet-screen-button
    "phone": "",                                          # mobile-screen-button
    "computer": "",                                       # laptop
    "printer": "",                                        # print
    "camera-photo": "", "camera-video": "",         # camera
    "video-display": "",                                  # tv
}
DEFAULT_ICON = ""  # bluetooth (Brands)


def _bus():
    return Gio.bus_get_sync(Gio.BusType.SYSTEM)


def _err(e):
    """'GDBus.Error:org.bluez.Error.Failed: Page Timeout' → 'Page Timeout' (or the error name)."""
    msg = e.message.split(": ", 1)[-1] if ": " in e.message else e.message
    return msg.removeprefix("GDBus.Error:")


def _call(path, iface, method, args=None, reply=None, timeout=10000):
    try:
        res = _bus().call_sync(BZ, path, iface, method, args, GLib.VariantType(reply) if reply else None,
                               Gio.DBusCallFlags.NO_AUTO_START, timeout, None)  # never start a stopped bluetoothd
        return True, res.unpack() if res else None
    except GLib.Error as e:
        return False, _err(e)


def _set(path, iface, prop, value):
    ok, msg = _call(path, PROPS, "Set", GLib.Variant("(ssv)", (iface, prop, value)))
    return ok, None if ok else msg


def _objects():
    ok, res = _call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects", reply="(a{oa{sa{sv}}})",
                    timeout=3000)
    return res[0] if ok and res else {}


def icon(name):
    return ICONS.get(name or "", DEFAULT_ICON)


def state():
    """(adapter, devices). adapter: {path, address, alias, powered} or None (no adapter / bluetoothd down).

    devices: [{path, address, name, alias, icon, paired, connected, trusted, battery, rssi}] for that adapter.
    `name` is the remote name or "" — Alias falls back to the address when a device never sent one.
    """
    objs = _objects()
    ad_path = next((p for p in sorted(objs) if ADAPTER in objs[p]), None)
    if not ad_path:
        return None, []
    a = objs[ad_path][ADAPTER]
    adapter = {"path": ad_path, "address": a.get("Address", ""), "alias": a.get("Alias") or a.get("Name", ""),
               "powered": bool(a.get("Powered"))}
    devices = []
    for path, ifaces in objs.items():
        d = ifaces.get(DEVICE)
        if not d or d.get("Adapter") != ad_path:
            continue
        devices.append({
            "path": path, "address": d.get("Address", ""), "name": d.get("Name", ""),
            "alias": d.get("Alias") or d.get("Name") or d.get("Address", ""), "icon": d.get("Icon", ""),
            "paired": bool(d.get("Paired")), "connected": bool(d.get("Connected")),
            "trusted": bool(d.get("Trusted")), "rssi": d.get("RSSI"),
            "battery": ifaces.get(BATTERY, {}).get("Percentage"),
        })
    devices.sort(key=lambda d: (not d["connected"], d["alias"].lower()))
    return adapter, devices


def _blocked(msg):
    return "lock" in (msg or "").lower()  # org.bluez.Error.Blocked / "Blocked through rfkill"


def set_powered(adapter_path, on):
    ok, msg = _set(adapter_path, ADAPTER, "Powered", GLib.Variant("b", on))
    if not ok and on and _blocked(msg) and shutil.which("rfkill"):
        # soft-blocked: /dev/rfkill is writable by the seat user. bluetoothd sees the unblock
        # asynchronously (its own rfkill fd), so retry for a moment. Worker thread: sleeping is fine.
        subprocess.run(["rfkill", "unblock", "bluetooth"], capture_output=True)
        for _ in range(6):
            time.sleep(0.5)
            ok, msg = _set(adapter_path, ADAPTER, "Powered", GLib.Variant("b", on))
            if ok or not _blocked(msg):
                break
    return ok, msg


def set_alias(adapter_path, alias):
    ok, msg = _set(adapter_path, ADAPTER, "Alias", GLib.Variant("s", alias))
    return ok, None if ok else f"Couldn't rename: {msg}"


def connect(path):
    ok, msg = _call(path, DEVICE, "Connect", timeout=40000)
    return ok, None if ok else msg


def disconnect(path):
    ok, msg = _call(path, DEVICE, "Disconnect", timeout=20000)
    return ok, None if ok else msg


def forget(adapter_path, path):
    ok, msg = _call(adapter_path, ADAPTER, "RemoveDevice", GLib.Variant("(o)", (path,)))
    return ok, None if ok else msg


def pair(path):
    """Pair → trust → connect. Pairing waits for the agent's PIN dialog, hence the long timeout."""
    ok, msg = _call(path, DEVICE, "Pair", timeout=120000)
    if not ok and "AlreadyExists" not in msg and "Already Exists" not in msg:
        return False, f"Pairing failed: {msg}"
    _set(path, DEVICE, "Trusted", GLib.Variant("b", True))
    ok, msg = connect(path)
    return True, None if ok else f"Paired, but connecting failed: {msg}"


def start_discovery(adapter_path):
    ok, msg = _call(adapter_path, ADAPTER, "StartDiscovery", timeout=5000)
    return ok, None if ok else msg


def stop_discovery(adapter_path):
    # BlueZ also stops it on its own when our bus connection goes away
    _call(adapter_path, ADAPTER, "StopDiscovery")


def watch(callback):
    """callback(path, signal, params) in the main loop when BlueZ objects or properties change. Returns unwatch()."""
    bus = _bus()
    ids = [bus.signal_subscribe(BZ, iface, member, None, None, Gio.DBusSignalFlags.NONE,
                                lambda *a: callback(a[2], a[4], a[5]))
           for iface, member in ((PROPS, "PropertiesChanged"),
                                 ("org.freedesktop.DBus.ObjectManager", "InterfacesAdded"),
                                 ("org.freedesktop.DBus.ObjectManager", "InterfacesRemoved"))]
    return lambda: [bus.signal_unsubscribe(i) for i in ids]

"""Desktop notifications with action buttons over Gio D-Bus (org.freedesktop.Notifications; mako in Hyprland).

Shared by fw-crash-watch (long-running, its own main loop), fw-health and fw-hwcheck (one notification, then
wait() for the click). Plain one-line messages from shell scripts stay with fw-notify.
"""
import os
import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

NAME = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
LOW, NORMAL, CRITICAL = 0, 1, 2


def _bus():
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION)
    except GLib.Error:
        return None


def session_env(name):
    """$name from this process, else from the systemd --user manager right now: a user unit's environment is
    fixed when it starts, which can be before uwsm exported the Hyprland session (e.g. a timer's catch-up at login)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        out = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in out.splitlines():
        key, _, value = line.partition("=")
        if key == name:
            return value
    return ""


def in_hyprland():
    return "hyprland" in session_env("XDG_CURRENT_DESKTOP").lower() and bool(session_env("WAYLAND_DISPLAY"))


def available(bus=None):
    """True when a notification daemon owns the name right now (never starts one through D-Bus activation)."""
    bus = bus or _bus()
    if bus is None:
        return False
    try:
        res = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                            GLib.Variant("(s)", (NAME,)), GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE, 3000, None)
        return bool(res.unpack()[0])
    except GLib.Error:
        return False


def send(app, title, body, actions=(), urgency=NORMAL, icon="", timeout=0, bus=None):
    """Notification id, or None (no daemon / D-Bus error). actions: [(key, label)]; "default" = a click on it.
    timeout in ms; 0 leaves it to the daemon (mako: default-timeout)."""
    bus = bus or _bus()
    if bus is None:
        return None
    flat = [s for pair in actions for s in pair]
    try:
        res = bus.call_sync(NAME, PATH, NAME, "Notify",
                            GLib.Variant("(susssasa{sv}i)", (app, 0, icon, title, body, flat,
                                                             {"urgency": GLib.Variant("y", urgency)}, timeout)),
                            GLib.VariantType("(u)"), Gio.DBusCallFlags.NO_AUTO_START, 5000, None)
        return res.unpack()[0]
    except GLib.Error:
        return None


def on_action(bus, callback):
    """callback(id, action) for every ActionInvoked; returns the subscription id."""
    def handler(_conn, _sender, _path, _iface, _signal, params):
        nid, action = params.unpack()
        callback(nid, action)
    return bus.signal_subscribe(None, NAME, "ActionInvoked", PATH, None, Gio.DBusSignalFlags.NONE, handler)


def wait(nid, limit=3600, bus=None):
    """Block until notification `nid` gets an action (returns its key) or closes / `limit` seconds pass (None)."""
    bus = bus or _bus()
    if bus is None or not nid:
        return None
    loop = GLib.MainLoop()
    result = []

    def acted(_c, _s, _p, _i, _sig, params):
        n, action = params.unpack()
        if n == nid:
            result.append(action)
            loop.quit()

    def closed(_c, _s, _p, _i, _sig, params):
        if params.unpack()[0] == nid:
            GLib.timeout_add(300, loop.quit)  # some daemons close right before ActionInvoked arrives

    subs = [bus.signal_subscribe(None, NAME, "ActionInvoked", PATH, None, Gio.DBusSignalFlags.NONE, acted),
            bus.signal_subscribe(None, NAME, "NotificationClosed", PATH, None, Gio.DBusSignalFlags.NONE, closed)]
    GLib.timeout_add_seconds(limit, loop.quit)
    loop.run()
    for s in subs:
        bus.signal_unsubscribe(s)
    return result[0] if result else None


def launch(argv):
    """Start a GUI command detached from the caller: through uwsm (its own unit, so it survives a oneshot service
    or a short-lived parent) inside a uwsm session, else in a new session."""
    if shutil.which("uwsm") and session_env("WAYLAND_DISPLAY"):
        argv = ["uwsm", "app", "--", *argv]
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)

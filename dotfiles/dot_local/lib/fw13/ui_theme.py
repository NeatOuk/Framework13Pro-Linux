"""GTK3 look shared by fw-settings and the bar panels: flat, no rounding, JetBrains Mono.

Colours come from fw13.theme.palette() (Tokyo Night, or the wallpaper palette). install() watches
~/.config/fw13/theme/ and the settings store, so an open window recolours when the theme changes; widgets that
draw their own colours (cairo) register with watch() and read rgb().
"""
import os
import re
import string

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import store, theme  # noqa: E402

CSS = string.Template("""
window, .page { background: $bg; color: $fg;
                font-family: "JetBrains Mono", "Font Awesome 6 Free"; font-size: 11pt; }
window.panel { border: 2px solid $accent; }
.title { color: $accent; }
.heading { color: $fg_bright; font-weight: bold; margin-top: 8px; }
.dim { color: $fg_dim; }
.ok { color: $ok; }
.warn { color: $warn; }
.bad { color: $bad; }
button { background: $surface2; color: $fg_bright; border: none; border-radius: 0; box-shadow: none;
         padding: 4px 14px; background-image: none; text-shadow: none; }
button:hover { background: $surface3; }
button.primary { background: $accent; color: $bg; }
button.danger:hover { background: $bad; color: $bg; }
button:disabled, button.primary:disabled { background: $surface2; color: $fg_dim; }
combobox button { padding: 2px 8px; }
entry { background: $bg_dim; color: $fg_bright; border: 1px solid $surface2; border-radius: 0; box-shadow: none;
        padding: 4px 8px; }
entry:focus { border-color: $accent; }
switch { background: $surface2; border: none; border-radius: 0; box-shadow: none; }
switch:checked { background: $accent; }
switch slider { background: $fg_bright; border: none; border-radius: 0; box-shadow: none; min-width: 20px; }
scale trough { background: $surface2; min-height: 6px; border-radius: 0; border: none; }
scale highlight { background: $accent; border-radius: 0; border: none; }
scale slider { background: $fg_bright; min-width: 14px; min-height: 14px; border-radius: 0;
               border: none; box-shadow: none; }
separator { background: $surface2; min-height: 1px; }
levelbar trough { background: $surface2; border: none; border-radius: 0; padding: 0; }
levelbar block { border: none; border-radius: 0; min-height: 8px; }
levelbar block.filled { background: $accent; }
levelbar block.filled.low { background: $bad; }
levelbar block.empty { background: $surface2; }
radio, check { background: $surface2; border: none; border-radius: 0; box-shadow: none; color: transparent;
               min-width: 14px; min-height: 14px; -gtk-icon-source: none; margin-right: 8px; }
radio:checked, check:checked { background: $accent; }
radiobutton:hover radio, checkbutton:hover check { background: $surface3; }
radiobutton:hover radio:checked, checkbutton:hover check:checked { background: $accent; }
/* fw-settings sidebar */
.sidebar { background: $bg_dim; }
.sidebar row { padding: 8px 14px; border-left: 3px solid transparent; color: $fg; }
.sidebar row:selected { background: $surface2; border-left-color: $accent; color: $fg_bright; }
.sidebar row:hover { background: $surface; }
list, list row { background: transparent; }
.item { padding: 6px 4px; border-bottom: 1px solid $surface; }
""")

_HEX = re.compile(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")
_current = dict(theme.TOKYO_NIGHT)
_provider = None
_monitors = []   # keep the Gio.FileMonitors alive
_listeners = []  # callables run after the palette changed
_timer = None


def current():
    """The palette the UI is drawn with (a theme.palette() snapshot; malformed roles fall back to Tokyo Night)."""
    return _current


def _load():
    try:
        p = theme.palette()
    except Exception:  # noqa: BLE001 — a broken store must not keep Settings from opening
        p = theme.TOKYO_NIGHT
    return {k: (p.get(k) if isinstance(p.get(k), str) and _HEX.fullmatch(p.get(k)) else v)
            for k, v in theme.TOKYO_NIGHT.items() if k != "ansi"}


def css(p=None):
    """The stylesheet (bytes) for palette `p` (default: the current one)."""
    p = p or _current
    return CSS.substitute({k: v[:7] for k, v in p.items()}).encode()


def rgb(role, p=None):
    """Palette role as cairo floats, e.g. cr.set_source_rgb(*rgb("accent"))."""
    c = (p or _current)[role].lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def watch(widget, cb):
    """Call cb() whenever the palette changes, until `widget` is destroyed."""
    _listeners.append(cb)
    widget.connect("destroy", lambda _w: cb in _listeners and _listeners.remove(cb))


def _apply():
    global _current
    p = _load()
    try:
        _provider.load_from_data(css(p))
    except GLib.Error:
        p = dict(theme.TOKYO_NIGHT)
        _provider.load_from_data(css(p))
    _current = p
    for cb in list(_listeners):
        cb()


def _changed(*_):
    """Debounced: the engine writes six files and then the store; recolour once, and only if colours moved."""
    global _timer
    if _timer:
        GLib.source_remove(_timer)
    _timer = GLib.timeout_add(250, _recheck)


def _recheck():
    global _timer
    _timer = None
    sync()
    return False


def sync():
    """Recolour now if the stored palette differs from the one in use (e.g. right after theme.set_source())."""
    if _provider is not None and _load() != _current:
        _apply()


def _monitor(path):
    try:
        m = Gio.File.new_for_path(path).monitor_directory(Gio.FileMonitorFlags.NONE, None)
    except GLib.Error:
        return
    m.connect("changed", _changed)
    _monitors.append(m)


def install():
    """Style every window of this process with the current palette and follow theme changes."""
    global _provider
    if _provider is None:
        _provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), _provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # palette() reads the store; the theme dir changes in the same set_source() call (a seeded-only
        # install has no store entry yet, so watch both). A missing dir is watched until it appears.
        _monitor(theme.DIR)
        _monitor(os.path.dirname(store.PATH))
    _apply()


def label(text, *classes, xalign=0, **kw):
    w = Gtk.Label(label=text, xalign=xalign, **kw)
    for c in classes:
        w.get_style_context().add_class(c)
    return w


def button(text, cb=None, *classes):
    b = Gtk.Button(label=text)
    for c in classes:
        b.get_style_context().add_class(c)
    if cb:
        b.connect("clicked", lambda _b: cb())
    return b

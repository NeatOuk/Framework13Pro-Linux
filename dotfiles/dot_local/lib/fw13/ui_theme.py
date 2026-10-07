"""GTK3 look shared by fw-settings and the bar panels: flat Tokyo Night, no rounding, JetBrains Mono."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

CSS = b"""
window, .page { background: #1a1b26; color: #a9b1d6;
                font-family: "JetBrains Mono", "Font Awesome 6 Free"; font-size: 11pt; }
window.panel { border: 2px solid #7aa2f7; }
.title { color: #7aa2f7; }
.heading { color: #c0caf5; font-weight: bold; margin-top: 8px; }
.dim { color: #565f89; }
.ok { color: #9ece6a; }
.warn { color: #e0af68; }
.bad { color: #f7768e; }
button { background: #292e42; color: #c0caf5; border: none; border-radius: 0; box-shadow: none;
         padding: 4px 14px; background-image: none; text-shadow: none; }
button:hover { background: #3b4261; }
button.primary { background: #7aa2f7; color: #1a1b26; }
button.danger:hover { background: #f7768e; color: #1a1b26; }
button:disabled, button.primary:disabled { background: #292e42; color: #565f89; }
combobox button { padding: 2px 8px; }
entry { background: #16161e; color: #c0caf5; border: 1px solid #292e42; border-radius: 0; box-shadow: none;
        padding: 4px 8px; }
entry:focus { border-color: #7aa2f7; }
switch { background: #292e42; border: none; border-radius: 0; box-shadow: none; }
switch:checked { background: #7aa2f7; }
switch slider { background: #c0caf5; border: none; border-radius: 0; box-shadow: none; min-width: 20px; }
scale trough { background: #292e42; min-height: 6px; border-radius: 0; border: none; }
scale highlight { background: #7aa2f7; border-radius: 0; border: none; }
scale slider { background: #c0caf5; min-width: 14px; min-height: 14px; border-radius: 0;
               border: none; box-shadow: none; }
separator { background: #292e42; min-height: 1px; }
levelbar trough { background: #292e42; border: none; border-radius: 0; padding: 0; }
levelbar block { border: none; border-radius: 0; min-height: 8px; }
levelbar block.filled { background: #7aa2f7; }
levelbar block.filled.low { background: #f7768e; }
levelbar block.empty { background: #292e42; }
radio, check { background: #292e42; border: none; border-radius: 0; box-shadow: none; color: transparent;
               min-width: 14px; min-height: 14px; -gtk-icon-source: none; margin-right: 8px; }
radio:checked, check:checked { background: #7aa2f7; }
radiobutton:hover radio, checkbutton:hover check { background: #3b4261; }
radiobutton:hover radio:checked, checkbutton:hover check:checked { background: #7aa2f7; }
/* fw-settings sidebar */
.sidebar { background: #16161e; }
.sidebar row { padding: 8px 14px; border-left: 3px solid transparent; color: #a9b1d6; }
.sidebar row:selected { background: #292e42; border-left-color: #7aa2f7; color: #c0caf5; }
.sidebar row:hover { background: #1f2335; }
list, list row { background: transparent; }
.item { padding: 6px 4px; border-bottom: 1px solid #1f2335; }
"""


def install():
    css = Gtk.CssProvider()
    css.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


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

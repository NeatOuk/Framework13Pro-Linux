"""Small building blocks for fw-settings pages."""
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ..ui_theme import label  # noqa: E402,F401  (re-export for pages)


def wrap(lbl):
    """Let a label wrap, so long text doesn't set the page's minimum width (Settings tiled at half a screen)."""
    lbl.set_line_wrap(True)
    lbl.set_line_wrap_mode(Pango.WrapMode.WORD)
    return lbl


NARROW = 620  # page width (px) below which rows put their control under the text (Settings at half a screen)


class Page(Gtk.ScrolledWindow):
    """Scrollable page with a title; add sections with heading() / row(). Rows registered with adapt() stack
    vertically when the page is narrow."""

    def __init__(self, title):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.narrow = False
        self.adaptive = []  # (row box, its control)
        self.connect("size-allocate", self._on_allocate)
        self.get_style_context().add_class("page")
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(24)
        self.box.pack_start(label(title, "title"), False, False, 0)
        self.add(self.box)

    def add_widget(self, w, expand=False):
        self.box.pack_start(w, expand, expand, 0)
        return w

    def heading(self, text):
        return self.add_widget(label(text, "heading"))

    def row(self, text, widget=None, hint=None):
        """'text  ...  widget' line, with an optional dim hint under the text."""
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(wrap(label(text)), False, False, 0)
        if hint:
            left.pack_start(wrap(label(hint, "dim")), False, False, 0)
        r.pack_start(left, True, True, 0)
        if widget is not None:
            widget.set_valign(Gtk.Align.CENTER)
            r.pack_end(widget, False, False, 0)
            self.adapt(r, widget)
        return self.add_widget(r)

    def adapt(self, r, widget):
        """Lay `r` (a horizontal Box: text, then `widget` packed at the end) out for the current width."""
        self.adaptive.append((r, widget))
        self._layout(r, widget)
        return r

    def _layout(self, r, widget):
        r.set_orientation(Gtk.Orientation.VERTICAL if self.narrow else Gtk.Orientation.HORIZONTAL)
        r.set_spacing(6 if self.narrow else 12)
        widget.set_halign(Gtk.Align.START if self.narrow else Gtk.Align.FILL)

    def _on_allocate(self, _w, alloc):
        narrow = alloc.width < NARROW
        if narrow != self.narrow:
            self.narrow = narrow
            GLib.idle_add(self._relayout)  # not from inside size-allocate

    def _relayout(self):
        self.adaptive = [(r, w) for r, w in self.adaptive if r.get_parent() is not None]
        for r, w in self.adaptive:
            self._layout(r, w)
        return False

    def clear(self, keep=1):
        """Remove everything after the first `keep` children (the title)."""
        for child in self.box.get_children()[keep:]:
            self.box.remove(child)
        self.adaptive = [(r, w) for r, w in self.adaptive if r.get_parent() is not None]

    def refresh(self):
        pass


def launch(*cmd):
    subprocess.Popen(["uwsm", "app", "--", *cmd], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def placeholder(title, text, tool_label=None, tool_cmd=None):
    page = Page(title)
    page.add_widget(label(text, "dim", wrap=True))
    if tool_label:
        b = Gtk.Button(label=tool_label)
        b.set_halign(Gtk.Align.START)
        b.connect("clicked", lambda _b: launch(*tool_cmd))
        page.add_widget(b)
    return page

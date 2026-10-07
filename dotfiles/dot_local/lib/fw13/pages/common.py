"""Small building blocks for fw-settings pages."""
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ..ui_theme import label  # noqa: E402,F401  (re-export for pages)


class Page(Gtk.ScrolledWindow):
    """Scrollable page with a title; add sections with heading() / row()."""

    def __init__(self, title):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
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
        left.pack_start(label(text), False, False, 0)
        if hint:
            left.pack_start(label(hint, "dim"), False, False, 0)
        r.pack_start(left, True, True, 0)
        if widget is not None:
            widget.set_valign(Gtk.Align.CENTER)
            r.pack_end(widget, False, False, 0)
        return self.add_widget(r)

    def clear(self, keep=1):
        """Remove everything after the first `keep` children (the title)."""
        for child in self.box.get_children()[keep:]:
            self.box.remove(child)

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

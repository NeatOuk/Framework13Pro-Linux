"""Display: brightness + arrange/refresh/scale (shared DisplayEditor) + night light."""
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import store  # noqa: E402
from ..ui_display import DisplayEditor  # noqa: E402
from .common import Page  # noqa: E402


def nightlight_on():
    return subprocess.run(["pgrep", "-x", "hyprsunset"], capture_output=True).returncode == 0


def nightlight(on, temp):
    subprocess.run(["pkill", "-x", "hyprsunset"])
    if on:
        subprocess.Popen(["uwsm", "app", "--", "hyprsunset", "-t", str(int(temp))], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class DisplayPage(Page):
    def __init__(self):
        super().__init__("Display")
        self.editor = DisplayEditor()
        self.add_widget(self.editor)
        self.heading("Night light")
        self.sw = Gtk.Switch()
        self.sw.set_active(nightlight_on())
        self.sw.connect("state-set", lambda _s, on: nightlight(on, self.temp.get_value()) or False)
        self.row("Warmer colours in the evening", self.sw, hint="Also SUPER+N")
        self.temp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2500, 6000, 100)
        self.temp.set_value(store.get("nightlight_temp"))
        self.temp.set_size_request(260, -1)
        self.temp.set_draw_value(False)
        self.tlabel = Gtk.Label(label=f"{int(self.temp.get_value())} K", width_chars=7, xalign=1)
        self.pending = None
        self.temp.connect("value-changed", self.on_temp)
        box = Gtk.Box(spacing=8)
        box.pack_start(self.temp, False, False, 0)
        box.pack_start(self.tlabel, False, False, 0)
        self.row("Temperature", box)

    def on_temp(self, scale):
        self.tlabel.set_text(f"{int(scale.get_value())} K")
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(400, self.flush_temp)

    def flush_temp(self):
        self.pending = None
        store.set("nightlight_temp", int(self.temp.get_value()))
        if self.sw.get_active():
            nightlight(True, self.temp.get_value())
        return False

    def refresh(self):
        if not self.editor.unconfirmed():
            self.editor.restore()  # re-read monitors (hotplug) — no-op when nothing was applied
        self.sw.set_active(nightlight_on())

    def closing(self):
        if self.editor.unconfirmed():
            self.editor.restore()


def build():
    return DisplayPage()

"""Sound: output and input devices (default + volume + mute) via wpctl."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import sound  # noqa: E402
from .common import Page, label, launch  # noqa: E402


class SoundPage(Page):
    def __init__(self):
        super().__init__("Sound")
        self.pending = {}
        self.refresh()

    def refresh(self):
        self.clear()
        devs = sound.devices()
        for key, title in (("sinks", "Output"), ("sources", "Input")):
            self.heading(title)
            if not devs[key]:
                self.add_widget(label("No devices", "dim"))
            for d in devs[key]:
                self.device_row(d)
        b = Gtk.Button(label="Advanced… (pavucontrol)")
        b.set_halign(Gtk.Align.START)
        b.connect("clicked", lambda _b: launch("pavucontrol"))
        self.add_widget(b)
        self.show_all()

    def device_row(self, d):
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        radio = Gtk.Button(label=("●  " if d["default"] else "○  ") + d["name"])
        radio.set_relief(Gtk.ReliefStyle.NONE)
        if d["default"]:
            radio.get_style_context().add_class("primary")
        radio.connect("clicked", lambda _b: (sound.set_default(d["id"]), self.refresh()))
        r.pack_start(radio, False, False, 0)
        mute = Gtk.ToggleButton(label="" if d["muted"] else "")
        mute.set_active(d["muted"])
        mute.connect("toggled", lambda b: (sound.set_mute(d["id"], b.get_active()),
                                           b.set_label("" if b.get_active() else "")))
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        vol.set_draw_value(False)
        vol.set_size_request(220, -1)
        vol.set_value(round(min(d["volume"], 1.0) * 100))
        pct = label(f"{int(vol.get_value())}%", width_chars=4, xalign=1)
        vol.connect("value-changed", self.on_volume, d["id"], pct)
        r.pack_end(pct, False, False, 0)
        r.pack_end(vol, False, False, 0)
        r.pack_end(mute, False, False, 0)
        self.add_widget(r)

    def on_volume(self, scale, node_id, pct):
        pct.set_text(f"{int(scale.get_value())}%")
        if self.pending.get(node_id):
            GLib.source_remove(self.pending[node_id])

        def flush():
            self.pending[node_id] = None
            sound.set_volume(node_id, scale.get_value() / 100)
            return False
        self.pending[node_id] = GLib.timeout_add(60, flush)


def build():
    return SoundPage()

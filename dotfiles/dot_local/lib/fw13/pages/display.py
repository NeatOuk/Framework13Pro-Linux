"""Display: brightness + auto-brightness + arrange/refresh/scale (shared DisplayEditor) + night light + its schedule."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import nightlight as nl  # noqa: E402
from .. import store  # noqa: E402
from ..ui_display import DisplayEditor  # noqa: E402
from .common import Page, label  # noqa: E402
from .system import bg  # noqa: E402


class DisplayPage(Page):
    def __init__(self):
        super().__init__("Display")
        self.editor = DisplayEditor()
        self.add_widget(self.editor)
        self.heading("Night light")
        self.sw = Gtk.Switch()
        self.sw.set_active(nl.on())
        self.sw_id = self.sw.connect("state-set", lambda _s, on: nl.switch(on, self.temp.get_value()) or False)
        self.row("Warmer colours in the evening", self.sw, hint="Also SUPER+N")
        self.temp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2500, 6000, 100)
        self.temp.set_value(store.get("nightlight_temp"))
        self.temp.set_size_request(160, -1)
        self.temp.set_draw_value(False)
        self.tlabel = Gtk.Label(label=f"{int(self.temp.get_value())} K", width_chars=7, xalign=1)
        self.pending = None
        self.temp.connect("value-changed", self.on_temp)
        box = Gtk.Box(spacing=8)
        box.pack_start(self.temp, False, False, 0)
        box.pack_start(self.tlabel, False, False, 0)
        self.row("Temperature", box)
        self.sched = Gtk.ComboBoxText()
        for k, v in nl.SCHEDULES.items():
            self.sched.append(k, v)
        self.sched.set_active_id(store.get("nightlight_schedule") or "off")
        self.sched.connect("changed", self.on_schedule)
        self.sched_row = self.row("Schedule", self.sched, hint=" ")
        self.sched_hint = self.sched_row.get_children()[0].get_children()[1]
        self.times = Gtk.Box(spacing=8)
        self.entries = []
        for key, default in zip(("nightlight_from", "nightlight_to"), nl.FALLBACK):
            e = Gtk.Entry(text=store.get(key) or default, width_chars=6, max_length=5)
            e.connect("activate", self.on_times)
            e.connect("focus-out-event", lambda *_: self.on_times() or False)
            self.entries.append((key, e))
        self.times.pack_start(self.entries[0][1], False, False, 0)
        self.times.pack_start(label("to"), False, False, 0)
        self.times.pack_start(self.entries[1][1], False, False, 0)
        self.times_row = self.row("On from", self.times, hint="24-hour HH:MM; SUPER+N still toggles until the next change")
        self.render_schedule()

    def render_schedule(self):
        mode = self.sched.get_active_id()
        self.times_row.set_no_show_all(mode != "custom")
        self.times_row.show_all() if mode == "custom" else self.times_row.hide()
        if mode == "sun":
            self.sched_hint.set_text("Looking up sunset…")
            bg(nl.window, lambda w: self.sched_hint.set_text(
                f"On at sunset {w[0]}, off at sunrise {w[1]}" + (" (fixed times: no forecast)" if w == nl.FALLBACK else "")))
        else:
            self.sched_hint.set_text("Turns night light on and off by itself" if mode == "custom" else
                                     "Night light only changes when you switch it")

    def on_schedule(self, combo):
        store.set("nightlight_schedule", combo.get_active_id())
        self.apply_schedule()
        self.render_schedule()

    def on_times(self, *_):
        bad = changed = False
        for key, e in self.entries:
            try:
                nl.minutes(e.get_text())
            except ValueError:
                bad = True
                continue
            changed |= e.get_text().strip() != store.get(key)
            store.set(key, e.get_text().strip())
        self.sched_hint.set_text("Use 24-hour times like 19:00" if bad else "Turns night light on and off by itself")
        if changed and not bad:  # only a real change re-applies, so leaving the field keeps a manual toggle
            self.apply_schedule()

    def apply_schedule(self):
        nl.reset()
        bg(nl.tick, lambda _r: GLib.timeout_add(1000, self.sync_switch) and False)  # hyprsunset takes a moment to start

    def sync_switch(self):
        """Show whether hyprsunset runs without the switch's handler starting or stopping it."""
        self.sw.handler_block(self.sw_id)
        self.sw.set_active(nl.on())
        self.sw.handler_unblock(self.sw_id)
        return False

    def on_temp(self, scale):
        self.tlabel.set_text(f"{int(scale.get_value())} K")
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(400, self.flush_temp)

    def flush_temp(self):
        self.pending = None
        store.set("nightlight_temp", int(self.temp.get_value()))
        if self.sw.get_active():
            nl.switch(True, self.temp.get_value())
        return False

    def refresh(self):
        if not self.editor.unconfirmed():
            self.editor.restore()  # re-read monitors (hotplug) — no-op when nothing was applied
        self.sync_switch()
        self.editor.refresh_auto()

    def closing(self):
        if self.editor.unconfirmed():
            self.editor.restore()


def build():
    return DisplayPage()

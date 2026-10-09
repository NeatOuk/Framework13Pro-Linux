"""DisplayEditor: brightness (+ auto switch) + drag-to-arrange monitors + refresh/scale, Apply → Keep (15 s) / Revert.

Used by the bar's fw-display-panel (in a layer-shell popup) and fw-settings' Display page.
"""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import als, displays, theme  # noqa: E402
from .ui_theme import rgb, watch  # noqa: E402

KEEP_SECONDS = 15
CANVAS_H = 170


class DisplayEditor(Gtk.Box):
    def __init__(self, brightness=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.mons = displays.read_monitors()
        self.before = None   # snapshots while waiting for Keep
        self.drag = None     # (monitor, grab offset x, y in logical px)
        self.view = None     # (factor, offset x, offset y) canvas mapping, fixed during a drag
        self.pending = None  # brightness debounce
        self.auto = None     # auto-brightness switch (only with a light sensor, inside Hyprland)

        if brightness and displays.has_backlight():
            row = Gtk.Box(spacing=10)
            row.pack_start(Gtk.Label(label=""), False, False, 0)
            self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
            self.bright.set_draw_value(False)
            self.bright.set_value(displays.get_brightness())
            self.pct = Gtk.Label(label=f"{int(self.bright.get_value())}%", width_chars=4, xalign=1)
            self.bright.connect("value-changed", self.on_brightness)
            row.pack_start(self.bright, True, True, 0)
            row.pack_start(self.pct, False, False, 0)
            self.pack_start(row, False, False, 0)
            if als.hyprland() and als.available():
                self.add_auto_row()

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(-1, CANVAS_H)
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK)
        self.canvas.connect("draw", self.on_draw)
        self.canvas.connect("button-press-event", self.on_press)
        self.canvas.connect("motion-notify-event", self.on_motion)
        self.canvas.connect("button-release-event", self.on_release)
        watch(self.canvas, self.canvas.queue_draw)  # recolour with the theme
        self.pack_start(self.canvas, False, False, 0)
        hint = Gtk.Label(label="Drag a screen to move it", xalign=0.5)
        hint.get_style_context().add_class("dim")
        self.pack_start(hint, False, False, 0)

        self.rows = Gtk.Grid(column_spacing=10, row_spacing=6)
        self.pack_start(self.rows, False, False, 0)
        self.build_rows()

        self.buttons = Gtk.Box(spacing=8)
        self.revert_btn = Gtk.Button(label="Revert")
        self.revert_btn.connect("clicked", lambda _b: self.restore())
        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.get_style_context().add_class("primary")
        self.apply_btn.connect("clicked", self.on_apply)
        self.ask = Gtk.Label(label="Keep these display settings?", xalign=0)
        self.ask.set_no_show_all(True)
        self.buttons.pack_start(self.ask, True, True, 0)
        self.buttons.pack_end(self.apply_btn, False, False, 0)
        self.buttons.pack_end(self.revert_btn, False, False, 0)
        self.pack_start(self.buttons, False, False, 0)
        self.set_dirty(False)

    def build_rows(self):
        for child in self.rows.get_children():
            self.rows.remove(child)
        for i, m in enumerate(self.mons):
            name = Gtk.Label(label=m.name, xalign=0)
            desc = Gtk.Label(label=m.desc, xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=16)
            desc.get_style_context().add_class("dim")
            hz = Gtk.ComboBoxText()
            for r in m.rates:
                hz.append(f"{r:.3f}", f"{r:.2f}".rstrip("0").rstrip(".") + " Hz")
            hz.set_active_id(f"{m.rr:.3f}")
            hz.connect("changed", self.on_rate, m)
            combo = Gtk.ComboBoxText()
            for s in m.scales():
                combo.append(f"{s:.6f}", f"{s:.2f}".rstrip("0").rstrip(".") + "×")
            combo.set_active_id(next(f"{s:.6f}" for s in m.scales() if abs(s - m.scale) < 0.001))
            combo.connect("changed", self.on_scale, m)
            self.rows.attach(name, 0, i, 1, 1)
            self.rows.attach(desc, 1, i, 1, 1)
            desc.set_hexpand(True)
            self.rows.attach(hz, 2, i, 1, 1)
            self.rows.attach(combo, 3, i, 1, 1)
        self.rows.show_all()

    def add_auto_row(self):
        row = Gtk.Box(spacing=10)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.pack_start(Gtk.Label(label="Adjust to ambient light", xalign=0), False, False, 0)
        self.auto_hint = Gtk.Label(xalign=0, wrap=True)
        self.auto_hint.get_style_context().add_class("dim")
        text.pack_start(self.auto_hint, False, False, 0)
        row.pack_start(text, True, True, 0)
        self.auto = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.auto.connect("state-set", self.on_auto)
        row.pack_end(self.auto, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.refresh_auto()

    def refresh_auto(self):
        """Switch and hint from the store and the daemon's state (paused by a manual change, ...)."""
        if self.auto is None:
            return False
        on = als.enabled()
        self.auto.handler_block_by_func(self.on_auto)
        self.auto.set_active(on)
        self.auto.handler_unblock_by_func(self.on_auto)
        holds = als.state()["holds"] if on else []
        self.auto_hint.set_text("Paused by a manual change until the next wake or login" if "manual" in holds
                                else "A brightness key or the slider pauses it until the next wake or login")
        return False

    def on_auto(self, _sw, on):
        als.set_enabled(on)
        GLib.timeout_add(1500, self.refresh_auto)
        return False

    def set_dirty(self, dirty):
        self.apply_btn.set_sensitive(dirty)
        self.revert_btn.set_sensitive(dirty)

    # brightness
    def on_brightness(self, scale):
        self.pct.set_text(f"{int(scale.get_value())}%")
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(50, self.flush_brightness)

    def flush_brightness(self):
        self.pending = None
        displays.set_brightness(self.bright.get_value())
        if self.auto is not None and self.auto.get_active():
            GLib.timeout_add(2500, self.refresh_auto)  # the daemon notices within ~2 s and pauses
        return False

    # canvas
    def mapping(self):
        if self.drag and self.view:
            return self.view
        a = self.canvas.get_allocation()
        bw = max(m.x + m.lw for m in self.mons) - min(m.x for m in self.mons)
        bh = max(m.y + m.lh for m in self.mons) - min(m.y for m in self.mons)
        f = min((a.width - 40) / bw, (a.height - 20) / bh)
        ox = (a.width - bw * f) / 2 - min(m.x for m in self.mons) * f
        oy = (a.height - bh * f) / 2 - min(m.y for m in self.mons) * f
        self.view = (f, ox, oy)
        return self.view

    def on_draw(self, _w, cr):
        if not self.mons:
            return
        f, ox, oy = self.mapping()
        for m in self.mons:
            x, y, w, h = ox + m.x * f, oy + m.y * f, m.lw * f, m.lh * f
            active = self.drag and self.drag[0] is m
            cr.set_source_rgb(*rgb("surface3" if active else "surface2"))
            cr.rectangle(x + 1, y + 1, w - 2, h - 2)
            cr.fill_preserve()
            cr.set_source_rgb(*rgb("accent" if active else "fg_dim"))
            cr.set_line_width(2)
            cr.stroke()
            cr.set_source_rgb(*rgb("fg_bright"))
            cr.select_font_face(theme.font())
            cr.set_font_size(12)
            for i, text in enumerate((m.name, f"{m.scale:.2f}".rstrip("0").rstrip(".") + "×")):
                ext = cr.text_extents(text)
                cr.move_to(x + (w - ext.width) / 2, y + h / 2 - 4 + i * 16)
                cr.show_text(text)

    def hit(self, ex, ey):
        f, ox, oy = self.mapping()
        lx, ly = (ex - ox) / f, (ey - oy) / f
        for m in reversed(self.mons):
            if m.x <= lx <= m.x + m.lw and m.y <= ly <= m.y + m.lh:
                return m, lx - m.x, ly - m.y
        return None

    def on_press(self, _w, e):
        if self.before is None and len(self.mons) > 1:
            self.drag = self.hit(e.x, e.y)
            self.canvas.queue_draw()

    def on_motion(self, _w, e):
        if self.drag:
            m, gx, gy = self.drag
            f, ox, oy = self.view
            m.x, m.y = (e.x - ox) / f - gx, (e.y - oy) / f - gy
            self.canvas.queue_draw()

    def on_release(self, _w, _e):
        if self.drag:
            m = self.drag[0]
            self.drag = None
            displays.snap(m, self.mons)
            displays.normalise(self.mons)
            self.set_dirty(True)
            self.canvas.queue_draw()

    def on_rate(self, combo, m):
        m.rr = float(combo.get_active_id())
        self.set_dirty(True)

    def on_scale(self, combo, m):
        m.scale = float(combo.get_active_id())
        displays.snap(m, self.mons)
        displays.normalise(self.mons)
        self.set_dirty(True)
        self.canvas.queue_draw()

    # apply / keep / revert
    def on_apply(self, _b):
        if self.before is not None:  # the button reads "Keep (n)" while waiting
            self.keep()
            return
        current = {m.desc: m for m in displays.read_monitors()}
        self.before = {m.desc: current[m.desc].snapshot() for m in self.mons if m.desc in current}
        if not displays.apply(self.mons):
            self.restore()
            return
        self.countdown = KEEP_SECONDS
        self.ask.show()
        self.apply_btn.set_label(f"Keep ({self.countdown})")
        self.revert_btn.set_sensitive(True)
        GLib.timeout_add_seconds(1, self.tick)

    def tick(self):
        if self.before is None:
            return False
        self.countdown -= 1
        if self.countdown <= 0:
            self.restore()
            return False
        self.apply_btn.set_label(f"Keep ({self.countdown})")
        return True

    def keep(self):
        self.before = None
        displays.save(self.mons)
        self.ask.hide()
        self.apply_btn.set_label("Apply")
        self.set_dirty(False)

    def restore(self):
        """Back to what Hyprland had before Apply (or just reload, if nothing was applied)."""
        for m in self.mons:
            if self.before and m.desc in self.before:
                m.x, m.y, m.scale, m.rr = self.before[m.desc]
        if self.before:
            displays.apply(self.mons)
        self.before = None
        self.mons = displays.read_monitors()
        self.build_rows()
        self.ask.hide()
        self.apply_btn.set_label("Apply")
        self.set_dirty(False)
        self.canvas.queue_draw()

    def unconfirmed(self):
        """True while Apply waits for Keep — the owner should restore() on close."""
        return self.before is not None

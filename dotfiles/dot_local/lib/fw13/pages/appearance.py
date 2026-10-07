"""Appearance: wallpaper, window gaps and border size (rounding stays 0 — house style).

HyprPage is shared with Input: both write ~/.config/hypr/settings.lua through fw13.hyprsettings.
"""
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from .. import hyprsettings as hs  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .common import Page, label  # noqa: E402


def background(work, done):
    """Run work() in a thread, then done(result) on the GTK main loop.

    The app is held until done() ran, and the thread is not a daemon: closing the window never cuts a save short.
    An exception in work() reaches done() as an error string.
    """
    app = Gio.Application.get_default()
    if app:
        app.hold()

    def finish(result):
        try:
            done(result)
        finally:
            if app:
                app.release()
        return False

    def run():
        try:
            result = work()
        except Exception as e:  # noqa: BLE001 — shown on the page instead of a silently dead thread
            result = f"Error: {e}"
        GLib.idle_add(finish, result)
    threading.Thread(target=run).start()


class HyprPage(Page):
    """A Page whose controls write settings.lua: debounced, checked by Hyprland, errors shown on top."""

    def __init__(self, title):
        super().__init__(title)
        self.pending, self.timer = {}, None
        self.closed = False  # window gone: late results must not touch the widgets
        self.status = self.add_widget(label("", "bad", wrap=True))
        self.status.set_no_show_all(True)

    def clear(self, keep=2):  # keep the title and the status line
        super().clear(keep)

    def show_status(self, err, css="bad"):
        if self.closed:
            return False
        ctx = self.status.get_style_context()
        for c in ("bad", "dim"):
            ctx.remove_class(c)
        ctx.add_class(css)
        self.status.set_text(err or "")
        self.status.set_visible(bool(err))
        return False

    def change(self, key, value, delay=300):
        self.pending[key] = value
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(delay, self.flush)

    def flush(self):
        self.timer = None
        changes, self.pending = self.pending, {}
        if changes:
            background(lambda: hs.write(changes), self.written)
        return False

    def written(self, err):
        self.show_status(err)
        if err and not self.closed:  # the controls show a value Hyprland refused: go back to what is saved
            self.refresh()
        return False

    def closing(self):
        """Save what is still waiting on the debounce, in the background (background() keeps the app alive)."""
        self.closed = True
        if self.timer:
            GLib.source_remove(self.timer)
            self.flush()

    def switch(self, text, key, hint=None):
        sw = Gtk.Switch()
        sw.set_active(bool(hs.get(key)))
        sw.connect("notify::active", lambda s, _p: self.change(key, s.get_active(), delay=0))
        return self.row(text, sw, hint=hint)

    def slider(self, text, key, lo, hi, step, hint=None, fmt="{:.0f}", width=220):
        box = Gtk.Box(spacing=12)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        scale.set_draw_value(False)
        scale.set_size_request(width, -1)
        scale.set_value(hs.get(key))
        value = label(fmt.format(scale.get_value()), width_chars=5, xalign=1)
        is_int = hs.KEYS[key] is int

        def moved(s):
            v = round(s.get_value() / step) * step
            v = int(round(v)) if is_int else round(v, 3)
            value.set_text(fmt.format(v))
            self.change(key, v)
        scale.connect("value-changed", moved)
        box.pack_start(scale, False, False, 0)
        box.pack_start(value, False, False, 0)
        return self.row(text, box, hint=hint)


class AppearancePage(HyprPage):
    def __init__(self):
        super().__init__("Appearance")
        self.confirm = False  # "Reset to defaults" clicked once: show Cancel / Reset
        self.refresh()

    def refresh(self):
        self.clear()
        self.heading("Wallpaper")
        path = hs.wallpaper()
        if path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 320, 180, True)
                img = Gtk.Image.new_from_pixbuf(pb)
                img.set_halign(Gtk.Align.START)
                self.add_widget(img)
            except GLib.Error:
                path = None
        self.row("~/.config/hypr/wallpaper.jpg" if path else "No wallpaper set",
                 button("Choose…", self.choose),
                 hint="Desktop (hyprpaper) and lock screen (hyprlock)")
        self.heading("Windows")
        self.slider("Gaps inside", "general.gaps_in", 0, 30, 1, hint="between windows")
        self.slider("Gaps outside", "general.gaps_out", 0, 30, 1, hint="between windows and the screen edge")
        self.slider("Border size", "general.border_size", 0, 6, 1)
        if self.confirm:
            box = Gtk.Box(spacing=8)
            box.pack_start(button("Cancel", lambda: self.ask_reset(False)), False, False, 0)
            box.pack_start(button("Reset", self.reset, "danger"), False, False, 0)
            self.row("Reset every Appearance and Input setting?", box,
                     hint="Touchpad, keyboard and layouts too; Hyprland reloads")
        else:
            reset = button("Reset to defaults", lambda: self.ask_reset(True), "danger")
            reset.set_halign(Gtk.Align.START)
            self.row("Back to the shipped look", reset,
                     hint="Clears every Appearance and Input change (touchpad, keyboard too)")
        self.show_all()

    def choose(self):
        dlg = Gtk.FileChooserDialog(title="Choose a wallpaper", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Set wallpaper", Gtk.ResponseType.ACCEPT)
        f = Gtk.FileFilter()
        f.set_name("Images")
        f.add_pixbuf_formats()
        dlg.add_filter(f)
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures and os.path.isdir(pictures):
            dlg.set_current_folder(pictures)
        src = dlg.get_filename() if dlg.run() == Gtk.ResponseType.ACCEPT else None
        dlg.destroy()
        if src:
            self.show_status("Setting wallpaper…", "dim")
            background(lambda: hs.set_wallpaper(src), self.wallpaper_set)

    def wallpaper_set(self, err):
        self.show_status(err)
        if not self.closed:
            self.refresh()
        return False

    def ask_reset(self, on):
        self.confirm = on
        self.refresh()

    def reset(self):
        self.confirm = False
        self.refresh()  # drop the Cancel / Reset buttons now: no second click while it runs
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self.pending = {}
        background(hs.reset, self.written_reset)

    def written_reset(self, err):
        self.show_status(err)
        if not self.closed:
            self.refresh()
        return False


def build():
    return AppearancePage()

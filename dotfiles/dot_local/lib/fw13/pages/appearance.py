"""Appearance: theme colours (wallpaper palette via matugen, or Tokyo Night), wallpaper gallery and effects,
window gaps and border size (rounding stays 0 — house style).

HyprPage is shared with Input: both write ~/.config/hypr/settings.lua through fw13.hyprsettings.
The thumbnail helpers (thumb_button, load_thumbs, install_thumb_css) are shared with fw-wallpaper.
"""
import os
import string
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import hyprsettings as hs  # noqa: E402
from .. import theme  # noqa: E402
from .. import wallpaper as wp  # noqa: E402
from ..ui_theme import button, current, rgb, sync, watch  # noqa: E402
from .common import Page, label, launch  # noqa: E402


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


THUMB_W = 160
MODES = (("dark", "Dark"), ("light", "Light"))
STYLES = (("scheme-tonal-spot", "Tonal spot (default)"), ("scheme-content", "Content"),
          ("scheme-expressive", "Expressive"), ("scheme-vibrant", "Vibrant"), ("scheme-neutral", "Neutral"),
          ("scheme-monochrome", "Monochrome"), ("scheme-fidelity", "Fidelity"), ("scheme-rainbow", "Rainbow"),
          ("scheme-fruit-salad", "Fruit salad"))
SWATCHES = (("bg", "Background"), ("surface", "Surface"), ("accent", "Accent"), ("accent2", "Second accent"),
            ("ok", "Good"), ("warn", "Warning"), ("bad", "Error"), ("fg", "Text"))


def swatches():
    """A row of small squares showing the palette in use; redraws itself when the theme changes."""
    box = Gtk.Box(spacing=6)
    for role, name in SWATCHES:
        area = Gtk.DrawingArea()
        area.set_size_request(26, 26)
        area.set_tooltip_text(f"{name}  {current()[role]}")

        def draw(w, cr, role=role):
            a = w.get_allocation()
            cr.set_source_rgb(*rgb("muted"))  # outline, so bg stays visible on the page background
            cr.rectangle(0, 0, a.width, a.height)
            cr.fill()
            cr.set_source_rgb(*rgb(role))
            cr.rectangle(1, 1, a.width - 2, a.height - 2)
            cr.fill()

        def recolour(w=area, role=role, name=name):
            w.set_tooltip_text(f"{name}  {current()[role]}")
            w.queue_draw()
        area.connect("draw", draw)
        watch(area, recolour)
        box.pack_start(area, False, False, 0)
    return box


THUMB_CSS = string.Template("""
button.thumb { padding: 0; border: 3px solid transparent; background: $surface; }
button.thumb:hover, button.thumb:focus { border-color: $fg_dim; }
button.thumb.current, button.thumb.current:hover, button.thumb.current:focus { border-color: $accent; }
""")
_thumb_provider = None


def install_thumb_css(widget):
    """Style .thumb buttons (current one: accent border) and follow theme changes while `widget` lives."""
    global _thumb_provider

    def load():
        _thumb_provider.load_from_data(THUMB_CSS.substitute({k: v[:7] for k, v in current().items()}).encode())
    if _thumb_provider is None:
        _thumb_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), _thumb_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    load()
    watch(widget, load)


def thumb_button(path, w, is_current, on_activate, on_menu=None):
    """A flat button showing `path`'s thumbnail (filled in later by load_thumbs; .image is its Gtk.Image).
    on_activate(path) on click/Enter; on_menu(path, event) on a right click."""
    b = Gtk.Button()
    b.get_style_context().add_class("thumb")
    if is_current:
        b.get_style_context().add_class("current")
    img = Gtk.Image()
    img.set_size_request(w, w * 9 // 16)
    b.add(img)
    b.image = img
    b.set_tooltip_text(os.path.basename(path) + ("  (current)" if is_current else ""))
    b.connect("clicked", lambda _b: on_activate(path))
    if on_menu:
        b.connect("button-press-event",
                  lambda _b, e: e.button == Gdk.BUTTON_SECONDARY and (on_menu(path, e) or True))
    return b


def _show_thumb(img, png):
    if png and img.get_parent() is not None:  # still on screen (a page refresh drops old buttons)
        img.set_from_file(png)
    return False


def load_thumbs(items, w):
    """Make/load thumbnails for [(path, Gtk.Image)] in a thread and show each as it is ready."""
    def run():
        for path, img in items:
            try:
                png = wp.thumbnail(path, w)
            except Exception:  # noqa: BLE001 — one bad picture must not stop the rest
                png = None
            GLib.idle_add(_show_thumb, img, png)
    threading.Thread(target=run, daemon=True).start()


def image_filter():
    f = Gtk.FileFilter()
    f.set_name("Pictures")
    for e in wp.readable_exts():
        f.add_pattern("*" + e)
        f.add_pattern("*" + e.upper())
    return f


def add_and_set(files):
    """Background work for "+ Add…": copy into the library, then make the first one the wallpaper."""
    added = wp.add(files)
    if not added:
        return "None of those pictures could be added"
    return wp.set(added[0])


def combo(options, active, cb):
    c = Gtk.ComboBoxText()
    for key, text in options:
        c.append(key, text)
    c.set_active_id(active)
    c.connect("changed", lambda w: cb(w.get_active_id()))
    return c


class AppearancePage(HyprPage):
    def __init__(self):
        super().__init__("Appearance")
        self.confirm = False  # "Reset to defaults" clicked once: show Cancel / Reset
        self.theming = False  # a theme change is running (matugen takes ~1 s): controls are insensitive
        self.queued = None    # (source, mode, type) asked for while one was running: run it next
        self.walling = False  # a wallpaper change (set / add / remove / effect) is running
        self.removing = None  # picture right-clicked → "Remove from library": show Cancel / Remove
        install_thumb_css(self)
        self.refresh()

    def theme_section(self):
        self.heading("Theme")
        s = theme.state()
        have_wall = hs.wallpaper() is not None
        follow = s["source"] == "wallpaper"
        box = Gtk.Box(spacing=16)
        wall = Gtk.RadioButton.new_with_label(None, "From wallpaper")
        tokyo = Gtk.RadioButton.new_with_label_from_widget(wall, "Tokyo Night")
        (wall if follow else tokyo).set_active(True)
        wall.set_sensitive(have_wall or follow)  # if it already follows, keep it selectable
        wall.connect("toggled", lambda b: b.get_active() and self.set_theme("wallpaper"))
        tokyo.connect("toggled", lambda b: b.get_active() and self.set_theme("tokyo-night"))
        box.pack_start(wall, False, False, 0)
        box.pack_start(tokyo, False, False, 0)
        hint = ("Colours for the bar, menus, notifications, terminal, lock screen and borders" if have_wall
                else "Set a wallpaper below to take the colours from it")
        controls = [self.row("Colours", box, hint=hint)]
        if follow:
            mode = combo(MODES, s["mode"], lambda v: self.set_theme("wallpaper", mode=v))
            style = combo(STYLES, s["type"], lambda v: self.set_theme("wallpaper", scheme_type=v))
            controls.append(self.row("Mode", mode))
            controls.append(self.row("Style", style, hint="How matugen builds the palette from the image"))
        self.row("Palette", swatches(), hint="Hover a colour for its name")
        for w in controls:
            w.set_sensitive(not self.theming)

    def set_theme(self, source, mode=None, scheme_type=None):
        if self.theming:  # one at a time: two set_source() calls would race on the store and files
            self.queued = (source, mode, scheme_type)
            return
        self.theming = True
        self.show_status("Reading colours from the wallpaper…" if source == "wallpaper" else "Applying theme…",
                         "dim")
        # via fw13.wallpaper: colours from the original picture, not the desktop image with its effect
        background(lambda: wp.set_theme(source, mode=mode, scheme_type=scheme_type), self.theme_set)
        GLib.idle_add(self.refresh_if_open)  # grey out the controls (not from inside their own signal)

    def theme_set(self, err):
        self.theming = False
        sync()  # don't wait for the file monitor
        if self.queued:
            nxt, self.queued = self.queued, None
            if nxt == ("reset",):
                self.reset()
            else:
                self.set_theme(*nxt)
            return False
        self.show_status(err)
        self.refresh_if_open()
        return False

    def refresh_if_open(self):
        if not self.closed:
            self.refresh()
        return False

    def refresh(self):
        self.clear()
        self.theme_section()
        self.wallpaper_section()
        self.heading("Windows")
        self.slider("Gaps inside", "general.gaps_in", 0, 30, 1, hint="between windows")
        self.slider("Gaps outside", "general.gaps_out", 0, 30, 1, hint="between windows and the screen edge")
        self.slider("Border size", "general.border_size", 0, 6, 1)
        if self.confirm:
            box = Gtk.Box(spacing=8)
            box.pack_start(button("Cancel", lambda: self.ask_reset(False)), False, False, 0)
            box.pack_start(button("Reset", self.reset, "danger"), False, False, 0)
            self.row("Reset every Appearance and Input setting?", box,
                     hint="Theme back to Tokyo Night; touchpad, keyboard and layouts too; Hyprland reloads")
        else:
            reset = button("Reset to defaults", lambda: self.ask_reset(True), "danger")
            reset.set_halign(Gtk.Align.START)
            self.row("Back to the shipped look", reset,
                     hint="Tokyo Night and every Appearance and Input change (touchpad, keyboard too); "
                          "the wallpaper is kept")
        self.show_all()

    def wallpaper_section(self):
        self.heading("Wallpaper")
        lib, cur = wp.library(), wp.current()
        cur = os.path.realpath(cur) if cur else None
        if lib:
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_min_children_per_line(1)  # one per line at half a screen
            flow.set_max_children_per_line(8)
            flow.set_column_spacing(8)
            flow.set_row_spacing(8)
            items = []
            for path in lib:
                b = thumb_button(path, THUMB_W, os.path.realpath(path) == cur, self.set_wallpaper, self.thumb_menu)
                flow.add(b)
                items.append((path, b.image))
            flow.set_sensitive(not self.walling)
            self.add_widget(flow)
            load_thumbs(items, THUMB_W)
        else:
            self.add_widget(label("No pictures yet: add some with + Add…, or put them in the folder", "dim"))
        if self.removing:
            box = Gtk.Box(spacing=8)
            box.pack_start(button("Cancel", lambda: self.ask_remove(None)), False, False, 0)
            box.pack_start(button("Remove", self.remove_picture, "danger"), False, False, 0)
            box.set_sensitive(not self.walling)  # a removal now would be dropped by wall_work
            self.row(f"Remove {os.path.basename(self.removing)} from the library?", box,
                     hint="Deletes the copy in the wallpaper folder")
        box = Gtk.Box(spacing=8)
        add = button("+ Add…", self.add_pictures)
        add.set_sensitive(not self.walling)
        box.pack_start(add, False, False, 0)
        box.pack_start(button("Open folder", self.open_folder), False, False, 0)
        self.row(wp.library_dir().replace(os.path.expanduser("~"), "~", 1), box,
                 hint="Click a picture to use it (SUPER+W too); right-click to remove it")
        st = wp.state()
        box = Gtk.Grid(column_spacing=8, row_spacing=6)  # two lines: fits Settings at half a screen
        box.attach(label("Desktop", "dim"), 0, 0, 1, 1)
        box.attach(combo(wp.EFFECTS, st["desktop_effect"], lambda v: self.set_effect(desktop=v)), 1, 0, 1, 1)
        box.attach(label("Lock screen", "dim"), 0, 1, 1, 1)
        box.attach(combo(wp.EFFECTS, st["lock_effect"], lambda v: self.set_effect(lock=v)), 1, 1, 1, 1)
        box.set_sensitive(not self.walling)
        self.row("Effects", box, hint="Applied to a copy; theme colours always come from the original")

    def wall_work(self, work, msg):
        if self.walling:
            return
        self.walling = True
        self.show_status(msg, "dim")
        background(work, self.wallpaper_done)
        GLib.idle_add(self.refresh_if_open)  # grey out the gallery (not from inside its own signal)

    def wallpaper_done(self, err):
        self.walling = False
        sync()  # palette swatches and the window follow new colours now
        self.show_status(err)
        self.refresh_if_open()
        return False

    def set_wallpaper(self, path):
        following = theme.state()["source"] == "wallpaper"
        self.wall_work(lambda: wp.set(path),
                       "Setting wallpaper and reading its colours…" if following else "Setting wallpaper…")

    def set_effect(self, desktop=None, lock=None):
        self.wall_work(lambda: wp.set_effects(desktop=desktop, lock=lock), "Rendering the wallpaper…")

    def thumb_menu(self, path, event):
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="Remove from library…")
        item.connect("activate", lambda _i: self.ask_remove(path))
        menu.append(item)
        menu.show_all()
        menu.attach_to_widget(self, None)
        menu.popup_at_pointer(event)

    def ask_remove(self, path):
        self.removing = path
        self.refresh()

    def remove_picture(self):
        if self.walling:  # keep the question open until the running task is done
            self.show_status("Busy: try again in a moment", "dim")
            return
        path, self.removing = self.removing, None
        if path:
            self.wall_work(lambda: wp.remove(path), "Removing…")
        else:
            self.refresh()

    def add_pictures(self):
        dlg = Gtk.FileChooserDialog(title="Add wallpapers", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.ACCEPT)
        dlg.set_select_multiple(True)
        dlg.add_filter(image_filter())
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures and os.path.isdir(pictures):
            dlg.set_current_folder(pictures)
        files = dlg.get_filenames() if dlg.run() == Gtk.ResponseType.ACCEPT else []
        dlg.destroy()
        if files:
            self.wall_work(lambda: add_and_set(files), "Adding and setting the wallpaper…")

    def open_folder(self):
        d = wp.library_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            self.show_status(f"Could not create {d}: {e}")
            return
        launch("xdg-open", d)

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
        self.queued = None  # the reset wins over a theme change asked for before it
        if self.theming:  # a theme change is running: reset once it is done (set_source must not race)
            self.queued = ("reset",)
            return
        self.theming = True

        def work():
            errs = [e for e in (hs.reset(), wp.set_theme("tokyo-night", mode="dark",
                                                         scheme_type=theme.DEFAULT_TYPE)) if e]
            return "; ".join(errs) or None

        background(work, self.written_reset)

    def written_reset(self, err):
        self.theming = False
        sync()
        nxt, self.queued = self.queued, None
        if nxt and not err:  # a theme change asked for while the reset ran
            self.set_theme(*nxt)
            return False
        self.show_status(err)
        if not self.closed:
            self.refresh()
        return False


def build():
    return AppearancePage()

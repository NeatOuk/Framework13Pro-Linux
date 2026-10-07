"""System: date & time, time zone, device name, firmware updates (fwupd), About this laptop."""
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import system  # noqa: E402
from .common import Page, label, launch  # noqa: E402

BUSY_NOTE = {"tz": "Setting the time zone…", "ntp": "Changing time sync…", "host": "Saving…"}


def bg(fn, done, *args, fail=lambda e: (False, str(e))):
    """Run fn(*args) in a worker thread, then done(result) on the GTK main loop; done(fail(exc)) if it raises."""
    def work():
        try:
            res = fn(*args)
        except Exception as e:  # noqa: BLE001 — the UI must always get an answer
            res = fail(e)
        GLib.idle_add(done, res)
    threading.Thread(target=work, daemon=True).start()


def _load_state():
    return system.time_state(), system.hostname()


class SystemPage(Page):
    def __init__(self):
        super().__init__("System")
        self.tick = None
        self.tz = None
        self.st = None        # timedatectl state; None until the first load
        self.hostname = None
        self.facts = None     # About rows; computed once, they don't change during a session
        self.zones = None     # None = still loading; [] = list unavailable
        self.tz_store = Gtk.ListStore(str)
        self.busy = set()     # pending "tz" / "ntp" / "host" actions (e.g. waiting on polkit)
        self.notes = {}       # last result message per action
        self.fw = None        # (updates, message) from the last check; None = checking
        self.clock = None
        self.connect("map", lambda _w: self.start_clock())
        self.connect("unmap", lambda _w: self.stop_clock())
        bg(system.timezones, self.got_zones, fail=lambda _e: [])
        bg(system.about, self.got_about, fail=lambda _e: [])
        self.render()
        self.check_firmware()
        self.reload()

    def refresh(self):
        """Page shown again: drop old result notes and re-read state in the background."""
        self.notes.clear()
        self.reload()

    def reload(self):
        bg(_load_state, self.got_state, fail=lambda _e: ({}, os.uname().nodename))

    def got_state(self, res):
        self.st, self.hostname = res
        self.tz = self.st.get("Timezone", "UTC")
        self.render()

    def got_about(self, facts):
        self.facts = facts
        self.render()

    def render(self):
        """Rebuild the page from cached state; never runs a subprocess."""
        self.clear()
        self.heading("Date & time")
        self.clock = label("", "title")
        self.row_widget(self.clock)
        self.update_clock()
        if self.st is None:
            self.add_widget(label("Loading…", "dim"))
        else:
            self.render_time()

        self.heading("Device name")
        if self.hostname is None:
            self.add_widget(label("Loading…", "dim"))
        else:
            self.render_host()

        self.heading("Firmware updates")
        self.fw_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_widget(self.fw_box)
        self.render_firmware()

        self.heading("About")
        if self.facts is None:
            self.add_widget(label("Loading…", "dim"))
        else:
            self.render_about()
        self.show_all()

    def render_time(self):
        st = self.st
        busy_tz = "tz" in self.busy
        self.tz_entry = Gtk.Entry(text=self.tz, width_chars=26)
        self.tz_entry.set_placeholder_text("Search, e.g. Phnom")
        self.tz_entry.connect("activate", lambda _e: self.set_timezone())
        self.tz_entry.set_completion(self.completion())
        self.tz_set = Gtk.Button(label="Set")
        self.tz_set.connect("clicked", lambda _b: self.set_timezone())
        self.tz_entry.set_sensitive(not busy_tz)
        self.tz_set.set_sensitive(not busy_tz and self.zones is not None)
        self.tz_note = label(BUSY_NOTE["tz"] if busy_tz else self.notes.get("tz", ""), "dim")
        self.row("Time zone", self.hbox(self.tz_entry, self.tz_set))
        self.add_widget(self.tz_note)

        busy_ntp = "ntp" in self.busy
        self.ntp = Gtk.Switch()
        self.ntp.set_active(st.get("NTP") == "yes")
        self.ntp.set_sensitive(not busy_ntp and st.get("CanNTP", "yes") == "yes")
        self.ntp.connect("state-set", self.on_ntp)
        synced = st.get("NTPSynchronized") == "yes"
        self.row("Set time automatically", self.ntp,
                 hint="Synchronized with network time" if synced and self.ntp.get_active() else
                 "Uses network time servers (NTP)")
        self.ntp_note = label(BUSY_NOTE["ntp"] if busy_ntp else self.notes.get("ntp", ""), "dim")
        self.add_widget(self.ntp_note)

    def render_host(self):
        busy = "host" in self.busy
        self.host = Gtk.Entry(text=self.hostname, width_chars=26, max_length=63)
        self.host_save = Gtk.Button(label="Save")
        self.host_save.connect("clicked", lambda _b: self.set_hostname())
        self.host.connect("changed", lambda e: self.host_save.set_sensitive(system.valid_hostname(e.get_text())))
        self.host.connect("activate", lambda _e: self.set_hostname())
        self.host.set_sensitive(not busy)
        self.host_save.set_sensitive(not busy)
        self.row("Hostname", self.hbox(self.host, self.host_save),
                 hint="Letters, digits and hyphens · shown on the network")
        self.host_note = label(BUSY_NOTE["host"] if busy else self.notes.get("host", ""), "dim")
        self.add_widget(self.host_note)

    def render_about(self):
        for k, v in self.facts:
            self.row(k, label(v, "dim", selectable=True, wrap=True, max_width_chars=48, xalign=1))
        copy = Gtk.Button(label="  Copy")
        copy.connect("clicked", lambda _b: self.copy_about())
        buttons = self.hbox(copy)
        if os.path.exists(system.REPORT):
            rep = Gtk.Button(label="  Install report")
            rep.connect("clicked", lambda _b: launch("xdg-open", system.REPORT))
            buttons.pack_start(rep, False, False, 0)
        buttons.set_halign(Gtk.Align.START)
        self.add_widget(buttons)

    # --- helpers ---

    @staticmethod
    def hbox(*widgets):
        b = Gtk.Box(spacing=8)
        for w in widgets:
            b.pack_start(w, False, False, 0)
        return b

    def row_widget(self, w):
        r = Gtk.Box()
        r.get_style_context().add_class("item")
        r.pack_start(w, False, False, 0)
        return self.add_widget(r)

    def start(self, what, fn, done, *args):
        """Mark an action pending, show it, and run it in the background."""
        self.busy.add(what)
        self.notes.pop(what, None)
        self.render()
        bg(fn, done, *args)

    def finish(self, what, res, ok_note=""):
        ok, msg = res
        self.busy.discard(what)
        self.notes[what] = ok_note if ok else msg
        self.render()
        self.reload()  # re-read what systemd really applied

    # --- clock (ticks only while the page is on screen) ---

    def start_clock(self):
        if not self.tick:
            self.update_clock()
            self.tick = GLib.timeout_add_seconds(1, self.update_clock)

    def stop_clock(self):
        if self.tick:
            GLib.source_remove(self.tick)
            self.tick = None

    def update_clock(self):
        if self.clock is None:
            return True
        try:
            zone = (GLib.TimeZone.new_identifier(self.tz) if self.tz else None) or GLib.TimeZone.new_local()
        except (TypeError, GLib.Error):
            zone = GLib.TimeZone.new_local()
        now = GLib.DateTime.new_now(zone)
        self.clock.set_text(f"{now.format('%A')} {now.get_day_of_month()} {now.format('%B %Y   %H:%M:%S')}")
        return True

    # --- time zone ---

    def got_zones(self, zones):
        self.zones = zones
        self.refresh_completion()
        if getattr(self, "tz_set", None) is not None and "tz" not in self.busy:
            self.tz_set.set_sensitive(True)

    def completion(self):
        comp = Gtk.EntryCompletion(model=self.tz_store, minimum_key_length=2)
        comp.set_text_column(0)
        comp.set_match_func(lambda _c, key, it: key.lower().replace(" ", "_") in self.tz_store[it][0].lower())
        comp.connect("match-selected", self.on_zone_picked)
        self.refresh_completion()
        return comp

    def on_zone_picked(self, _comp, model, it):
        self.tz_entry.set_text(model[it][0])
        self.set_timezone()
        return True

    def refresh_completion(self):
        if self.zones and not len(self.tz_store):
            for z in self.zones:
                self.tz_store.append([z])

    def set_timezone(self):
        if "tz" in self.busy or self.zones is None:
            return
        tz = self.tz_entry.get_text().strip()
        if self.zones:  # map "asia/phnom penh" to "Asia/Phnom_Penh"
            canon = {z.lower(): z for z in self.zones}
            tz = canon.get(tz.lower().replace(" ", "_"), tz)
            if tz not in self.zones:
                self.notes["tz"] = f"Unknown time zone “{tz}” — pick one from the list"
                self.tz_note.set_text(self.notes["tz"])
                return
        if tz == self.tz:
            return
        self.start("tz", system.set_timezone, self.done_timezone, tz)  # [] = list unavailable: backend checks the shape

    def done_timezone(self, res):
        self.finish("tz", res)

    # --- NTP ---

    def on_ntp(self, _sw, on):
        if "ntp" not in self.busy:
            self.start("ntp", system.set_ntp, self.done_ntp, on)
        return True  # the switch is rebuilt from what timedated reports

    def done_ntp(self, res):
        self.finish("ntp", res)

    # --- hostname ---

    def set_hostname(self):
        if "host" in self.busy:
            return
        name = self.host.get_text().strip()
        if name == self.hostname:
            return
        if not system.valid_hostname(name):
            self.notes["host"] = "Use letters, digits and hyphens (1-63, no hyphen at either end)"
            self.host_note.set_text(self.notes["host"])
            return
        self.start("host", system.set_hostname, self.done_hostname, name)

    def done_hostname(self, res):
        self.finish("host", res, "Saved")

    # --- firmware ---

    def check_firmware(self):
        self.fw = None
        self.render_firmware()
        bg(system.firmware_updates, self.got_firmware, fail=lambda e: ([], str(e)))

    def got_firmware(self, res):
        self.fw = res
        self.render_firmware()

    def render_firmware(self):
        for c in self.fw_box.get_children():
            self.fw_box.remove(c)
        check = Gtk.Button(label="  Check now")
        check.connect("clicked", lambda _b: self.check_firmware())
        if self.fw is None:
            check.set_sensitive(False)
            self.fw_box.pack_start(label("Checking for updates…", "dim"), False, False, 0)
            buttons = self.hbox(check)
        else:
            updates, msg = self.fw
            for u in updates:
                r = Gtk.Box(spacing=12)
                r.get_style_context().add_class("item")
                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                left.pack_start(label(u["device"]), False, False, 0)
                left.pack_start(label(f"{u['current']}  →  {u['new']}", "dim"), False, False, 0)
                r.pack_start(left, True, True, 0)
                if u["urgency"] in ("high", "critical"):
                    r.pack_end(label(u["urgency"], "warn"), False, False, 0)
                self.fw_box.pack_start(r, False, False, 0)
            if not updates:
                self.fw_box.pack_start(label(msg, "ok" if msg == "Everything is up to date" else "dim",
                                             wrap=True), False, False, 0)
            buttons = self.hbox(check)
            if updates:
                upd = Gtk.Button(label="Update…")
                upd.get_style_context().add_class("primary")
                upd.connect("clicked", lambda _b: launch("kitty", "--hold", "-e", "fwupdmgr", "update"))
                buttons.pack_start(upd, False, False, 0)
        self.fw_box.pack_start(buttons, False, False, 0)
        self.fw_box.show_all()

    # --- about ---

    def copy_about(self):
        text = "\n".join(f"{k}: {v}" for k, v in self.facts or [])
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text(text, -1)
        cb.store()

    def closing(self):
        self.stop_clock()


def build():
    return SystemPage()

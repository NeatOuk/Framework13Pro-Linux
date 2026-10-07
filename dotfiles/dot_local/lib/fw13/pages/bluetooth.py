"""Bluetooth: adapter power + name, paired devices (connect / disconnect / forget), scan and pair new ones."""
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import bt  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .common import Page, label, launch, wrap  # noqa: E402

SCAN_SECONDS = 20
WATCHED = {"Powered", "Alias", "Name", "Connected", "Paired", "Trusted", "Percentage"}


class BluetoothPage(Page):
    def __init__(self):
        super().__init__("Bluetooth")
        self.adapter = None
        self.busy = {}          # device path → "Connecting…" etc. while a worker runs
        self.confirm = None     # device path awaiting "Forget?" confirmation
        self.msg = None         # (text, css class) from the last action
        self.found = []         # paths seen (unpaired) during the current/last scan, in order
        self.scan_stop = None   # threading.Event while scanning
        self.scan_left = 0
        self.alias_entry = None
        self.scan_btn = None
        self.new_box = None     # "Add a device" list, updated in place during a scan
        self.new_rows = {}      # path → (row, signature) in new_box
        self.new_empty = None   # placeholder label in new_box
        self.top_sig = None     # everything above the new-device list, to skip needless full rebuilds
        self.pending = None
        self.tearing = False    # set while the Name entry is being destroyed: its focus-out must not rename
        self.closed = False
        self.unwatch = bt.watch(self.on_signal)
        self.refresh()

    # ---- state → widgets

    def editing(self):
        """True while the Name field holds an uncommitted edit; rebuilding would throw it away."""
        e = self.alias_entry
        return bool(e and self.adapter and e.is_focus() and e.get_text().strip() != self.adapter["alias"])

    def rebuild(self):
        """Every non-initial rebuild goes through here: deferred while the user is typing a name."""
        if self.closed:
            pass  # a worker finished after the window closed
        elif self.editing():
            self.schedule()
        else:
            self.refresh()
        return False

    def refresh(self):
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = None
        self.adapter, devices = bt.state()
        a = self.adapter
        top = None if not a else (
            tuple(sorted(a.items())), self.msg, self.confirm, bool(self.scan_stop),
            tuple(sorted(self.busy.items())),
            tuple((d["path"], d["alias"], d["icon"], d["connected"], d["battery"]) for d in devices if d["paired"]))
        if top is not None and top == self.top_sig and self.new_box:
            self.update_new(devices)  # only the scan results changed: keep the rows (and buttons) that stay
            return
        self.top_sig = top

        refocus = bool(self.alias_entry and self.alias_entry.is_focus())
        self.tearing = True
        self.clear()
        self.tearing = False
        self.alias_entry = self.scan_btn = self.new_box = self.new_empty = None
        self.new_rows = {}
        if not a:
            self.add_widget(label("No Bluetooth adapter", "dim"))
            self.show_all()
            return
        sw = Gtk.Switch()
        sw.set_active(a["powered"])
        sw.connect("state-set", self.on_power)
        self.row("Bluetooth", sw, hint=a["address"])
        rest = len(self.box.get_children())

        self.alias_entry = Gtk.Entry(text=a["alias"])
        self.alias_entry.set_width_chars(20)
        self.alias_entry.connect("activate", self.on_alias)
        self.alias_entry.connect("focus-out-event", self.on_alias_focus_out)
        self.row("Name", self.alias_entry, hint="how this laptop appears to other devices")
        if self.msg:
            self.add_widget(label(self.msg[0], self.msg[1], wrap=True))

        self.heading("My devices")
        paired = [d for d in devices if d["paired"]]
        if not paired:
            self.add_widget(label("No paired devices", "dim"))
        for d in paired:
            self.add_widget(self.device_row(d))

        self.heading("Add a device")
        scan = self.scan_btn = Gtk.Button(label=f"Stop ({self.scan_left} s)" if self.scan_stop else "Scan")
        scan.set_halign(Gtk.Align.START)
        scan.connect("clicked", self.on_scan)
        self.add_widget(scan)
        self.new_box = self.add_widget(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8))
        self.update_new(devices)

        more = Gtk.Button(label="More… (Bluetooth Manager)")
        more.set_halign(Gtk.Align.START)
        more.set_margin_top(12)
        more.connect("clicked", lambda _b: launch("blueman-manager"))
        self.add_widget(more)
        if not a["powered"]:
            for child in self.box.get_children()[rest:]:
                child.set_sensitive(False)
        self.show_all()
        if refocus:
            self.alias_entry.grab_focus_without_selecting()

    def update_new(self, devices):
        """Sync the "Add a device" rows with the scan results, touching only rows that changed."""
        new = self.new_devices(devices)
        sigs = {d["path"]: (d["alias"], d["address"], d["icon"], self.busy.get(d["path"])) for d in new}
        for path, (row, sig) in list(self.new_rows.items()):
            if sigs.get(path) != sig:
                self.new_box.remove(row)
                del self.new_rows[path]
        for i, d in enumerate(new):
            if d["path"] not in self.new_rows:
                row = self.device_row(d)
                self.new_box.pack_start(row, False, False, 0)
                row.show_all()
                self.new_rows[d["path"]] = (row, sigs[d["path"]])
            self.new_box.reorder_child(self.new_rows[d["path"]][0], i)

        text = None if new else ("Searching… put the device in pairing mode" if self.scan_stop
                                 else "Scan to find devices that are in pairing mode")
        if self.new_empty and (text is None or self.new_empty.get_text() != text):
            self.new_box.remove(self.new_empty)
            self.new_empty = None
        if text and not self.new_empty:
            self.new_empty = wrap(label(text, "dim"))
            self.new_box.pack_start(self.new_empty, False, False, 0)
            self.new_empty.show()

    def new_devices(self, devices):
        """Unpaired devices seen by our scan; nameless (MAC-only) ones only when nothing has a name."""
        by_path = {d["path"]: d for d in devices if not d["paired"]}
        if self.scan_stop:
            for d in by_path.values():
                if d["rssi"] is not None and d["path"] not in self.found:
                    self.found.append(d["path"])
        seen = [by_path[p] for p in self.found if p in by_path]
        named = [d for d in seen if d["name"]]
        return named or seen

    def device_row(self, d):
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        r.pack_start(label(bt.icon(d["icon"]), width_chars=2, xalign=0.5), False, False, 0)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(wrap(label(d["alias"])), False, False, 0)
        if d["path"] in self.busy:
            left.pack_start(label(self.busy[d["path"]], "warn"), False, False, 0)
        elif d["paired"]:
            status = "Connected" if d["connected"] else "Not connected"
            if d["battery"] is not None:
                status += f" · battery {d['battery']}%"
            left.pack_start(label(status, "ok" if d["connected"] else "dim"), False, False, 0)
        elif d["alias"] != d["address"]:  # nameless devices already show the address as their title
            left.pack_start(label(d["address"], "dim"), False, False, 0)
        r.pack_start(left, True, True, 0)

        buttons = Gtk.Box(spacing=6)
        buttons.set_valign(Gtk.Align.CENTER)
        path = d["path"]
        if path in self.busy:
            pass
        elif not d["paired"]:
            buttons.pack_start(button("Pair", lambda: self.run(path, "Pairing…", bt.pair, path),
                                      "primary"), False, False, 0)
        elif self.confirm == path:
            buttons.pack_start(label(f"Forget {d['alias']}?", "warn"), False, False, 0)
            buttons.pack_start(button("Cancel", lambda: self.set_confirm(None)), False, False, 0)
            buttons.pack_start(button("Forget", lambda: self.run(path, "Forgetting…", bt.forget,
                                                                 self.adapter["path"], path),
                                      "danger"), False, False, 0)
        else:
            if d["connected"]:
                buttons.pack_start(button("Disconnect", lambda: self.run(path, "Disconnecting…",
                                                                         bt.disconnect, path)), False, False, 0)
            else:
                buttons.pack_start(button("Connect", lambda: self.run(path, "Connecting…", bt.connect, path),
                                          "primary"), False, False, 0)
            buttons.pack_start(button("Forget", lambda: self.set_confirm(path), "danger"), False, False, 0)
        r.pack_end(buttons, False, False, 0)
        self.adapt(r, buttons)
        return r

    # ---- actions (BlueZ calls run in worker threads)

    def run(self, path, busy_text, fn, *args):
        self.busy[path] = busy_text
        self.confirm = None
        self.msg = None
        self.rebuild()

        def work():
            ok, err = fn(*args)
            GLib.idle_add(self.done, path, err)
        threading.Thread(target=work, daemon=True).start()

    def done(self, path, err):
        self.busy.pop(path, None)
        self.msg = (err, "bad") if err else None
        return self.rebuild()

    def set_confirm(self, path):
        self.confirm = path
        self.rebuild()

    def on_power(self, _sw, on):
        ad = self.adapter["path"]

        def work():
            ok, err = bt.set_powered(ad, on)
            GLib.idle_add(self.done, ad, None if ok else f"Couldn't turn Bluetooth {'on' if on else 'off'}: {err}")
        threading.Thread(target=work, daemon=True).start()
        return True  # keep the switch where it was; done() → refresh() shows the real state

    def on_alias_focus_out(self, entry, _ev):
        # rename when the user clicks elsewhere in the window, not when the window loses focus
        # (alt-tab, close) or the entry is torn down by a rebuild
        win = entry.get_toplevel()
        if not (self.tearing or self.closed) and isinstance(win, Gtk.Window) and win.is_active():
            self.on_alias(entry)
        return False

    def on_alias(self, entry):
        text = entry.get_text().strip()
        if not (self.adapter and text and text != self.adapter["alias"]):
            return
        ad = self.adapter["path"]
        self.adapter["alias"] = text  # optimistic; a failure rebuilds from BlueZ with the error shown

        def work():
            _ok, err = bt.set_alias(ad, text)
            GLib.idle_add(self.done, ad, err)
        threading.Thread(target=work, daemon=True).start()

    def on_scan(self, _b):
        if self.scan_stop:
            self.scan_stop.set()
            return
        ad = self.adapter["path"]
        stop = self.scan_stop = threading.Event()
        self.found = []
        self.scan_left = SCAN_SECONDS
        self.msg = None
        self.rebuild()

        def work():
            ok, err = bt.start_discovery(ad)
            if not ok:
                GLib.idle_add(self.scan_done, stop, f"Couldn't scan: {err}")
                return
            for left in range(SCAN_SECONDS - 1, -1, -1):
                if stop.wait(1):
                    break
                GLib.idle_add(self.tick, stop, left)
            bt.stop_discovery(ad)
            GLib.idle_add(self.scan_done, stop, None)
        threading.Thread(target=work, daemon=True).start()

    def tick(self, stop, left):
        if self.scan_stop is stop:
            self.scan_left = left
            if self.scan_btn:
                self.scan_btn.set_label(f"Stop ({left} s)")
        return False

    def scan_done(self, stop, err):
        if self.scan_stop is stop:
            self.scan_stop = None
            if err:
                self.msg = (err, "bad")
            self.rebuild()
        return False

    # ---- live updates from BlueZ signals, debounced

    def on_signal(self, path, member, params):
        if member == "PropertiesChanged":
            iface, changed, _inv = params.unpack()
            if iface not in (bt.ADAPTER, bt.DEVICE, bt.BATTERY):
                return
            # RSSI: a device BlueZ already knew about shows up in our scan
            fresh = self.scan_stop and "RSSI" in changed and path not in self.found
            if not fresh and not WATCHED & set(changed):
                return
        self.schedule()

    def schedule(self):
        if self.pending is None:
            self.pending = GLib.timeout_add(400, self.flush)

    def flush(self):
        if self.editing():
            return True  # don't rebuild under the user's typing; retry shortly
        self.pending = None
        self.refresh()
        return False

    def closing(self):
        self.closed = True  # window is going away: an unsaved Name edit is dropped, not committed
        if self.scan_stop:
            self.scan_stop.set()
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = None
        self.unwatch()


def build():
    return BluetoothPage()

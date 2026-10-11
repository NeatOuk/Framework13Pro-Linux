"""Network: Wi-Fi (switch, networks, connect/forget, hidden), Ethernet via nmcli, and every VPN (fw13.vpn:
NetworkManager's + strongSwan's): connect/disconnect, edit (nm-connection-editor / pages/vpn_edit.py), add."""
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import net, vpn  # noqa: E402
from ..ui_theme import button  # noqa: E402
from . import vpn_edit  # noqa: E402
from .common import Page, label, launch, wrap  # noqa: E402
from .system import bg  # noqa: E402

WIFI_ICON, LOCK_ICON, ETH_ICON, VPN_ICON = "", "", "", ""


def _buttons(*widgets):
    box = Gtk.Box(spacing=6)
    for w in widgets:
        box.pack_start(w, False, False, 0)
    return box


def _valid_psk(pw, security):
    if "WPA3" in security.split() and "WPA2" not in security.split():
        return len(pw) >= 1  # SAE takes any length
    return 8 <= len(pw) <= 63 or (len(pw) == 64 and all(c in "0123456789abcdefABCDEF" for c in pw))


class NetworkPage(Page):
    def __init__(self):
        super().__init__("Network")
        self.status = self.add_widget(label("", "dim", wrap=True))
        self.status.set_no_show_all(True)
        self.busy = False
        self.confirming = False  # a Forget confirm or the password dialog is open
        self.refresh()
        self.connect("map", self._first_map)

    def _first_map(self, _w):
        """The cached scan list goes stale; rescan quietly the first time the page is shown."""
        self.disconnect_by_func(self._first_map)
        if net.wifi_enabled():
            threading.Thread(target=self._quiet_scan, daemon=True).start()

    # --- background work -------------------------------------------------
    def set_status(self, text, cls="dim"):
        ctx = self.status.get_style_context()
        for c in ("dim", "bad", "ok"):
            ctx.remove_class(c)
        ctx.add_class(cls)
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    def run_bg(self, msg, fn, *args):
        """Run fn(*args) -> error|None in a thread; lock the page meanwhile, then refresh."""
        if self.busy:
            return
        self.busy = True
        self.set_status(msg)
        for child in self.box.get_children()[2:]:
            child.set_sensitive(False)

        def work():
            try:
                err = fn(*args)
            except Exception as e:  # noqa: BLE001  never leave the page locked
                err = str(e)
            GLib.idle_add(self._done, err)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, err):
        self.busy = False
        self.set_status(err or "", "bad" if err else "dim")
        self.refresh()
        return False

    def _quiet_scan(self):
        net.rescan()
        time.sleep(4)  # `rescan` returns before results arrive
        GLib.idle_add(self._quiet_refresh)

    def _quiet_refresh(self):
        if not (self.busy or self.confirming):  # an action refreshes when done; don't kill a confirm
            self.refresh()
        return False

    @staticmethod
    def _scan():
        net.rescan()  # "not allowed right after a scan" is fine: the list is fresh then
        time.sleep(4)

    # --- layout ------------------------------------------------------------
    def refresh(self):
        if self.busy:
            return
        self.confirming = False
        self.clear(keep=2)
        devs = net.devices()
        conns = net.connections()
        wifi_dev = next((d["device"] for d in devs if d["type"] == "wifi"), None)
        wifi_conns = [c for c in conns if c["type"] == net.WIFI]

        self.heading("Wi-Fi")
        seen = set()
        if not wifi_dev:
            self.add_widget(label("No Wi-Fi adapter", "dim"))
        else:
            on = net.wifi_enabled()
            sw = Gtk.Switch()
            sw.set_active(on)
            sw.connect("state-set", self.on_wifi_switch)
            self.row("Wi-Fi", sw, hint=wifi_dev)
            if on:
                tools = _buttons(button("Rescan", lambda: self.run_bg("Scanning…", self._scan)),
                                 button("+ Hidden network…", lambda: self.on_hidden(wifi_dev)))
                tools.set_halign(Gtk.Align.START)
                self.add_widget(tools)
                saved = {}
                for c in wifi_conns:  # an active profile wins over another one for the same SSID
                    if c["ssid"] not in saved or c["active"]:
                        saved[c["ssid"]] = c
                nets = net.networks()
                if not nets:
                    self.add_widget(label("No networks found — try Rescan", "dim"))
                for n in nets:
                    seen.add(n["ssid"])
                    self.wifi_row(n, saved.get(n["ssid"]), wifi_dev)
                for c in wifi_conns:  # connected, but not in the (stale) scan list yet
                    if c["active"] and c["ssid"] not in seen:
                        seen.add(c["ssid"])
                        self.item(f"{WIFI_ICON}  {c['ssid'] or c['name']}", None,
                                  [self.disconnect_button(c["ssid"] or c["name"], c), self.forget_button(c)],
                                  lead="Connected")
                away = [c for c in wifi_conns if c["ssid"] not in seen and not c["active"]]
                if away:
                    self.heading("Saved networks")
                    for c in away:
                        self.item(f"{WIFI_ICON}  {c['name']}", "Not in range", [self.forget_button(c)])

        self.heading("Ethernet")
        eths = [d for d in devs if d["type"] == "ethernet"]
        if not eths:
            self.add_widget(label("No Ethernet port", "dim"))
        for d in eths:
            state = d["state"].split(" (")[0].capitalize()
            ip = net.device_ip(d["device"]) if d["state"].startswith("connected") else ""
            title = d["connection"] or d["device"]
            self.item(f"{ETH_ICON}  {title}", " · ".join(x for x in (ip, d["device"]) if x), [],
                      lead=state, lead_cls="ok" if d["state"].startswith("connected") else "dim")

        self.render_vpns()

        adv = Gtk.Button(label="Advanced… (connection editor)")
        adv.set_halign(Gtk.Align.START)
        adv.connect("clicked", lambda _b: launch("nm-connection-editor"))
        self.add_widget(adv)
        self.show_all()

    def render_vpns(self):
        self.heading("VPN")
        vs = vpn.vpns()
        if not vs:
            self.add_widget(label("No VPN yet: add one below", "dim"))
        for v in vs:
            if v["active"]:
                act = button("Disconnect",
                             lambda v=v: self.run_bg(f"Disconnecting {v['name']}…", self.vpn_set, v, False))
            else:
                act = button("Connect", lambda v=v: self.run_bg(f"Connecting {v['name']}…", self.vpn_set, v, True),
                             "primary")
            edit = button("Edit…", lambda v=v: self.swan_edit(v["id"]) if v["backend"] == "swan"
                          else launch("nm-connection-editor", "-e", v["id"]))
            self.item(f"{VPN_ICON}  {v['name']}", v["kind"], [act, edit],
                      lead="Connected" if v["active"] else None, lead_cls="ok")
        adds = [button("+ OpenVPN, OpenConnect, Cisco… or import a file",
                       lambda: launch("nm-connection-editor", "-c", "-t", "vpn")),
                button("+ WireGuard file…", self.import_wireguard)]
        if vpn_edit.installed():
            adds.insert(0, button("+ IKEv2 (FortiGate / strongSwan)…", lambda: self.swan_edit(None)))
        for b in adds:
            b.set_halign(Gtk.Align.START)
            self.add_widget(b)

    @staticmethod
    def vpn_set(v, on):
        err = vpn.set_active(v, on)
        if err and on and v["backend"] == "nm" and vpn.needs_secrets(err):  # password not saved: ask in a terminal
            GLib.idle_add(lambda: launch("fw-term", "--hold", "-e", "nmcli", "--ask", "connection", "up", "uuid",
                                         v["id"]) and False)
            err = "Asking for the VPN password in a terminal…"
        subprocess.run(["pkill", "-RTMIN+13", "-x", "waybar"], check=False)  # bar shield (fw-vpn)
        return err

    def import_wireguard(self):
        dlg = Gtk.FileChooserDialog(title="WireGuard configuration", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Import", Gtk.ResponseType.OK)
        f = Gtk.FileFilter()
        f.set_name("WireGuard (*.conf)")
        f.add_pattern("*.conf")
        dlg.add_filter(f)
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if path:
            self.run_bg("Importing…", net.import_vpn, "wireguard", path)

    # strongSwan: the root helper asks polkit, so it runs in a thread; the form itself is modal on the main loop
    def swan_edit(self, name, typed=None, error=""):
        self.set_status("Waiting for authorisation…")
        bg(vpn_edit.show, lambda cur: self.swan_form(cur, typed, error), name, fail=lambda e: {"error": str(e)})

    def swan_form(self, cur, typed=None, error=""):
        if "error" in cur:
            self.set_status(cur["error"], "bad")
            return False
        self.set_status("")
        self.confirming = True
        try:
            req = vpn_edit.dialog(self.get_toplevel(), cur, typed, error)
            if req == "delete" and not self.confirm(f"Delete the VPN {cur['name']}?"):
                req = None
        finally:
            self.confirming = False
        if req == "delete":
            self.set_status(f"Deleting {cur['name']}…")
            bg(vpn_edit.delete, self.swan_saved, cur["name"], fail=lambda e: {"error": str(e)})
        elif req:
            self.set_status("Saving…")
            bg(vpn_edit.write, lambda res: self.swan_saved(res, cur, req), req, fail=lambda e: {"error": str(e)})
        return False

    def swan_saved(self, res, cur=None, req=None):
        if "error" in res and req is not None:  # back to the form with what was typed
            return self.swan_form(cur, req, res["error"])
        self.set_status(res.get("error") or res.get("note") or "Saved", "bad" if "error" in res else "dim")
        subprocess.run(["pkill", "-RTMIN+13", "-x", "waybar"], check=False)
        self.refresh()
        return False

    def confirm(self, question):
        dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True, message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.OK_CANCEL, text=question)
        dlg.format_secondary_text("The file is kept as a .bak next to it.")
        ok = dlg.run() == Gtk.ResponseType.OK
        dlg.destroy()
        return ok

    def item(self, title, hint, buttons, lead=None, lead_cls="ok"):
        """A row: title, a hint line ('lead' coloured, then the dim rest), buttons on the right."""
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(wrap(label(title)), False, False, 0)
        sub = Gtk.Box()
        if lead:
            sub.pack_start(label(lead, lead_cls), False, False, 0)  # one word
        if hint:
            sub.pack_start(wrap(label((" · " if lead else "") + hint, "dim")), True, True, 0)
        left.pack_start(sub, False, False, 0)
        r.pack_start(left, True, True, 0)
        box = _buttons(*buttons)
        box.set_valign(Gtk.Align.CENTER)
        r.pack_end(box, False, False, 0)
        self.adapt(r, box)
        return self.add_widget(r)

    def wifi_row(self, n, conn, ifname):
        ssid, sec = n["ssid"], n["security"]
        hint = [f"{n['signal']}%", f"{LOCK_ICON} {sec}" if sec else "Open"]
        if conn and not n["in_use"]:
            hint.append("Saved")
        buttons = []
        if n["in_use"] and conn:
            buttons.append(self.disconnect_button(ssid, conn))
        elif not n["in_use"]:
            buttons.append(button("Connect", lambda: self.on_connect(n, conn, ifname), "primary"))
        if conn:
            buttons.append(self.forget_button(conn))
        self.item(f"{WIFI_ICON}  {ssid}", " · ".join(hint), buttons,
                  lead="Connected" if n["in_use"] else None)

    def disconnect_button(self, ssid, conn):
        return button("Disconnect", lambda: self.run_bg(f"Disconnecting from {ssid}…", net.down, conn["uuid"]))

    def forget_button(self, conn):
        """Forget, with a confirm step in place of the row's buttons."""
        b = button("Forget", None, "danger")

        def ask(_b):
            self.confirming = True
            box = b.get_parent()
            for w in box.get_children():
                box.remove(w)
            box.pack_start(wrap(label("Forget this network?", "warn")), False, False, 0)
            box.pack_start(button("Cancel", self.refresh), False, False, 0)
            box.pack_start(button("Forget", lambda: self.run_bg(f"Forgetting {conn['name']}…", net.forget,
                                                                conn["uuid"]), "danger"), False, False, 0)
            box.show_all()
        b.connect("clicked", ask)
        return b

    # --- actions -------------------------------------------------------------
    def on_connect(self, n, conn, ifname):
        ssid, sec = n["ssid"], n["security"]
        if conn:
            self.run_bg(f"Connecting to {ssid}…", net.up, conn["uuid"])
        elif net.unsupported(sec):
            self.set_status(net.unsupported(sec), "bad")
        elif net.needs_password(sec):
            got = self.ask_secret(f"Connect to {ssid}", sec)
            if got:
                self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, sec, got[1], ifname)
        else:
            self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, sec, "", ifname)

    def on_wifi_switch(self, _sw, state):
        """Block the switch's own state change; the refresh after the action shows the real one."""
        if state:  # scan right away, or the list stays empty until a manual Rescan
            self.run_bg("Turning Wi-Fi on…", lambda: net.set_wifi(True) or self._scan())
        else:
            self.run_bg("Turning Wi-Fi off…", net.set_wifi, False)
        return True

    def on_hidden(self, ifname):
        got = self.ask_secret("Hidden network", "WPA2", ask_ssid=True)
        if got:
            ssid, pw = got
            self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, "WPA2" if pw else "", pw, ifname, True)

    def ask_secret(self, title, security, ask_ssid=False):
        """Modal dialog in the app's style -> (ssid, password) or None. For a hidden network the password
        is optional (empty = open network)."""
        dlg = Gtk.Dialog(transient_for=self.get_toplevel(), modal=True, title=title)
        dlg.get_style_context().add_class("panel")
        dlg.set_default_size(380, -1)
        area = dlg.get_content_area()
        area.set_spacing(8)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, f"set_margin_{side}")(16)
        area.pack_start(label(title, "title"), False, False, 0)
        ssid_entry = Gtk.Entry(placeholder_text="Network name (SSID)") if ask_ssid else None
        if ssid_entry:
            area.pack_start(ssid_entry, False, False, 0)
        pw = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD,
                       placeholder_text="Password (blank for an open network)" if ask_ssid else "Password")
        area.pack_start(pw, False, False, 0)
        show = Gtk.CheckButton(label="Show password")
        show.connect("toggled", lambda c: pw.set_visibility(c.get_active()))
        area.pack_start(show, False, False, 0)
        if not ask_ssid:
            area.pack_start(label(f"{LOCK_ICON} {security}", "dim"), False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("Connect", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("primary")
        dlg.set_default_response(Gtk.ResponseType.OK)

        def valid():
            p = pw.get_text()
            if ssid_entry:
                return bool(ssid_entry.get_text().strip()) and (not p or _valid_psk(p, "WPA2"))
            return _valid_psk(p, security)

        def changed(*_):
            ok.set_sensitive(valid())
        for e in (pw, ssid_entry):
            if e:
                e.connect("changed", changed)
                e.connect("activate", lambda _e: valid() and dlg.response(Gtk.ResponseType.OK))
        changed()
        dlg.show_all()
        self.confirming = True
        try:
            resp = dlg.run()
        finally:
            self.confirming = False
        result = ((ssid_entry.get_text().strip() if ssid_entry else ""), pw.get_text())
        dlg.destroy()
        return result if resp == Gtk.ResponseType.OK and (ssid_entry is None or result[0]) else None


def build():
    return NetworkPage()

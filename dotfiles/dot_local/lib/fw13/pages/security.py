"""Security: fingerprint, lock screen, disk encryption unlock (LUKS + TPM), Secure Boot, Citadel firewall, VPN
(strongSwan toggle note, pointer to Network → VPN) and the login screen.

Root-only facts (LUKS tokens, Secure Boot) come from /var/lib/fw13/health-root.json (fw-health-root, hourly), so
opening the page never asks for a password. Changing how the disk unlocks runs `sudo fw-disk-unlock <mode>` in a
terminal (it asks for the disk passphrase there); the passphrase slot is never removed.
"""
import glob
import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import health, setup, system  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .common import Page, label, launch  # noqa: E402
from .system import bg  # noqa: E402

UNLOCK = (("password", "Password only"), ("tpm-pin", "TPM + PIN"), ("tpm", "TPM automatic"))
REMOVE_SH = 'read -rp "Delete every enrolled finger? [y/N] " a; [[ $a == [yY]* ]] && fprintd-delete "$USER"'
VPN_CTL = "/usr/local/bin/fw-vpn-ctl"
VPN_POLICY = "/usr/share/polkit-1/actions/org.fw13.vpn.policy"


def _load():
    """Everything the page shows; runs in a worker thread."""
    return {"fingers": setup.fingerprints(), "root": health.root_facts(), "citadel": system.citadel_status(),
            "citadel_app": shutil.which("citadel-app"), "login": setup.login_screen(),
            "vpn": bool(glob.glob("/etc/strongswan/swanctl/conf.d/*.conf"))}


def unlock_mode(luks):
    """'password' / 'tpm-pin' / 'tpm' from the root facts' luks entry, None when unknown."""
    if not luks or luks.get("tpm2") is None:
        return None
    return ("tpm-pin" if luks.get("pin") else "tpm") if luks["tpm2"] else "password"


def _term(*cmd):
    launch("fw-term", "--hold", "-e", *cmd)


def _row_buttons(*widgets):
    box = Gtk.Box(spacing=6)
    for w in widgets:
        box.pack_start(w, False, False, 0)
    return box


class SecurityPage(Page):
    def __init__(self):
        super().__init__("Security")
        self.st = None
        self.add_widget(label("Loading…", "dim"))
        self.refresh()

    def refresh(self):
        bg(_load, self.got_state, fail=lambda e: {"error": str(e)})

    def got_state(self, st):
        self.st = st
        self.render()
        return False

    def render(self):
        self.clear()
        st = self.st
        if "error" in st:
            self.add_widget(label(st["error"], "bad", wrap=True))
            self.show_all()
            return
        root = st["root"]
        self.render_fingerprint(st["fingers"])
        self.heading("Lock screen")
        self.row("Lock after idle", button("Power settings", lambda: launch("fw-settings", "power")),
                 hint="Set per power source in Power → Screen & sleep · SUPER+L locks right away")
        self.row("Lock now", button("Lock", lambda: subprocess.Popen(["loginctl", "lock-session"])))
        self.render_disk(root)
        self.heading("Secure Boot")
        sb = None if root is None else root.get("secure_boot")
        self.row("Secure Boot", label({True: "On", False: "Off"}.get(sb, "Unknown"),
                                      {True: "ok", False: "warn"}.get(sb, "dim")),
                 hint="Changed in the BIOS (F2 at power-on), not from here")
        self.render_citadel(st["citadel"], st["citadel_app"])
        self.render_vpn(st["vpn"])
        self.heading("Login screen")
        self.row("Login", label(st["login"], "dim"))
        self.show_all()

    def render_fingerprint(self, n):
        self.heading("Fingerprint")
        if n is None:
            self.row("Fingerprint reader", label("No reader found", "dim"))
            return
        enrol = button("Enrol", lambda: _term("fprintd-enroll"))
        remove = button("Remove all", lambda: _term("bash", "-c", REMOVE_SH))
        remove.set_sensitive(n > 0)
        self.row(f"{n} finger{'s' if n != 1 else ''} enrolled", _row_buttons(enrol, remove),
                 hint="Used for sudo, polkit and the lock screen")

    def render_disk(self, root):
        self.heading("Disk encryption")
        if root is None or "luks" not in root:  # missing, stale, or written by an fw-health-root without LUKS facts
            self.row("Status unknown", hint="Root facts not written yet: sudo systemctl start fw-health-root")
            return
        luks = root.get("luks")
        if luks is None:
            self.row("Not encrypted", label("No LUKS under /", "warn"),
                     hint="Encryption is chosen when Fedora is installed")
            return
        mode = unlock_mode(luks)
        sb = root.get("secure_boot")
        combo = Gtk.ComboBoxText()
        for mid, text in UNLOCK:
            # TPM automatic needs Secure Boot (fw-disk-unlock refuses it otherwise); still listed if already in use
            if mid != "tpm" or sb is True or mode == "tpm":
                combo.append(mid, text)
        if mode:
            combo.set_active_id(mode)
        combo.connect("changed", self.on_unlock, mode)
        hint = "Opens a terminal: asks for the disk passphrase, which always stays as the fallback"
        if sb is not True:
            hint += " · TPM automatic needs Secure Boot on"
        elif mode != "tpm":
            hint += " · TPM automatic only guards against the disk leaving the laptop; TPM + PIN also against a stolen laptop"
        self.row("Unlock at boot" if mode else "Unlock at boot (unknown)", combo, hint=hint)

    def on_unlock(self, combo, mode):
        new = combo.get_active_id()
        if not new or new == mode:
            return
        _term("sudo", "fw-disk-unlock", new)
        # The terminal does the change (or the user cancels); show the real state until the page reloads.
        combo.handler_block_by_func(self.on_unlock)
        if mode:
            combo.set_active_id(mode)
        else:
            combo.set_active(-1)
        combo.handler_unblock_by_func(self.on_unlock)

    def render_vpn(self, have):
        self.heading("VPN")
        if have:
            free = os.path.exists(VPN_CTL) and os.path.exists(VPN_POLICY)
            self.row("strongSwan connect / disconnect", label("No password" if free else "Asks for the password", "dim"),
                     hint="Bar shield menu · admins (wheel) at the laptop, these connections only" if free
                     else "Re-run the installer's system phase for the passwordless toggle")
        self.row("Your VPNs", button("Network settings", lambda: launch("fw-settings", "network")),
                 hint="Add, edit and connect every VPN in Network → VPN")

    def render_citadel(self, st, app):
        self.heading("Firewall (Citadel)")
        if st is None:
            self.row("Citadel", label("Not running" if app else "Not installed", "dim"))
            return
        on = bool(st.get("enforce"))
        state = label("Enforcing" if on else "Monitoring only", "ok" if on else "warn")
        widgets = [state]
        if app:
            widgets.append(button("Open Citadel", lambda: launch("citadel-app")))
        self.row(f"Outbound firewall · {st.get('mode', '')} · {st.get('activeProfile', '')}".rstrip(" ·"),
                 _row_buttons(*widgets), hint=st.get("enforceError") or "Asks before an app connects out")


def build():
    return SecurityPage()

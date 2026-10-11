"""VPN editor for Settings → Security: a form over the root helper /usr/local/bin/fw-vpn-config (pkexec; polkit
asks for the password once and keeps it a few minutes, so Save doesn't ask again). Secrets never come back from
the helper: the password and pre-shared key fields start empty and mean "keep" when left so."""
import json
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .common import label  # noqa: E402

HELPER = "/usr/local/bin/fw-vpn-config"
# key, label, placeholder, secret
FIELDS = (("name", "Name", "e.g. office", False),
          ("server", "Server", "vpn.example.com or an IP address", False),
          ("remote_id", "Gateway ID", "optional: the FortiGate's local ID", False),
          ("local_id", "Your ID", "optional: same as the username", False),
          ("username", "Username", "", False),
          ("password", "Password", "", True),
          ("psk", "Pre-shared key", "", True),
          ("networks", "Networks", "e.g. 10.0.0.0/16, 192.168.1.0/24 (empty = all traffic)", False))
REQUIRED = ("name", "server", "username")


def installed():
    return os.access(HELPER, os.X_OK)


def _run(args, data=None):
    r = subprocess.run(["pkexec", HELPER, *args], input=data, capture_output=True, text=True, timeout=120)
    if r.returncode in (126, 127) and not r.stdout.strip():
        raise RuntimeError("Not authorised (cancelled)")
    try:
        out = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError((r.stderr or "fw-vpn-config failed").strip().splitlines()[-1]) from None
    if "error" in out:
        raise RuntimeError(out["error"])
    return out


def show():
    return _run(["show"])


def write(req):
    return _run(["write"], json.dumps(req))


def dialog(parent, cur, typed=None, error=""):
    """Modal form → the request for write() or None. cur: show()'s answer ({} = new VPN); typed: values to put
    back after a failed save."""
    values = {**cur, **(typed or {})}
    dlg = Gtk.Dialog(transient_for=parent, modal=True, title="Edit VPN" if cur else "Add VPN")
    dlg.get_style_context().add_class("panel")
    dlg.set_default_size(460, -1)
    area = dlg.get_content_area()
    area.set_spacing(8)
    for side in ("top", "bottom", "start", "end"):
        getattr(area, f"set_margin_{side}")(16)
    area.pack_start(label("Edit VPN" if cur else "Add VPN", "title"), False, False, 0)
    area.pack_start(label("FortiGate-style IKEv2: the gateway proves itself with the pre-shared key, you log in "
                          "with username and password.", "dim", wrap=True, max_width_chars=55), False, False, 0)
    grid = Gtk.Grid(row_spacing=6, column_spacing=12)
    entries = {}
    for i, (key, text, hint, secret) in enumerate(FIELDS):
        kept = secret and cur.get(f"has_{key}")
        e = Gtk.Entry(text=values.get(key) or "" if not secret else (typed or {}).get(key, ""),
                      visibility=not secret, hexpand=True, max_length=256,
                      placeholder_text="unchanged" if kept else hint)
        if secret:
            e.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        entries[key] = e
        grid.attach(label(text, xalign=0), 0, i, 1, 1)
        grid.attach(e, 1, i, 1, 1)
    area.pack_start(grid, False, False, 0)
    show_box = Gtk.CheckButton(label="Show password and key")
    show_box.connect("toggled", lambda c: [entries[k].set_visibility(c.get_active())
                                           for k, *_r, s in FIELDS if s])
    area.pack_start(show_box, False, False, 0)
    err = label(error, "bad", wrap=True, max_width_chars=55)
    area.pack_start(err, False, False, 0)
    dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
    ok = dlg.add_button("Save", Gtk.ResponseType.OK)
    ok.get_style_context().add_class("primary")

    def changed(*_):
        missing = [k for k in REQUIRED if not entries[k].get_text().strip()]
        missing += [k for k, *_r, s in FIELDS if s and not cur.get(f"has_{k}") and not entries[k].get_text()]
        ok.set_sensitive(not missing)
    for e in entries.values():
        e.connect("changed", changed)
    changed()
    dlg.show_all()
    resp = dlg.run()
    # read before destroy(): afterwards the entries read as empty
    req = {k: e.get_text() if s else e.get_text().strip() for (k, *_r, s), e in zip(FIELDS, entries.values())}
    dlg.destroy()
    if resp != Gtk.ResponseType.OK:
        return None
    req["old"] = cur.get("name")
    return req

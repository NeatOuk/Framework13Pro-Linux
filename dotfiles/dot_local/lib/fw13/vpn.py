"""Every VPN in one list: NetworkManager's (OpenVPN, OpenConnect, vpnc, WireGuard… via net.py) and strongSwan's
(/etc/strongswan/swanctl/conf.d/<name>.conf, IKEv2 PSK + EAP, which NetworkManager's plugin can't do).

Used by the bar (fw-vpn: shield + menu) and Settings → Network. NetworkManager VPNs go up/down with nmcli (no
root); strongSwan ones through `pkexec fw-vpn-ctl up|down <name>` (polkit: no password for wheel at the laptop).
Without root the only strongSwan state is charon's route table 220 (shared by all its tunnels), so the name of the
connection we brought up is remembered in $XDG_RUNTIME_DIR/fw-vpn-swan.
"""
import glob
import os
import re
import subprocess

from . import net

SWAN_DIR = "/etc/strongswan/swanctl/conf.d"
CTL = "/usr/local/bin/fw-vpn-ctl"
STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "fw-vpn-swan")
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
KINDS = {"openvpn": "OpenVPN", "openconnect": "OpenConnect", "vpnc": "Cisco IPsec", "strongswan": "IKEv2",
         "l2tp": "L2TP", "pptp": "PPTP", "libreswan": "IPsec", "fortisslvpn": "FortiSSL", "wireguard": "WireGuard"}


def swan_names():
    return sorted(n for n in (os.path.basename(f)[:-5] for f in glob.glob(os.path.join(SWAN_DIR, "*.conf")))
                  if NAME_RE.fullmatch(n))


def swan_routes():
    r = subprocess.run(["ip", "-4", "route", "show", "table", "220"], capture_output=True, text=True)
    return [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []


def _swan_active(names, routes):
    """The strongSwan connections that are up (best effort, see the module doc)."""
    if not routes:
        return set()
    try:
        remembered = set(open(STATE).read().split()) & set(names)
    except OSError:
        remembered = set()
    # shortcut: brought up some other way (sudo swanctl) with several defined → we can't tell which; show none
    return remembered or (set(names) if len(names) == 1 else set())


def _remember(name, up):
    try:
        cur = set(open(STATE).read().split())
    except OSError:
        cur = set()
    cur = (cur | {name}) if up else (cur - {name})
    with open(STATE, "w") as f:
        f.write("\n".join(sorted(cur)))


def _nm_kinds(uuids):
    kinds, uuid = {}, None
    if uuids:
        for k, v in net._rows("-f", "connection.uuid,vpn.service-type", "connection", "show", *uuids, n=2):
            if k == "connection.uuid":
                uuid = v
            elif k == "vpn.service-type" and uuid:
                kinds[uuid] = KINDS.get(v.rsplit(".", 1)[-1], "VPN")
    return kinds


def vpns():
    """[{id, name, kind, backend: "nm"|"swan", active}], NetworkManager's first."""
    nm = [c for c in net.connections() if c["type"] in net.VPN_TYPES]
    kinds = _nm_kinds([c["uuid"] for c in nm if c["type"] == "vpn"])
    out = [{"id": c["uuid"], "name": c["name"], "backend": "nm", "active": c["active"],
            "kind": "WireGuard" if c["type"] == "wireguard" else kinds.get(c["uuid"], "VPN")} for c in nm]
    names = swan_names()
    up = _swan_active(names, swan_routes()) if names else set()
    out += [{"id": n, "name": n, "backend": "swan", "active": n in up, "kind": "IKEv2 · strongSwan"} for n in names]
    return out


def set_active(v, on):
    """Connect or disconnect one entry of vpns(); returns an error string or None."""
    if v["backend"] == "nm":
        return net.up(v["id"]) if on else net.down(v["id"])
    cmd = [CTL, "up" if on else "down", v["id"]] if os.access(CTL, os.X_OK) else \
        ["swanctl", "--initiate", "--child", v["id"]] if on else ["swanctl", "--terminate", "--ike", v["id"]]
    r = subprocess.run(["pkexec", *cmd], capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        lines = (r.stderr or r.stdout).strip().splitlines()
        return lines[-1] if lines else "Cancelled"
    _remember(v["id"], on)
    return None


def needs_secrets(err):
    """nmcli's answer when a VPN's password isn't saved and no agent asked for it."""
    return bool(err) and "secret" in err.lower()

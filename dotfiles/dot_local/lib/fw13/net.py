"""Wi-Fi, Ethernet and VPN through NetworkManager's nmcli (terse, escaped output)."""
import os
import re
import subprocess
import tempfile

WIFI = "802-11-wireless"
VPN_TYPES = ("vpn", "wireguard")


def split(line):
    """One `nmcli -t -e yes` line -> fields: split on unescaped ':', then drop the escapes."""
    fields, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def _run(*args, timeout=60):
    """nmcli with args -> (ok, stdout, first error line)."""
    try:
        p = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "", "Timed out"
    except OSError as e:
        return False, "", str(e)
    err = next((ln for ln in p.stderr.splitlines() if ln.strip()), "") or f"nmcli failed ({p.returncode})"
    return p.returncode == 0, p.stdout, err.removeprefix("Error: ")


def _rows(*args, n):
    ok, out, _ = _run("-t", "-e", "yes", *args, timeout=15)
    rows = [split(ln) for ln in out.splitlines() if ln] if ok else []
    return [r for r in rows if len(r) == n]


def _err(result):
    ok, _out, err = result
    return None if ok else err


def wifi_enabled():
    return _run("radio", "wifi", timeout=10)[1].strip() == "enabled"


def set_wifi(on):
    return _err(_run("radio", "wifi", "on" if on else "off", timeout=15))


def devices():
    """[{device, type, state, connection}] without loopback / p2p."""
    return [{"device": d, "type": t, "state": s, "connection": c}
            for d, t, s, c in _rows("-f", "DEVICE,TYPE,STATE,CONNECTION", "device", n=4)
            if t in ("wifi", "ethernet")]


def device_ip(dev):
    """First IPv4 address (without prefix) of a device, or ''."""
    for name, value in _rows("-f", "IP4.ADDRESS", "device", "show", dev, n=2):
        if name.startswith("IP4.ADDRESS") and value:
            return value.split("/")[0]
    return ""


def connections():
    """Saved profiles [{name, uuid, type, device, active, ssid}]; ssid only for Wi-Fi."""
    conns = [{"name": n, "uuid": u, "type": t, "device": d, "active": a == "yes", "ssid": ""}
             for n, u, t, d, a in _rows("-f", "NAME,UUID,TYPE,DEVICE,ACTIVE", "connection", "show", n=5)
             if t != "loopback"]
    wifi = [c for c in conns if c["type"] == WIFI]
    if wifi:  # one call for every Wi-Fi profile's SSID (the name can differ from it)
        by_uuid, uuid = {c["uuid"]: c for c in wifi}, None
        for name, value in _rows("-f", "connection.uuid,802-11-wireless.ssid", "connection", "show",
                                 *[c["uuid"] for c in wifi], n=2):
            if name == "connection.uuid":
                uuid = value
            elif name == "802-11-wireless.ssid" and uuid in by_uuid:
                by_uuid[uuid]["ssid"] = value
    return conns


def networks():
    """Visible Wi-Fi networks, one per SSID, strongest first: [{ssid, signal, security, in_use}]."""
    best = {}
    for in_use, signal, security, ssid in _rows("-f", "IN-USE,SIGNAL,SECURITY,SSID", "dev", "wifi", "list",
                                                "--rescan", "no", n=4):
        if not ssid:  # hidden network
            continue
        n = {"ssid": ssid, "signal": int(signal) if signal.isdigit() else 0,
             "security": "" if security in ("", "--") else security, "in_use": in_use == "*"}
        old = best.get(ssid)
        if old is None or (n["in_use"], n["signal"]) > (old["in_use"], old["signal"]):
            best[ssid] = n
    return sorted(best.values(), key=lambda n: (not n["in_use"], -n["signal"], n["ssid"].lower()))


def rescan():
    return _err(_run("dev", "wifi", "rescan", timeout=30))


def up(uuid):
    return _err(_run("-w", "45", "connection", "up", "uuid", uuid, timeout=60))


def down(uuid):
    return _err(_run("connection", "down", "uuid", uuid, timeout=30))


def forget(uuid):
    return _err(_run("connection", "delete", "uuid", uuid, timeout=30))


def _owe(sec):
    """OWE or OWE transition mode (OWE-TM): encrypted, but no password."""
    return bool(sec) and all(s.startswith("OWE") for s in sec)


def needs_password(security):
    return bool(security) and not _owe(security.split())


def unsupported(security):
    """Why a network can't be joined from here (802.1X, WEP), or None."""
    sec = security.split()
    if any(s.startswith("802.1X") for s in sec):
        return "Enterprise (802.1X) Wi-Fi: set it up with Advanced…"
    if "WEP" in sec:
        return "WEP Wi-Fi: set it up with Advanced…"
    return None


def connect_new(ssid, security, password, ifname="", hidden=False):
    """Create a profile for a new network and bring it up. The secret goes through a 0600 passwd-file,
    never argv. On failure the half-made profile is removed. Returns an error string or None."""
    sec = security.split()
    if unsupported(security):
        return unsupported(security)
    args = ["connection", "add", "type", "wifi", "con-name", ssid, "ssid", ssid]
    if ifname:
        args += ["ifname", ifname]
    if hidden:
        args += ["802-11-wireless.hidden", "yes"]
    if _owe(sec):
        args += ["802-11-wireless-security.key-mgmt", "owe"]
    elif password:
        mgmt = "sae" if sec and all(s == "WPA3" for s in sec) else "wpa-psk"
        args += ["802-11-wireless-security.key-mgmt", mgmt]
    ok, out, err = _run(*args, timeout=20)
    if not ok:
        return err
    m = re.search(r"\(([0-9a-f-]{36})\)", out)
    if not m:
        return "Could not create the connection"
    uuid = m.group(1)
    up_args = ["-w", "45", "connection", "up", "uuid", uuid]
    path = None
    try:
        if password:
            fd, path = tempfile.mkstemp(prefix="fw-net-", dir=os.environ.get("XDG_RUNTIME_DIR"))
            with os.fdopen(fd, "w") as f:  # mkstemp already made it 0600
                f.write(f"802-11-wireless-security.psk:{password}\n")
            up_args += ["passwd-file", path]
        ok, _out, err = _run(*up_args, timeout=60)
    finally:
        if path:
            os.unlink(path)
    if not ok:
        forget(uuid)
        return err
    return None

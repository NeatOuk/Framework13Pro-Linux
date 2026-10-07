"""Cloudflare WARP backend for fw-warp-panel and the bar icon (no GTK).

Everything goes through `warp-cli -j` (JSON). warp-cli refuses to run without `--accept-tos` unless the Terms of
Service were accepted in a TTY, so every call passes it, but only after the user accepted them in the panel
(store key "warp_tos"). Read-only calls are cheap (a socket to warp-svc); the panel polls them from a thread.
Exit IP / Cloudflare location come from Cloudflare's own trace endpoint (/cdn-cgi/trace on 1.1.1.1 and its IPv6
twin), traffic and MTU from /sys/class/net/<WARP interface>.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request

from . import store

TOS_KEY = "warp_tos"
TOS_URL = "https://www.cloudflare.com/application/terms/"
PRIVACY_URL = "https://www.cloudflare.com/application/privacypolicy/"
IFACE = "CloudflareWARP"

MODES = [("warp", "WARP (VPN)"), ("warp+doh", "WARP + DNS over HTTPS"), ("warp+dot", "WARP + DNS over TLS"),
         ("doh", "DNS only, over HTTPS (1.1.1.1)"), ("dot", "DNS only, over TLS"),
         ("proxy", "Local SOCKS5 proxy"), ("tunnel_only", "Tunnel, no DNS proxy")]
FAMILIES = [("off", "Off"), ("malware", "Block malware"), ("full", "Block malware + adult content")]
PROTOCOLS = [("MASQUE", "MASQUE (HTTP/3)"), ("WireGuard", "WireGuard")]


def installed():
    return shutil.which("warp-cli") is not None


def tos_accepted():
    return bool(store.get(TOS_KEY))


def accept_tos():
    store.set(TOS_KEY, True)


def cli(*args, json_out=True, timeout=10):
    """Run warp-cli; returns (ok, parsed JSON or text). Never prompts (stdin closed, ToS flag given)."""
    if not installed():
        return False, "warp-cli is not installed"
    if not tos_accepted():
        return False, "Cloudflare's Terms of Service are not accepted yet"
    cmd = ["warp-cli", "--accept-tos", "--no-paginate"] + (["-j"] if json_out else []) + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (r.stdout or "").strip()
    if r.returncode != 0 or out.startswith("Error"):
        return False, (out or r.stderr or "warp-cli failed").strip().removeprefix("Error: ")
    if not json_out:
        return True, out
    try:
        return True, json.loads(out)
    except ValueError:
        return True, out  # some commands print plain text even with -j


def status():
    """{'status': 'Connected'|'Disconnected'|'Connecting'|'Unable'|..., 'reason': str} or None."""
    ok, d = cli("status", timeout=5)
    if not ok or not isinstance(d, dict):
        return None
    return {"status": d.get("status", "Unknown"), "reason": reason_text(d.get("reason"))}


def reason_text(r):
    """warp-cli reasons are strings or {"RegistrationMissing": "DaemonStartup"}-style objects."""
    if r is None:
        return ""
    if isinstance(r, str):
        return split_camel(r)
    if isinstance(r, dict):
        return "; ".join(f"{split_camel(k)}" + (f" ({reason_text(v)})" if v not in (None, "", {}) else "")
                         for k, v in r.items())
    if isinstance(r, list):
        return "; ".join(reason_text(x) for x in r)
    return str(r)


def split_camel(s):
    out = ""
    for i, ch in enumerate(s):
        if ch.isupper() and i and (s[i - 1].islower() or (i + 1 < len(s) and s[i + 1].islower())):
            out += " "
        out += ch
    return out


def settings():
    ok, d = cli("settings", "list", timeout=5)
    return d.get("settings", {}) if ok and isinstance(d, dict) else {}


def find(d, *needles, default=None):
    """First value whose key contains all needles (settings keys appear only once they're set)."""
    for k, v in (d or {}).items():
        if all(n in k.lower() for n in needles):
            return v
    return default


def registration():
    ok, d = cli("registration", "show", timeout=5)
    return d if ok and isinstance(d, dict) else None


def organization():
    ok, d = cli("registration", "organization", timeout=5)
    return d if ok else None


def tunnel_stats():
    ok, d = cli("tunnel", "stats", timeout=5)
    return d if ok else None


def warp_stats():
    ok, d = cli("stats", timeout=5)
    return d if ok else None


def dns_stats():
    ok, d = cli("dns", "stats", timeout=5)
    return d if ok else None


def network():
    ok, d = cli("debug", "network", timeout=5)
    return d if ok else None


def trusted_ssids():
    ok, d = cli("trusted", "ssid", "list", timeout=5)
    return d if ok else None


def split_hosts():
    ok, d = cli("tunnel", "host", "list", timeout=5)
    return d if ok else None


# --- actions (return None or an error text) -----------------------------------------------------------------

def _do(*args, timeout=30):
    ok, d = cli(*args, json_out=False, timeout=timeout)
    return None if ok else str(d)


def connect():
    return _do("connect")


def disconnect():
    return _do("disconnect")


def register():
    return _do("registration", "new", timeout=60)


def unregister():
    return _do("registration", "delete")


def join_org(team, wait=20):
    """Join a Zero Trust organization ("team name", as in <team>.cloudflareaccess.com). Returns (url, error).

    Replaces the current registration (a free one included). `registration new <team>` prints a sign-in URL and
    keeps waiting for the browser; after the login, the browser opens com.cloudflare.warp://…, which
    com.cloudflare.warp.desktop hands to `warp-cli registration token`. So the command is left running in its own
    session and only its URL is returned for the caller to open.
    """
    team = team.strip().removesuffix(".cloudflareaccess.com").removeprefix("https://")
    if not team or any(c.isspace() for c in team):
        return None, "Enter your team name (the part before .cloudflareaccess.com)"
    if registration() is not None:
        err = unregister()
        if err:
            return None, err
    cmd = ["warp-cli", "--accept-tos", "registration", "new", team]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, start_new_session=True)
    except OSError as e:
        return None, str(e)
    found, lines = [], []

    def read():
        for line in p.stdout:
            lines.append(line.strip())
            m = re.search(r"https://\S+", line)
            if m and not found:
                found.append(m.group(0))
    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(wait)
    if found:
        return found[0], None
    if p.poll() == 0:
        return None, None  # registered without a browser step (e.g. a service token from MDM)
    msg = next((ln.removeprefix("Error: ") for ln in reversed(lines) if ln), "no sign-in link from warp-cli")
    return None, msg


def set_mode(mode):
    return _do("mode", mode)


def set_families(mode):
    return _do("dns", "families", mode)


def set_protocol(proto):
    return _do("tunnel", "protocol", "set", proto)


def set_license(key):
    return _do("registration", "license", key, timeout=60)


def set_trusted(kind, enabled):
    """kind: 'wifi' or 'ethernet' (disconnect on every network of that kind)."""
    return _do("trusted", kind, "enable" if enabled else "disable")


def add_trusted_ssid(ssid):
    return _do("trusted", "ssid", "add", ssid)


def remove_trusted_ssid(ssid):
    return _do("trusted", "ssid", "remove", ssid)


def add_split_host(host):
    return _do("tunnel", "host", "add", host)


def remove_split_host(host):
    return _do("tunnel", "host", "remove", host)


def add_split_ip(ip):
    return _do("tunnel", "ip", "add-range" if "/" in ip else "add", ip)


def remove_split_ip(ip):
    return _do("tunnel", "ip", "remove-range" if "/" in ip else "remove", ip)


def add_fallback(domain):
    return _do("dns", "fallback", "add", domain)


def remove_fallback(domain):
    return _do("dns", "fallback", "remove", domain)


def set_proxy_port(port):
    return _do("proxy", "port", str(int(port)))


# --- outside warp-cli ----------------------------------------------------------------------------------------

def trace(v6=False, timeout=4):
    """Cloudflare's /cdn-cgi/trace as a dict (ip, loc, colo, warp=on|plus|off, http, tls, …), or None."""
    url = "https://[2606:4700:4700::1111]/cdn-cgi/trace" if v6 else "https://1.1.1.1/cdn-cgi/trace"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            text = r.read(4096).decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def iface():
    """{'mtu': int, 'rx': bytes, 'tx': bytes, 'addrs': [..]} for the WARP interface, or None when it's down."""
    base = f"/sys/class/net/{IFACE}"
    if not os.path.isdir(base):
        return None

    def num(p):
        try:
            with open(os.path.join(base, p)) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return 0
    addrs = []
    try:
        r = subprocess.run(["ip", "-j", "addr", "show", "dev", IFACE], capture_output=True, text=True, timeout=3)
        for a in json.loads(r.stdout or "[]"):
            addrs += [f"{i['local']}/{i['prefixlen']}" for i in a.get("addr_info", [])]
    except (OSError, ValueError, subprocess.TimeoutExpired, KeyError):
        pass
    return {"mtu": num("mtu"), "rx": num("statistics/rx_bytes"), "tx": num("statistics/tx_bytes"), "addrs": addrs}


def citadel_note():
    """A warning when Citadel enforces but has no allow policy for warp-svc yet, else None."""
    if not shutil.which("citadel"):
        return None
    try:
        st = json.loads(subprocess.run(["citadel", "status"], capture_output=True, text=True, timeout=3).stdout)
        if not st.get("enforce"):
            return None
        rules = json.loads(subprocess.run(["citadel", "rules"], capture_output=True, text=True, timeout=3).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired, AttributeError):
        return None
    for r in rules if isinstance(rules, list) else []:
        if str(r.get("app", "")).endswith("/warp-svc") and r.get("action") == "allow":
            return None
    return "Citadel enforces: allow warp-svc at its gate (Always allow), or WARP can't connect"


def human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def bar():
    """Waybar JSON for the cloud icon: class connected | connecting | disconnected | off (not set up)."""
    icon = ""  # FA6 cloud
    if not installed():
        return {"text": "", "class": "hidden"}
    if not tos_accepted():
        return {"text": icon, "class": "off", "tooltip": "Cloudflare WARP: click to set up"}
    st = status()
    if st is None:
        return {"text": icon, "class": "off", "tooltip": "Cloudflare WARP: the warp-svc service isn't answering"}
    s = st["status"]
    cls = {"Connected": "connected", "Connecting": "connecting"}.get(s, "disconnected")
    tip = f"Cloudflare WARP: {s}" + (f" ({st['reason']})" if st["reason"] and s != "Connected" else "")
    return {"text": icon, "class": cls, "tooltip": tip}


def pretty_key(k):
    return split_camel(str(k).replace("_", " ")).strip().capitalize()


def flatten(d, prefix=""):
    """[(label, value text)] for any warp-cli JSON (nested dicts/lists), for 'show everything' sections."""
    rows = []
    if isinstance(d, dict):
        for k, v in d.items():
            label = f"{prefix}{pretty_key(k)}"
            if isinstance(v, dict) and v:
                rows += flatten(v, label + " · ")
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                for i, x in enumerate(v, 1):
                    rows += flatten(x, f"{label} {i} · ")
            else:
                rows.append((label, value_text(v)))
    elif isinstance(d, list):
        for i, x in enumerate(d, 1):
            rows += flatten(x, f"{prefix}{i} · ") if isinstance(x, (dict, list)) else [(f"{prefix}{i}", value_text(x))]
    elif d not in (None, ""):
        rows.append((prefix.rstrip(" ·") or "Info", value_text(d)))
    return rows


def value_text(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return ", ".join(value_text(x) for x in v) or "—"
    if v is None or v == "":
        return "—"
    return str(v)

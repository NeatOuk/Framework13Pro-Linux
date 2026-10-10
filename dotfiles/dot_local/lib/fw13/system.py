"""Date & time (timedatectl), device name (hostnamectl), package updates (dnf5), firmware updates (fwupdmgr) and About facts.

Setters go through systemd's D-Bus services, so the running polkit agent asks for the password — no sudo.
All of these may block (polkit prompt, LVFS lookups): call them from a worker thread.
"""
import json
import os
import re
import shutil
import subprocess

REPORT = os.path.expanduser("~/.local/state/fw13-hypr/install-report.txt")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
TZ_RE = re.compile(r"^[A-Za-z0-9_+][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+)*$")  # never starts with '-'


def _run(*cmd, timeout=None):
    """(returncode, stdout, stderr); 127 when the tool is missing."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out"
    except OSError as e:
        return 126, "", f"{cmd[0]}: {e.strerror or e}"


def _err(rc, err, what):
    """(ok, message) — the tool's last stderr line, or a generic note."""
    if rc == 0:
        return True, ""
    lines = [s.strip() for s in err.splitlines() if s.strip()]
    return False, lines[-1] if lines else f"{what} failed"


def citadel_status():
    """`citadel status` (Citadel firewall) as a dict, or None when it isn't installed or doesn't answer."""
    _rc, out, _e = _run("citadel", "status", timeout=3)
    try:
        st = json.loads(out)
    except ValueError:
        return None
    return st if isinstance(st, dict) else None


# --- date & time -------------------------------------------------------------

def time_state():
    """`timedatectl show` as a dict: Timezone, NTP, CanNTP, NTPSynchronized, …"""
    _rc, out, _e = _run("timedatectl", "show")
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def timezones():
    _rc, out, _e = _run("timedatectl", "list-timezones")
    return [s.strip() for s in out.splitlines() if s.strip()]


def set_timezone(tz):
    if not TZ_RE.match(tz):
        return False, f"“{tz}” is not a time zone name"
    return _err(*_run("timedatectl", "set-timezone", tz)[0::2], "Setting the time zone")


def set_ntp(on):
    return _err(*_run("timedatectl", "set-ntp", "true" if on else "false")[0::2], "Changing time sync")


# --- device name -------------------------------------------------------------

def hostname():
    _rc, out, _e = _run("hostnamectl", "--json=short")
    try:
        return json.loads(out).get("Hostname") or os.uname().nodename
    except ValueError:
        return os.uname().nodename


def valid_hostname(name):
    """RFC 1123 label: letters, digits, hyphens; 1-63 chars; no hyphen at either end."""
    return bool(HOSTNAME_RE.match(name))


def set_hostname(name):
    if not valid_hostname(name):
        return False, "Use letters, digits and hyphens (1-63, not starting or ending with a hyphen)"
    return _err(*_run("hostnamectl", "set-hostname", name)[0::2], "Renaming")


# --- software updates --------------------------------------------------------

def package_updates():
    """(count, message); count None when the check failed. Read-only and offline: `dnf5 --cacheonly
    check-upgrade` (exit 100 = updates) on the cache dnf-makecache.timer keeps fresh."""
    rc, out, err = _run("dnf5", "-q", "--cacheonly", "check-upgrade", timeout=120)
    if rc == 0:
        return 0, "Everything is up to date"
    if rc != 100:
        return None, _err(rc, err, "Checking for updates")[1]
    # package lines are "name.arch  version  repo" at column 0; headers have one word, obsoleted lines are indented
    n = sum(1 for line in out.splitlines() if line[:1].strip() and len(line.split()) == 3)
    return n, f"{n} package update{'s' if n != 1 else ''}"


# --- firmware ----------------------------------------------------------------

def firmware_updates():
    """(updates, message). updates: [{device, current, new, urgency}]; message explains an empty list.

    Read-only: `fwupdmgr get-updates`. Never refreshes metadata (that is `fwupdmgr refresh`, run by the
    fwupd-refresh timer); missing/old metadata just shows fwupdmgr's own note.
    """
    rc, out, err = _run("fwupdmgr", "get-updates", "--json", timeout=120)
    if rc == 127:
        return [], err
    data = None
    start = out.find("{")
    if start >= 0:
        try:
            data = json.loads(out[start:])
        except ValueError:
            data = None
    if not isinstance(data, dict):
        data = {}
    if rc == 2:  # "No updates available" / nothing to do
        return [], "Everything is up to date"
    error = data.get("Error")
    if error:  # with --json, fwupdmgr reports failures on stdout as {"Error": {...}}
        msg = error.get("Message") if isinstance(error, dict) else str(error)
        return [], msg or _err(rc or 1, err, "Checking for updates")[1]
    ups = []
    devices = data.get("Devices")
    for d in devices if isinstance(devices, list) else []:
        if not isinstance(d, dict):
            continue
        rels = d.get("Releases")
        rel = rels[0] if isinstance(rels, list) and rels and isinstance(rels[0], dict) else {}  # newest first
        if rel.get("Version"):
            ups.append({"device": d.get("Name", "Device"), "current": d.get("Version", "?"),
                        "new": rel["Version"], "urgency": rel.get("Urgency", "")})
    if ups:
        return ups, ""
    if rc == 0 and "Devices" in data:
        return [], "Everything is up to date"
    _ok, msg = _err(rc or 1, err, "Checking for updates")
    return [], msg


# --- about -------------------------------------------------------------------

def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def os_name():
    m = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', _read("/etc/os-release"), re.M)
    return m.group(1) if m else "Linux"


def hyprland_version():
    rc, out, _e = _run("hyprctl", "-j", "version", timeout=3)
    try:
        v = json.loads(out) if rc == 0 else {}
    except ValueError:
        v = {}
    return v.get("tag") or v.get("version") or ""


def cpu():
    m = re.search(r"^model name\s*:\s*(.+)$", _read("/proc/cpuinfo"), re.M)
    return f"{m.group(1).strip()} · {os.cpu_count()} threads" if m else ""


def memory():
    m = re.search(r"^MemTotal:\s*(\d+) kB", _read("/proc/meminfo"), re.M)
    return _size(int(m.group(1)) * 1024) if m else ""


def disk(path="/"):
    try:
        st = os.statvfs(path)
    except OSError:
        return ""
    return f"{_size(st.f_bavail * st.f_frsize)} free of {_size(st.f_blocks * st.f_frsize)}"


def gpus():
    if not shutil.which("lspci"):
        return []
    _rc, out, _e = _run("lspci", timeout=5)
    return [line.split(": ", 1)[1] for line in out.splitlines()
            if re.search(r"VGA compatible controller|Display controller|3D controller", line) and ": " in line]


def about():
    """[(label, value)] for the About section; empty values are left out."""
    model = " ".join(s for s in (_read("/sys/class/dmi/id/sys_vendor"),
                                 _read("/sys/class/dmi/id/product_name")) if s)
    hypr = hyprland_version()
    rows = [("System", os_name()), ("Kernel", os.uname().release),
            ("Hyprland", hypr.lstrip("v") if hypr else ""), ("Model", model), ("CPU", cpu()),
            ("Memory", memory()), ("Disk (/)", disk())]
    rows += [("Graphics", g) for g in gpus()]
    return [(k, v) for k, v in rows if v]

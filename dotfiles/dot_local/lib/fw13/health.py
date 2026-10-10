"""Read-only health checks: the hardware group (fw-hwcheck) and the daily group (fw-health, user timer).

Every check returns Result(id, status, summary, fix): status OK / WARN / FAIL / SKIP / MANUAL / INFO, a one-line
summary and a hint (a command or a Settings page, "" when there's nothing to do). Nothing here changes the system.
Expected Framework values live in EXPECTED; on any other machine the hardware checks give SKIP (with what was
found), and an expectation not yet seen on the real Framework (verified=False) gives WARN instead of FAIL.

Root-only facts (Timeshift's snapshot list) come from /var/lib/fw13/health-root.json, written hourly by the
fw-health-root system timer. FW13_HEALTH_ROOT=<dir> reads /sys, /proc and that file below <dir> (tests).
"""
import glob
import json
import os
import re
import shutil
import time
from collections import namedtuple

from . import power, setup, system

Result = namedtuple("Result", "id status summary fix")
Exp = namedtuple("Exp", "path value verified")
OK, WARN, FAIL, SKIP, MANUAL, INFO = "OK", "WARN", "FAIL", "SKIP", "MANUAL", "INFO"
ATTENTION = (WARN, FAIL)
ROOT = os.environ.get("FW13_HEALTH_ROOT", "/")
GIB = 1 << 30

# Framework Laptop 13, AMD Ryzen AI 300 (HX 370, Radeon 890M, MT7925). value None = the path only has to exist.
EXPECTED = {
    "vendor":    Exp("/sys/class/dmi/id/sys_vendor", "Framework", True),
    "product":   Exp("/sys/class/dmi/id/product_name", "Laptop 13", False),        # substring
    "cpu":       Exp("/sys/devices/system/cpu/cpufreq/policy0/scaling_driver", "amd-pstate-epp", False),
    "pstate":    Exp("/sys/devices/system/cpu/amd_pstate/status", "active", False),
    "epp":       Exp("/sys/devices/system/cpu/cpufreq/policy0/energy_performance_preference", None, False),
    "gpu":       Exp("/sys/class/drm/card[0-9]*/device/driver", "amdgpu", True),
    "backlight": Exp("/sys/class/backlight/amdgpu_bl*", None, False),
    "wifi":      Exp("/sys/class/net/*/device/driver", "mt7925e", True),
    "charge":    Exp("/sys/class/power_supply/BAT*/charge_control_end_threshold", None, False),  # cros_charge-control
    "sleep":     Exp("/sys/power/mem_sleep", "s2idle", True),
    "platform":  Exp("/sys/firmware/acpi/platform_profile_choices", "low-power balanced performance", False),
    "light":     Exp("net.hadess.SensorProxy HasAmbientLight", True, False),
    "battery":   Exp("UPower Capacity (% of design)", 80, True),                     # below → WARN
}
TITLES = {
    "cpu": "CPU", "gpu": "Graphics", "wifi": "Wi-Fi", "bluetooth": "Bluetooth", "battery": "Battery",
    "firmware": "Firmware", "fingerprint": "Fingerprint", "light": "Light sensor", "suspend": "Suspend",
    "power": "Power profiles", "vaapi": "Video decoding",
    "units": "Services", "disk": "Disk space", "backup": "Backup (restic)", "timeshift": "Timeshift",
    "restart": "Reboot needed", "updates": "Firmware updates", "battery-health": "Battery health",
    "nvme": "SSD health", "coredumps": "Crashes", "journal": "Journal errors",
}
MANUAL_STEPS = [
    ("m-suspend", "Suspend and resume a few times (lid closed); Wi-Fi, Bluetooth and sound come back"),
    ("m-fingerprint", "Fingerprint works at the login screen (tuigreet) and for sudo"),
    ("m-charge", "With the charge limit on, charging stops at 80 %"),
    ("m-keys", "F-row keys: volume, brightness, mic mute and airplane mode"),
    ("m-light", "Brightness follows the room light (once auto-brightness is switched on)"),
    ("m-steam", "Steam starts a game, also through gamescope"),
]
ROOT_JSON = "/var/lib/fw13/health-root.json"
ROOT_JSON_MAX_AGE = 3 * 3600


def _p(path):
    return os.path.join(ROOT, path.lstrip("/"))


def _read(path):
    try:
        with open(_p(path)) as f:
            return f.read().strip()
    except OSError:
        return ""


def _glob(pattern):
    return sorted(glob.glob(_p(pattern)))


def _run(*cmd, timeout=30):
    return system._run(*cmd, timeout=timeout)


def _ago(ts, now=None):
    s = max(0, int((now or time.time()) - ts))
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 2 * 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def _uptime():
    try:
        return float(_read("/proc/uptime").split()[0])
    except (ValueError, IndexError):
        return 0.0


def is_framework():
    return (_read(EXPECTED["vendor"].path) == EXPECTED["vendor"].value
            and EXPECTED["product"].value in _read(EXPECTED["product"].path))


def _miss(verified):
    """Status for a value that doesn't match EXPECTED on the Framework."""
    return FAIL if verified else WARN


_kernel_errors = None


def kernel_errors():
    """This boot's kernel messages at priority err or worse (cached; "" when the journal isn't readable)."""
    global _kernel_errors
    if _kernel_errors is None:
        _rc, out, _e = _run("journalctl", "-k", "-b", "-p", "err", "-q", "--no-pager", "-o", "cat", timeout=30)
        _kernel_errors = out.splitlines()
    return _kernel_errors


def _driver_errors(word):
    return [line for line in kernel_errors() if word in line.lower()]


# --- hardware group ----------------------------------------------------------------------------------------

def check_cpu(fw):
    e = EXPECTED
    driver, mode, epp = _read(e["cpu"].path), _read(e["pstate"].path), _read(e["epp"].path)
    found = " · ".join(x for x in (driver or "no cpufreq driver", mode and f"{mode} mode", epp and f"EPP {epp}") if x)
    if not fw:
        return Result("cpu", SKIP, f"not a Framework 13 · {found}", "")
    if driver != e["cpu"].value:
        return Result("cpu", _miss(e["cpu"].verified), f"{found} (expected {e['cpu'].value})",
                      "amd-pstate is the default on Fedora; check the kernel command line for amd_pstate=")
    if mode and mode != e["pstate"].value:
        return Result("cpu", WARN, f"{found} (expected {e['pstate'].value} mode)",
                      "remove amd_pstate=passive/guided from the kernel command line")
    if not epp:
        return Result("cpu", WARN, f"{found}, no energy preference file", "")
    return Result("cpu", OK, found, "")


def _drivers(pattern):
    """{device dir name: driver name} for a */device/driver glob."""
    out = {}
    for link in _glob(pattern):
        dev = link.split(os.sep)[-3]
        out[dev] = os.path.basename(os.path.realpath(link))
    return out


def check_gpu(fw):
    e = EXPECTED
    drivers = sorted(set(_drivers(e["gpu"].path).values()))
    bl = [os.path.basename(p) for p in _glob(e["backlight"].path)]
    errors = [line for line in _driver_errors("amdgpu") if re.search(r"firmware|fail|error|timeout|hang", line, re.I)]
    found = ", ".join(drivers) or "no GPU driver"
    if not fw:
        return Result("gpu", SKIP, f"not a Framework 13 · {found}", "")
    if e["gpu"].value not in drivers:
        return Result("gpu", _miss(e["gpu"].verified), f"{found} (expected {e['gpu'].value})",
                      "check amd-gpu-firmware is installed: rpm -q amd-gpu-firmware")
    if errors:
        return Result("gpu", WARN, f"amdgpu · {len(errors)} error(s) this boot: {errors[-1][:120]}",
                      "journalctl -k -b -p err -g amdgpu")
    if not bl:
        return Result("gpu", _miss(e["backlight"].verified), "amdgpu, but no amdgpu_bl* backlight", "")
    return Result("gpu", OK, f"amdgpu · backlight {bl[0]} · no errors this boot", "")


def check_wifi(fw):
    e = EXPECTED
    wireless = {os.path.basename(os.path.dirname(p)) for p in _glob("/sys/class/net/*/wireless")}
    drivers = {dev: drv for dev, drv in _drivers(e["wifi"].path).items() if dev in wireless}
    found = ", ".join(f"{dev} ({drv})" for dev, drv in sorted(drivers.items())) or "no Wi-Fi device"
    if not fw:
        return Result("wifi", SKIP, f"not a Framework 13 · {found}", "")
    if not drivers:
        return Result("wifi", FAIL, "no Wi-Fi device", "rpm -q mt7xxx-firmware; journalctl -k -b -g mt7925")
    if e["wifi"].value not in drivers.values():
        return Result("wifi", WARN, f"{found} (expected the MT7925, {e['wifi'].value}); a swapped card?", "")
    errors = _driver_errors("mt7925")
    if errors:
        return Result("wifi", WARN, f"{found} · {len(errors)} error(s) this boot: {errors[-1][:120]}",
                      "journalctl -k -b -p err -g mt7925")
    return Result("wifi", OK, f"{found} · no errors this boot", "")


def check_bluetooth(fw):
    from . import bt
    adapter, _devices = bt.state()
    found = "no adapter" if not adapter else f"{adapter['alias'] or adapter['address']} · " \
                                               f"{'on' if adapter['powered'] else 'off'}"
    if not fw:
        return Result("bluetooth", SKIP, f"not a Framework 13 · {found}", "")
    if not adapter:
        return Result("bluetooth", FAIL, "no adapter (or bluetoothd isn't running)", "systemctl status bluetooth")
    if not adapter["powered"]:
        return Result("bluetooth", WARN, f"{found} (radio switched off)", "turn it on from the bar's Bluetooth menu")
    return Result("bluetooth", OK, found, "")


def _battery_facts(b):
    cap = b.get("Capacity")
    cycles = b.get("ChargeCycles", -1)
    if cycles is None or cycles < 0:
        native = b.get("NativePath", "")
        raw = _read(f"/sys/class/power_supply/{native}/cycle_count") if native else ""
        cycles = int(raw) if raw.isdigit() and int(raw) > 0 else None
    return cap, cycles


def check_battery(fw):
    e = EXPECTED
    b = power.battery()
    if not fw:
        if not b:
            return Result("battery", SKIP, "not a Framework 13 · no battery", "")
        cap, _c = _battery_facts(b)
        return Result("battery", SKIP, f"not a Framework 13 · {cap:.0f} % of design", "")
    if not b:
        return Result("battery", FAIL, "no battery seen by UPower", "systemctl status upower")
    cap, cycles = _battery_facts(b)
    parts = [f"{cap:.0f} % of design capacity"] + ([f"{cycles} cycles"] if cycles else [])
    limit = _glob(e["charge"].path)
    if limit:
        on = b.get("ChargeThresholdEnabled")
        try:
            with open(limit[0]) as f:
                end = f.read().strip()
        except OSError:
            end = "?"
        parts.append(f"charge limit {end} % ({'on' if on else 'off'})")
    if cap < e["battery"].value:
        return Result("battery", WARN, " · ".join(parts), "the battery has worn; Framework sells replacements")
    if not limit:
        return Result("battery", _miss(e["charge"].verified), " · ".join(parts + ["no charge limit control"]),
                      "needs the cros_charge-control kernel module (kernel 6.12+): lsmod | grep cros_charge")
    return Result("battery", OK, " · ".join(parts), "")


_fw_updates = None


def firmware_updates():
    global _fw_updates
    if _fw_updates is None:
        _fw_updates = system.firmware_updates()
    return _fw_updates


def check_firmware(fw):
    bios = _read("/sys/class/dmi/id/bios_version") or "?"
    if not fw:
        return Result("firmware", SKIP, f"not a Framework 13 · BIOS {bios}", "")
    if not shutil.which("fwupdmgr"):
        return Result("firmware", WARN, f"BIOS {bios} · fwupd isn't installed", "")
    ups, msg = firmware_updates()
    if ups:
        names = ", ".join(f"{u['device']} {u['current']} → {u['new']}" for u in ups)
        return Result("firmware", WARN, f"BIOS {bios} · updates: {names}", "Settings → System → Firmware")
    return Result("firmware", OK, f"BIOS {bios} · {msg or 'no updates'}", "")


def check_fingerprint(fw):
    n = setup.fingerprints()
    found = "no reader" if n is None else f"{n} finger(s) enrolled"
    if not fw:
        return Result("fingerprint", SKIP, f"not a Framework 13 · {found}", "")
    if n is None:
        return Result("fingerprint", FAIL, "fprintd sees no reader", "rpm -q fprintd libfprint; lsusb | grep -i goodix")
    if n == 0:
        return Result("fingerprint", WARN, "reader found, no finger enrolled", "fprintd-enroll")
    return Result("fingerprint", OK, found, "")


def _sensor_proxy():
    """HasAmbientLight, or None when iio-sensor-proxy isn't running."""
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        res = bus.call_sync("net.hadess.SensorProxy", "/net/hadess/SensorProxy", "org.freedesktop.DBus.Properties",
                            "Get", GLib.Variant("(ss)", ("net.hadess.SensorProxy", "HasAmbientLight")),
                            GLib.VariantType("(v)"), Gio.DBusCallFlags.NO_AUTO_START, 3000, None)
        return bool(res.unpack()[0])
    except GLib.Error:
        return None


def check_light(fw):
    has = _sensor_proxy()
    found = {None: "iio-sensor-proxy isn't running", True: "ambient light sensor found",
             False: "no ambient light sensor"}[has]
    if not fw:
        return Result("light", SKIP, f"not a Framework 13 · {found}", "")
    if has is None:
        return Result("light", WARN, found, "systemctl status iio-sensor-proxy")
    if not has:
        return Result("light", _miss(EXPECTED["light"].verified), found, "journalctl -b -u iio-sensor-proxy")
    return Result("light", OK, found, "")


def check_suspend(fw):
    modes = _read(EXPECTED["sleep"].path)
    active = (re.search(r"\[(\w+)\]", modes) or [None, modes or "?"])[1]
    ok_n, fail_n = _read("/sys/power/suspend_stats/success"), _read("/sys/power/suspend_stats/fail")
    _rc, last, _e = _run("journalctl", "-k", "-b", "-q", "--no-pager", "-o", "short-iso", "-n", "1",
                         "-g", "PM: suspend exit", timeout=20)
    parts = [active]
    if ok_n.isdigit():
        parts.append(f"{ok_n} suspends this boot")
    if last.strip():
        parts.append(f"last resume {last.split()[0][:16].replace('T', ' ')}")
    found = " · ".join(parts)
    if not fw:
        return Result("suspend", SKIP, f"not a Framework 13 · {found}", "")
    if active != EXPECTED["sleep"].value:
        return Result("suspend", _miss(EXPECTED["sleep"].verified), f"{found} (expected s2idle)",
                      "remove mem_sleep_default= from the kernel command line")
    if fail_n.isdigit() and int(fail_n):
        dev = _read("/sys/power/suspend_stats/last_failed_dev")
        return Result("suspend", WARN, f"{found} · {fail_n} failed" + (f" (last: {dev})" if dev else ""),
                      "journalctl -k -b -g 'PM:'")
    return Result("suspend", OK, found, "")


def check_power(fw):
    names, active = power.profiles()
    t = power.tuning()
    parts = [f"{active} ({', '.join(names)})" if names else "no power-profiles service"]
    if t.get("platform_profile"):
        parts.append(f"platform {t['platform_profile']}")
    if t.get("tuned"):
        parts.append(f"tuned {t['tuned']}")
    if "abm" in t:
        parts.append(f"ABM {t['abm']}")
    found = " · ".join(parts)
    if not fw:
        return Result("power", SKIP, f"not a Framework 13 · {found}", "")
    if not names:
        return Result("power", WARN, found, "systemctl status tuned-ppd power-profiles-daemon")
    choices = _read(EXPECTED["platform"].path).split()
    missing = [c for c in EXPECTED["platform"].value.split() if c not in choices]
    if missing:
        return Result("power", _miss(EXPECTED["platform"].verified),
                      f"{found} · platform choices: {' '.join(choices) or 'none'}", "")
    return Result("power", OK, found, "")


def check_vaapi(fw):
    if not fw:
        return Result("vaapi", SKIP, "not a Framework 13", "")
    return Result("vaapi", MANUAL, "check by hand: vainfo should list H.264/HEVC/AV1 on radeonsi",
                  "distrobox create -n va -i fedora:44 && distrobox enter va -- "
                  "sh -c 'sudo dnf -y install libva-utils && vainfo'")


HARDWARE = [check_cpu, check_gpu, check_wifi, check_bluetooth, check_battery, check_firmware, check_fingerprint,
            check_light, check_suspend, check_power, check_vaapi]


def hardware():
    fw = is_framework()
    out = []
    for check in HARDWARE:
        try:
            out.append(check(fw))
        except Exception as e:  # noqa: BLE001 — one broken check must not hide the others
            out.append(Result(check.__name__[6:], WARN, f"check failed: {e}", ""))
    out += [Result(i, MANUAL if fw else SKIP, text, "") for i, text in MANUAL_STEPS]
    return out


# --- daily group -------------------------------------------------------------------------------------------

def check_units():
    failed = []
    for scope in ([], ["--user"]):
        _rc, out, _e = _run("systemctl", *scope, "--failed", "--plain", "--no-legend", "--no-pager", timeout=20)
        failed += [line.split()[0] + (" (user)" if scope else "") for line in out.splitlines() if line.split()]
    if failed:
        return Result("units", WARN, f"{len(failed)} failed: {', '.join(failed)}",
                      "systemctl status <unit> (add --user for user ones)")
    return Result("units", OK, "no failed services", "")


def check_disk():
    seen, rows, status = set(), [], OK
    for mount in ("/", os.path.expanduser("~")):
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        dev = (st.f_frsize, st.f_blocks, st.f_files)  # one filesystem: btrfs subvolumes (/ and /home) differ in st_dev
        if dev in seen:
            continue
        seen.add(dev)
        free = st.f_bavail * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        pct = 100 * used / max(1, used + free)
        rows.append(f"{'/' if mount == '/' else '~'} {pct:.0f} % used, {free / GIB:.0f} GiB free")
        if free < 2 * GIB or pct > 98:
            status = FAIL
        elif (free < 10 * GIB or pct > 90) and status != FAIL:
            status = WARN
    return Result("disk", status, " · ".join(rows) or "couldn't read",
                  "" if status == OK else "du -xh --max-depth=1 ~ | sort -h | tail")


def _backup_journal(since_days=35):
    """(time, "done"/"failed"/…) of the newest finished restic-backup run in the user journal, else (0, "").
    systemd's ExecMainExitTimestamp only covers the current user manager; the journal survives logout and reboot."""
    _rc, out, _e = _run("journalctl", "--user", "-u", setup.UNIT, "JOB_TYPE=start", "--since", f"-{since_days}d",
                        "-r", "-n", "20", "-q", "--no-pager", "-o", "json", "--output-fields=JOB_RESULT", timeout=30)
    for line in out.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("JOB_RESULT"):  # the "Starting …" line has no result
            return int(e.get("__REALTIME_TIMESTAMP", "0")) // 1_000_000, e["JOB_RESULT"]
    return 0, ""


def check_backup(now):
    if not os.path.exists(setup.T_RESTIC_ENV):
        return Result("backup", SKIP, "restic isn't set up", "Settings → My Framework → Backup")
    st = setup.backup_state()
    if st["running"]:
        return Result("backup", OK, "a backup is running now", "")
    if not st["last"]:  # not run in this user manager (login/reboot): ask the journal
        last, res = _backup_journal()
        st.update(last=last, result="success" if res == "done" else res, status="")
    last = st["last"]
    when = f"last run {_ago(last, now)}" if last else "no backup in the last 35 days"
    if not st["timer"]:
        return Result("backup", WARN, f"the daily backup is off · {when}", "Settings → My Framework → Backup")
    if last and st["result"] not in ("", "success"):
        why = f"{st['result']}, exit {st['status']}" if st["status"] else st["result"]
        return Result("backup", FAIL, f"the last backup failed ({why}) · {when}",
                      "journalctl --user -u restic-backup -n 50")
    if not last:
        return Result("backup", WARN, when, "Settings → My Framework → Backup → Back up now")
    if now - last > 3 * 86400:
        return Result("backup", WARN, when, "journalctl --user -u restic-backup.timer")
    return Result("backup", OK, when, "")


def root_facts(now=None):
    """The fw-health-root JSON when it's fresh (≤ 3 h), else None."""
    try:
        with open(_p(ROOT_JSON)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    gen = data.get("generated") if isinstance(data, dict) else None
    if not isinstance(gen, (int, float)) or (now or time.time()) - gen > ROOT_JSON_MAX_AGE:
        return None
    return data


def _timeshift_journal(since_days=35):
    """(time of the newest "Snapshot saved successfully", recent error lines) from Timeshift's syslog lines."""
    _rc, out, _e = _run("journalctl", "-t", "timeshift", "--since", f"-{since_days}d", "-q", "--no-pager",
                        "-o", "json", "--output-fields=MESSAGE", timeout=30)
    newest, errors = 0, []
    for line in out.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        msg = e.get("MESSAGE") if isinstance(e.get("MESSAGE"), str) else ""
        ts = int(e.get("__REALTIME_TIMESTAMP", 0)) // 1_000_000
        if "Snapshot saved successfully" in msg:
            newest, errors = max(newest, ts), []  # errors before a good snapshot no longer matter
        elif (msg.startswith("E: ") or re.search(r"\berror\b|failed", msg, re.I)) and "notification" not in msg:
            errors.append(msg)
    return newest, errors


def _timeshift_max_age():
    """Seconds a snapshot may be old under the active schedule (twice the shortest interval; boot only → 8 days)."""
    try:
        with open(_p("/etc/timeshift/timeshift.json")) as f:
            conf = json.load(f)
    except (OSError, ValueError):
        return 8 * 86400
    on = {k[9:] for k, v in conf.items() if k.startswith("schedule_") and str(v).lower() == "true"}
    for level, age in (("hourly", 86400), ("daily", 2 * 86400), ("weekly", 8 * 86400), ("monthly", 32 * 86400)):
        if level in on:
            return age
    return 8 * 86400


def check_timeshift(now):
    state = setup.timeshift_state()
    if not state:
        return Result("timeshift", SKIP, "Timeshift isn't set up", "sudo fw-timeshift-setup")
    newest_j, errors = _timeshift_journal()
    facts = root_facts(now)
    ts = (facts or {}).get("timeshift") or {}
    count = ts.get("snapshots") if ts.get("state") == "ok" else None
    newest = max(newest_j, (ts.get("newest") or 0) if count is not None else 0)
    parts = [state]
    if count is not None:
        parts.append(f"{count} snapshots")
    parts.append(f"newest {_ago(newest, now)}" if newest else "no snapshot seen")
    summary = " · ".join(parts)
    if "not scheduled" in state:
        return Result("timeshift", WARN, summary, "Timeshift → Schedule, and: systemctl is-enabled crond")
    if errors:
        return Result("timeshift", WARN, f"{summary} · {errors[-1][:120]}", "journalctl -t timeshift -p warning")
    stale = not newest or now - newest > _timeshift_max_age()
    if stale and _uptime() > 3600:  # right after boot, Timeshift's own boot/hourly job may not have run yet
        return Result("timeshift", WARN, summary, "journalctl -t timeshift -t CROND -n 40")
    return Result("timeshift", OK, summary, "")


def check_restart():
    if not shutil.which("dnf5"):
        return Result("restart", SKIP, "dnf5 isn't installed", "")
    # Repos off: the check only needs the rpmdb and the boot time, never metadata (no network, no cache needed).
    rc, out, err = _run("dnf5", "-q", "--disablerepo=*", "needs-restarting", "-r", timeout=90)
    text = (out + err).lower()
    if rc == 0:
        return Result("restart", OK, "no reboot needed", "")
    if rc == 1 and "reboot is required" in text:
        return Result("restart", WARN, "a reboot is recommended (kernel or core libraries were updated)",
                      "reboot when convenient")
    if "unknown" in text or "not found" in text:
        return Result("restart", SKIP, "dnf5 needs-restarting isn't available", "rpm -q dnf5-plugins")
    lines = [s.strip() for s in (err or out).splitlines() if s.strip()]
    return Result("restart", WARN, "couldn't check: " + (lines[-1][:120] if lines else f"exit {rc}"),
                  "dnf5 needs-restarting -r")


def check_updates():
    if not shutil.which("fwupdmgr"):
        return Result("updates", SKIP, "fwupd isn't installed", "")
    ups, msg = firmware_updates()
    if ups:
        return Result("updates", WARN, f"{len(ups)} firmware update(s): " +
                      ", ".join(f"{u['device']} → {u['new']}" for u in ups), "Settings → System → Firmware")
    return Result("updates", OK, msg or "no firmware updates", "")


def check_battery_health():
    b = power.battery()
    if not b:
        return Result("battery-health", SKIP, "no battery", "")
    cap, cycles = _battery_facts(b)
    text = f"{cap:.0f} % of design capacity" + (f" · {cycles} cycles" if cycles else "")
    if cap < EXPECTED["battery"].value:
        return Result("battery-health", WARN, text, "the battery has worn; consider a replacement")
    return Result("battery-health", OK, text, "")


def _udisks_objects():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
    res = bus.call_sync("org.freedesktop.UDisks2", "/org/freedesktop/UDisks2", "org.freedesktop.DBus.ObjectManager",
                        "GetManagedObjects", None, GLib.VariantType("(a{oa{sa{sv}}})"), Gio.DBusCallFlags.NONE,
                        10000, None)

    def smart(path):
        try:
            r = bus.call_sync("org.freedesktop.UDisks2", path, "org.freedesktop.UDisks2.NVMe.Controller",
                              "SmartGetAttributes", GLib.Variant("(a{sv})", ({},)), GLib.VariantType("(a{sv})"),
                              Gio.DBusCallFlags.NONE, 10000, None)
            return r.unpack()[0]
        except GLib.Error:
            return {}
    return res.unpack()[0], smart


def check_nvme():
    try:
        objs, smart = _udisks_objects()
    except Exception as e:  # noqa: BLE001 — GLib.Error / no udisks2
        return Result("nvme", SKIP, f"udisks2 not reachable ({getattr(e, 'message', e)})", "rpm -q udisks2")
    rows, status, fixes = [], OK, ""
    for path, ifaces in sorted(objs.items()):
        drive = ifaces.get("org.freedesktop.UDisks2.Drive", {})
        name = drive.get("Model") or os.path.basename(path)
        nvme = ifaces.get("org.freedesktop.UDisks2.NVMe.Controller")
        ata = ifaces.get("org.freedesktop.UDisks2.Drive.Ata")
        if nvme is not None:
            a = smart(path)
            bad = list(nvme.get("SmartCriticalWarning") or [])
            if a and a.get("avail_spare", 100) <= a.get("spare_thresh", 0):
                bad.append("spare below threshold")
            used = a.get("percent_used")
            parts = [name] + ([f"{used} % worn"] if used is not None else [])
            temp = nvme.get("SmartTemperature") or 0
            if temp:
                parts.append(f"{temp - 273} °C")
            if bad:
                status, fixes = FAIL, "back up now; sudo nvme smart-log /dev/nvme0"
                parts.append("critical: " + ", ".join(bad))
            elif (used or 0) >= 90 or a.get("media_errors", 0) > 0:
                status = WARN if status == OK else status
                fixes = fixes or "back up regularly; the SSD is near the end of its rated life"
                if a.get("media_errors", 0):
                    parts.append(f"{a['media_errors']} media errors")
            rows.append(" ".join(parts[:1]) + (" · " + " · ".join(parts[1:]) if parts[1:] else ""))
        elif ata is not None and ata.get("SmartEnabled"):
            failing = ata.get("SmartFailing")
            rows.append(f"{name} · {'SMART says failing' if failing else 'SMART ok'}")
            if failing:
                status, fixes = FAIL, "back up now"
    if not rows:
        return Result("nvme", SKIP, "no NVMe/SATA drive with SMART data", "")
    return Result("nvme", status, " | ".join(rows), fixes)


def check_coredumps(since):
    _rc, out, _e = _run("coredumpctl", "list", "--no-pager", "--json=short", "--since",
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since)), timeout=30)
    try:
        dumps = json.loads(out) if out.strip() else []
    except ValueError:
        dumps = []
    me = os.getuid()
    # Same filter as fw-crash-watch: this user and root; the login screen's short-lived users (≥ 60000) are noise.
    dumps = [d for d in dumps if isinstance(d, dict) and (d.get("uid") in (0, me) or (d.get("uid") or 0) < 1000)]
    if not dumps:
        return Result("coredumps", OK, "no new crashes", "")
    names = sorted({os.path.basename(d.get("exe") or "?") for d in dumps})
    return Result("coredumps", WARN, f"{len(dumps)} new crash(es): {', '.join(names)}", "coredumpctl list; fw-jarvis crash")


def journal_errors():
    _rc, out, _e = _run("journalctl", "-b", "-p", "err", "-q", "--no-pager", "-o", "cat", timeout=30)
    return len(out.splitlines())


def daily(since=None, now=None):
    now = now or time.time()
    since = since or now - 86400
    checks = [check_units, check_disk, lambda: check_backup(now), lambda: check_timeshift(now), check_restart,
              check_updates, check_battery_health, check_nvme, lambda: check_coredumps(since)]
    ids = ["units", "disk", "backup", "timeshift", "restart", "updates", "battery-health", "nvme", "coredumps"]
    out = []
    for cid, check in zip(ids, checks):
        try:
            out.append(check())
        except Exception as e:  # noqa: BLE001
            out.append(Result(cid, WARN, f"check failed: {e}", ""))
    n = journal_errors()
    out.append(Result("journal", INFO, f"{n} error lines this boot (journalctl -b -p err)", ""))
    return out


# --- output ------------------------------------------------------------------------------------------------

def title(cid):
    return TITLES.get(cid, "To do by hand" if cid.startswith("m-") else cid)


def attention(results):
    return [r for r in results if r.status in ATTENTION]


def as_dicts(results):
    return [{"id": r.id, "title": title(r.id), "status": r.status, "summary": r.summary, "fix": r.fix}
            for r in results]


def text(results, color=False):
    marks = {OK: ("OK", "32"), WARN: ("WARN", "33"), FAIL: ("FAIL", "31"), SKIP: ("SKIP", "90"),
             MANUAL: ("TODO", "36"), INFO: ("INFO", "90")}
    lines = []
    for r in results:
        word, code = marks.get(r.status, (r.status, "0"))
        tag = f"\033[{code}m{word:<5}\033[0m" if color else f"{word:<5}"
        lines.append(f"{tag} {title(r.id):<17} {r.summary}")
        if r.fix and r.status in (WARN, FAIL, MANUAL):
            lines.append(f"{'':<5} {'':<17} → {r.fix}")
    return "\n".join(lines)


def markdown(results, heading):
    _rc, kernel, _e = _run("uname", "-r", timeout=5)
    parts = [f"# {heading}", f"{time.strftime('%Y-%m-%d %H:%M')} · {system.os_name()} · kernel {kernel.strip()}"]
    bad = attention(results)
    if bad:
        parts.append("## Needs attention")
        parts.append("\n".join(f"- **{title(r.id)}** ({r.status}): {r.summary}" + (f"  \n  Fix: {r.fix}"
                                                                                   if r.fix else "") for r in bad))
    else:
        parts.append("Nothing needs attention.")
    parts.append("## All checks")
    parts.append("\n".join(f"- {r.status} · {title(r.id)}: {r.summary}" for r in results))
    return "\n\n".join(parts) + "\n"

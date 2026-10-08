"""Auto-brightness: ambient light sensor (iio-sensor-proxy, net.hadess.SensorProxy on the system bus via Gio)
and the pure logic behind the fw-autobrightness daemon (log-lux curve, smoothing, hysteresis, manual-change test).

Off by default: Settings → Display / the display panel turn store key `autobrightness` on and start
fw-autobrightness.service (Hyprland only, see the unit's ExecCondition). The daemon writes its pid and a small
state file in $XDG_RUNTIME_DIR; `fw-autobrightness pause|resume|status` signal it by that pid.
No gi import at module level: the hypridle hooks (`pause`/`resume`) must start fast.
"""
import glob
import json
import math
import os
import signal
import subprocess

from . import store

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNTIME, "fw-autobrightness.pid")
STATE = os.path.join(RUNTIME, "fw-autobrightness.json")
UNIT = "fw-autobrightness.service"
KEY = "autobrightness"

BUS = "net.hadess.SensorProxy"
OBJ = "/net/hadess/SensorProxy"

# Curve (tuned on the Framework 13; the Dell only proves the plumbing): brightness rises linearly with log10(lux)
# from MIN_PCT at LUX_LOW to MAX_PCT at LUX_HIGH, clamped outside.
LUX_LOW, LUX_HIGH = 5.0, 2000.0
MIN_PCT, MAX_PCT = 8, 100
ALPHA = 0.25        # moving average (exponential) of log-lux per sample, one sample a second (~4 s to settle)
HYSTERESIS = 5      # percentage points: smaller differences are left alone (no flicker around a threshold)
WINDOW = 3          # median of the last WINDOW readings goes into the average: one odd reading (a flash) is dropped
TOLERANCE = 2       # points: a reading this far from what we set (after SETTLE) was changed by someone else
SETTLE = 1.0        # seconds after our last write before a reading counts (brightnessctl runs async)
RAMP_MS = 40        # one step every RAMP_MS ...
RAMP_STEPS = 15     # ... at most this many steps per change (~0.6 s)


# --- pure functions (unit-tested, no I/O) ----------------------------------------------------------------
def curve(lux):
    """Lux → brightness percent."""
    lo, hi = math.log10(LUX_LOW + 1), math.log10(LUX_HIGH + 1)
    f = (math.log10(max(0.0, lux) + 1) - lo) / (hi - lo)
    return round(MIN_PCT + (MAX_PCT - MIN_PCT) * min(1.0, max(0.0, f)))


def median(readings):
    """Median of the recent raw readings (the caller keeps the last WINDOW)."""
    xs = sorted(readings)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def smooth(avg, lux, alpha=ALPHA):
    """Exponential moving average in the log domain (a lamp switched on is a ratio, not a difference).
    avg is None for the first sample after start or a pause: take the reading as it is."""
    v = math.log10(max(0.0, lux) + 1)
    return v if avg is None else avg + alpha * (v - avg)


def unsmooth(avg):
    """Averaged log value → lux, for curve()."""
    return 10 ** avg - 1


def target(current, wanted, hysteresis=HYSTERESIS):
    """The brightness to move to, or None to stay. The extremes are always reachable, so a dark room gets
    MIN_PCT even when it's closer than the hysteresis."""
    if wanted == current:
        return None
    if abs(wanted - current) >= hysteresis or wanted in (MIN_PCT, MAX_PCT):
        return wanted
    return None


def ramp(start, end, steps=RAMP_STEPS):
    """Intermediate values from start (exclusive) to end (inclusive), at most `steps` of them."""
    n = min(steps, abs(end - start))
    return [round(start + (end - start) * i / n) for i in range(1, n + 1)] if n else []


def manual(expected, actual, since_write, tolerance=TOLERANCE, settle=SETTLE):
    """True when the backlight no longer shows what we set: a brightness key, a slider or another tool moved it."""
    if expected is None or actual is None or since_write < settle:
        return False
    return abs(actual - expected) > tolerance


# --- backlight / lid (sysfs, read only) --------------------------------------------------------------------
def backlight():
    """First backlight device, the same one brightnessctl picks by default."""
    devs = sorted(glob.glob("/sys/class/backlight/*"))
    return devs[0] if devs else None


def read_pct(dev=None):
    """Current brightness in percent (linear, as `brightnessctl set N%` writes it), or None."""
    dev = dev or backlight()
    try:
        cur = int(open(os.path.join(dev, "brightness")).read())
        top = int(open(os.path.join(dev, "max_brightness")).read())
        return round(cur * 100 / top) if top > 0 else None
    except (OSError, ValueError, TypeError):
        return None


def lid_closed():
    for path in glob.glob("/proc/acpi/button/lid/*/state"):
        try:
            if "closed" in open(path).read():
                return True
        except OSError:
            pass
    return False


# --- sensor (Gio, imported lazily) ---------------------------------------------------------------------------
def _gio():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
    return Gio, GLib


def sensor_props():
    """{'HasAmbientLight': bool, 'LightLevel': float, 'LightLevelUnit': str} or {} (no proxy running)."""
    Gio, GLib = _gio()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        res = bus.call_sync(BUS, OBJ, "org.freedesktop.DBus.Properties", "GetAll", GLib.Variant("(s)", (BUS,)),
                            GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NO_AUTO_START, 2000, None)
        return res.unpack()[0]
    except GLib.Error:
        return {}


def has_sensor():
    return bool(sensor_props().get("HasAmbientLight"))


def available():
    """Both a light sensor and a backlight: the switch is shown only then."""
    return backlight() is not None and has_sensor()


# --- daemon control ----------------------------------------------------------------------------------------
def enabled():
    return bool(store.get(KEY))


def hyprland():
    """Running inside Hyprland (the user manager's env is set by uwsm; a stale one has no socket dir)."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    return bool(sig) and os.path.isdir(os.path.join(RUNTIME, "hypr", sig))


def set_enabled(on):
    """Settings switch: remember the choice, then start/stop the user unit (async; GNOME never gets here)."""
    store.set(KEY, bool(on))
    subprocess.Popen(["systemctl", "--user", "start" if on else "stop", UNIT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pid():
    """The running daemon's pid (pidfile checked against /proc), or None."""
    try:
        p = int(open(PIDFILE).read())
        with open(f"/proc/{p}/cmdline", "rb") as f:
            return p if b"fw-autobrightness" in f.read() else None
    except (OSError, ValueError):
        return None


def signal_daemon(sig):
    p = pid()
    if p is None:
        return False
    try:
        os.kill(p, sig)
        return True
    except OSError:
        return False


def pause():
    """Idle hook (dim / screen off): hold until resume(). Not a manual pause."""
    return signal_daemon(signal.SIGUSR1)


def resume():
    return signal_daemon(signal.SIGUSR2)


def state():
    """{'running': bool, 'holds': [...]} plus, while running, 'lux' and 'brightness'. Holds: 'idle' (hypridle dim /
    screen off), 'sleep', 'lid' (closed), 'manual' (someone changed the brightness: until the next wake or login)."""
    if pid() is None:
        return {"running": False, "holds": []}
    try:
        return {"running": True, "holds": [], **json.load(open(STATE))}
    except (OSError, ValueError):
        return {"running": True, "holds": []}


def write_state(data):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, STATE)

"""Framework: fan, keyboard backlight, fingerprint LED and read-only EC reports, over Framework's framework_tool
(install.sh, /usr/local/bin). The EC needs root, so changes run through pkexec (polkit asks) and reports open in a
terminal with sudo. Read without root: fan speed (cros_ec hwmon) and the keyboard backlight (LED class, set via
brightnessctl). The charge limit lives on the Power page (UPower). Flashing, key remapping, EC reboot and the
Laptop 12/16-only options are left out on purpose."""
import glob
import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .common import Page, label, launch  # noqa: E402
from .system import bg  # noqa: E402

TOOL = "framework_tool"
KBD_LED = "chromeos::kbd_backlight"
FAN_MODES = [("auto", "Automatic"), ("25", "25 %"), ("50", "50 %"), ("75", "75 %"), ("100", "100 % (full)")]
FP_LEVELS = [("auto", "Automatic"), ("high", "High"), ("medium", "Medium"), ("low", "Low"), ("ultra-low", "Ultra low")]
REPORTS = [("--versions", "Firmware versions", "BIOS, EC, USB-C controllers, cards, SSD"),
           ("--power", "Battery and charger", "charge state, cycle count, adapter"),
           ("--thermal", "Temperatures and fan", "every EC sensor"),
           ("--privacy", "Privacy switches", "camera and microphone kill switches"),
           ("--pdports", "USB-C ports", "what each port is supplying or drawing"),
           ("--inputdeck", "Input modules", "keyboard, touchpad and their connectors"),
           ("--intrusion", "Chassis opened", "how often the bottom cover was removed")]


def fan_hwmon():
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(os.path.join(d, "name")) as f:
                if f.read().strip() == "cros_ec" and os.path.exists(os.path.join(d, "fan1_input")):
                    return d
        except OSError:
            pass
    return None


def read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def kbd_path():
    p = f"/sys/class/leds/{KBD_LED}"
    return p if os.path.isdir(p) else None


def ec(*args):
    """Run framework_tool as root through polkit; returns (ok, message)."""
    r = subprocess.run(["pkexec", shutil.which(TOOL), *args], capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        return True, ""
    lines = (r.stderr or r.stdout).strip().splitlines()
    return False, lines[-1] if lines else "cancelled"


class FrameworkPage(Page):
    def __init__(self):
        super().__init__("Framework")
        self.hwmon = fan_hwmon()
        self.rpm = None
        self.status = None
        self.refresh()
        if self.hwmon:
            self.timer = GLib.timeout_add_seconds(2, self.tick)
            self.connect("destroy", lambda _w: GLib.source_remove(self.timer))

    def refresh(self):
        self.clear()
        if not shutil.which(TOOL):
            self.add_widget(label("framework_tool isn't installed (install.sh adds it on Framework laptops).",
                                  "dim", wrap=True))
            self.show_all()
            return
        self.status = label("", "dim", wrap=True)
        self.add_widget(self.status)

        self.heading("Fan")
        if self.hwmon:
            self.rpm = label("", "dim")
            self.row("Speed now", self.rpm)
            self.tick()
        self.row("Fan mode", self.combo(FAN_MODES, self.set_fan),
                 hint="A fixed speed lasts until you pick Automatic again, or the laptop restarts")

        kbd = kbd_path()
        if kbd:
            self.heading("Keyboard backlight")
            mx = read_int(os.path.join(kbd, "max_brightness")) or 100
            cur = read_int(os.path.join(kbd, "brightness")) or 0
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
            scale.set_value(round(cur * 100 / mx))
            scale.set_size_request(220, -1)
            scale.connect("value-changed", lambda s: subprocess.Popen(
                ["brightnessctl", "-q", "-d", KBD_LED, "set", f"{int(s.get_value())}%"]))
            self.row("Brightness", scale, hint="Fn+Space cycles it too")

        self.heading("Fingerprint reader")
        self.row("Power button LED", self.combo(FP_LEVELS, lambda v: self.run_ec("--fp-led-level", v)),
                 hint="Brightness of the light around the fingerprint reader")

        self.heading("Reports")
        for opt, title, hint in REPORTS:
            b = Gtk.Button(label="Show…")
            b.connect("clicked", lambda _b, o=opt: launch("fw-term", "--hold", "-e", "sudo", TOOL, o))
            self.row(title, b, hint=hint)
        self.add_widget(label("Reports open in a terminal and ask for your password (the EC needs root).",
                              "dim", wrap=True))
        self.show_all()

    @staticmethod
    def combo(items, on_pick):
        """A combo with no preselection: the EC's current setting can't be read without root."""
        c = Gtk.ComboBoxText()
        c.append("", "Choose…")
        for key, text in items:
            c.append(key, text)
        c.set_active_id("")
        c.connect("changed", lambda w: w.get_active_id() and on_pick(w.get_active_id()))
        return c

    def set_fan(self, mode):
        if mode == "auto":
            self.run_ec("--autofanctrl")
        else:
            self.run_ec("--fansetduty", mode)

    def run_ec(self, *args):
        self.status.set_text("Waiting for authorisation…")
        bg(ec, self.ec_done, *args, fail=lambda e: (False, str(e)))

    def ec_done(self, res):
        ok, msg = res
        self.status.set_text("Done" if ok else f"Not changed: {msg}")
        return False

    def tick(self):
        if self.rpm is None:
            return True
        rpm = read_int(os.path.join(self.hwmon, "fan1_input"))
        self.rpm.set_text("off" if rpm == 0 else f"{rpm} rpm" if rpm is not None else "unknown")
        return True


def build():
    return FrameworkPage()

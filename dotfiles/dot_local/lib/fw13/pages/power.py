"""Power: battery state, time left/to full, health, power profile, 80 % charge limit, screen & sleep timeouts."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import idle, power  # noqa: E402
from .common import Page, label  # noqa: E402


class PowerPage(Page):
    def __init__(self):
        super().__init__("Power")
        self.refresh()

    def refresh(self):
        self.clear()
        b = power.battery()
        if b:
            self.heading("Battery")
            pct, state = round(b.get("Percentage", 0)), b.get("State", 0)
            bar = Gtk.LevelBar.new_for_interval(0, 100)
            bar.set_value(pct)
            bar.set_size_request(220, 10)
            self.row(f"{power.STATES.get(state, 'Battery')} · {pct}%", bar)
            t = b.get("TimeToFull") if state == 1 else b.get("TimeToEmpty") if state in (2, 6) else 0
            if t:
                self.row(f"{power.duration(t)} {'until full' if state == 1 else 'left'}")
            rate = b.get("EnergyRate", 0)
            if rate > 0.1 and state in (1, 2, 6):
                self.row(f"{'Charging at' if state == 1 else 'Drawing'} {rate:.1f} W")
            if b.get("Capacity", 0) > 0:
                self.row(f"Health {b['Capacity']:.1f}%",
                         hint=f"{b.get('EnergyFull', 0):.1f} of {b.get('EnergyFullDesign', 0):.1f} Wh")
            tech = power.TECH.get(b.get("Technology"), "")
            self.row(f"{b.get('Vendor', '')} {b.get('Model', '')}".strip(), hint=tech or None)
            if b.get("ChargeThresholdSupported"):
                sw = Gtk.Switch()
                sw.set_active(bool(b.get("ChargeThresholdEnabled")))
                sw.connect("state-set", lambda _s, on: not power.set_charge_limit(on))
                self.row("Limit charging", sw,
                         hint=f"Stop at {b.get('ChargeEndThreshold', 80)}% and resume at "
                              f"{b.get('ChargeStartThreshold', 75)}% — better for battery lifespan")
        names, active = power.profiles()
        if names:
            self.heading("Power profile")
            group = None
            for name in names:
                rb = Gtk.RadioButton.new_with_label_from_widget(group, name.replace("-", " ").capitalize())
                group = group or rb
                rb.set_active(name == active)
                rb.connect("toggled", lambda r, n=name: r.get_active() and power.set_profile(n))
                self.add_widget(rb)
        self.heading("Screen & sleep")
        cur = idle.get()
        for key, text, hint in (("idle_dim", "Dim the screen after", "to 10 % brightness; any input restores it"),
                                ("idle_lock", "Lock after", "SUPER+L locks right away"),
                                ("idle_screen_off", "Turn the screen off after", None),
                                ("idle_suspend", "Suspend after", "the laptop also locks before sleeping")):
            combo = Gtk.ComboBoxText()
            choices = sorted(set(idle.CHOICES) | {cur[key]})
            for s in choices:
                combo.append(str(s), idle.label(s))
            combo.set_active_id(str(cur[key]))
            combo.connect("changed", lambda c, k=key: idle.write({k: int(c.get_active_id())}))
            self.row(text, combo, hint=hint)
        if not b and not names:
            self.add_widget(label("No battery or power profile service found.", "dim"))
        self.show_all()


def build():
    return PowerPage()

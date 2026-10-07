"""Input: touchpad (scrolling, tapping, typing guard, speed), keyboard repeat and layouts, input methods."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import hyprsettings as hs  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .appearance import HyprPage  # noqa: E402
from .common import launch  # noqa: E402


class InputPage(HyprPage):
    def __init__(self):
        super().__init__("Input")
        self.refresh()

    def refresh(self):
        self.clear()
        self.heading("Touchpad")
        self.switch("Natural scrolling", "input.touchpad.natural_scroll", hint="content follows your fingers")
        self.switch("Tap to click", "input.touchpad.tap_to_click")
        self.switch("Disable while typing", "input.touchpad.disable_while_typing")
        self.slider("Scroll speed", "input.touchpad.scroll_factor", 0.1, 2.0, 0.05, fmt="{:.2f}")
        self.slider("Pointer speed", "input.sensitivity", -1.0, 1.0, 0.05, fmt="{:+.2f}",
                    hint="touchpad and mice; 0 = unchanged")
        self.heading("Keyboard")
        self.slider("Repeat rate", "input.repeat_rate", 10, 80, 1, hint="characters per second")
        self.slider("Repeat delay", "input.repeat_delay", 150, 800, 10, fmt="{:.0f} ms",
                    hint="before a held key repeats")
        box = Gtk.Box(spacing=8)
        self.layout = Gtk.Entry(text=hs.get("input.kb_layout"), width_chars=14)
        self.layout.connect("activate", lambda _e: self.apply_layout())
        box.pack_start(self.layout, False, False, 0)
        box.pack_start(button("Apply", self.apply_layout), False, False, 0)
        self.row("Layouts", box, hint="XKB names, comma-separated: us or us,de")
        ime = button("Input methods (Khmer)…", lambda: launch("fcitx5-configtool"))
        ime.set_halign(Gtk.Align.START)
        self.row("Typing other scripts", ime, hint="fcitx5")
        self.show_all()

    def apply_layout(self):
        value, err = hs.check_layout(self.layout.get_text())
        if err:
            self.show_status(err)
            return
        self.layout.set_text(value)
        self.change("input.kb_layout", value, delay=0)


def build():
    return InputPage()

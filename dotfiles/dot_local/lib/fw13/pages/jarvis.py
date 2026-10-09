"""Jarvis: which Claude model and effort the panel (SUPER+A) and fw-jarvis sessions use."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import jarvis, store  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page  # noqa: E402


class JarvisPage(Page):
    def __init__(self):
        super().__init__("Jarvis")
        self.status = label("", "dim", wrap=True)
        self.heading("Claude")
        self.model = Gtk.ComboBoxText.new_with_entry()
        for key, text in jarvis.MODELS:
            self.model.append(key, text)
        entry = self.model.get_child()
        entry.set_width_chars(22)
        entry.set_text(jarvis.model())
        entry.connect("activate", lambda _e: self.apply_model())
        self.model.connect("changed", self.picked)
        box = Gtk.Box(spacing=8)
        box.pack_start(self.model, False, False, 0)
        box.pack_start(button("Apply", self.apply_model), False, False, 0)
        self.row("Model", box, hint="Pick one or type a full name such as claude-opus-5-5; empty = Claude Code's "
                 "default. An alias follows the newest model of that kind")
        eff = Gtk.ComboBoxText()
        for key, text in jarvis.EFFORTS:
            eff.append(key, text)
        eff.set_active_id(jarvis.effort())
        eff.connect("changed", lambda c: self.save("jarvis_effort", c.get_active_id() or ""))
        self.row("Effort", eff, hint="How hard Claude thinks: lower is faster and uses less of your plan limits")
        self.add_widget(self.status)
        self.add_widget(label("Used for the panel's answers, Continue in terminal and Work on repo, from the next "
                              "question on. OpenCode sessions use the model chosen in the OpenCode panel.",
                              "dim", wrap=True))
        self.show_all()

    def picked(self, combo):
        key = combo.get_active_id()  # a list pick (typing leaves it None until Apply)
        if key is not None:
            self.save("jarvis_model", key)
            combo.get_child().set_text(key)

    def apply_model(self):
        value, err = jarvis.check_model(self.model.get_child().get_text())
        if err:
            self.status.set_text(err)
            return
        self.save("jarvis_model", value)

    def save(self, key, value):
        store.set(key, value)
        self.status.set_text("Saved")


def build():
    return JarvisPage()

"""Jarvis: which Claude model and effort the panel (SUPER+A) and fw-jarvis sessions use."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import jarvis, store  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page, launch  # noqa: E402


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
        self.heading("When Claude is unreachable")
        sw = Gtk.Switch(active=jarvis.fallback_on())
        sw.connect("notify::active", lambda w, _p: self.save("jarvis_fallback", w.get_active()))
        others = [lbl.removeprefix("OpenCode · ") for lbl, t in jarvis.agents() if t != "claude"]
        self.row("Answer with an Ollama server", sw,
                 hint=(f"Without internet, or when Claude can't be reached, the panel answers with {others[0]} "
                       "(the first OpenCode server that answers)") if others else
                 "No Ollama server with a model yet: add one in the OpenCode panel (the >_ icon)")
        self.heading("Memory")
        self.add_widget(label("Notes Jarvis reads before every answer. Jarvis proposes them (Save / Skip in the "
                              "panel); say \"remember …\" to add one.", "dim", wrap=True))
        self.mem = self.add_widget(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8))
        self.add_widget(button("Open file", self.open_memory)).set_halign(Gtk.Align.START)
        self.fill_memory()
        self.show_all()

    def refresh(self):  # notes saved in the panel since the page was built
        self.fill_memory()

    def fill_memory(self):
        for c in self.mem.get_children():
            self.mem.remove(c)
        lines = jarvis.notes()
        if not lines:
            self.mem.pack_start(label("No notes yet", "dim", xalign=0), False, False, 0)
        for line in lines:
            r = Gtk.Box(spacing=12)
            r.get_style_context().add_class("item")
            r.pack_start(label(line[2:], wrap=True, xalign=0), True, True, 0)
            r.pack_end(button("Remove", lambda line=line: self.forget(line)), False, False, 0)
            self.mem.pack_start(r, False, False, 0)
        self.mem.show_all()

    def forget(self, line):
        jarvis.forget(line)
        self.fill_memory()

    def open_memory(self):
        jarvis.ensure_memory()
        launch("xdg-open", jarvis.MEMORY)

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

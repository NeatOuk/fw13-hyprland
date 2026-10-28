"""Jarvis: which Claude model and effort the panel (SUPER+A) and fw-jarvis sessions use, the Ollama fallback, the
laptop's own Ollama models (fw13.ollama) and Jarvis's memory."""
import shutil

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import agents, jarvis, ollama, store  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page, bg, launch  # noqa: E402


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
                              "question on. Coding-agent sessions (OpenCode or Pi) use the model chosen in Settings → "
                              "Coding agent.",
                              "dim", wrap=True))
        self.heading("When Claude is unreachable")
        sw = Gtk.Switch(active=jarvis.fallback_on())
        sw.connect("notify::active", lambda w, _p: self.save("jarvis_fallback", w.get_active()))
        others = [lbl.split(" · ", 1)[-1] for lbl, t in jarvis.agents() if t != "claude"]
        self.row("Answer with an Ollama server", sw,
                 hint=(f"Without internet, or when Claude can't be reached, the panel answers with {others[0]} "
                       f"(the first server that answers, through {agents.name()})") if others else
                 "No Ollama server with a model yet: add one in Settings → Coding agent")
        self.laya_section()
        self.heading("Local models (Ollama)")
        self.local = self.add_widget(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8))
        name = Gtk.Entry(placeholder_text="e.g. qwen3:8b", width_chars=22)
        get = button("Download…", lambda: self.pull(name.get_text().strip()))
        name.connect("activate", lambda _e: self.pull(name.get_text().strip()))
        box = Gtk.Box(spacing=8)
        box.pack_start(name, False, False, 0)
        box.pack_start(get, False, False, 0)
        self.row("Download a model", box, hint="Opens a terminal with the download progress · names from ollama.com/library")
        self.fill_local()
        self.heading("Memory")
        self.add_widget(label("Notes Jarvis reads before every answer. Jarvis proposes them (Save / Skip in the "
                              "panel); say \"remember …\" to add one.", "dim", wrap=True))
        self.mem = self.add_widget(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8))
        self.add_widget(button("Open file", self.open_memory)).set_halign(Gtk.Align.START)
        self.fill_memory()
        self.show_all()

    def laya_section(self):
        self.heading("Laya decision model")
        sw = Gtk.Switch(active=jarvis.laya_on())
        sw.connect("notify::active", lambda w, _p: self.save("jarvis_laya", w.get_active()))
        self.row("Use Laya decision model", sw, hint="A self-hosted classifier rates each action card safe, risky or "
                 "destructive. Advice only: nothing runs without your Run click")
        self.laya_url = Gtk.Entry(text=jarvis.laya_url(), placeholder_text="http://host:port", width_chars=22)
        self.laya_url.connect("activate", lambda _e: self.apply_laya_url())
        box = Gtk.Box(spacing=8)
        box.pack_start(self.laya_url, False, False, 0)
        box.pack_start(button("Apply", self.apply_laya_url), False, False, 0)
        self.laya_result = label("", "dim")
        box.pack_start(button("Test", self.test_laya), False, False, 0)
        box.pack_start(self.laya_result, False, False, 0)
        self.row("Laya server URL", box, hint="http(s)://host[:port]; Test checks /health and one classification")
        self.laya_token = Gtk.Entry(visibility=False, placeholder_text="Paste token", width_chars=22)
        self.laya_token.connect("activate", lambda _e: self.save_laya_token())
        self.token_state = label("", "dim")
        box = Gtk.Box(spacing=8)
        box.pack_start(self.laya_token, False, False, 0)
        box.pack_start(button("Save", self.save_laya_token), False, False, 0)
        box.pack_start(button("Remove", self.clear_laya_token), False, False, 0)
        box.pack_start(self.token_state, False, False, 0)
        self.row("Laya token", box, hint="Kept in GNOME Keyring (service laya), never shown or written to a file")
        self.fill_token()
        self.row("Decision dialog", button("Open…", lambda: launch("fw-laya")),
                 hint="Describe a situation, list the options, Laya picks one (also in the app launcher: Laya Decide)")

    def fill_token(self):
        bg(lambda: bool(jarvis.laya_token()),
           lambda has: (self.token_state.set_text("Token saved" if has else "No token"), False)[1], fail=lambda e: False)

    def apply_laya_url(self):
        value, err = jarvis.check_laya_url(self.laya_url.get_text())
        if err:
            self.status.set_text(err)
            return
        self.laya_url.set_text(value)
        self.save("jarvis_laya_url", value)

    def test_laya(self):
        value, err = jarvis.check_laya_url(self.laya_url.get_text())
        if err or not value:
            self.status.set_text(err or "Type the Laya server URL first")
            return
        self.laya_result.set_text("Testing…")
        bg(jarvis.laya_test, lambda res: (self.laya_result.set_text(res), False)[1], value, fail=lambda e: "Unreachable")

    def save_laya_token(self):
        token = self.laya_token.get_text().strip()
        if not token:
            self.status.set_text("Paste the token first")
            return
        self.laya_token.set_text("")
        bg(jarvis.laya_save_token, lambda err: (self.status.set_text(err or "Token saved"), self.fill_token(), False)[2],
           token, fail=str)

    def clear_laya_token(self):
        bg(jarvis.laya_clear_token, lambda _r: (self.status.set_text("Token removed"), self.fill_token(), False)[2])

    def refresh(self):  # notes saved in the panel since the page was built; models pulled meanwhile
        self.fill_memory()
        self.fill_local()

    def fill_local(self):
        bg(ollama.state, self.got_local, fail=lambda e: {"up": False, "models": [], "loaded": {}})

    def got_local(self, st):
        for c in self.local.get_children():
            self.local.remove(c)
        if not st["up"]:
            msg = ("The Ollama service isn't running (sudo systemctl start ollama)" if shutil.which("ollama") else
                   "Ollama isn't installed: re-run install.sh --with=ai (remote servers still work)")
            self.local.pack_start(label(msg, "warn", wrap=True), False, False, 0)
        elif not st["models"]:
            self.local.pack_start(label("No models on this laptop yet", "dim"), False, False, 0)
        for m in st["models"]:
            share = st["loaded"].get(m["name"])
            where = "" if share is None else (" · loaded on the GPU" if share > 0.95 else
                                               f" · loaded, {int(share * 100)} % on the GPU" if share else " · loaded on the CPU")
            r = Gtk.Box(spacing=12)
            r.get_style_context().add_class("item")
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            left.pack_start(label(m["name"], xalign=0), False, False, 0)
            left.pack_start(label(" · ".join(x for x in (ollama.gb(m["size"]), m["params"], m["quant"]) if x) + where,
                                  "dim", xalign=0), False, False, 0)
            r.pack_start(left, True, True, 0)
            r.pack_end(button("Remove", lambda n=m["name"]: self.remove_model(n), "danger"), False, False, 0)
            self.local.pack_start(r, False, False, 0)
        self.local.pack_start(label("The coding agent and the fallback above use these through the \"laptop\" server; "
                                    "pick the model in Settings → Coding agent.", "dim", wrap=True), False, False, 0)
        self.local.show_all()
        return False

    def pull(self, name):
        if not shutil.which("ollama"):
            self.status.set_text("Ollama isn't installed: re-run install.sh --with=ai")
            return
        if not ollama.valid(name):
            self.status.set_text("Type a model name such as qwen3:8b")
            return
        launch("fw-term", "--hold", "-e", "ollama", "pull", name)
        self.status.set_text(f"Downloading {name} in a terminal; it shows up here when done (reopen the page)")

    def remove_model(self, name):
        self.status.set_text(f"Removing {name}…")
        bg(ollama.remove, lambda err: (self.status.set_text(err or f"Removed {name}"), self.fill_local(), False)[2],
           name, fail=lambda e: str(e))

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

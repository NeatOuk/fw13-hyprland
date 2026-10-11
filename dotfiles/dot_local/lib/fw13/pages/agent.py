"""Coding agent: OpenCode or Pi for the >_ icon, Jarvis' Open button and its Ollama fallback, plus the Ollama servers
and the default server + model both agents share (fw13.agents; the same data as the >_ panel)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .. import agents, store  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page, launch  # noqa: E402
from .system import bg  # noqa: E402


class AgentPage(Page):
    def __init__(self):
        super().__init__("Coding agent")
        self.status = label("", "dim", wrap=True)
        self.probed = {}  # (name, url) → (online, models) from the last probe
        self.heading("Coding agent")
        box = Gtk.Box(spacing=12)
        self.radios = {}
        group = None
        for a, title in agents.AGENTS.items():
            r = Gtk.RadioButton.new_with_label_from_widget(group, title)
            group = group or r
            r.set_active(a == agents.agent())
            r.connect("toggled", lambda w, a=a: w.get_active() and self.choose(a))
            self.radios[a] = r
            box.pack_start(r, False, False, 0)
        self.row("Agent", box, hint="OpenCode or Pi (pi.dev): the >_ icon, Jarvis' Open button and Jarvis' answers when "
                 "Claude is unreachable start it. Both use the same servers and models below")
        bg(lambda: {a: agents.version(a) for a in agents.AGENTS}, self.got_versions, fail=lambda e: {})

        self.heading("Ollama servers")
        self.servers_box = self.add_widget(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8))
        self.name = Gtk.Entry(placeholder_text="name, e.g. nas", width_chars=12)
        self.url = Gtk.Entry(placeholder_text="http://nas:11434", width_chars=22)
        self.url.connect("activate", lambda _e: self.add_server())
        add = Gtk.Box(spacing=8)
        for w in (self.name, self.url, button("Add", self.add_server)):
            add.pack_start(w, False, False, 0)
        self.row("Add server", add, hint="Lowercase letters, digits and -; the address is http(s)://host[:port] "
                 "(port 11434 when left out)")

        self.heading("Default model")
        self.server = Gtk.ComboBoxText()
        self.server_handler = self.server.connect("changed", lambda _c: self.fill_models())
        self.row("Server", self.server, hint="Where new sessions and Jarvis' fallback go first")
        self.model = Gtk.ComboBoxText()
        self.model_handler = self.model.connect("changed", lambda _c: self.pick_model())
        self.row("Model", self.model, hint="Models the server had at the last check")
        self.add_widget(self.status)

        self.heading("Models and keys")
        self.row("Download models", button("Jarvis settings", lambda: launch("fw-settings", "jarvis")),
                 hint="Settings → Jarvis → Local models downloads and removes the laptop's own models")
        self.row("Ollama Cloud key", button("My Framework", lambda: launch("fw-settings", "fw13")),
                 hint="Set the key in My Framework; Ollama Cloud then shows up here as a server")
        self.render()
        self.refresh()
        self.show_all()

    def refresh(self):
        lst = agents.servers()
        bg(agents.probe_all, self.got_probe, lst, fail=lambda e: {})

    def got_versions(self, versions):
        for a, r in self.radios.items():
            v = versions.get(a)
            r.set_label(f"{agents.name(a)} {v.split()[-1]}" if v else f"{agents.name(a)} (not installed)")
            r.set_sensitive(bool(v) or r.get_active())
        return False

    def got_probe(self, status):
        self.probed = status
        st = agents.remember_probe(agents.load_state(), status)
        agents.save_state(st)
        agents.generate(st, agents.servers())
        self.render()
        return False

    def render(self):
        for c in self.servers_box.get_children():
            self.servers_box.remove(c)
        st = agents.load_state()
        lst = agents.servers()
        for n, url in lst:
            if (n, url) in self.probed:
                online, models = self.probed[(n, url)]
                state = f"online · {len(models)} models" if online else "offline"
            else:
                state = "checking…"
            r = Gtk.Box(spacing=12)
            r.get_style_context().add_class("item")
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            title = "Ollama Cloud" if (n, url) == agents.CLOUD else n
            left.pack_start(label(title + ("  ●" if n == st.get("active") else ""), xalign=0), False, False, 0)
            left.pack_start(label(f"{url} · {state}", "dim", xalign=0), False, False, 0)
            r.pack_start(left, True, True, 0)
            if n != "laptop" and (n, url) != agents.CLOUD:
                r.pack_end(button("Remove", lambda n=n: self.remove(n), "danger"), False, False, 0)
            self.servers_box.pack_start(r, False, False, 0)
        self.servers_box.show_all()
        self.server.handler_block(self.server_handler)
        self.server.remove_all()
        for n, url in lst:
            self.server.append(n, "Ollama Cloud" if (n, url) == agents.CLOUD else n)
        self.server.set_active_id(st.get("active") or (lst[0][0] if lst else None))
        self.server.handler_unblock(self.server_handler)
        self.fill_models()

    def fill_models(self):
        n = self.server.get_active_id()
        st = agents.load_state()
        self.model.handler_block(self.model_handler)
        self.model.remove_all()
        models = st.get("known", {}).get(n, [])
        for m in models:
            self.model.append(m, m)
        chosen = st.get("model", {}).get(n)
        if chosen and chosen not in models:  # chosen earlier, server offline or model gone now
            self.model.append(chosen, chosen)
        self.model.set_active_id(chosen)
        self.model.set_sensitive(bool(models or chosen))
        self.model.handler_unblock(self.model_handler)
        if n and n != st.get("active") and chosen:  # a server with a model: use it right away
            self.use(n, chosen)

    def pick_model(self):
        n, m = self.server.get_active_id(), self.model.get_active_id()
        if n and m:
            self.use(n, m)

    def use(self, n, m):
        agents.use(n, m)
        self.status.set_text(f"Using {n} · {m} for OpenCode and Pi")
        self.render()

    def choose(self, a):
        store.set("coding_agent", a)
        self.status.set_text(f"{agents.name(a)} from now on: the >_ icon and Jarvis start it")

    def add_server(self):
        n, url = self.name.get_text(), self.url.get_text()
        _n, _u, err = agents.check_server(n, url, agents.servers())
        if err:
            self.status.set_text(err)
            return
        self.status.set_text(f"Adding {n.strip().lower()}…")
        bg(agents.add_server, self.added, n, url, fail=lambda e: (str(e), False, []))

    def added(self, res):
        err, online, models = res
        if err:
            self.status.set_text(err)
        else:
            self.name.set_text("")
            self.url.set_text("")
            self.status.set_text(f"Added: {'online · %d models' % len(models) if online else 'offline for now'}")
            self.refresh()
        return False

    def remove(self, n):
        agents.remove_server(n)
        self.status.set_text(f"Removed {n}")
        self.probed = {s: v for s, v in self.probed.items() if s[0] != n}
        self.render()


def build():
    return AgentPage()

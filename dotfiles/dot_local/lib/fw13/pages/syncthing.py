"""Syncthing: service on/off, version, this device's ID (Copy), other devices, folders, Open full UI, Rescan all.
Over fw13.syncthing (REST API, read-only apart from Rescan). Listed only when syncthing is installed
(pages/__init__.py NEEDS). Polls every few seconds while the page is on screen; re-renders only on a change."""
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import syncthing  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page, bg, launch  # noqa: E402

POLL = 3  # s
UI = "http://127.0.0.1:8384"


def _load():
    running, enabled = syncthing.service()
    if not running:
        return {"running": False, "enabled": enabled}
    try:
        return {"running": True, "enabled": enabled, **syncthing.snapshot()}
    except syncthing.Error as e:
        return {"running": True, "enabled": enabled, "error": str(e)}


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


class SyncthingPage(Page):
    def __init__(self):
        super().__init__("Syncthing")
        self.state = None   # _load() result; None = loading
        self.msg = ""       # result of the last action (start/stop, rescan, copy)
        self.loading = False
        self.timer = None
        self.connect("map", lambda _w: self.start())
        self.connect("unmap", lambda _w: self.stop())
        self.connect("destroy", lambda _w: self.stop())
        self.render()
        self.reload()

    def start(self):
        if not self.timer:
            self.timer = GLib.timeout_add_seconds(POLL, lambda: self.reload() or True)

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def refresh(self):
        self.reload()

    def reload(self):
        if not self.loading:
            self.loading = True
            bg(_load, self.got, fail=lambda e: {"running": False, "enabled": False, "error": str(e)})

    def got(self, state):
        self.loading = False
        if state != self.state:  # unchanged → keep the widgets (no flicker, scroll and focus stay)
            self.state = state
            self.render()

    def say(self, msg):
        self.msg = msg
        self.render()
        if msg:  # a note goes away after a while unless a newer one replaced it
            GLib.timeout_add_seconds(5, lambda: self.msg == msg and self.say("") and False)

    def render(self):
        self.clear()
        st = self.state
        self.heading("Status")
        if st is None:
            self.add_widget(label("Loading…", "dim"))
            self.show_all()
            return
        sw = Gtk.Switch()
        sw.set_active(st["running"])
        sw.connect("state-set", self.on_switch)
        if st["running"]:
            hint = f"Running · {st['version']}" if "version" in st else "Running"
            hint += "" if st["enabled"] else " · not started at login"
        else:
            hint = "Stopped: switch on to start it now and at every login"
        self.row("Syncthing", sw, hint=hint)
        if self.msg:
            self.add_widget(label(self.msg, "dim", wrap=True))
        if st.get("error"):
            self.add_widget(label(st["error"], "dim", wrap=True))
        if "id" in st:
            self.row("This device's ID", button("Copy", lambda: self.copy(st["id"])),
                     hint=f"{syncthing.short_id(st['id'])} · {st['id']}")
        if st["running"]:
            self.row("Full Syncthing UI", button("Open full UI", lambda: launch("xdg-open", UI)),
                     hint="Add devices and folders there; it opens in your browser")
        if "folders" in st:
            self.row("Rescan all folders", button("Rescan all", self.rescan),
                     hint="Looks for changes now instead of waiting for the next scan")
            self.render_devices(st["devices"])
            self.render_folders(st["folders"])
        self.show_all()

    def render_devices(self, devices):
        self.heading("Devices")
        if not devices:
            self.add_widget(label("No other devices yet: add one in the full UI", "dim"))
        for d in devices:
            if d["paused"]:
                hint = "paused"
            elif d["connected"]:
                hint = f"connected · {d['via']}"
            else:
                hint = f"not connected · last seen {d['seen']}"
            self.row(d["name"], hint=f"{hint} · {syncthing.short_id(d['id'])}")

    def render_folders(self, folders):
        self.heading("Folders")
        if not folders:
            self.add_widget(label("No shared folders yet: add one in the full UI", "dim"))
        for f in folders:
            self.row(f["label"], hint=f"{f['path']} · {f['state']} · shared with {_plural(f['shared'], 'device')}")

    def on_switch(self, sw, on):
        sw.set_sensitive(False)
        self.msg = ("Starting" if on else "Stopping") + " Syncthing…"
        bg(syncthing.set_service, self.switched, on)
        return False

    def switched(self, res):
        ok, err = res
        self.msg = "" if ok else f"systemctl failed: {err}"
        self.state = None if ok else self.state
        self.reload()
        if not ok:
            self.render()

    def rescan(self):
        def done(err):
            self.say(err or "Rescan started")
        bg(lambda: syncthing.rescan() and None, done, fail=str)

    def copy(self, device_id):
        try:
            subprocess.run(["wl-copy", device_id], timeout=5, check=True)
            self.say("Device ID copied")
        except (OSError, subprocess.SubprocessError) as e:
            self.say(f"Copy failed: {e}")


def build():
    return SyncthingPage()

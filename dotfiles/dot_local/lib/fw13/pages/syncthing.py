"""Syncthing: service on/off, version, this device's ID (Copy), other devices (add, pause, remove), folders (add,
open, share, pause, remove), Open full UI, Rescan all. Over fw13.syncthing (REST API). Listed only when syncthing
is installed (pages/__init__.py NEEDS). Polls every few seconds while the page is on screen; re-renders only on a
change. Forms are dialogs, so a re-render never loses what is being typed."""
import os
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
        return {"running": True, "enabled": enabled, **syncthing.snapshot(), "pending": syncthing.pending()}
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
                     hint="Advanced options (versioning, ignore patterns, bandwidth); it opens in your browser")
        if "folders" in st:
            self.row("Rescan all folders", button("Rescan all", self.rescan),
                     hint="Looks for changes now instead of waiting for the next scan")
            self.render_pending(st.get("pending") or [], st["devices"])
            self.render_devices(st["devices"])
            self.render_folders(st["folders"])
        self.show_all()

    def buttons(self, *specs):
        """A row of buttons from (text, callback[, css class]) specs."""
        box = Gtk.Box(spacing=6)
        for spec in specs:
            box.pack_start(button(*spec), False, False, 0)
        return box

    def render_pending(self, reqs, devices):
        if not reqs:
            return
        self.heading("Requests")
        names = {d["id"]: d["name"] for d in devices}
        for r in reqs:
            if r["kind"] == "device":
                text = f"{r['name']} wants to connect"
                hint = syncthing.short_id(r["id"]) + (f" · {r['address']}" if r["address"] else "")
                accept = (lambda r=r: self.act(f"{r['name']} added", syncthing.add_device, r["id"], r["name"]))
                ignore = (lambda r=r: self.act(f"{r['name']} ignored", syncthing.ignore_device, r["id"]))
            else:
                text = f"{names.get(r['device'], syncthing.short_id(r['device']))} shares “{r['label']}”"
                hint = "Accept to sync it on this laptop"
                accept = (lambda r=r: self.accept_folder(r))
                ignore = (lambda r=r: self.act(f"“{r['label']}” ignored", syncthing.ignore_folder, r["id"], r["label"],
                                               r["device"]))
            self.row(text, self.buttons(("Accept", accept, "primary"), ("Ignore", ignore)), hint=hint)

    def accept_folder(self, r):
        dlg, box = self.dialog(f"Accept “{r['label']}”", "Accept")
        box.pack_start(label("Save it to"), False, False, 0)
        path = Gtk.Entry(activates_default=True, width_chars=50, text=syncthing.default_path(r["label"]))
        box.pack_start(path, False, False, 0)
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        where = path.get_text()
        dlg.destroy()
        if ok and where.strip():
            self.act(f"“{r['label']}” syncs to {where}", syncthing.accept_folder, r["id"], r["label"], r["device"],
                     os.path.expanduser(where.strip()))

    def render_devices(self, devices):
        self.heading("Devices")
        self.row("Add a device", button("Add device…", self.add_device),
                 hint="Paste the other device's ID (Syncthing on it: Actions → Show ID)")
        if not devices:
            self.add_widget(label("No other devices yet", "dim"))
        for d in devices:
            if d["paused"]:
                hint = "paused"
            elif d["connected"]:
                hint = f"connected · {d['via']}"
            else:
                hint = f"not connected · last seen {d['seen']}"
            self.row(d["name"], self.buttons(
                ("Resume" if d["paused"] else "Pause", lambda d=d: self.act(
                    "Resumed" if d["paused"] else "Paused", syncthing.set_paused, "device", d["id"], not d["paused"])),
                ("Remove", lambda d=d: self.remove("device", d["id"], d["name"]), "danger")),
                hint=f"{hint} · {syncthing.short_id(d['id'])}")

    def render_folders(self, folders):
        self.heading("Folders")
        self.row("Add a folder", button("Add folder…", self.add_folder),
                 hint="Pick a folder on this laptop and the devices to share it with")
        if not folders:
            self.add_widget(label("No shared folders yet", "dim"))
        for f in folders:
            self.row(f["label"], self.buttons(
                ("Open", lambda f=f: launch("xdg-open", f["path"])),
                ("Share…", lambda f=f: self.share(f)),
                ("Resume" if f["paused"] else "Pause", lambda f=f: self.act(
                    "Resumed" if f["paused"] else "Paused", syncthing.set_paused, "folder", f["id"], not f["paused"])),
                ("Remove", lambda f=f: self.remove("folder", f["id"], f["label"]), "danger")),
                hint=f"{f['path']} · {f['state']} · shared with {_plural(f['shared'], 'device')}")

    # ---- actions: Syncthing calls run in a worker thread; the next poll shows the result

    def act(self, done_msg, fn, *args):
        def done(err):
            self.say(err or done_msg)
            self.reload()
        bg(lambda: fn(*args) and None, done, fail=str)

    def dialog(self, title, ok):
        """(dialog, content box) with Cancel + `ok` buttons."""
        dlg = Gtk.Dialog(title=title, transient_for=self.get_toplevel(), modal=True)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, ok, Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_spacing(8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(16)
        return dlg, box

    def device_checks(self, box, chosen=()):
        """A check button per other device → {device ID: check}."""
        checks = {}
        for d in (self.state or {}).get("devices", []):
            c = checks[d["id"]] = Gtk.CheckButton(label=d["name"])
            c.set_active(d["id"] in chosen)
            box.pack_start(c, False, False, 0)
        if not checks:
            box.pack_start(label("No other devices yet: add one first", "dim"), False, False, 0)
        return checks

    def add_device(self):
        dlg, box = self.dialog("Add device", "Add")
        box.pack_start(label("Device ID"), False, False, 0)
        ident = Gtk.Entry(activates_default=True, width_chars=60)
        box.pack_start(ident, False, False, 0)
        box.pack_start(label("Name (optional)"), False, False, 0)
        name = Gtk.Entry(activates_default=True)
        box.pack_start(name, False, False, 0)
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        text, nick = ident.get_text(), name.get_text()
        dlg.destroy()
        if ok and text.strip():
            self.act("Device added: it connects once the other side adds this laptop too",
                     lambda: syncthing.add_device(syncthing.check_id(text), nick))

    def add_folder(self):
        dlg, box = self.dialog("Add folder", "Add")
        box.pack_start(label("Folder"), False, False, 0)
        chooser = Gtk.FileChooserButton(title="Folder to sync", action=Gtk.FileChooserAction.SELECT_FOLDER)
        chooser.set_current_folder(os.path.expanduser("~"))
        box.pack_start(chooser, False, False, 0)
        box.pack_start(label("Name (optional)"), False, False, 0)
        name = Gtk.Entry(activates_default=True)
        box.pack_start(name, False, False, 0)
        box.pack_start(label("Share with"), False, False, 0)
        checks = self.device_checks(box)
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        path, nick = chooser.get_filename(), name.get_text()
        devices = [i for i, c in checks.items() if c.get_active()]
        dlg.destroy()
        if ok and path:
            self.act("Folder added", syncthing.add_folder, path, nick, devices)

    def share(self, f):
        dlg, box = self.dialog(f"Share {f['label']}", "Save")
        box.pack_start(label(f"Share {f['label']} with:"), False, False, 0)
        checks = self.device_checks(box, f["devices"])
        dlg.show_all()
        ok = dlg.run() == Gtk.ResponseType.OK
        changes = {i: c.get_active() for i, c in checks.items() if c.get_active() != (i in f["devices"])}
        dlg.destroy()
        if ok and changes:
            self.act("Sharing updated", lambda: [syncthing.share(f["id"], i, on) for i, on in changes.items()] and None)

    def remove(self, kind, ident, name):
        detail = ("Its files stay on this laptop; it stops syncing." if kind == "folder"
                  else "Folders stop syncing with it; it can be added again later.")
        dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True, message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.YES_NO, text=f"Remove {name} from Syncthing?")
        dlg.format_secondary_text(detail)
        dlg.set_default_response(Gtk.ResponseType.NO)
        ok = dlg.run() == Gtk.ResponseType.YES
        dlg.destroy()
        if ok:
            self.act(f"{name} removed", syncthing.remove, kind, ident)

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

"""Apps: the apps in the launcher (+ Flatpak apps), where each came from, pending updates, Uninstall… in a terminal."""
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402

from .. import apps, system  # noqa: E402
from ..ui_theme import button, label  # noqa: E402
from .common import Page, bg, launch  # noqa: E402

ICON = 24
REFOCUS = 5  # s: Settings regaining focus re-reads the list at most this often (e.g. back from an Uninstall terminal)
UPDATE_ALL = ("fw-term", "--hold", "-e", "fw-updates", "apply")
OPTIONAL_HINT = "Installed by this desktop · optional: the installer won't reinstall it once removed"


def _load():
    return apps.installed(), system.package_upgrades()


def icon(name):
    img = Gtk.Image()
    if name.startswith("/"):
        try:
            img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(name, ICON, ICON, True))
        except Exception:  # noqa: BLE001 — a broken icon file only loses the picture
            pass
    elif name:
        img.set_from_icon_name(name, Gtk.IconSize.LARGE_TOOLBAR)
        img.set_pixel_size(ICON)
    img.set_size_request(ICON, ICON)
    return img


class AppsPage(Page):
    def __init__(self):
        super().__init__("Apps")
        self.list = None     # apps.installed(); None = loading
        self.pk = None       # ([(name, version)] or None, message) from dnf's cache
        self.fp = None       # {(installation, app id): version} from the Flatpak remotes; None = checking
        self.loading = False
        self.loaded_at = 0.0
        self.hooked = False
        self.connect("map", self.on_map)
        self.render()
        self.reload(flatpak=True)

    def on_map(self, _w):
        top = self.get_toplevel()
        if not self.hooked and isinstance(top, Gtk.Window):
            self.hooked = True
            top.connect("notify::is-active", self.on_active)

    def on_active(self, win, _p):
        if win.is_active() and self.get_mapped() and time.monotonic() - self.loaded_at > REFOCUS:
            self.reload()

    def refresh(self):
        self.reload()

    def reload(self, flatpak=False):
        """Re-read the apps and dnf's cache (local, fast); flatpak=True also asks the Flatpak remotes (network)."""
        if flatpak:
            self.fp = None
            bg(apps.flatpak_updates, self.got_flatpak, fail=lambda _e: {})
        if self.loading:
            return
        self.loading = True
        bg(_load, self.got, fail=lambda e: ([], (None, str(e))))

    def got(self, res):
        self.loading = False
        self.loaded_at = time.monotonic()
        self.list, self.pk = res
        self.render()

    def got_flatpak(self, ups):
        self.fp = ups
        self.render()

    def update_of(self, app):
        """New version for an app, '' when there is one without a version, None for none."""
        if app["kind"] == "rpm" and self.pk and self.pk[0]:
            return dict(self.pk[0]).get(app["package"])
        if app["kind"] == "flatpak" and self.fp:
            return self.fp.get((app["installation"], app["flatpak"]))
        return None

    def render(self):
        self.clear()
        self.heading("Updates")
        self.render_updates()
        self.heading("Installed apps")
        script = apps.remove_all_script(self.list) if self.list else None
        if script:
            names = sorted({a["name"] for a in self.list if a.get("optional")})
            self.row("Remove pre-installed apps…", button("Remove all…", lambda: launch(
                "fw-term", "--hold", "-e", "bash", "-c", script), "danger"),
                hint="The optional apps this desktop installed: " + ", ".join(names) + ". One dnf list to confirm; "
                     "the installer won't put them back")
        if self.list is None:
            self.add_widget(label("Loading…", "dim"))
        else:
            rows = sorted(self.list, key=lambda a: (self.update_of(a) is None, a["name"].lower()))
            for app in rows:
                self.render_app(app)
            self.add_widget(label("Uninstall… opens a terminal: dnf or flatpak lists what goes and asks before "
                                  "removing anything. Apps from Steam, Lutris or other launchers are removed there.",
                                  "dim", wrap=True))
        self.render_removed()
        self.show_all()

    def render_removed(self):
        names = apps.skipped()
        if not names:
            return
        self.heading("Removed apps")
        for n in names:
            self.row(n, button("Reinstall on next installer run", lambda n=n: self.unskip(n)),
                     hint="install.sh skips it until then")

    def unskip(self, name):
        apps.unskip(name)
        self.render()

    def render_updates(self):
        check = button("  Check now", lambda: self.reload(flatpak=True))
        box = Gtk.Box(spacing=8)
        box.pack_start(check, False, False, 0)
        if self.list is None or self.pk is None:
            check.set_sensitive(False)
            self.row("Checking for updates…", box)
            return
        ups, msg = self.pk
        n_apps = sum(self.update_of(a) is not None for a in self.list)
        total = (len(ups) if ups else 0) + len(self.fp or {})
        hint = [f"{msg} in total" if ups else msg if ups is not None else f"dnf: {msg}"]
        if self.fp is None:
            hint.append("checking Flatpak…")
        elif self.fp:
            hint.append(f"{len(self.fp)} Flatpak update{'s' if len(self.fp) != 1 else ''}")
        if total:
            box.pack_start(button("Update all…", lambda: launch(*UPDATE_ALL), "primary"), False, False, 0)
            hint.append("Update all takes a Timeshift snapshot first; the terminal asks for your password")
        text = f"{n_apps} app update{'s' if n_apps != 1 else ''}" if n_apps else "Apps are up to date"
        self.row(text, box, hint=" · ".join(hint))

    def render_app(self, app):
        ver = self.update_of(app)
        hint = [app["source"]]
        if ver is not None:
            hint.append(f"Update available → {ver}" if ver else "Update available")
        if app["protected"]:
            hint.append(app["protected"])
        if app.get("optional"):
            hint += [OPTIONAL_HINT] + [n for n in [apps.OPTIONAL[app["optional"]][1]] if n]
        argv = apps.uninstall_argv(app)
        widget = button("Uninstall…", lambda: launch("fw-term", "--hold", "-e", *argv)) if argv else None
        r = self.row(app["name"], widget, hint=" · ".join(hint))
        img = icon(app["icon"])
        img.set_valign(Gtk.Align.CENTER)
        r.pack_start(img, False, False, 0)
        r.reorder_child(img, 0)


def build():
    return AppsPage()

"""Network: Wi-Fi (switch, country = regulatory domain via pkexec fw-wifi-country, networks, connect/forget, hidden), Ethernet via nmcli, and every VPN (fw13.vpn:
NetworkManager's + strongSwan's): connect/disconnect, edit (nm-connection-editor / pages/vpn_edit.py), add."""
import json
import os
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import bar as waybar, net, vpn  # noqa: E402
from ..ui_theme import button  # noqa: E402
from . import vpn_edit  # noqa: E402
from .common import Page, bg, label, launch, wrap  # noqa: E402

VPN_POLICY = "/usr/share/polkit-1/actions/org.fw13.vpn.policy"
WIFI_ICON, LOCK_ICON, ETH_ICON, VPN_ICON = "", "", "", ""


def _buttons(*widgets):
    box = Gtk.Box(spacing=6)
    for w in widgets:
        box.pack_start(w, False, False, 0)
    return box


def _country_names():
    """ISO 3166 code -> name from iso-codes (Fedora core); {} when missing (codes alone)."""
    try:
        with open("/usr/share/iso-codes/json/iso_3166-1.json") as f:
            return {c["alpha_2"]: c.get("common_name", c["name"]) for c in json.load(f)["3166-1"]}
    except (OSError, ValueError, KeyError):
        return {}


def _valid_psk(pw, security):
    if "WPA3" in security.split() and "WPA2" not in security.split():
        return len(pw) >= 1  # SAE takes any length
    return 8 <= len(pw) <= 63 or (len(pw) == 64 and all(c in "0123456789abcdefABCDEF" for c in pw))


class NetworkPage(Page):
    def __init__(self):
        super().__init__("Network")
        self.status = self.add_widget(label("", "dim", wrap=True))
        self.status.set_no_show_all(True)
        self.busy = False
        self.confirming = False  # a Forget confirm or the password dialog is open
        self.refresh()
        self.connect("map", self._first_map)

    def _first_map(self, _w):
        """The cached scan list goes stale; rescan quietly the first time the page is shown."""
        self.disconnect_by_func(self._first_map)
        if net.wifi_enabled():
            threading.Thread(target=self._quiet_scan, daemon=True).start()

    # --- background work -------------------------------------------------
    def set_status(self, text, cls="dim"):
        ctx = self.status.get_style_context()
        for c in ("dim", "bad", "ok"):
            ctx.remove_class(c)
        ctx.add_class(cls)
        self.status.set_text(text)
        self.status.set_visible(bool(text))

    def run_bg(self, msg, fn, *args):
        """Run fn(*args) -> error|None in a thread; lock the page meanwhile, then refresh."""
        if self.busy:
            return
        self.busy = True
        self.set_status(msg)
        for child in self.box.get_children()[2:]:
            child.set_sensitive(False)

        def work():
            try:
                err = fn(*args)
            except Exception as e:  # noqa: BLE001  never leave the page locked
                err = str(e)
            GLib.idle_add(self._done, err)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, err):
        self.busy = False
        self.set_status(err or "", "bad" if err else "dim")
        self.refresh()
        then, self.then = getattr(self, "then", None), None  # a follow-up the worker asked for (imported())
        if then:
            then()
        return False

    def _quiet_scan(self):
        net.rescan()
        time.sleep(4)  # `rescan` returns before results arrive
        GLib.idle_add(self._quiet_refresh)

    def _quiet_refresh(self):
        if not (self.busy or self.confirming):  # an action refreshes when done; don't kill a confirm
            self.refresh()
        return False

    @staticmethod
    def _scan():
        net.rescan()  # "not allowed right after a scan" is fine: the list is fresh then
        time.sleep(4)

    # --- layout ------------------------------------------------------------
    def refresh(self):
        if self.busy:
            return
        self.confirming = False
        self.clear(keep=2)
        devs = net.devices()
        conns = net.connections()
        wifi_dev = next((d["device"] for d in devs if d["type"] == "wifi"), None)
        wifi_conns = [c for c in conns if c["type"] == net.WIFI]

        self.heading("Wi-Fi")
        seen = set()
        if not wifi_dev:
            self.add_widget(label("No Wi-Fi adapter", "dim"))
        else:
            on = net.wifi_enabled()
            sw = Gtk.Switch()
            sw.set_active(on)
            sw.connect("state-set", self.on_wifi_switch)
            self.row("Wi-Fi", sw, hint=wifi_dev)
            self.country_row()
            if on:
                tools = _buttons(button("Rescan", lambda: self.run_bg("Scanning…", self._scan)),
                                 button("+ Hidden network…", lambda: self.on_hidden(wifi_dev)))
                tools.set_halign(Gtk.Align.START)
                self.add_widget(tools)
                saved = {}
                for c in wifi_conns:  # an active profile wins over another one for the same SSID
                    if c["ssid"] not in saved or c["active"]:
                        saved[c["ssid"]] = c
                nets = net.networks()
                if not nets:
                    self.add_widget(label("No networks found — try Rescan", "dim"))
                for n in nets:
                    seen.add(n["ssid"])
                    self.wifi_row(n, saved.get(n["ssid"]), wifi_dev)
                for c in wifi_conns:  # connected, but not in the (stale) scan list yet
                    if c["active"] and c["ssid"] not in seen:
                        seen.add(c["ssid"])
                        self.item(f"{WIFI_ICON}  {c['ssid'] or c['name']}", None,
                                  [self.disconnect_button(c["ssid"] or c["name"], c), self.forget_button(c)],
                                  lead="Connected")
                away = [c for c in wifi_conns if c["ssid"] not in seen and not c["active"]]
                if away:
                    self.heading("Saved networks")
                    for c in away:
                        self.item(f"{WIFI_ICON}  {c['name']}", "Not in range", [self.forget_button(c)])

        self.heading("Ethernet")
        eths = [d for d in devs if d["type"] == "ethernet"]
        if not eths:
            self.add_widget(label("No Ethernet port", "dim"))
        for d in eths:
            state = d["state"].split(" (")[0].capitalize()
            ip = net.device_ip(d["device"]) if d["state"].startswith("connected") else ""
            title = d["connection"] or d["device"]
            self.item(f"{ETH_ICON}  {title}", " · ".join(x for x in (ip, d["device"]) if x), [],
                      lead=state, lead_cls="ok" if d["state"].startswith("connected") else "dim")

        self.render_vpns()

        adv = Gtk.Button(label="Advanced… (connection editor)")
        adv.set_halign(Gtk.Align.START)
        adv.connect("clicked", lambda _b: launch("nm-connection-editor"))
        self.add_widget(adv)
        self.show_all()

    def country_row(self):
        """Regulatory country: which bands the radio may use (6 GHz = Wi-Fi 6E/7 only where the country allows it)."""
        cur, six = net.wifi_country()
        combo = Gtk.ComboBoxText()
        combo.append("00", "Default (world)")
        names = _country_names()
        for cc in sorted(net.wifi_countries(), key=lambda c: names.get(c, c)):
            combo.append(cc, f"{names.get(cc, cc)} ({cc})")
        combo.set_active_id(cur) or combo.set_active_id("00")
        combo.connect("changed", lambda c: c.get_active_id() != cur and self.run_bg(
            "Setting the Wi-Fi country… (Wi-Fi may reconnect)", net.set_wifi_country, c.get_active_id()))
        six_text = "6 GHz (Wi-Fi 6E/7) allowed" if six else "No 6 GHz (Wi-Fi 6E/7) in this country"
        self.row("Wi-Fi country", combo, hint=f"{six_text} · use the country you are in")

    def render_vpns(self):
        self.heading("VPN")
        vs = vpn.vpns()
        free = os.path.exists(vpn.CTL) and os.path.exists(VPN_POLICY)  # strongSwan toggle via fw-vpn-ctl + polkit rule
        if not vs:
            self.add_widget(label("No VPN yet: add one below", "dim"))
        secrets = vpn.openvpn_needs([v["id"] for v in vs if v["backend"] == "nm"])
        for v in vs:
            if v["active"]:
                act = button("Disconnect",
                             lambda v=v: self.run_bg(f"Disconnecting {v['name']}…", self.vpn_set, v, False))
            else:
                act = button("Connect", lambda v=v: self.run_bg(f"Connecting {v['name']}…", self.vpn_set, v, True),
                             "primary")
            edit = button("Edit…", lambda v=v: self.swan_edit(v["id"]) if v["backend"] == "swan"
                          else launch("nm-connection-editor", "-e", v["id"]))
            hint = v["kind"] + (" · no password (wheel at the laptop)" if v["backend"] == "swan" and free else "")
            buttons = [act, edit]
            if v["backend"] == "nm" or vpn_edit.installed():
                buttons.append(button("Delete", lambda v=v: self.delete_vpn(v), "danger"))
            if v["id"] in secrets:
                buttons.append(button("Save password…", lambda v=v: self.save_secrets(v, secrets[v["id"]])))
            self.item(f"{VPN_ICON}  {v['name']}", hint, buttons,
                      lead="Connected" if v["active"] else None, lead_cls="ok")
        adds = [button("+ OpenVPN file (.ovpn)…", lambda: self.import_file("openvpn", "OpenVPN", "*.ovpn", "*.conf")),
                button("+ WireGuard file…", lambda: self.import_file("wireguard", "WireGuard", "*.conf")),
                button("+ OpenConnect, Cisco… or another file",
                       lambda: launch("nm-connection-editor", "-c", "-t", "vpn"))]
        if vpn_edit.installed():
            adds.insert(0, button("+ IKEv2 (FortiGate / strongSwan)…", lambda: self.swan_edit(None)))
        for b in adds:
            b.set_halign(Gtk.Align.START)
            self.add_widget(b)

    @staticmethod
    def vpn_set(v, on):
        err = vpn.set_active(v, on)
        if err and on and v["backend"] == "nm" and vpn.needs_secrets(err):  # password not saved: ask in a terminal
            GLib.idle_add(lambda: launch("fw-term", "--hold", "-e", "nmcli", "--ask", "connection", "up", "uuid",
                                         v["id"]) and False)
            err = "Asking for the VPN password in a terminal…"
        waybar.refresh("vpn")  # bar shield (fw-vpn)
        return err

    def import_file(self, kind, name, *patterns):
        """Pick a VPN file and import it with NetworkManager (`nmcli connection import type <kind>`); certificates and
        keys inline or next to an .ovpn are copied in by the OpenVPN plugin; a password is asked at first connect."""
        dlg = Gtk.FileChooserDialog(title=f"{name} configuration", transient_for=self.get_toplevel(),
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Import", Gtk.ResponseType.OK)
        f = Gtk.FileFilter()
        f.set_name(f"{name} ({' '.join(patterns)})")
        for pat in patterns:
            f.add_pattern(pat)
        dlg.add_filter(f)
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if path:
            before = {v["id"] for v in vpn.vpns()}
            self.run_bg("Importing…", self.imported, kind, path, before)

    def imported(self, kind, path, before):
        """Import in the worker thread; a new OpenVPN profile that needs a password or key passphrase then asks for
        it once (Save password…) instead of on every connect."""
        err = net.import_vpn(kind, path)
        new = [v for v in vpn.vpns() if v["id"] not in before] if not err else []
        need = vpn.openvpn_needs([v["id"] for v in new])
        asks = [v for v in new if v["id"] in need]
        if asks:  # after _done unlocks the page, so the dialog's own run_bg isn't refused as busy
            self.then = lambda: self.save_secrets(asks[0], need[asks[0]["id"]])
        return err

    def save_secrets(self, v, need):
        got = self.ask_ovpn(v["name"], need)
        if got:
            self.run_bg(f"Saving {v['name']}…", vpn.save_openvpn_secrets, v["id"], *got)

    # strongSwan: the root helper asks polkit, so it runs in a thread; the form itself is modal on the main loop
    def swan_edit(self, name, typed=None, error=""):
        self.set_status("Waiting for authorisation…")
        bg(vpn_edit.show, lambda cur: self.swan_form(cur, typed, error), name, fail=lambda e: {"error": str(e)})

    def swan_form(self, cur, typed=None, error=""):
        if "error" in cur:
            self.set_status(cur["error"], "bad")
            return False
        self.set_status("")
        self.confirming = True
        try:
            req = vpn_edit.dialog(self.get_toplevel(), cur, typed, error)
            if req == "delete" and not self.confirm(f"Delete the VPN {cur['name']}?"):
                req = None
        finally:
            self.confirming = False
        if req == "delete":
            self.set_status(f"Deleting {cur['name']}…")
            bg(vpn_edit.delete, self.swan_saved, cur["name"], fail=lambda e: {"error": str(e)})
        elif req:
            self.set_status("Saving…")
            bg(vpn_edit.write, lambda res: self.swan_saved(res, cur, req), req, fail=lambda e: {"error": str(e)})
        return False

    def swan_saved(self, res, cur=None, req=None):
        if "error" in res and req is not None:  # back to the form with what was typed
            return self.swan_form(cur, req, res["error"])
        self.set_status(res.get("error") or res.get("note") or "Saved", "bad" if "error" in res else "dim")
        waybar.refresh("vpn")
        self.refresh()
        return False

    def confirm(self, question, detail="The file is kept as a .bak next to it."):
        """Yes/No pop-up -> True for Yes."""
        dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True, message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.YES_NO, text=question)
        dlg.format_secondary_text(detail)
        dlg.set_default_response(Gtk.ResponseType.NO)
        ok = dlg.run() == Gtk.ResponseType.YES
        dlg.destroy()
        return ok

    def delete_vpn(self, v):
        swan = v["backend"] == "swan"
        if not self.confirm(f"Delete the VPN {v['name']}?", "The file is kept as a .bak next to it." if swan
                            else "Its saved password and settings go with it."):
            return
        if swan:
            self.set_status(f"Deleting {v['name']}…")
            bg(vpn_edit.delete, self.swan_saved, v["id"], fail=lambda e: {"error": str(e)})
        else:
            self.run_bg(f"Deleting {v['name']}…", net.forget, v["id"])

    def item(self, title, hint, buttons, lead=None, lead_cls="ok"):
        """A row: title, a hint line ('lead' coloured, then the dim rest), buttons on the right."""
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(wrap(label(title)), False, False, 0)
        sub = Gtk.Box()
        if lead:
            sub.pack_start(label(lead, lead_cls), False, False, 0)  # one word
        if hint:
            sub.pack_start(wrap(label((" · " if lead else "") + hint, "dim")), True, True, 0)
        left.pack_start(sub, False, False, 0)
        r.pack_start(left, True, True, 0)
        box = _buttons(*buttons)
        box.set_valign(Gtk.Align.CENTER)
        r.pack_end(box, False, False, 0)
        self.adapt(r, box)
        return self.add_widget(r)

    def wifi_row(self, n, conn, ifname):
        ssid, sec = n["ssid"], n["security"]
        hint = [f"{n['signal']}%", f"{LOCK_ICON} {sec}" if sec else "Open"]
        if conn and not n["in_use"]:
            hint.append("Saved")
        buttons = []
        if n["in_use"] and conn:
            buttons.append(self.disconnect_button(ssid, conn))
        elif not n["in_use"]:
            buttons.append(button("Connect", lambda: self.on_connect(n, conn, ifname), "primary"))
        if conn:
            buttons.append(self.forget_button(conn))
        self.item(f"{WIFI_ICON}  {ssid}", " · ".join(hint), buttons,
                  lead="Connected" if n["in_use"] else None)

    def disconnect_button(self, ssid, conn):
        return button("Disconnect", lambda: self.run_bg(f"Disconnecting from {ssid}…", net.down, conn["uuid"]))

    def forget_button(self, conn):
        return self.confirm_button("Forget", "Forget this network?", f"Forgetting {conn['name']}…",
                                   net.forget, conn["uuid"])

    def confirm_button(self, text, question, busy, fn, *args):
        """A danger button with a confirm step in place of the row's buttons; then run_bg(busy, fn, *args)."""
        b = button(text, None, "danger")

        def ask(_b):
            self.confirming = True
            box = b.get_parent()
            for w in box.get_children():
                box.remove(w)
            box.pack_start(wrap(label(question, "warn")), False, False, 0)
            box.pack_start(button("Cancel", self.refresh), False, False, 0)
            box.pack_start(button(text, lambda: self.run_bg(busy, fn, *args), "danger"), False, False, 0)
            box.show_all()
        b.connect("clicked", ask)
        return b

    # --- actions -------------------------------------------------------------
    def on_connect(self, n, conn, ifname):
        ssid, sec = n["ssid"], n["security"]
        if conn:
            self.run_bg(f"Connecting to {ssid}…", net.up, conn["uuid"])
        elif net.unsupported(sec):
            self.set_status(net.unsupported(sec), "bad")
        elif net.needs_password(sec):
            got = self.ask_secret(f"Connect to {ssid}", sec)
            if got:
                self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, sec, got[1], ifname)
        else:
            self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, sec, "", ifname)

    def on_wifi_switch(self, _sw, state):
        """Block the switch's own state change; the refresh after the action shows the real one."""
        if state:  # scan right away, or the list stays empty until a manual Rescan
            self.run_bg("Turning Wi-Fi on…", lambda: net.set_wifi(True) or self._scan())
        else:
            self.run_bg("Turning Wi-Fi off…", net.set_wifi, False)
        return True

    def on_hidden(self, ifname):
        got = self.ask_secret("Hidden network", "WPA2", ask_ssid=True)
        if got:
            ssid, pw = got
            self.run_bg(f"Connecting to {ssid}…", net.connect_new, ssid, "WPA2" if pw else "", pw, ifname, True)

    def ask_secret(self, title, security, ask_ssid=False):
        """Modal dialog in the app's style -> (ssid, password) or None. For a hidden network the password
        is optional (empty = open network)."""
        dlg = Gtk.Dialog(transient_for=self.get_toplevel(), modal=True, title=title)
        dlg.get_style_context().add_class("panel")
        dlg.set_default_size(380, -1)
        area = dlg.get_content_area()
        area.set_spacing(8)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, f"set_margin_{side}")(16)
        area.pack_start(label(title, "title"), False, False, 0)
        ssid_entry = Gtk.Entry(placeholder_text="Network name (SSID)") if ask_ssid else None
        if ssid_entry:
            area.pack_start(ssid_entry, False, False, 0)
        pw = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD,
                       placeholder_text="Password (blank for an open network)" if ask_ssid else "Password")
        area.pack_start(pw, False, False, 0)
        show = Gtk.CheckButton(label="Show password")
        show.connect("toggled", lambda c: pw.set_visibility(c.get_active()))
        area.pack_start(show, False, False, 0)
        if not ask_ssid:
            area.pack_start(label(f"{LOCK_ICON} {security}", "dim"), False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("Connect", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("primary")
        dlg.set_default_response(Gtk.ResponseType.OK)

        def valid():
            p = pw.get_text()
            if ssid_entry:
                return bool(ssid_entry.get_text().strip()) and (not p or _valid_psk(p, "WPA2"))
            return _valid_psk(p, security)

        def changed(*_):
            ok.set_sensitive(valid())
        for e in (pw, ssid_entry):
            if e:
                e.connect("changed", changed)
                e.connect("activate", lambda _e: valid() and dlg.response(Gtk.ResponseType.OK))
        changed()
        dlg.show_all()
        self.confirming = True
        try:
            resp = dlg.run()
        finally:
            self.confirming = False
        result = ((ssid_entry.get_text().strip() if ssid_entry else ""), pw.get_text())
        dlg.destroy()
        return result if resp == Gtk.ResponseType.OK and (ssid_entry is None or result[0]) else None


    def ask_ovpn(self, name, need):
        """Dialog for an OpenVPN profile's username/password and key passphrase -> (username, password, passphrase)
        with None for what isn't asked, or None when skipped."""
        dlg = Gtk.Dialog(transient_for=self.get_toplevel(), modal=True, title=f"VPN {name}")
        dlg.get_style_context().add_class("panel")
        dlg.set_default_size(380, -1)
        area = dlg.get_content_area()
        area.set_spacing(8)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, f"set_margin_{side}")(16)
        area.pack_start(label(f"Save the password for {name}", "title"), False, False, 0)
        area.pack_start(wrap(label("Kept in the VPN's profile (readable by root only), so connecting doesn't ask "
                                   "again. Skip = asked on each connect.", "dim")), False, False, 0)

        def secret(placeholder):
            e = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD, placeholder_text=placeholder)
            area.pack_start(e, False, False, 0)
            return e
        user = Gtk.Entry(text=need["username"], placeholder_text="Username") if need["password"] else None
        if user:
            area.pack_start(user, False, False, 0)
        pw = secret("Password") if need["password"] else None
        phrase = secret("Private key passphrase") if need["passphrase"] else None
        entries = [e for e in (pw, phrase) if e]
        show = Gtk.CheckButton(label="Show")
        show.connect("toggled", lambda c: [e.set_visibility(c.get_active()) for e in entries])
        area.pack_start(show, False, False, 0)
        dlg.add_button("Skip", Gtk.ResponseType.CANCEL)
        ok = dlg.add_button("Save", Gtk.ResponseType.OK)
        ok.get_style_context().add_class("primary")
        dlg.set_default_response(Gtk.ResponseType.OK)

        def changed(*_):
            ok.set_sensitive(all(e.get_text() for e in entries) and (user is None or bool(user.get_text().strip())))
        for e in (user, *entries):
            if e:
                e.connect("changed", changed)
                e.connect("activate", lambda _e: ok.get_sensitive() and dlg.response(Gtk.ResponseType.OK))
        changed()
        dlg.show_all()
        self.confirming = True
        try:
            resp = dlg.run()
        finally:
            self.confirming = False
        result = (user.get_text().strip() if user else None, pw.get_text() if pw else None,
                  phrase.get_text() if phrase else None)
        dlg.destroy()
        return result if resp == Gtk.ResponseType.OK else None


def build():
    return NetworkPage()

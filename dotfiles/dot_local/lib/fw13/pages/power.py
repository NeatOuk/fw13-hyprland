"""Power: battery state, time left/to full, health, power profile, 80 % charge limit, a read-only tuning readout,
screen & sleep timeouts (plugged in and on battery), low-battery warning levels (fw-battery-warn), hibernate status
and suspend-then-hibernate (both changed by `sudo fw-hibernate-setup` in fw-term; the page only reads)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import idle, power, store  # noqa: E402
from ..ui_theme import button  # noqa: E402
from .common import Page, label, launch  # noqa: E402


class PowerPage(Page):
    def __init__(self):
        super().__init__("Power")
        self.refresh()

    def refresh(self):
        self.clear()
        b = power.battery()
        can_hib = power.can_hibernate() in ("yes", "challenge")
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
                rb.connect("toggled", lambda r, n=name: r.get_active() and self.switch_profile(n))
                self.add_widget(rb)
        tun = power.tuning_rows()
        if tun:  # read-only: what the profile set (sysfs + tuned); refreshed with the page
            self.heading("Tuning")
            for title, value, hint in tun:
                self.row(title, label(value, "dim"), hint=hint)
        self.heading("Screen & sleep")
        cur = idle.get()
        rows = (("idle_dim", "Dim the screen after", "to 10 % brightness; any input restores it"),
                ("idle_lock", "Lock after", "SUPER+L locks right away"),
                ("idle_screen_off", "Turn the screen off after", None),
                ("idle_suspend", "Suspend after", "the laptop also locks before sleeping"))
        for suffix, title in (("", "Plugged in"), (idle.BAT, "On battery")):
            if suffix and not b:
                continue  # no battery: only the plugged-in timeouts apply
            self.add_widget(label(title, "dim"))
            for key, text, hint in rows:
                k = key + suffix
                combo = Gtk.ComboBoxText()
                for s in sorted(set(idle.CHOICES) | {cur[k]}):
                    combo.append(str(s), idle.label(s))
                combo.set_active_id(str(cur[k]))
                combo.connect("changed", lambda c, k=k: idle.write({k: int(c.get_active_id())}))
                self.row(text, combo, hint=hint)
            if suffix and can_hib:
                combo = Gtk.ComboBoxText()
                for value, text in power.HIBERNATE_CHOICES:
                    combo.append(value, text)
                combo.set_active_id(power.hibernate_delay())
                combo.connect("changed", lambda c: _term("sudo", "fw-hibernate-setup", "delay", c.get_active_id()))
                self.row("Then hibernate after", combo,
                         hint="on battery: suspend, then save to disk and power off; also when the lid closes")
            if suffix:
                combo = Gtk.ComboBoxText()
                for value, text in power.WARN_CHOICES:
                    combo.append(value, text)
                combo.set_active_id(store.get("battery_warn") or power.WARN_CHOICES[0][0])
                combo.connect("changed", lambda c: store.set("battery_warn", c.get_active_id()))
                self.row("Warn at", combo, hint="low-battery notifications; 10 and 5 % stay up, even in Focus and Zen")
        if b:
            self.heading("When the battery is very low")
            if can_hib:
                status, hint = "Hibernate: ready", "at the critical level the laptop suspends, then hibernates (UPower Auto)"
            elif power.disk_swap():
                status, hint = "Hibernate: not available", "check that Secure Boot / kernel lockdown is off"
            else:
                status, hint = "Hibernate: not set up (no disk swap)", "at the critical level the laptop only suspends"
            self.row(status, hint=hint)
            self.add_widget(button("Undo hibernate…" if can_hib else "Set up hibernate…",
                                   lambda: _term("sudo", "fw-hibernate-setup", *(["undo"] if can_hib else []))))
        if not b and not names:
            self.add_widget(label("No battery or power profile service found.", "dim"))
        self.show_all()

    def switch_profile(self, name):
        # The profile daemon applies EPP/platform profile a moment later; re-read the Tuning rows then.
        if power.set_profile(name):
            GLib.timeout_add(800, lambda: self.refresh() and False)


def _term(*cmd):
    launch("fw-term", "--hold", "-e", *cmd)


def build():
    return PowerPage()

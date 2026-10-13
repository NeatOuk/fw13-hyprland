"""Hardware sections of Settings → My Framework (pages/fw13.py): fan, keyboard backlight, fingerprint LED and read-only EC reports, over Framework's framework_tool
(install.sh, /usr/local/bin). The EC needs root, so changes run through pkexec (polkit asks) and reports open in a
terminal with sudo. Read without root: fan speed (cros_ec hwmon) and the keyboard backlight (LED class, set via
brightnessctl). The charge limit lives on the Power page (UPower). Flashing, key remapping, EC reboot and the
Laptop 12/16-only options are left out on purpose."""
import glob
import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import hyprsettings as hs  # noqa: E402
from ..hypr import hj  # noqa: E402
from .common import bg, label, launch  # noqa: E402

TOOL = "framework_tool"
TOUCH = "input.touchdevice.enabled"
KBD_LED = "chromeos::kbd_backlight"
FAN_MODES = [("auto", "Automatic"), ("25", "25 %"), ("50", "50 %"), ("75", "75 %"), ("100", "100 % (full)")]
HAPTIC_LEVELS = [("0", "Off"), ("25", "25 %"), ("50", "50 %"), ("75", "75 %"), ("100", "100 % (strongest)")]
FP_LEVELS = [("auto", "Automatic"), ("high", "High"), ("medium", "Medium"), ("low", "Low"), ("ultra-low", "Ultra low")]
REPORTS = [("--versions", "Firmware versions", "BIOS, EC, USB-C controllers, cards, SSD"),
           ("--power", "Battery and charger", "charge state, cycle count, adapter"),
           ("--thermal", "Temperatures and fan", "every EC sensor"),
           ("--privacy", "Privacy switches", "camera and microphone kill switches"),
           ("--pdports", "USB-C ports", "what each port is supplying or drawing"),
           ("--inputdeck", "Input modules", "keyboard, touchpad and their connectors"),
           ("--intrusion", "Chassis opened", "how often the bottom cover was removed"),
           ("--dp-hdmi-info", "Display expansion cards", "HDMI / DisplayPort card firmware and state"),
           ("--audio-card-info", "Audio expansion card", "firmware and state of a plugged-in audio card"),
           ("--s0ix-counter", "Deep sleep count", "how often the laptop reached hardware sleep (s0ix)"),
           ("--ec-hib-delay", "Power-off delay", "the current setting below, in seconds"),
           ("--console recent", "Controller log", "the EC's own recent log, for debugging")]
HIB_DELAYS = [("300", "5 minutes"), ("3600", "1 hour"), ("86400", "1 day")]


def fan_hwmon():
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            with open(os.path.join(d, "name")) as f:
                if f.read().strip() == "cros_ec" and os.path.exists(os.path.join(d, "fan1_input")):
                    return d
        except OSError:
            pass
    return None


def read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def kbd_path():
    p = f"/sys/class/leds/{KBD_LED}"
    return p if os.path.isdir(p) else None


def ec(*args):
    """Run framework_tool as root through polkit; returns (ok, message)."""
    r = subprocess.run(["pkexec", shutil.which(TOOL), *args], capture_output=True, text=True, timeout=60)
    if r.returncode == 0:
        return True, ""
    lines = (r.stderr or r.stdout).strip().splitlines()
    return False, lines[-1] if lines else "cancelled"


def haptic_touchpad():
    """True when a touchpad's HID descriptor has the Haptics usage page (0x0E): Framework's haptic touchpad."""
    for d in glob.glob("/sys/bus/hid/devices/*"):
        if not any(n.endswith("Touchpad") for n in map(read_text, glob.glob(f"{d}/input/input*/name"))):
            continue
        try:
            with open(f"{d}/report_descriptor", "rb") as f:
                if b"\x05\x0e" in f.read():
                    return True
        except OSError:
            pass
    return False


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def has_touchscreen():
    d = hj("devices")
    return isinstance(d, dict) and bool(d.get("touch"))


class Hardware:
    """Adds the Framework hardware sections to a page (heading/row/add_widget/set_status); the page calls
    render(page) on each rebuild. Keeps one 2 s timer for the fan speed."""

    def __init__(self, page):
        self.page = page
        self.hwmon = fan_hwmon()
        self.rpm = None
        if self.hwmon:
            timer = GLib.timeout_add_seconds(2, self.tick)
            page.connect("destroy", lambda _w: GLib.source_remove(timer))

    def render(self):
        page = self.page
        self.rpm = None
        if has_touchscreen():
            page.heading("Touch screen")
            sw = Gtk.Switch(active=bool(hs.get(TOUCH)))
            sw.connect("notify::active", lambda s, _p: self.set_touch(s.get_active()))
            page.row("Touch input", sw, hint="Off ignores touches on the screen; the touchpad keeps working")
        if not shutil.which(TOOL):
            return
        page.heading("Fan")
        if self.hwmon:
            self.rpm = label("", "dim")
            page.row("Speed now", self.rpm)
            self.tick()
        page.row("Fan mode", self.combo(FAN_MODES, self.set_fan),
                 hint="A fixed speed lasts until you pick Automatic again, or the laptop restarts")

        kbd = kbd_path()
        if kbd:
            page.heading("Keyboard backlight")
            mx = read_int(os.path.join(kbd, "max_brightness")) or 100
            cur = read_int(os.path.join(kbd, "brightness")) or 0
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
            scale.set_value(round(cur * 100 / mx))
            scale.set_size_request(220, -1)
            scale.connect("value-changed", lambda s: subprocess.Popen(
                ["brightnessctl", "-q", "-d", KBD_LED, "set", f"{int(s.get_value())}%"]))
            page.row("Brightness", scale, hint="Fn+Space cycles it too")

        if haptic_touchpad():
            page.heading("Touchpad")
            page.row("Haptic feedback", self.combo(HAPTIC_LEVELS, lambda v: self.run_ec("--haptic-intensity", v)),
                     hint="Strength of the click you feel; Off turns the vibration off")

        page.heading("Fingerprint reader")
        page.row("Power button LED", self.combo(FP_LEVELS, lambda v: self.run_ec("--fp-led-level", v)),
                 hint="Brightness of the light around the fingerprint reader")

        page.heading("When shut down")
        page.row("Fully power off after", self.combo(HIB_DELAYS, lambda v: self.run_ec("--ec-hib-delay", v)),
                 hint="Until then the controller stays awake (fast power-on, a little battery drain); "
                      "shorter keeps more charge while the laptop is off")

        page.heading("Hardware reports")
        for opt, title, hint in REPORTS:
            b = Gtk.Button(label="Show…")
            b.connect("clicked", lambda _b, o=opt: launch("fw-term", "--hold", "-e", "sudo", TOOL, *o.split()))
            page.row(title, b, hint=hint)
        page.add_widget(label("Reports open in a terminal and ask for your password (the EC needs root).",
                              "dim", wrap=True))

    @staticmethod
    def combo(items, on_pick):
        """A combo with no preselection: the EC's current setting can't be read without root."""
        c = Gtk.ComboBoxText()
        c.append("", "Choose…")
        for key, text in items:
            c.append(key, text)
        c.set_active_id("")
        c.connect("changed", lambda w: w.get_active_id() and on_pick(w.get_active_id()))
        return c

    def set_fan(self, mode):
        if mode == "auto":
            self.run_ec("--autofanctrl")
        else:
            self.run_ec("--fansetduty", mode)

    def set_touch(self, on):
        # on = back to the default (no override); the first change runs Hyprland --verify-config, so off the UI thread
        self.page.set_status("Saving…")
        bg(hs.write, self.touch_done, {TOUCH: None if on else False}, fail=str)

    def touch_done(self, err):
        self.page.set_status(err or "Done", "bad" if err else "ok")
        return False

    def run_ec(self, *args):
        self.page.set_status("Waiting for authorisation…")
        bg(ec, self.ec_done, *args, fail=lambda e: (False, str(e)))

    def ec_done(self, res):
        ok, msg = res
        self.page.set_status("Done" if ok else f"Not changed: {msg}", "ok" if ok else "bad")
        return False

    def tick(self):
        if self.rpm is not None:
            rpm = read_int(os.path.join(self.hwmon, "fan1_input"))
            self.rpm.set_text("off" if rpm == 0 else f"{rpm} rpm" if rpm is not None else "unknown")
        return True

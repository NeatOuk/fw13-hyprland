"""Sound: output and input devices (default + volume + mute) via wpctl, speaker sound (EasyEffects via fw13.speakers),
noise suppression."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .. import sound, speakers, store  # noqa: E402
from .common import Page, bg, label  # noqa: E402


class SoundPage(Page):
    def __init__(self):
        super().__init__("Sound")
        self.pending = {}
        self.noise_busy = False
        self.noise_note = ""
        self.refresh()

    def refresh(self):
        self.clear()
        devs = sound.devices()
        for key, title in (("sinks", "Output"), ("sources", "Input")):
            self.heading(title)
            if not devs[key]:
                self.add_widget(label("No devices", "dim"))
            for d in devs[key]:
                self.device_row(d)
        self.heading("Apps")
        playing = sound.apps()
        if not playing:
            self.add_widget(label("No app is playing sound", "dim"))
        for a in playing:
            self.app_row(a)
        self.speaker_section()
        self.heading("Microphone")
        self.noise_row()
        self.show_all()

    def device_row(self, d):
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("item")
        radio = Gtk.Button(label=("●  " if d["default"] else "○  ") + d["name"])
        radio.set_relief(Gtk.ReliefStyle.NONE)
        if d["default"]:
            radio.get_style_context().add_class("primary")
        radio.connect("clicked", lambda _b: (sound.set_default(d["id"]), self.refresh()))
        radio.get_child().set_ellipsize(Pango.EllipsizeMode.END)  # long device names: Settings at half a screen
        radio.get_child().set_xalign(0)
        radio.set_tooltip_text(d["name"])
        r.pack_start(radio, True, True, 0)
        mute = Gtk.ToggleButton(label="" if d["muted"] else "")
        mute.set_active(d["muted"])
        mute.connect("toggled", lambda b: (sound.set_mute(d["id"], b.get_active()),
                                           b.set_label("" if b.get_active() else "")))
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        vol.set_draw_value(False)
        vol.set_size_request(140, -1)
        vol.set_value(round(min(d["volume"], 1.0) * 100))
        pct = label(f"{int(vol.get_value())}%", width_chars=4, xalign=1)
        vol.connect("value-changed", self.on_volume, d["id"], pct)
        controls = Gtk.Box(spacing=12)
        controls.pack_start(mute, False, False, 0)
        controls.pack_start(vol, False, False, 0)
        controls.pack_start(pct, False, False, 0)
        controls.set_valign(Gtk.Align.CENTER)
        r.pack_end(controls, False, False, 0)
        self.adapt(r, controls)  # narrow: device name on its own line, controls under it
        self.add_widget(r)

    def app_row(self, a):
        """Per-app volume: like a device row, without the default choice."""
        mute = Gtk.ToggleButton(label="\uf6a9" if a["muted"] else "\uf028")
        mute.set_active(a["muted"])
        mute.connect("toggled", lambda b: (sound.set_mute(a["id"], b.get_active()),
                                           b.set_label("\uf6a9" if b.get_active() else "\uf028")))
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        vol.set_draw_value(False)
        vol.set_size_request(140, -1)
        vol.set_value(round(min(a["volume"], 1.0) * 100))
        pct = label(f"{int(vol.get_value())}%", width_chars=4, xalign=1)
        vol.connect("value-changed", self.on_volume, a["id"], pct)
        box = Gtk.Box(spacing=12)
        for w in (mute, vol, pct):
            box.pack_start(w, False, False, 0)
        self.row(a["name"], box)

    def speaker_section(self):
        if not speakers.available():
            return
        self.heading("Speaker sound")
        on = Gtk.Switch(active=speakers.enabled())
        on.connect("notify::active", lambda s, _p: speakers.set_enabled(s.get_active()))
        self.row("Speaker tuning", on, hint="Framework's speaker correction (EasyEffects), for the built-in speakers only")
        cur = speakers.preset()
        combo = Gtk.ComboBoxText()
        for key, text in speakers.PRESETS:
            combo.append(key, text)
        combo.set_active_id(cur)
        combo.connect("changed", lambda c: self.pick_preset(c.get_active_id()))
        self.row("Sound", combo, hint="Framework: fuller and louder · Clear voice: softer, clearer speech · "
                                      "Custom: the sliders below")
        if cur != speakers.CUSTOM:
            return
        vals = speakers.eq()
        for key, text in speakers.SLIDERS:
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -speakers.LIMIT, speakers.LIMIT, 0.5)
            scale.set_draw_value(False)
            scale.set_size_request(180, -1)
            scale.set_value(vals[key])
            scale.add_mark(0, Gtk.PositionType.BOTTOM, None)
            val = label(f"{vals[key]:+.1f} dB", width_chars=8, xalign=1)
            scale.connect("value-changed", self.on_eq, key, val)
            box = Gtk.Box(spacing=8)
            box.pack_start(scale, False, False, 0)
            box.pack_start(val, False, False, 0)
            hint = {"bass": "below 150 Hz", "warmth": "around 300 Hz (minus = less muddy)",
                    "voice": "around 3 kHz (speech, presence)", "air": "above 8 kHz (detail)",
                    "level": "overall loudness"}[key]
            self.row(text, box, hint=hint)

    def pick_preset(self, name):
        store.set("speaker_preset", name)  # now, so the rebuilt page shows it; writing + loading runs in the background
        bg(speakers.apply, lambda _r: False, name)
        GLib.idle_add(lambda: self.refresh() and False)  # not from inside the combo's own signal

    def on_eq(self, scale, key, val):
        val.set_text(f"{scale.get_value():+.1f} dB")
        vals = dict(speakers.eq(), **self.pending.get("eq_vals", {}))
        vals[key] = scale.get_value()
        self.pending["eq_vals"] = vals
        if self.pending.get("eq"):
            GLib.source_remove(self.pending["eq"])

        def flush():  # one rewrite + reload after the drag settles
            self.pending["eq"] = None
            bg(speakers.apply, lambda _r: False, speakers.CUSTOM, self.pending.pop("eq_vals"))
            return False
        self.pending["eq"] = GLib.timeout_add(350, flush)

    def noise_row(self):
        sw = Gtk.Switch(active=sound.noise_suppression())
        sw.set_sensitive(not self.noise_busy)
        sw.connect("state-set", self.on_noise)
        self.row("Noise suppression", sw, hint="Adds a Noise-cancelled microphone (WebRTC) and makes it the default; "
                 "switching restarts the audio, so sound drops out for a moment")
        if self.noise_busy or self.noise_note:
            self.add_widget(label("Restarting audio\u2026" if self.noise_busy else self.noise_note, "dim"))

    def on_noise(self, _sw, on):
        if not self.noise_busy:
            self.noise_busy, self.noise_note = True, ""
            self.refresh()
            bg(sound.set_noise_suppression, self.done_noise, on)
        return True  # the switch is rebuilt from the drop-in's presence

    def done_noise(self, res):
        self.noise_busy, self.noise_note = False, res[1]
        self.refresh()

    def on_volume(self, scale, node_id, pct):
        pct.set_text(f"{int(scale.get_value())}%")
        if self.pending.get(node_id):
            GLib.source_remove(self.pending[node_id])

        def flush():
            self.pending[node_id] = None
            sound.set_volume(node_id, scale.get_value() / 100)
            return False
        self.pending[node_id] = GLib.timeout_add(60, flush)


def build():
    return SoundPage()

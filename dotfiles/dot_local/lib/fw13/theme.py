"""Desktop colours: Tokyo Night, or a palette generated from the wallpaper with matugen.

The base configs (hypr theme.lua, hyprlock.conf, waybar style.css, fuzzel.ini, mako, kitty.conf, ghostty) hold no colours;
they include the files this module writes into ~/.config/fw13/theme/. chezmoi seeds those once (create_) with
render(TOKYO_NIGHT), so a fresh install looks the same as before.

GTK and Qt apps follow too (read at app start; GTK 3 also live, see apply_gtk()):
  gtk3.css / gtk4.css   libadwaita named colours (@define-color; gtk4.css also the --*-color variables). GTK 3 and
                        plain GTK 4 apps get them through the "fw13" GTK theme in ~/.local/share/themes/fw13, which
                        is adw-gtk3[-dark] plus gtk3.css/gtk4.css; libadwaita apps ignore GTK themes and read
                        ~/.config/gtk-4.0/gtk.css, which @imports gtk4.css (only when that file is ours, see
                        link_gtk()).
  ghostty               Ghostty colours; ~/.config/ghostty/config includes it (optional: "?" path).
  grub/                 GRUB boot menu (theme.txt + images), drawn by fw13.grub when `sudo fw-grub-theme` runs.
  qt6ct-colors.conf     qt6ct colour scheme; ~/.config/qt6ct/qt6ct.conf points at it and ~/.config/uwsm/env-hyprland
                        sets QT_QPA_PLATFORMTHEME=qt6ct for the Hyprland session only (new Qt apps after re-login).
  fcitx5-theme.conf     fcitx5 classic UI theme; ~/.local/share/fcitx5/themes/fw13/theme.conf links to it
                        (link_fcitx()) and classicui.conf selects it in Hyprland sessions (apply_fcitx()).
These are not chezmoi seeds: ensure_files() (init(), run_once) writes them from the current palette, so an
upgrade of a wallpaper-following install does not start out with Tokyo Night GTK/Qt/Ghostty colours.

Apps with their own settings files, changed only from a Hyprland session:
  Chromium   GTK mode (extensions.theme.system_theme) once per profile at login, unless the user chose a theme
             (chromium_gtk()); it then takes its colours from the fw13 GTK theme. GNOME's Chromium too (Adwaita).
             Opt-in switch (store CHROMIUM_FORCE) replaces a chosen theme with GTK mode at every login (_chromium_force()).
  VS Code    on by default, switch in Settings → Appearance (store VSCODE_ON): theme-scoped workbench.colorCustomizations, removed at logout.
Terminal tools (btop's TTY theme, fzf --color=16, bat's ansi theme) use kitty's 16 colours: nothing to write.

Other desktops on the same account (Fedora Workstation/KDE bases, CLAUDE.md 3a): gtk-theme and color-scheme
(org.gnome.desktop.interface, dconf) and ~/.config/gtk-4.0/gtk.css are per user, not per session. So they are only
set from a Hyprland session, the values they replace are saved first (store key GTK_SAVED), and session_end() /
restore_gtk() put them back and remove our gtk-4.0/gtk.css (the same for fcitx5's Theme and the VS Code block);
session_start() re-applies at the next Hyprland login (`python3 -m fw13.theme session-start|session-end`). Until
a session_end() runs (e.g. after a crash), GNOME shows the fw13 GTK theme and our light/dark choice; KDE resets
gtk-theme itself at Plasma login.

State lives in fw13.store under "theme":
  {"source": "tokyo-night" | "wallpaper", "mode": "dark" | "light", "type": "scheme-tonal-spot",
   "pick": "colourful" | "0".."3" (matugen's source colour: most saturated candidate, or candidate N, 0 = most of
   the image), "wallpaper": path, "palette": {...last generated}}
Palette values are "#rrggbb" ("shadow" is "#rrggbbaa"); "ansi" is the 16 terminal colours.
"""
import colorsys
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from . import store
from .hypr import lua

DIR = os.path.expanduser("~/.config/fw13/theme")
SOURCES = ("tokyo-night", "wallpaper")
MODES = ("dark", "light")
TYPES = ("scheme-tonal-spot", "scheme-content", "scheme-expressive", "scheme-vibrant", "scheme-neutral",
         "scheme-monochrome", "scheme-fidelity", "scheme-rainbow", "scheme-fruit-salad")
DEFAULT_TYPE = "scheme-tonal-spot"
PICKS = ("colourful", "0", "1", "2", "3")

# The Linux console's default VGA black and grey: what tuigreet (no --theme) shows on the login screen; hyprlock copies it
TTY = {"bg": "#000000", "fg": "#aaaaaa"}

TOKYO_NIGHT = {
    "bg": "#1a1b26", "bg_dim": "#16161e",
    "surface": "#1f2335", "surface2": "#292e42", "surface3": "#3b4261",
    "fg": "#a9b1d6", "fg_bright": "#c0caf5", "fg_dim": "#565f89", "muted": "#414868",
    "accent": "#7aa2f7", "accent2": "#bb9af7",
    "ok": "#9ece6a", "warn": "#e0af68", "bad": "#f7768e",
    "border": "#7aa2f7", "shadow": "#1a1a1aee",
    "ansi": ["#15161e", "#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6",
             "#414868", "#ff7a93", "#b9f27c", "#ff9e64", "#7da6ff", "#bb9af7", "#0db9d7", "#c0caf5"],
}
# Tokyo Night Day (folke/tokyonight.nvim's light style): Light under Tokyo Night, and light parts of a Custom look
TOKYO_DAY = {
    "bg": "#e1e2e7", "bg_dim": "#d0d5e3",
    "surface": "#d6d8e1", "surface2": "#c4c8da", "surface3": "#b6bbd2",
    "fg": "#3760bf", "fg_bright": "#1f2a5c", "fg_dim": "#6172b0", "muted": "#a8aecb",
    "accent": "#2e7de9", "accent2": "#9854f1",
    "ok": "#587539", "warn": "#8c6c3e", "bad": "#c4204f",
    "border": "#2e7de9", "shadow": "#00000066",
    "ansi": ["#e9e9ed", "#f52a65", "#587539", "#8c6c3e", "#2e7de9", "#9854f1", "#007197", "#6172b0",
             "#a1a6c5", "#f52a65", "#587539", "#8c6c3e", "#2e7de9", "#9854f1", "#007197", "#3760bf"],
}
ROLES = tuple(k for k in TOKYO_NIGHT if k != "ansi")


def _tokyo(mode):
    """Tokyo Night as shipped, or Tokyo Night Day raised to the light contrast minimums (adjust() is defined below)."""
    if mode != "light":
        return dict(TOKYO_NIGHT)
    p = adjust(TOKYO_DAY, "light")
    return {**p, "ansi": [p["ansi"][0], *(ensure(c, p["bg"], ANSI_MIN["light"][0]) for c in p["ansi"][1:7]),
                          p["fg"], ensure(p["ansi"][8], p["bg"], ANSI_MIN["light"][1]),
                          *(ensure(c, p["bg"], ANSI_MIN["light"][0]) for c in p["ansi"][9:15]), p["fg_bright"]]}


# ---- colour maths -------------------------------------------------------------------------------------------

def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(min(max(v, 0.0), 1.0) * 255):02x}" for v in rgb)


def _lum(c):
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    """WCAG 2 contrast ratio (1–21)."""
    a, b = sorted((_lum(fg[:7]), _lum(bg[:7])), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _hsl(c):
    h, li, s = colorsys.rgb_to_hls(*_rgb(c))
    return h * 360, s, li


def _from_hsl(h, s, li):
    return _hex(colorsys.hls_to_rgb((h % 360) / 360, li, s))


def ensure(fg, bg, ratio):
    """`fg` with its HSL lightness moved away from `bg` until contrast(fg, bg) >= ratio (or it can't go further)."""
    if contrast(fg, bg) >= ratio:
        return fg
    h, s, li = _hsl(fg)
    step = 0.01 if _lum(bg) < 0.18 else -0.01  # dark background: lighten; light: darken
    out = fg
    while 0.0 <= li <= 1.0 and contrast(out, bg) < ratio:
        li += step
        out = _from_hsl(h, s, min(max(li, 0.0), 1.0))
    return out


# Minimum contrast against bg for each role that is read as text or as an accent line. muted (inactive
# workspace numbers, inactive borders) is meant to recede: 2 keeps it about as visible as Tokyo Night's (1.9);
# matugen's light outline_variant is ~1.6 without it.
MIN_CONTRAST = {"fg": 4.5, "fg_bright": 4.5, "accent": 3, "accent2": 3, "ok": 4.5, "warn": 4.5, "bad": 4.5,
                "border": 3, "muted": 2}


# Light palettes read weaker than dark ones at the same ratio (matugen's light text is a mid brown, and Glossy
# light puts it over a blurred wallpaper), so they get roughly the dark palette's measured contrast.
MIN_CONTRAST_LIGHT = {"fg": 10, "fg_bright": 14, "fg_dim": 6, "accent": 7, "accent2": 7, "ok": 7, "warn": 7,
                      "bad": 7, "border": 4, "muted": 2.5}
ANSI_MIN = {"dark": (4.5, 3), "light": (7, 6)}  # (colours, bright black) against bg
DIM_LIGHT = 0.75  # terminals' dim-text opacity on light palettes (dark keeps kitty 0.4 / Ghostty 0.5)


def adjust(p, mode="dark"):
    """A copy of palette `p` meeting MIN_CONTRAST (MIN_CONTRAST_LIGHT for light) against p["bg"]. For matugen
    palettes and Tokyo Night Day; Tokyo Night is shipped as is."""
    out = dict(p)
    for role, ratio in (MIN_CONTRAST_LIGHT if mode == "light" else MIN_CONTRAST).items():
        out[role] = ensure(out[role], out["bg"], ratio)
    return out


def _harmonize(c, toward, limit=15.0):
    """Rotate the hue of `c` toward `toward` by half the difference, at most `limit` degrees (Material-style)."""
    h, s, li = _hsl(c)
    d = (_hsl(toward)[0] - h + 180) % 360 - 180
    return _from_hsl(h + max(-limit, min(limit, d / 2)), s, li)


def _hue_near(c, hue, tol):
    h, s, _ = _hsl(c)
    return s > 0.2 and abs((h - hue + 180) % 360 - 180) <= tol


def _dark(p):
    return _lum(p["bg"]) < 0.18


def _on(c, p):
    """Text colour for a fill of `c`: the palette's bg or fg_bright, whichever reads better."""
    return max((p["bg"], p["fg_bright"]), key=lambda t: contrast(t, c))


def _shade(c, d):
    """`c` with its HSL lightness moved by `d` (-1..1)."""
    h, s, li = _hsl(c)
    return _from_hsl(h, s, min(max(li + d, 0.0), 1.0))


# ---- matugen ------------------------------------------------------------------------------------------------

def _matugen(path, mode, scheme_type, pick="colourful"):
    how = ["--prefer", "saturation"] if pick == "colourful" else ["--source-color-index", pick]
    cmd = ["matugen", "image", path, "--dry-run", "--json", "hex", "-m", mode, *how, "-t", scheme_type]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                           env={**os.environ, "NO_COLOR": "1"})
    except FileNotFoundError:
        raise RuntimeError("matugen is not installed") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("matugen took too long") from None
    if r.returncode:
        # First line is the cause (e.g. a decode error); a panic's backtrace hint follows it.
        lines = [ln.strip() for ln in r.stderr.splitlines() if ln.strip()]
        if any("unexpected argument" in ln for ln in lines):  # Fedora's matugen 3.x
            raise RuntimeError("matugen 4 or newer is needed (install.sh installs it from the Hyprland COPR)")
        raise RuntimeError(lines[0][:200] if lines else "matugen failed")
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise RuntimeError("matugen returned no colours") from None


def _ansi_base16(b16, p, mode):
    """ANSI from matugen's base16 if it reads like a terminal scheme on our bg, else None.

    matugen's base16 is sampled from the image (base00 is often a mid-tone, base08 rarely red), so this is
    mostly a guard; the usual result is the Tokyo Night hues below.
    """
    try:
        c = {k: b16[k][mode]["color"] for k in ("base00", "base03", "base05", "base07", "base08", "base0a",
                                                 "base0b", "base0c", "base0d", "base0e")}
    except (KeyError, TypeError):
        return None
    hues = (("base08", 0, 30), ("base0b", 120, 45), ("base0a", 50, 30), ("base0d", 220, 40))
    if contrast(c["base00"], p["bg"]) > 1.25 or contrast(c["base05"], p["bg"]) < 4.5:
        return None
    if any(contrast(c[k], p["bg"]) < ANSI_MIN[mode][0] for k in ("base08", "base0a", "base0b", "base0c", "base0d", "base0e")):
        return None
    if not all(_hue_near(c[k], hue, tol) for k, hue, tol in hues):
        return None
    six = [c[k] for k in ("base08", "base0b", "base0a", "base0d", "base0e", "base0c")]
    return [c["base00"], *six, c["base05"], c["base03"], *six, c["base07"]]


def _ansi(p, mode="dark"):
    """Tokyo Night's hues, harmonised toward the accent and made readable on bg; black/white from the palette."""
    colours, grey = ANSI_MIN[mode]
    tn = TOKYO_NIGHT["ansi"]
    black = p["bg_dim"] if _lum(p["bg"]) < 0.18 else p["surface3"]
    out = [black] + [None] * 6 + [p["fg"], p["fg_dim"]] + [None] * 6 + [p["fg_bright"]]
    for i in list(range(1, 7)) + list(range(9, 15)):
        out[i] = ensure(_harmonize(tn[i], p["accent"]), p["bg"], colours)
    out[8] = ensure(out[8], p["bg"], grey)
    return out


def source_colors(path):
    """matugen's candidate source colours for `path`, most of the image first ([] on failure)."""
    try:
        r = subprocess.run(["matugen", "image", path, "--show-source-colors", "-m", "dark"], capture_output=True,
                           text=True, timeout=60, stdin=subprocess.DEVNULL, env={**os.environ, "NO_COLOR": "1"})
    except (OSError, subprocess.TimeoutExpired):
        return []
    return re.findall(r"#[0-9a-fA-F]{6}", r.stdout)[:len(PICKS) - 1]


def from_wallpaper(path, mode="dark", scheme_type=DEFAULT_TYPE, pick="colourful"):
    """Palette for `path` (jpg/png/jxl) via matugen. Raises RuntimeError with a short message on failure."""
    mode = mode if mode in MODES else "dark"
    scheme_type = scheme_type if scheme_type in TYPES else DEFAULT_TYPE
    data = _matugen(path, mode, scheme_type, pick if pick in PICKS else "colourful")
    try:
        m = {k: v[mode]["color"] for k, v in data["colors"].items()}
        p = {
            "bg": m["surface"], "bg_dim": m["surface_container_lowest"],
            "surface": m["surface_container"], "surface2": m["surface_container_high"],
            "surface3": m["surface_container_highest"],
            "fg": m["on_surface_variant"], "fg_bright": m["on_surface"], "fg_dim": m["outline"],
            "muted": m["outline_variant"],
            "accent": m["primary"], "accent2": m["tertiary"], "bad": m["error"], "border": m["primary"],
            "shadow": m["shadow"] + ("ee" if mode == "dark" else "66"),
        }
    except (KeyError, TypeError):
        raise RuntimeError("matugen output is missing colours") from None
    # Material has no success/warning roles: Tokyo Night's green/yellow, hue nudged toward the accent.
    p["ok"] = _harmonize(TOKYO_NIGHT["ok"], p["accent"])
    p["warn"] = _harmonize(TOKYO_NIGHT["warn"], p["accent"])
    p = adjust(p, mode)
    p["ansi"] = _ansi_base16(data.get("base16") or {}, p, mode) or _ansi(p, mode)
    return p


# ---- state --------------------------------------------------------------------------------------------------

def state():
    t = store.get("theme")
    t = t if isinstance(t, dict) else {}
    return {"source": t.get("source") if t.get("source") in SOURCES else "tokyo-night",
            "mode": t.get("mode") if t.get("mode") in MODES else "dark",
            "type": t.get("type") if t.get("type") in TYPES else DEFAULT_TYPE,
            "pick": t.get("pick") if t.get("pick") in PICKS else "colourful",
            "wallpaper": t.get("wallpaper"), "palette": t.get("palette")}


def _valid(p):
    return (isinstance(p, dict) and all(isinstance(p.get(k), str) and p[k].startswith("#") for k in ROLES)
            and isinstance(p.get("ansi"), list) and len(p["ansi"]) == 16)


def palette():
    """The main palette (apps): the last generated one when following the wallpaper, else Tokyo Night (Day)."""
    s = state()
    if s["source"] == "wallpaper" and _valid(s["palette"]):
        return s["palette"]
    return _tokyo(s["mode"])


# ---- rendering ----------------------------------------------------------------------------------------------

def _h(c):
    return c.lstrip("#")[:6]


def _a(c, alpha="ff"):
    return _h(c) + alpha


LOOK = "theme_look"  # fw13.store key: Appearance → Look = {"look", "parts": {part: look}, "clear"}
GLASS = "theme_glass"  # the earlier Glass switches, read once to fill LOOK
LOOKS = ("dark", "light", "glossy", "glossy_light", "custom")  # Custom = a look per part
PART_LOOKS = ("dark", "light", "glossy", "glossy_light")  # glossy = Glossy dark; both see-through and blurred
GLOSSY = {"glossy": "dark", "glossy_light": "light"}  # glossy look → its colours
GLASS_PARTS = ("bar", "menus", "panels", "apps")  # bar · launcher/menus + notifications · fw13 panels + Settings · app windows
GLASS_CLEAR = (10, 90, 55)  # See-through %: min, max, default
SHEEN = "#ffffff"  # the glossy highlight on glass surfaces
ALT = "theme_alt"  # fw13.store key: the wallpaper palette in the other mode, for parts that differ from the apps


def _clamp_clear(v):
    lo, hi, default = GLASS_CLEAR
    return min(hi, max(lo, int(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def look_state():
    """{"look", "parts": {part: dark|light|glossy|glossy_light}, "clear"}. Parts follow the look unless it is Custom; without
    a stored LOOK the old Glass switches give Custom (glossy where on) and the palette's mode gives the rest."""
    v = store.get(LOOK)
    base = state()["mode"]
    if not isinstance(v, dict):
        g = store.get(GLASS)
        g = {"bar": True, "menus": True, "panels": True} if g is True else (g if isinstance(g, dict) else {})
        on = {k: "glossy" for k in GLASS_PARTS if g.get(k) is True}
        v = {"look": "custom" if on else base, "parts": on, "clear": g.get("clear")}
    lk = v.get("look") if v.get("look") in LOOKS else base
    stored = v.get("parts") if isinstance(v.get("parts"), dict) else {}
    parts = {k: (stored.get(k) if lk == "custom" and stored.get(k) in PART_LOOKS else
                 base if lk == "custom" else lk) for k in GLASS_PARTS}
    return {"look": lk, "parts": parts, "clear": _clamp_clear(v.get("clear"))}


def look():
    return look_state()["look"]


def part_look(part, ls=None):
    return (ls or look_state())["parts"][part]


def part_mode(part, ls=None):
    """The colours a part is drawn in (Glossy dark / Glossy light → dark / light)."""
    pl = part_look(part, ls)
    return GLOSSY.get(pl, pl)


def glass(part=None):
    ls = look_state()
    return part_look(part, ls) in GLOSSY if part else any(v in GLOSSY for v in ls["parts"].values())


def glass_alpha(part, ls=None):
    """How solid a part is (0–1); the terminal is the benchmark. App windows: 1 − See-through × 0.25 (Hyprland's
    window opacity). Every other glossy part looks like a terminal: Terminal Opacity × the app windows' value
    (when those are glossy). For fw13's own *windows* (Settings) Hyprland already applies the app opacity, so
    ui_theme uses window_alpha() there instead."""
    ls = ls or look_state()
    if part_look(part, ls) not in GLOSSY:
        return 1.0
    apps = round(1 - ls["clear"] / 100 * 0.25, 2)
    if part == "apps":
        return apps
    return round(window_alpha() * (apps if part_look("apps", ls) in GLOSSY else 1), 2)


def window_alpha():
    """The terminal's own opacity: what an fw13 window's CSS background uses, under Hyprland's window opacity."""
    return terminal_look()["opacity"]


def set_look(look=None, part=None, value=None, clear=None):
    """Store one Look change (the look, one part's look under Custom, or See-through). Returns the mode the
    main palette (= the apps') must be rebuilt in when that changed (the caller runs set_source), else None."""
    cur = look_state()
    new = {"look": cur["look"], "parts": dict(cur["parts"]), "clear": cur["clear"]}
    if look in LOOKS:
        new["look"] = look
        if look != "custom":
            new["parts"] = {k: look for k in GLASS_PARTS}
    if part in GLASS_PARTS and value in PART_LOOKS:
        new["look"], new["parts"] = "custom", {**new["parts"], part: value}
    if clear is not None:
        new["clear"] = _clamp_clear(clear)
    store.set(LOOK, new)
    mode = part_mode("apps", look_state())
    return mode if mode != state()["mode"] else None


def palette_for(mode):
    """The palette in `mode`: the main one when it matches, else Tokyo Night (Day) or the wallpaper's other-mode
    palette (made with matugen once per wallpaper/style/pick, kept in ALT). Falls back to the main palette."""
    s = state()
    if mode == s["mode"]:
        return palette()
    if s["source"] != "wallpaper":
        return _tokyo(mode)
    key = [s["wallpaper"], s["type"], s["pick"], mode]
    alt = store.get(ALT)
    if isinstance(alt, dict) and alt.get("key") == key and _valid(alt.get("palette")):
        return alt["palette"]
    try:
        p = from_wallpaper(s["wallpaper"], mode, s["type"], s["pick"])
    except (RuntimeError, OSError, TypeError):
        return palette()
    store.set(ALT, {"key": key, "palette": p})
    return p


def part_palette(part):
    return palette_for(part_mode(part))


def reload_hyprland():
    """looknfeel.lua reads hypr.lua's glass keys only at config load."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        _quiet("hyprctl", "reload")


def _hypr_values(p):
    """Hyprland colour strings; keys are what looknfeel.lua reads as theme.*."""
    shadow = p["shadow"].lstrip("#")
    return {"accent": f"rgb({_h(p['accent'])})", "magenta": f"rgb({_h(p['accent2'])})",
            "bg": f"rgb({_h(p['bg'])})", "muted": f"rgb({_h(p['muted'])})",
            "shadow": f"rgba({shadow if len(shadow) == 8 else shadow + 'ee'})"}


HEAD = "Written by fw13.theme (Settings → Appearance). Changes here are replaced."

FONT = "font"  # fw13.store key: one font for the bar, menus, notifications, lock screen, panels and terminals
DEFAULT_FONT = "JetBrains Mono"


def _font_ok(name):
    """A family name safe to write into every config format (no quotes, newlines or separators)."""
    return isinstance(name, str) and re.fullmatch(r"\w[\w .+&-]{0,63}", name) is not None


def fonts():
    """Installed monospace font families, sorted: the font also drives the terminals, so it has to be fixed-width."""
    try:
        out = subprocess.run(["fc-list", ":spacing=mono", "family"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    names = {line.split(",")[0].strip() for line in out.splitlines()}
    return sorted({n for n in names if _font_ok(n) and "Emoji" not in n} | {DEFAULT_FONT}, key=str.lower)


def font():
    name = store.get(FONT)
    return name if _font_ok(name) else DEFAULT_FONT


def set_font(name):
    """Store `name`, rewrite every generated file and reload the apps. Returns None or an error message."""
    if name not in fonts():
        return f"Font not installed: {name}"
    old = store.get(FONT)
    store.set(FONT, name)
    try:
        write(palette())
    except OSError as e:
        store.set(FONT, old)  # the choice shown must match the files
        return f"Could not write the theme files: {e}"
    return None


TERMINAL = "terminal_look"  # fw13.store key: the Terminal section of Settings → Appearance, for kitty and Ghostty
TERMINAL_DEFAULT = {"size": 11.5, "opacity": 0.9, "padding": 14, "line": 100, "cursor": "block", "blink": True,
                    "bold": True, "ligatures": True}
TERMINAL_RANGE = {"size": (8, 24), "opacity": (0.5, 1.0), "padding": (0, 40), "line": (80, 160)}  # line: % of cell
CURSORS = {"block": ("block", "block"), "beam": ("beam", "bar"), "underline": ("underline", "underline")}  # kitty, Ghostty


HINTS_OFF = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "fw13",
                         "terminal-hints-off")  # read by ~/.bashrc.local: no key hint in the prompt


def terminal_look():
    """The stored terminal look, each value clamped to TERMINAL_RANGE (a hand-edited store can't break the configs)."""
    saved = store.get(TERMINAL)
    saved = saved if isinstance(saved, dict) else {}
    out = {}
    for k, lo_hi in TERMINAL_RANGE.items():
        v, d = saved.get(k), TERMINAL_DEFAULT[k]
        out[k] = min(max(float(v), lo_hi[0]), lo_hi[1]) if isinstance(v, (int, float)) and not isinstance(v, bool) else d
    out["padding"], out["line"] = int(out["padding"]), int(out["line"])
    out["cursor"] = saved.get("cursor") if saved.get("cursor") in CURSORS else TERMINAL_DEFAULT["cursor"]
    for k in ("blink", "bold", "ligatures"):
        out[k] = saved.get(k) if isinstance(saved.get(k), bool) else TERMINAL_DEFAULT[k]
    out["hints"] = not os.path.exists(HINTS_OFF)
    return out


def set_terminal(key, value):
    """Store one terminal value, rewrite only the kitty and Ghostty theme files and reload both (cheap: a slider
    calls this while it moves). Returns None or an error message."""
    if key == "hints":  # a marker file for the shell, not a terminal config line; new terminals pick it up
        try:
            if value:
                if os.path.exists(HINTS_OFF):
                    os.remove(HINTS_OFF)
            else:
                os.makedirs(os.path.dirname(HINTS_OFF), exist_ok=True)
                open(HINTS_OFF, "w").close()
        except OSError as e:
            return f"Could not change the key hint: {e}"
        return None
    if key not in TERMINAL_DEFAULT:
        return f"Unknown terminal setting: {key}"
    store.set(TERMINAL, {k: v for k, v in {**terminal_look(), key: value}.items() if k != "hints"})
    files = render(palette())
    try:
        os.makedirs(DIR, exist_ok=True)
        for name in ("kitty.conf", "ghostty", "waybar.css"):  # a glossy bar follows the terminal's Opacity
            _atomic(os.path.join(DIR, name), files[name])
    except OSError as e:
        return f"Could not write the terminal files: {e}"
    _quiet("pkill", "-SIGUSR2", "-x", "waybar")
    _quiet("pkill", "-SIGUSR1", "-x", "kitty")
    _quiet("pkill", "-SIGUSR2", "-x", "ghostty")
    return None


def _gtk_colors(p):
    """libadwaita / adw-gtk3 named colours for palette `p` (same roles as fw-settings' own ui_theme)."""
    dark = _dark(p)

    def text(c):  # standalone coloured text (links, warning labels) on window and view backgrounds
        return ensure(ensure(c, p["bg"], 4.5), p["bg_dim"], 4.5)
    raised = p["surface2"] if dark else p["bg_dim"]  # popovers/dialogs: lighter than the window in both modes
    c = {}
    for name, role in (("accent", "accent"), ("destructive", "bad"), ("success", "ok"), ("warning", "warn"),
                       ("error", "bad")):
        c[f"{name}_bg_color"] = p[role]
        c[f"{name}_fg_color"] = _on(p[role], p)
        c[f"{name}_color"] = text(p[role])
    c.update({
        "window_bg_color": p["bg"], "window_fg_color": p["fg"],
        "view_bg_color": p["bg_dim"], "view_fg_color": p["fg_bright"],
        "headerbar_bg_color": p["surface"], "headerbar_fg_color": p["fg_bright"],
        "headerbar_border_color": p["fg_bright"], "headerbar_backdrop_color": p["bg"],
        "sidebar_bg_color": p["bg_dim"], "sidebar_fg_color": p["fg"],
        "sidebar_backdrop_color": p["bg_dim"], "sidebar_border_color": p["surface2"],
        "secondary_sidebar_bg_color": p["bg"], "secondary_sidebar_fg_color": p["fg"],
        "secondary_sidebar_backdrop_color": p["bg"], "secondary_sidebar_border_color": p["surface2"],
        "card_bg_color": p["surface"] if dark else p["bg_dim"], "card_fg_color": p["fg_bright"],
        "popover_bg_color": raised, "popover_fg_color": p["fg_bright"],
        "dialog_bg_color": raised, "dialog_fg_color": p["fg_bright"],
        "thumbnail_bg_color": raised, "thumbnail_fg_color": p["fg_bright"],
        "borders": p["surface3"], "unfocused_borders": p["surface2"],
    })
    return {k: v[:7] for k, v in c.items()}


def _gtk_css(p, variables):
    lines = [f"/* {HEAD} */"] + [f"@define-color {k} {v};" for k, v in _gtk_colors(p).items()]
    if variables:  # libadwaita >= 1.6 styles with CSS variables; the named colours above are only aliases there
        lines += [":root {"] + [f"  --{k.replace('_', '-')}: {v};" for k, v in _gtk_colors(p).items()
                                if k.endswith("_color")] + ["}"]
    return "\n".join(lines) + "\n"


# QPalette::ColorRole order, as in qt6ct's colour schemes (/usr/share/qt6ct/colors/*.conf): 21 entries per line.
QT_ROLES = ("WindowText", "Button", "Light", "Midlight", "Dark", "Mid", "Text", "BrightText", "ButtonText",
            "Base", "Window", "Shadow", "Highlight", "HighlightedText", "Link", "LinkVisited", "AlternateBase",
            "NoRole", "ToolTipBase", "ToolTipText", "PlaceholderText")


def _qt_scheme(p):
    """qt6ct colour scheme text. Window/WindowText/Base/Highlight (what Citadel and most Qt apps paint with)
    are bg/fg/surface/accent; Light..Mid are bevel shades of Button for the Fusion style."""
    dark = _dark(p)
    button = p["surface2"]
    active = {
        "WindowText": p["fg"], "Button": button,
        "Light": _shade(button, 0.15), "Midlight": _shade(button, 0.07),
        "Dark": _shade(button, -0.15), "Mid": _shade(button, -0.07),
        "Text": p["fg_bright"], "BrightText": p["fg_bright"] if dark else p["bg_dim"], "ButtonText": p["fg_bright"],
        "Base": p["surface"], "Window": p["bg"], "Shadow": "#000000",
        "Highlight": p["accent"], "HighlightedText": _on(p["accent"], p),
        "Link": ensure(p["accent"], p["surface"], 4.5), "LinkVisited": ensure(p["accent2"], p["surface"], 4.5),
        "AlternateBase": p["surface2"], "NoRole": p["bg"],
        "ToolTipBase": p["surface2"], "ToolTipText": p["fg_bright"], "PlaceholderText": p["fg_dim"],
    }
    disabled = dict(active)
    for role in ("WindowText", "Text", "ButtonText", "HighlightedText", "BrightText"):
        disabled[role] = p["fg_dim"]
    disabled["Highlight"] = p["surface3"]

    def line(colors):
        return ", ".join("#ff" + _h(colors[r]) for r in QT_ROLES)
    return (f"; {HEAD}\n[ColorScheme]\n"
            f"active_colors={line(active)}\n"
            f"disabled_colors={line(disabled)}\n"
            f"inactive_colors={line(active)}\n")


def _fcitx_theme(p):
    """fcitx5 classic UI theme (candidate popup and its menu), laid out like fcitx5's default-dark. The page and
    menu images are links to default-dark's (link_fcitx()). No [AccentColorField]: with it, fcitx5 would paint
    those parts in the desktop portal's accent colour instead of ours."""
    sel, on_sel = p["accent"], _on(p["accent"], p)
    lines = [f"# {HEAD}", "[Metadata]", "Name=fw13", "Version=1", "Author=fw13",
             "Description=fw13 palette (Settings → Appearance)", "ScaleWithDPI=True", ""]

    def margins(section, n):
        return [f"[{section}]", f"Left={n}", f"Right={n}", f"Top={n}", f"Bottom={n}", ""]
    lines += ["[InputPanel]", f"NormalColor={p['fg_bright']}", f"HighlightCandidateColor={on_sel}",
              f"HighlightColor={p['accent']}", f"HighlightBackgroundColor={p['surface2']}",
              "PageButtonAlignment=Last Candidate", ""]
    lines += margins("InputPanel/TextMargin", 5) + margins("InputPanel/ContentMargin", 2)
    lines += ["[InputPanel/Background]", f"Color={p['bg']}", f"BorderColor={p['border']}", "BorderWidth=2", ""]
    lines += margins("InputPanel/Background/Margin", 2)
    lines += ["[InputPanel/Highlight]", f"Color={sel}", ""] + margins("InputPanel/Highlight/Margin", 5)
    for name, img in (("PrevPage", "prev.svg"), ("NextPage", "next.svg")):
        lines += [f"[InputPanel/{name}]", f"Image={img}", "",
                  f"[InputPanel/{name}/ClickMargin]", "Left=5", "Right=5", "Top=4", "Bottom=4", ""]
    lines += ["[Menu]", f"NormalColor={p['fg_bright']}", f"HighlightCandidateColor={on_sel}", ""]
    lines += ["[Menu/Background]", f"Color={p['bg']}", f"BorderColor={p['border']}", "BorderWidth=2", ""]
    lines += margins("Menu/Background/Margin", 2) + margins("Menu/ContentMargin", 2)
    lines += ["[Menu/CheckBox]", "Image=radio.svg", "", "[Menu/SubMenu]", "Image=arrow.svg", ""]
    lines += ["[Menu/Highlight]", f"Color={sel}", ""] + margins("Menu/Highlight/Margin", 5)
    lines += ["[Menu/Separator]", f"Color={p['muted']}", ""] + margins("Menu/TextMargin", 5)
    return "\n".join(lines)


def _hex_alpha(a):
    return f"{round(a * 255):02x}"


def _css_alpha(c, a):
    return c if a >= 1 else f"alpha({c}, {a:g})"


def _hypr_glass(ls):
    """hypr.lua's Glass keys for looknfeel.lua: which layers blur, and the app windows' opacity."""
    active = glass_alpha("apps", ls)
    return ("".join(f"  glass_{k:<6} = {'true' if part_look(k, ls) in GLOSSY else 'false'},\n" for k in GLASS_PARTS)
            + f"  app_opacity = {active:g},\n  app_opacity_inactive = {max(0.5, round(active - 0.08, 2)):g},\n")


def render(p):
    """{filename in ~/.config/fw13/theme: text} for palette `p` (the apps'); the bar and the menus use their own
    part's palette under a Custom look."""
    ls, main_mode = look_state(), state()["mode"]

    def pal(part):
        m = part_mode(part, ls)
        return p if m == main_mode else palette_for(m)
    pb, pm = pal("bar"), pal("menus")
    v = _hypr_values(p)
    f = font()
    hypr = (f"-- {HEAD}\n-- Read by ~/.config/hypr/theme.lua (falls back to Tokyo Night if this file breaks).\n"
            "return {\n" + "".join(f'  {k:<7} = "{c}",\n' for k, c in v.items())
            + _hypr_glass(ls) + "}\n")
    waybar = (f"/* {HEAD} */\n"
              f"@define-color bg {pb['bg']};\n"
              f"@define-color bar_bg {_css_alpha(pb['bg'], glass_alpha('bar', ls))};\n"
              f"@define-color bar_sheen alpha({SHEEN}, 0);\n"  # the bar matches the terminal: no shine
              f"@define-color bar_edge alpha({SHEEN}, 0);\n"
              f"@define-color fg {pb['fg']};\n"
              f"@define-color accent {pb['accent']};\n"
              f"@define-color muted {pb['muted']};\n"
              f"@define-color red {pb['bad']};\n"
              f"@define-color yellow {pb['warn']};\n"
              f'* {{ font-family: "{f}", "Font Awesome 6 Free", "Font Awesome 6 Brands", "Noto Sans Khmer", sans-serif; }}\n')
    fuzzel = (f"# {HEAD}\n[main]\nfont={f}:size=12,Font Awesome 6 Free:size=12\n[colors]\n"
              f"background={_a(pm['bg'], _hex_alpha(min(glass_alpha('menus', ls), 0.95)))}\n"
              f"text={_a(pm['fg'])}\n"
              f"match={_a(pm['accent'])}\n"
              f"selection={_a(pm['surface2'])}\n"
              f"selection-text={_a(pm['fg_bright'])}\n"
              f"selection-match={_a(pm['accent'])}\n"
              f"border={_a(pm['border'])}\n")
    mako = (f"# {HEAD}\n"
            f"background-color=#{_a(pm['bg'], _hex_alpha(glass_alpha('menus', ls)))}\n"
            f"text-color={pm['fg']}\n"
            f"border-color={pm['border']}\n"
            f"progress-color=over #{_a(pm['accent'], '66')}\n"
            f"font={f} 11\n"  # fw-osd volume/brightness bar, text stays readable
            "[urgency=critical]\n"
            f"border-color={pm['bad']}\n")
    t = terminal_look()
    kitty = [f"# {HEAD}",
             f"font_family {f}",
             f"font_size {t['size']:g}",
             f"background_opacity {t['opacity']:g}",
             f"window_padding_width {t['padding']}",
             f"modify_font cell_height {t['line']}%",
             f"cursor_shape {CURSORS[t['cursor']][0]}",
             f"cursor_blink_interval {-1 if t['blink'] else 0}",
             f"disable_ligatures {'never' if t['ligatures'] else 'always'}"]
    if not t["bold"]:  # bold drawn with the regular face
        kitty += [f"bold_font family='{f}' style=Regular", f"bold_italic_font family='{f}' style=Italic"]
    if _lum(p["bg"]) > 0.5:  # dim text (SGR 2) at kitty's 0.4 / Ghostty's 0.5 washes out on a light background
        kitty.append(f"dim_opacity {DIM_LIGHT:g}")
    kitty += [f"background {p['bg']}",
              f"foreground {p['fg']}",
              f"selection_background {p['surface2']}",
              f"cursor {p['fg_bright']}"]
    for i in range(8):
        kitty += [f"color{i:<2} {p['ansi'][i]}", f"color{i + 8:<2} {p['ansi'][i + 8]}"]
    ghostty = [f"# {HEAD}",
               f"font-family = {f}",
               f"font-size = {t['size']:g}",
               f"background-opacity = {t['opacity']:g}",
               f"window-padding-x = {t['padding']}",
               f"window-padding-y = {t['padding']}",
               f"adjust-cell-height = {t['line'] - 100}%",
               f"cursor-style = {CURSORS[t['cursor']][1]}",
               f"cursor-style-blink = {'true' if t['blink'] else 'false'}",
               f"font-style-bold = {'default' if t['bold'] else 'false'}",
               f"font-style-bold-italic = {'default' if t['bold'] else 'false'}",
               f"font-feature = {'' if t['ligatures'] else '-calt, -liga, -dlig'}",
               f"background = {p['bg']}",
               f"foreground = {p['fg']}",
               f"selection-background = {p['surface2']}",
               f"selection-foreground = {p['fg_bright']}",
               f"cursor-color = {p['fg_bright']}"]
    ghostty += [f"palette = {i}={p['ansi'][i]}" for i in range(16)]
    if _lum(p["bg"]) > 0.5:
        ghostty.append(f"faint-opacity = {DIM_LIGHT:g}")
    hyprlock = (f"# {HEAD}\n"
                f"$fw_font = {f}\n"
                f"$fw_base = rgba({_a(p['bg'])})\n"
                f"$fw_inner = rgba({_a(p['bg'], 'cc')})\n"
                f"$fw_outer = rgba({_a(p['accent'])})\n"
                f"$fw_text = rgba({_a(p['fg_bright'])})\n"
                f"$fw_check = rgba({_a(p['ok'])})\n"
                f"$fw_fail = rgba({_a(p['bad'])})\n"
                f"$fw_clock = rgba({_a(p['fg'])})\n"
                f"$fw_tty_bg = rgba({_a(TTY['bg'])})\n"
                f"$fw_tty_fg = rgba({_a(TTY['fg'])})\n")
    return {"hypr.lua": hypr, "waybar.css": waybar, "fuzzel.ini": fuzzel, "mako": mako,
            "kitty.conf": "\n".join(kitty) + "\n", "ghostty": "\n".join(ghostty) + "\n", "hyprlock.conf": hyprlock,
            "gtk3.css": _gtk_css(p, variables=False), "gtk4.css": _gtk_css(p, variables=True),
            "qt6ct-colors.conf": _qt_scheme(p), "fcitx5-theme.conf": _fcitx_theme(p),
            "framework-logo.svg": _framework_logo(pb, LOGO_PX), "framework-logo@2x.svg": _framework_logo(pb, LOGO_PX * 2),
            **{f"wifi-{n}{x}.svg": _wifi(pb, n, px) for n in range(1, 5) for x, px in (("", 16), ("@2x", 32))}}



# Framework's gear mark (Framework Computer's trademark): the symbol from framework-logo.svg in Framework's own
# FrameworkComputer/dotmatrixtool repository (MIT), the wordmark left out. Drawn by the bar's Framework-menu button
# (waybar style.css background-image) in the accent colour, by fw-settings and on the GRUB card. The one
# non-Font-Awesome icon, by the user's choice. Written at exactly the size the bar shows (LOGO_PX, twice that for
# scale-2 surfaces) and picked with -gtk-scaled() in style.css: GTK resamples CSS background images with a cheap
# filter, which makes any other size look jagged or soft (fractional scaling draws the bar at scale 2).
FRAMEWORK_LOGO = (
    "M29.8357 11.1639L27.5526 9.80995C26.4837 9.17385 25.823 8.00115 25.823 6.73249V4.02461C25.823 3.47024 25.5774 "
    "2.94786 25.1588 2.5996C23.9135 1.56549 22.5125 0.726826 20.9974 0.126259C20.4923 -0.0727449 19.9285 -0.0336548"
    " 19.4615 0.24353L17.175 1.60102C16.1061 2.23713 14.7881 2.23713 13.7158 1.60102L11.4292 0.24353C10.9622 -0.033"
    "6548 10.3949 -0.0762986 9.89333 0.126259C8.37474 0.726826 6.97722 1.56549 5.73536 2.59605C5.3168 2.9443 5.0712"
    " 3.46669 5.0712 4.02106V6.72894C5.0712 7.99759 4.41395 9.1703 3.34159 9.8064L1.05852 11.1603C0.591524 11.4375 "
    "0.273277 11.9173 0.190256 12.4645C0.0622657 13.2712 0 14.0957 0 14.9343C0 15.773 0.0622657 16.5974 0.186797 17"
    ".4005C0.269818 17.9478 0.588065 18.4311 1.05506 18.7083L3.33813 20.0622C4.40703 20.6983 5.06774 21.871 5.06774"
    " 23.1397V25.8476C5.06774 26.4019 5.31334 26.9243 5.7319 27.2726C6.97376 28.3031 8.37474 29.1418 9.88987 29.742"
    "4C10.3949 29.9414 10.9588 29.9023 11.4258 29.6251L13.7123 28.2676C14.7812 27.6315 16.0991 27.6315 17.1715 28.2"
    "676L19.458 29.6251C19.925 29.9023 20.4923 29.9414 20.9939 29.7424C22.5091 29.1418 23.91 28.3031 25.1519 27.272"
    "6C25.5705 26.9243 25.8161 26.4019 25.8161 25.8476V23.1397C25.8161 21.871 26.4768 20.6983 27.5457 20.0622L29.82"
    "87 18.7083C30.2957 18.4311 30.614 17.9514 30.697 17.4005C30.8181 16.5974 30.8838 15.773 30.8838 14.9343C30.883"
    "8 14.0957 30.8215 13.2712 30.697 12.4681C30.6174 11.9208 30.3026 11.4411 29.8357 11.1639ZM15.4454 24.4688C10.3"
    "223 24.4688 6.16776 20.2008 6.16776 14.9379C6.16776 9.67491 10.3223 5.40698 15.4454 5.40698C20.5684 5.40698 24"
    ".7229 9.67491 24.7229 14.9379C24.7229 20.2008 20.5684 24.4688 15.4454 24.4688Z"
)
LOGO_VIEWBOX = "0 -0.5 30.8 30.8"  # the gear spans x 0–30.8, y 0–29.8: centred in a square
LOGO_PX = 15  # on the bar (style.css background-size matches)


def _framework_logo(p, px):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="{LOGO_VIEWBOX}">'
            f'<path fill="#{_h(p["accent"])}" d="{FRAMEWORK_LOGO}"/></svg>\n')


# Wi-Fi strength for the bar's network module (waybar states s1–s4 → style.css background): a dot and three arcs,
# the first n lit in the text colour, the rest dim. Font Awesome Free has only the full Wi-Fi glyph.
WIFI_PARTS = ('<circle cx="12" cy="19" r="2.2" fill="{c}"/>',
              '<path d="M8.3 15.3a5.3 5.3 0 0 1 7.4 0" {s}/>',
              '<path d="M4.9 11.9a10.1 10.1 0 0 1 14.2 0" {s}/>',
              '<path d="M1.5 8.5a14.9 14.9 0 0 1 21 0" {s}/>')


def _wifi(p, n, px):
    parts = []
    for i, part in enumerate(WIFI_PARTS):
        c = "#" + _h(p["fg"] if i < n else p["muted"])
        parts.append(part.format(c=c, s=f'fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round"'))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="{LOGO_VIEWBOX}">'
            + "".join(parts) + "</svg>\n")


# ---- GTK theme + user gtk.css -------------------------------------------------------------------------------

GTK_THEME = "fw13"
GTK_THEME_DIR = os.path.expanduser("~/.local/share/themes/" + GTK_THEME)
GTK_MARK = "/* fw13: written by fw13.theme. Delete this line to keep your own copy of this file. */"
SYSTEM_THEMES = "/usr/share/themes"  # adw-gtk3 / adw-gtk3-dark (adw-gtk3-theme, packages/96-theme.txt)
GTK_SAVED = "theme_gtk_saved"  # fw13.store key: the gtk-theme / color-scheme apply_gtk() replaced


def _in_hyprland():
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def gtk_base(p):
    """The adw-gtk3 variant the fw13 GTK theme is built on, by the palette's lightness."""
    return "adw-gtk3-dark" if _dark(p) else "adw-gtk3"


def gtk_base_installed(p):
    """True if the base theme for `p` is installed. Without it the fw13 theme's @import fails and GTK 3 apps
    would lose all widget styling, so apply_gtk() never selects fw13 then."""
    return os.path.isfile(os.path.join(SYSTEM_THEMES, gtk_base(p), "gtk-3.0", "gtk.css"))


def render_gtk_theme(p):
    """{path in GTK_THEME_DIR: text}: the "fw13" GTK theme, adw-gtk3[-dark] (by the palette's lightness) with
    our colours on top. It is a theme rather than ~/.config/gtk-3.0/gtk.css because GTK 3 loads the user gtk.css
    once per process, while a theme is re-parsed (with its @imports) whenever gtk-theme changes."""
    base = gtk_base(p)
    out = {"index.theme": f"# {HEAD}\n[Desktop Entry]\nType=X-GNOME-Metatheme\nName={GTK_THEME}\n"
                          f"Comment=adw-gtk3 with the fw13 palette (~/.config/fw13/theme)\n\n"
                          f"[X-GNOME-Metatheme]\nGtkTheme={GTK_THEME}\n"}
    for ver, colours in (("gtk-3.0", "gtk3.css"), ("gtk-4.0", "gtk4.css")):
        css = (f"/* {HEAD} */\n"
               f'@import url("file://{SYSTEM_THEMES}/{base}/{ver}/gtk.css");\n'
               f'@import url("file://{os.path.join(DIR, colours)}");\n')
        # gtk-dark.css is loaded instead when an app asks for a dark variant: same palette either way.
        out[f"{ver}/gtk.css"] = out[f"{ver}/gtk-dark.css"] = css
    return out


def _user_gtk_css():
    """~/.config/gtk-4.0/gtk.css (read by every GTK 4 app at start, libadwaita ones included)."""
    return os.path.expanduser("~/.config/gtk-4.0/gtk.css"), (
        f"{GTK_MARK}\n/* libadwaita apps ignore GTK themes; this gives them the fw13 palette at start. */\n"
        f'@import url("file://{os.path.join(DIR, "gtk4.css")}");\n')


def _read(path):
    """File text, None if absent; OSError/UnicodeDecodeError if unreadable."""
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def link_gtk():
    """Make ~/.config/gtk-4.0/gtk.css @import our gtk4.css, unless the user has their own file there (one
    without GTK_MARK), which is left alone. Returns None or a short note saying why nothing was written.

    Only from a Hyprland session: the file is read by GTK 4 apps in every session, so installing from GNOME/KDE
    must not recolour their libadwaita apps (session_start() links it at the next Hyprland login, session_end()
    removes it). GTK 3 needs no user gtk.css (the fw13 theme carries the colours); one there with colours would
    even pin them, since GTK 3 never re-reads it."""
    path, text = _user_gtk_css()
    if not _in_hyprland():
        return None
    try:
        cur = _read(path)
    except (OSError, UnicodeDecodeError):
        return f"{path} is not readable; GTK 4 apps keep their own colours"
    if cur is not None and GTK_MARK not in cur:
        return f"{path} is yours, left as is; libadwaita apps keep their colours (@import {DIR}/gtk4.css to opt in)"
    if cur != text:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic(path, text)
    return None


def unlink_gtk():
    """Remove ~/.config/gtk-4.0/gtk.css if it is ours (has GTK_MARK)."""
    path, _ = _user_gtk_css()
    try:
        cur = _read(path)
        if cur is not None and GTK_MARK in cur:
            os.unlink(path)
    except (OSError, UnicodeDecodeError):
        pass


def _write_gtk_theme(p, only_missing=False):
    written = []
    for rel, text in render_gtk_theme(p).items():
        path = os.path.join(GTK_THEME_DIR, rel)
        if only_missing and os.path.isfile(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic(path, text)
        written.append(os.path.join("themes", GTK_THEME, rel))
    return written


def _atomic(path, text, mode=0o644):
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _atomic_user(path, text):
    """_atomic() for a file of another app (settings.json, classicui.conf, Chromium's Preferences): through a
    symlink to its target (the user may keep it in a dotfiles repo) and keeping the file's mode."""
    path = os.path.realpath(path)
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _atomic(path, text, mode=mode)


# Lines a generated file must hold; one of ours (HEAD on top) written before a line was added is rewritten by
# ensure_files() (written only on a palette change otherwise, so an existing install would never get it).
REQUIRED = {"mako": ("progress-color=", "font="), "fuzzel.ini": ("font=",), "waybar.css": ("font-family", "@define-color bar_bg", "@define-color bar_sheen", "@define-color bar_edge"),
            "hyprlock.conf": ("$fw_font", "$fw_tty_bg")}


def _outdated(name):
    text = _read_quiet(os.path.join(DIR, name))
    return (name in REQUIRED and text is not None and HEAD in text.split("\n", 1)[0]
            and any(line not in text for line in REQUIRED[name]))


def ensure_files():
    """Write any missing generated file from the current palette (mako refuses to start when its include is
    missing), and any of ours that lacks a line added since (REQUIRED). Other existing files are left alone."""
    os.makedirs(DIR, exist_ok=True)
    p = palette()
    missing = {n: t for n, t in render(p).items()
               if not os.path.isfile(os.path.join(DIR, n)) or _outdated(n)}
    for name, text in missing.items():
        _atomic(os.path.join(DIR, name), text)
    return sorted(missing) + _write_gtk_theme(p, only_missing=True)


def write(p, apply=True):
    """Write every generated file for `p` (atomically), the fw13 GTK theme and (if ours, under Hyprland) the
    GTK 4 user gtk.css, then reload running apps unless apply=False."""
    os.makedirs(DIR, exist_ok=True)
    for name, text in render(p).items():
        _atomic(os.path.join(DIR, name), text)
    _write_gtk_theme(p)
    link_gtk()
    chromium_policy(p, signal=apply)
    if apply:
        reload(p)


def _quiet(*cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _gsettings_get(key):
    try:
        r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key], capture_output=True,
                           text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip().strip("'") if r.returncode == 0 else None


def _gsettings_set(key, value):
    _quiet("gsettings", "set", "org.gnome.desktop.interface", key, value)


def _save_gtk(theme_name, scheme):
    """Remember the gtk-theme / color-scheme apply_gtk() is about to replace (once: a saved pair is kept until
    restore_gtk() uses it, so a second apply does not save our own values)."""
    if theme_name == GTK_THEME or isinstance(store.get(GTK_SAVED), dict):
        return
    try:
        store.set(GTK_SAVED, {"gtk-theme": theme_name, "color-scheme": scheme})
    except OSError:
        pass


def apply_gtk(p=None, refresh=True):
    """Point GTK at the fw13 theme and the palette's light/dark (org.gnome.desktop.interface gtk-theme and
    color-scheme). Under Hyprland GTK 3/4 read these from GSettings (dconf) directly, and libadwaita apps get
    color-scheme through xdg-desktop-portal-gtk, so no settings.ini is needed (GSettings would override it).
    Returns None or a short note.

    Only inside a Hyprland session (never in CI or from another desktop). The keys are per user, so GNOME sees
    them too: the values replaced are saved first (GTK_SAVED) and restore_gtk() puts them back.
    gtk-theme is set to fw13 only when its adw-gtk3 base is installed (else GTK 3 apps would be unstyled).
    refresh: if gtk-theme is already fw13, switch it to plain adw-gtk3 and back so running GTK 3 apps re-parse
    the theme and its @imports; GTK compares names, so setting the same name again does nothing, and the short
    pause keeps apps from reading both writes as one (they read the key when the change signal arrives).
    """
    if not _in_hyprland() or not shutil.which("gsettings"):
        return None
    p = p or palette()
    dark = _dark(p)
    want = "prefer-dark" if dark else "prefer-light"
    current = _gsettings_get("gtk-theme")
    if current is None:
        return None  # no GSettings schema / dconf: nothing to set
    scheme = _gsettings_get("color-scheme")
    _save_gtk(current, scheme)
    if scheme != want:
        _gsettings_set("color-scheme", want)
    if not gtk_base_installed(p):
        if current == GTK_THEME:  # fw13 without its base is unstyled: back to what was there before
            saved = store.get(GTK_SAVED)
            prev = saved.get("gtk-theme") if isinstance(saved, dict) else None
            _gsettings_set("gtk-theme", prev if prev and prev != GTK_THEME else "Adwaita")
        return f"{gtk_base(p)} is not installed (adw-gtk3-theme); GTK 3 apps keep their theme"
    if current == GTK_THEME:
        if not refresh:
            return None
        _gsettings_set("gtk-theme", gtk_base(p))
        time.sleep(0.4)
    _gsettings_set("gtk-theme", GTK_THEME)
    return None


def restore_gtk():
    """Undo apply_gtk() and link_gtk(): put back the saved gtk-theme / color-scheme (gtk-theme only while it is
    still ours) and remove our ~/.config/gtk-4.0/gtk.css. Safe to call anywhere; a no-op if nothing is saved."""
    unlink_gtk()
    saved = store.get(GTK_SAVED)
    if not isinstance(saved, dict) or not shutil.which("gsettings"):
        return
    if _gsettings_get("gtk-theme") == GTK_THEME:
        prev = saved.get("gtk-theme")
        if prev and prev != GTK_THEME:
            _gsettings_set("gtk-theme", prev)
        else:
            _quiet("gsettings", "reset", "org.gnome.desktop.interface", "gtk-theme")
    if saved.get("color-scheme") in ("default", "prefer-dark", "prefer-light"):
        _gsettings_set("color-scheme", saved["color-scheme"])
    try:
        data = store.load()
        data.pop(GTK_SAVED, None)
        store.save(data)
    except OSError:
        pass


# ---- fcitx5 candidate popup ---------------------------------------------------------------------------------

FCITX_THEME = "fw13"
FCITX_THEME_DIR = os.path.expanduser("~/.local/share/fcitx5/themes/" + FCITX_THEME)
FCITX_IMAGES = "/usr/share/fcitx5/themes/default-dark"  # prev/next/radio/arrow.svg (fcitx5-data)
FCITX_CONF = os.path.expanduser("~/.config/fcitx5/conf/classicui.conf")
FCITX_KEYS = ("Theme", "DarkTheme")  # classic UI: theme for a light / dark desktop (UseDarkTheme)
FCITX_SAVED = "theme_fcitx_saved"  # fw13.store key: the classicui.conf values apply_fcitx() replaced


def link_fcitx():
    """Make ~/.local/share/fcitx5/themes/fw13/ a theme: theme.conf → our fcitx5-theme.conf, images → fcitx5's
    default-dark ones. Links only (they follow every palette change); a real file there is left alone."""
    links = {"theme.conf": os.path.join(DIR, "fcitx5-theme.conf")}
    for img in ("prev.svg", "next.svg", "radio.svg", "arrow.svg"):
        if os.path.isfile(os.path.join(FCITX_IMAGES, img)):
            links[img] = os.path.join(FCITX_IMAGES, img)
    try:
        os.makedirs(FCITX_THEME_DIR, exist_ok=True)
        for name, target in links.items():
            path = os.path.join(FCITX_THEME_DIR, name)
            if os.path.islink(path):
                if os.readlink(path) == target:
                    continue
                os.unlink(path)
            elif os.path.lexists(path):
                continue
            os.symlink(target, path)
    except OSError:
        pass


def _ini_top(text, key):
    """Value of a top-level (before any [section]) `key=` line in fcitx5 config `text`, None if absent."""
    for line in (text or "").splitlines():
        if line.strip().startswith("["):
            break
        k, sep, v = line.partition("=")
        if sep and k.strip() == key:
            return v.strip()
    return None


def _ini_set_top(text, values):
    """`text` with the top-level keys in `values` set (value None: line removed), other lines kept as they are."""
    lines = (text or "").splitlines()
    end = next((i for i, ln in enumerate(lines) if ln.strip().startswith("[")), len(lines))
    head, seen = [], set()
    for line in lines[:end]:
        k, sep, _ = line.partition("=")
        if sep and k.strip() in values:
            seen.add(k.strip())
            if values[k.strip()] is not None:
                head.append(f"{k.strip()}={values[k.strip()]}")
            continue
        head.append(line)
    head += [f"{k}={v}" for k, v in values.items() if k not in seen and v is not None]
    out = head + lines[end:]
    return "\n".join(out) + "\n" if out else ""


def _read_quiet(path):
    try:
        return _read(path)
    except (OSError, UnicodeDecodeError):
        return None


def apply_fcitx():
    """Point fcitx5's classic UI (Theme and DarkTheme in ~/.config/fcitx5/conf/classicui.conf) at the fw13 theme
    and reload fcitx5. Only inside Hyprland: the file is per user, so the values replaced are saved first
    (FCITX_SAVED) and restore_fcitx() puts them back at logout, like apply_gtk(). Returns None or a short note."""
    if not _in_hyprland():
        return None
    link_fcitx()
    try:
        cur = _read(FCITX_CONF)
    except (OSError, UnicodeDecodeError):
        return f"{FCITX_CONF} is not readable; the input method popup keeps its theme"
    old = {k: _ini_top(cur, k) for k in FCITX_KEYS}
    if all(v == FCITX_THEME for v in old.values()):
        return None
    saved = store.get(FCITX_SAVED)
    if isinstance(saved, dict):  # left over (no session_end(), e.g. a crash): keep what was picked since then
        new = {**saved, **{k: v for k, v in old.items() if v != FCITX_THEME}}
    else:  # values that are already ours are not worth saving: restore removes them
        new = {"exists": cur is not None, **{k: (None if v == FCITX_THEME else v) for k, v in old.items()}}
    if new != saved:
        try:
            store.set(FCITX_SAVED, new)
        except OSError:
            return "Could not save the input method theme; left as is"
    try:
        _atomic_user(FCITX_CONF, _ini_set_top(cur, {k: FCITX_THEME for k in FCITX_KEYS}))
    except OSError as e:
        return f"Could not set the input method theme: {e}"
    _quiet("fcitx5-remote", "--check", "-r")
    return None


def restore_fcitx():
    """Undo apply_fcitx(): Theme/DarkTheme back to the saved values while they are still ours (one the user
    picked in fcitx5's settings meanwhile is kept), and remove classicui.conf if we created it and it holds
    nothing else. Safe anywhere; a no-op if nothing is saved."""
    saved = store.get(FCITX_SAVED)
    if not isinstance(saved, dict):
        return
    try:
        cur = _read(FCITX_CONF)
        if cur is not None:
            back = {k: saved.get(k) for k in FCITX_KEYS if _ini_top(cur, k) == FCITX_THEME}
            text = _ini_set_top(cur, back) if back else cur
            if not saved.get("exists") and not text.strip() and not os.path.islink(FCITX_CONF):
                os.unlink(FCITX_CONF)
            elif text != cur:
                _atomic_user(FCITX_CONF, text)
    except (OSError, UnicodeDecodeError):
        return
    try:
        data = store.load()
        data.pop(FCITX_SAVED, None)
        store.save(data)
    except OSError:
        pass


# ---- Chromium GTK mode --------------------------------------------------------------------------------------

CHROMIUM_DIR = os.path.expanduser("~/.config/chromium")
CHROMIUM_DONE = "theme_chromium_gtk"  # fw13.store key: profile dirs chromium_gtk() has handled (once each)
CHROMIUM_FORCE = "chromium_gtk_force"  # fw13.store key: the Appearance switch (off by default): replaces a theme
#                                        the user chose with GTK mode, at every login while Chromium is closed
CHROMIUM_HINT = "theme_chromium_hint"  # fw13.store key: True when the setting was protected (Appearance hint)


def _chromium_running():
    """True if Chromium (any profile of ~/.config/chromium) is running, or we cannot tell."""
    try:
        r = subprocess.run(["pgrep", "-x", "chromium-browse"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        if r.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        return True
    lock = os.path.join(CHROMIUM_DIR, "SingletonLock")
    if not os.path.lexists(lock):
        return False
    try:  # "<hostname>-<pid>": live if that pid exists on this host
        host, _, pid = os.readlink(lock).rpartition("-")
    except OSError:
        return True
    return host != os.uname().nodename or not pid.isdigit() or os.path.exists(f"/proc/{pid}")


def _mac_protected(path):
    """True if Chromium keeps a MAC for extensions.theme in the prefs file `path` (protection.macs, nested or
    dotted); editing a protected value would make Chromium reset it and warn about settings changed outside."""
    try:
        with open(path) as f:
            macs = json.load(f).get("protection", {}).get("macs", {})
    except FileNotFoundError:
        return False
    except (OSError, ValueError, AttributeError):
        return True
    if not isinstance(macs, dict):
        return False
    ext = macs.get("extensions")
    return ((isinstance(ext, dict) and "theme" in ext)
            or any(k.startswith("extensions.theme") for k in macs))


def _chromium_profiles():
    return [n for n in sorted(os.listdir(CHROMIUM_DIR)) if n not in ("System Profile", "Guest Profile")
            and os.path.isfile(os.path.join(CHROMIUM_DIR, n, "Preferences"))]


def _chromium_own(theme, browser_theme):
    """True if the user chose a theme: GTK/Classic (system_theme), a theme extension, or a colour (any
    browser.theme key but the light/dark color_scheme: user_color[2], color_variant[2], is_grayscale[2],
    follows_system_colors, saved_local_theme, ...)."""
    return ("system_theme" in theme or bool(theme.get("id"))
            or any(k not in ("color_scheme", "color_scheme2") for k in browser_theme))


def _chromium_theme(prefs):
    """(data, extensions.theme, browser.theme) of a Preferences file; TypeError/AttributeError if it is not that
    shape, OSError/ValueError if unreadable."""
    with open(prefs) as f:
        data = json.load(f)
    theme = data.setdefault("extensions", {}).setdefault("theme", {})
    browser_theme = data.get("browser", {}).get("theme", {})
    if not isinstance(theme, dict) or not isinstance(browser_theme, dict):
        raise TypeError(prefs)
    return data, theme, browser_theme


def _chromium_hint_needed():
    """True while a profile still has the protected setting unset (the Appearance hint stays until then)."""
    for name in _chromium_profiles():
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            _data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if not _chromium_own(theme, browser_theme) and (
                _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences"))):
            return True
    return False


def chromium_gtk():
    """Chromium in GTK mode (its colours from the fw13 GTK theme, see apply_gtk()): set
    extensions.theme.system_theme = 1 in each profile's Preferences, once per profile, only when the key is not
    there (a theme the user chose, incl. a theme extension or colour, is never overridden), Chromium is not
    running (it rewrites Preferences on exit) and the value is not MAC-protected. Only inside Hyprland.
    Returns None or a short note."""
    if not _in_hyprland():
        return None
    if store.get(CHROMIUM_HINT) and not (os.path.isdir(CHROMIUM_DIR) and _chromium_hint_needed()):
        _drop(CHROMIUM_HINT)  # GTK chosen in Chromium meanwhile, or the profile is gone
    if not os.path.isdir(CHROMIUM_DIR):
        return None
    if store.get(CHROMIUM_FORCE):
        return _chromium_force()
    done = store.get(CHROMIUM_DONE)
    done = done if isinstance(done, list) else []
    todo = [n for n in _chromium_profiles() if n not in done]
    if not todo:
        return None
    if _chromium_running():
        return "Chromium is running; GTK mode is set at the next login"
    notes = []
    for name in todo:
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError):
            continue  # unreadable now: try again next login
        except (TypeError, AttributeError):
            done.append(name)  # not the shape we know: left alone
            continue
        if _chromium_own(theme, browser_theme):
            done.append(name)  # the user's own choice
            continue
        if _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences")):
            try:
                store.set(CHROMIUM_HINT, True)
            except OSError:
                pass
            notes.append("Chromium protects its theme setting; choose GTK in Chromium's Settings → Appearance")
            done.append(name)
            continue
        theme["system_theme"] = 1  # ui::SystemTheme::kGtk
        try:
            _atomic_user(prefs, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        except OSError as e:
            notes.append(f"Could not set Chromium's GTK mode: {e}")
            continue
        done.append(name)
    try:
        store.set(CHROMIUM_DONE, done)
    except OSError:
        pass
    return "; ".join(dict.fromkeys(notes)) or None


CHROMIUM_POLICY = os.path.join(DIR, "chromium-policy.json")  # /etc/chromium/policies/managed/fw13-theme.json links here


CHROMIUM_POLICY_LINK = "/etc/chromium/policies/managed/fw13-theme.json"  # made by install.sh (root)


def _chromium_browsers():
    """PIDs of running Chromium browser processes (not its zygote/renderer children)."""
    try:
        r = subprocess.run(["pgrep", "-x", "chromium-browse"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for pid in r.stdout.split():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"--type=" not in f.read():
                    out.append(int(pid))
        except (OSError, ValueError):
            pass
    return out


def chromium_policy(p, signal=True):
    """Chromium's BrowserThemeColor policy from the palette's accent, so a running Chromium follows the colours:
    Chromium builds its whole palette from that one seed and re-reads policies on SIGHUP. Only with the Appearance
    switch (CHROMIUM_FORCE) on; switched off, the file is emptied (the symlink in /etc/chromium/policies/managed
    stays valid, root made it once). Nothing happens unless the switch is on or the /etc link exists (then the
    file is kept as "{}", so Chromium never reads a dangling link)."""
    on = bool(store.get(CHROMIUM_FORCE))
    if not on and not os.path.exists(CHROMIUM_POLICY) and not os.path.islink(CHROMIUM_POLICY_LINK):
        return
    text = json.dumps({"BrowserThemeColor": p["accent"]} if on else {}) + "\n"
    try:
        with open(CHROMIUM_POLICY) as f:
            if f.read() == text:
                return
    except OSError:
        pass
    try:
        _atomic(CHROMIUM_POLICY, text)
    except OSError:
        return
    if signal and _in_hyprland():
        for pid in _chromium_browsers():
            try:
                os.kill(pid, 1)  # SIGHUP: reload policies
            except OSError:
                pass


def _chromium_gtk_wanted(theme, browser_theme):
    """True if a profile still differs from the state the BrowserThemeColor policy needs: Chromium's own theme
    (system_theme 0, not GTK mode, which would take its colours from GTK and ignore the policy seed), no theme
    extension, no colour theme, and the light/dark mode following the system (color_scheme/color_scheme2 absent
    or 0), so the frame takes the fw13 theme's dark or light."""
    return (theme.get("system_theme") not in (None, 0) or bool(theme.get("id"))
            or any(v != 0 for v in browser_theme.values()))


def _chromium_force():
    """The Appearance switch is on: every profile ends up in GTK mode, replacing a theme or colour the user chose
    in Chromium, and a fixed Light/Dark mode (that is what the switch is for). Same limits as chromium_gtk(): Chromium closed (it rewrites
    Preferences on exit), value not MAC-protected, Hyprland only. Returns None or a short note."""
    todo = []
    for name in _chromium_profiles():
        prefs = os.path.join(CHROMIUM_DIR, name, "Preferences")
        try:
            data, theme, browser_theme = _chromium_theme(prefs)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if _chromium_gtk_wanted(theme, browser_theme):
            todo.append((name, prefs, data, theme, browser_theme))
    if not todo:
        return None
    if _chromium_running():
        return "Chromium is running; the theme is set at the next login"
    notes = []
    for name, prefs, data, theme, browser_theme in todo:
        if _mac_protected(prefs) or _mac_protected(os.path.join(CHROMIUM_DIR, name, "Secure Preferences")):
            notes.append("Chromium protects its theme setting; the policy colour may not apply")
            continue
        theme.pop("id", None)
        theme["system_theme"] = 0  # ui::SystemTheme::kDefault: colours come from the policy seed, not GTK
        browser_theme.clear()  # colour theme keys and a fixed Light/Dark mode: the mode follows the system
        try:
            _atomic_user(prefs, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        except OSError as e:
            notes.append(f"Could not set Chromium's theme: {e}")
    return "; ".join(dict.fromkeys(notes)) or None


def set_chromium(on):
    """The Settings → Appearance switch for Chromium: store it, then apply (the theme is replaced by GTK mode
    now if Chromium is closed, else at the next login). Switching off only stops forcing: the theme that was
    replaced is not restored. Returns None or a note."""
    try:
        store.set(CHROMIUM_FORCE, bool(on))
    except OSError as e:
        return f"Could not save the setting: {e}"
    chromium_policy(palette())
    if not on:
        return None
    if not _in_hyprland():
        return "Chromium follows the theme in Hyprland sessions"
    if not os.path.isdir(CHROMIUM_DIR):
        return None
    return chromium_gtk()


# ---- VS Code (on by default, switch in Settings → Appearance) ----------------------------------------------------------------

VSCODE_SETTINGS = os.path.expanduser("~/.config/Code/User/settings.json")
VSCODE_ON = "vscode_theme"  # fw13.store key: the switch (on by default: store.DEFAULTS)
VSCODE_APPLIED = "theme_vscode_applied"  # fw13.store key: {"key": scope, "hash": of the block we wrote}
# VS Code's own default themes (theme ids; 1.140: "Dark 2026"/"Light 2026" default, "Dark Modern"/"Light Modern"
# the previous ones, migrated from "Default Dark Modern"). The colours are scoped to them, so a theme the user
# picked keeps its own colours. Syntax colours stay the theme's, hence only the themes matching the palette's mode.
VSCODE_THEMES = {"dark": ("Dark 2026", "Dark Modern"), "light": ("Light 2026", "Light Modern")}


def _vscode_scope(p):
    return "".join(f"[{t}]" for t in VSCODE_THEMES["dark" if _dark(p) else "light"])


def _vscode_colors(p):
    """workbench.colorCustomizations for palette `p`: window chrome, editor background and the terminal."""
    sel = p["surface2"]
    c = {
        "focusBorder": p["accent"], "foreground": p["fg"], "descriptionForeground": p["fg_dim"],
        "editor.background": p["bg"], "editor.foreground": p["fg_bright"],
        "editor.lineHighlightBackground": p["surface"], "editor.selectionBackground": p["surface3"],
        "editorLineNumber.foreground": p["fg_dim"], "editorLineNumber.activeForeground": p["fg_bright"],
        "editorCursor.foreground": p["fg_bright"], "editorWidget.background": p["surface"],
        "editorGroupHeader.tabsBackground": p["bg_dim"], "editorGroup.border": p["surface2"],
        "tab.activeBackground": p["bg"], "tab.activeForeground": p["fg_bright"], "tab.activeBorderTop": p["accent"],
        "tab.inactiveBackground": p["bg_dim"], "tab.inactiveForeground": p["fg_dim"], "tab.border": p["bg_dim"],
        "titleBar.activeBackground": p["bg_dim"], "titleBar.activeForeground": p["fg"],
        "titleBar.inactiveBackground": p["bg_dim"], "titleBar.inactiveForeground": p["fg_dim"],
        "activityBar.background": p["bg_dim"], "activityBar.foreground": p["fg_bright"],
        "activityBar.inactiveForeground": p["fg_dim"], "activityBar.activeBorder": p["accent"],
        "activityBarBadge.background": p["accent"], "activityBarBadge.foreground": _on(p["accent"], p),
        "sideBar.background": p["bg_dim"], "sideBar.foreground": p["fg"],
        "sideBarSectionHeader.background": p["bg_dim"],
        "statusBar.background": p["bg_dim"], "statusBar.foreground": p["fg"],
        "statusBar.noFolderBackground": p["bg_dim"], "statusBar.debuggingBackground": p["warn"],
        "statusBar.debuggingForeground": _on(p["warn"], p),
        "panel.background": p["bg"], "panel.border": p["surface2"],
        "panelTitle.activeBorder": p["accent"], "panelTitle.activeForeground": p["fg_bright"],
        "list.activeSelectionBackground": sel, "list.activeSelectionForeground": p["fg_bright"],
        "list.inactiveSelectionBackground": p["surface"], "list.hoverBackground": p["surface"],
        "list.focusOutline": p["accent"], "list.highlightForeground": p["accent"],
        "input.background": p["surface"], "input.foreground": p["fg_bright"], "input.border": p["surface3"],
        "dropdown.background": p["surface"], "dropdown.foreground": p["fg_bright"],
        "quickInput.background": p["surface"], "quickInput.foreground": p["fg_bright"],
        "button.background": p["accent"], "button.foreground": _on(p["accent"], p),
        "button.hoverBackground": _shade(p["accent"], 0.05 if _dark(p) else -0.05),
        "badge.background": p["accent"], "badge.foreground": _on(p["accent"], p),
        "progressBar.background": p["accent"], "textLink.foreground": ensure(p["accent"], p["bg"], 4.5),
        "errorForeground": p["bad"], "editorError.foreground": p["bad"], "editorWarning.foreground": p["warn"],
        "terminal.background": p["bg"], "terminal.foreground": p["fg"],
        "terminalCursor.foreground": p["fg_bright"], "terminal.selectionBackground": sel,
    }
    names = ("Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White")
    for i, n in enumerate(names):
        c[f"terminal.ansi{n}"] = p["ansi"][i]
        c[f"terminal.ansiBright{n}"] = p["ansi"][i + 8]
    return {k: v[:7] for k, v in c.items()}


def _hash(block):
    return hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def _vscode_lock():
    """One VS Code settings change at a time: the Settings page switch (a thread per flip) and a theme change
    (reload(), maybe in another process) would otherwise interleave read-modify-write and lose the record."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or DIR, "fw13-vscode.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:  # a new open file per caller: flock also excludes other threads of this process
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _vscode_load():
    """(settings dict, text, None) or (None, None, note); text is the file as read (None if missing). A missing
    or empty file is {}; JSONC (comments, trailing commas) is left alone, since rewriting it as JSON would drop
    the user's comments."""
    try:
        text = _read(VSCODE_SETTINGS)
    except (OSError, UnicodeDecodeError):
        return None, None, "VS Code's settings.json is not readable; left as is"
    if text is None or not text.strip():
        return {}, text, None
    try:
        data = json.loads(text)
    except ValueError:
        return None, None, ("VS Code's settings.json has comments or trailing commas; left as is "
                            "(VS Code keeps its colours)")
    if not isinstance(data, dict):
        return None, None, "VS Code's settings.json is not a JSON object; left as is"
    cc = data.get("workbench.colorCustomizations", {})
    if not isinstance(cc, dict):
        return None, None, "VS Code's workbench.colorCustomizations is not an object; left as is"
    return data, text, None


def _vscode_dump(data, text):
    """JSON in the file's own layout: its indent (tab or n spaces; VS Code's default 4 for a new file), \\u
    escapes if it used them, its final newline."""
    m = re.search(r"\n([ \t]+)\S", text or "")
    indent = (("\t" if m.group(1)[0] == "\t" else len(m.group(1))) if m else 4)
    ascii_only = bool(text) and "\\u" in text and text.isascii()
    out = json.dumps(data, indent=indent, ensure_ascii=ascii_only)
    return out + "\n" if not text or text.endswith("\n") else out


def _vscode_save(data, cc, text):
    if cc:
        data["workbench.colorCustomizations"] = cc
    else:
        data.pop("workbench.colorCustomizations", None)
    _atomic_user(VSCODE_SETTINGS, _vscode_dump(data, text))


def _drop(key):
    try:
        data = store.load()
        data.pop(key, None)
        store.save(data)
    except OSError:
        pass


def _apply_vscode(p):
    if not store.get(VSCODE_ON) or not _in_hyprland():
        return None
    if not os.path.isfile(VSCODE_SETTINGS) and not shutil.which("code"):
        return None
    p = p or palette()
    data, text, note = _vscode_load()
    if note:
        return note
    cc = dict(data.get("workbench.colorCustomizations", {}))
    key, block = _vscode_scope(p), _vscode_colors(p)
    applied = store.get(VSCODE_APPLIED)
    applied = applied if isinstance(applied, dict) and isinstance(applied.get("key"), str) else None
    if applied and applied["key"] in cc:
        if _hash(cc[applied["key"]]) != applied.get("hash"):
            return "VS Code's theme colours were edited by hand; left as is"
        if applied["key"] != key:
            del cc[applied["key"]]  # the palette changed mode: the other default themes now
    if key in cc and not (applied and applied["key"] == key):
        return f"VS Code's settings.json has its own colours for {key}; left as is"
    if cc.get(key) == block and applied and applied.get("hash") == _hash(block):
        return None
    cc[key] = block
    record = {"key": key, "hash": _hash(block)}
    if applied and "was" in applied:
        record["was"] = applied["was"]
    elif not applied and (text is None or not text.strip()):
        record["was"] = text  # None: no file before us (restore removes it again), "": an empty one
    try:  # remember the block first: a block in the file without a record would look like the user's own
        store.set(VSCODE_APPLIED, record)
        _vscode_save(data, cc, text)
    except OSError as e:
        if applied:
            store.set(VSCODE_APPLIED, applied)
        else:
            _drop(VSCODE_APPLIED)
        return f"Could not write VS Code's settings: {e}"
    return None


def _restore_vscode():
    applied = store.get(VSCODE_APPLIED)
    if not isinstance(applied, dict) or not isinstance(applied.get("key"), str):
        return None
    data, text, note = _vscode_load()
    if note:
        return note  # the record stays: removed once the file is readable JSON again
    cc = dict(data.get("workbench.colorCustomizations", {}))
    key = applied["key"]
    if key in cc and _hash(cc[key]) == applied.get("hash"):
        del cc[key]
        try:
            if not cc and data.keys() <= {"workbench.colorCustomizations"} and "was" in applied:
                if applied["was"] is None:  # we created the file and it holds nothing else
                    if not os.path.islink(VSCODE_SETTINGS):
                        os.unlink(VSCODE_SETTINGS)
                else:
                    _atomic_user(VSCODE_SETTINGS, applied["was"])
            else:
                _vscode_save(data, cc, text)
        except OSError as e:
            return f"Could not write VS Code's settings: {e}"
    _drop(VSCODE_APPLIED)
    return None


def apply_vscode(p=None):
    """Give VS Code's default themes the palette: one theme-scoped block in workbench.colorCustomizations of
    ~/.config/Code/User/settings.json (VS Code recolours live). Only with the switch on (VSCODE_ON) and inside
    Hyprland; restore_vscode() removes the block at logout. The block's hash is kept in the store: once it was
    edited by hand, or the user has their own block for that scope, it is left alone. The file keeps its
    layout (_vscode_dump()). Returns None or a note."""
    try:
        with _vscode_lock():
            return _apply_vscode(p)
    except OSError as e:
        return f"Could not write VS Code's settings: {e}"


def restore_vscode():
    """Remove the block apply_vscode() wrote (unless it was edited by hand: then it is the user's now), and the
    file itself if we created it and nothing else is in it. Safe anywhere; a no-op if nothing was applied.
    Returns None or a note."""
    try:
        with _vscode_lock():
            return _restore_vscode()
    except OSError as e:
        return f"Could not write VS Code's settings: {e}"


def set_vscode(on):
    """The Settings → Appearance switch: store it, then apply or remove the colours. Under the lock the stored
    value decides, so quick flips (each in its own thread) end in the state of the last one stored. Returns None
    or a note."""
    try:
        with _vscode_lock():
            store.set(VSCODE_ON, bool(on))
            if store.get(VSCODE_ON):
                return _apply_vscode(None) or (None if _in_hyprland()
                                               else "VS Code follows the theme in Hyprland sessions")
            return _restore_vscode()
    except OSError as e:
        return f"Could not save the setting: {e}"


# ---- Hyprland session ---------------------------------------------------------------------------------------

def session_start():
    """At Hyprland login: missing files, the GTK 4 user gtk.css and gtk-theme/color-scheme (another desktop or
    a session_end() may have reset them), the fcitx5 theme, Chromium's GTK mode (once per profile) and the
    VS Code colours (if switched on). Returns a note or None."""
    try:
        if "mako" in ensure_files() and shutil.which("makoctl"):
            _quiet("makoctl", "reload")  # mako may be up already (D-Bus activated before this service)
    except OSError:
        pass
    link_fcitx()
    notes = [n for n in (link_gtk(), apply_gtk(refresh=False), apply_fcitx(), chromium_gtk(), apply_vscode())
             if n]
    return "; ".join(notes) or None


def session_end():
    """At Hyprland logout: hand the shared settings back to other desktops (GTK, fcitx5, VS Code)."""
    restore_vscode()
    restore_fcitx()
    restore_gtk()


def reload(p=None):
    """Make running apps pick up the files; each step is a no-op when the app isn't running.

    fuzzel and hyprlock read their config at start, so they need nothing. GTK 3 apps recolour through
    apply_gtk(); GTK 4 (libadwaita) apps read their colours at start. Qt apps on qt6ct (Citadel) recolour a few
    seconds after _nudge_qt6ct().
    """
    p = p or palette()
    try:
        ensure_files()
    except OSError:
        pass
    _quiet("pkill", "-SIGUSR2", "-x", "waybar")  # re-reads style.css (and its @import)
    if shutil.which("makoctl"):
        _quiet("makoctl", "reload")
    _quiet("pkill", "-SIGUSR1", "-x", "kitty")  # every kitty re-reads kitty.conf incl. includes
    _quiet("pkill", "-SIGUSR2", "-x", "ghostty")  # Ghostty (1.2+) reloads its config incl. config-file
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        v = {k: f'"{c}"' for k, c in _hypr_values(p).items()}
        try:
            lua("hl.config({ general = { col = { "
                f"active_border = {{ colors = {{ {v['accent']}, {v['magenta']} }}, angle = 45 }}, "
                f"inactive_border = {v['muted']} }} }}, "
                f"decoration = {{ shadow = {{ color = {v['shadow']} }} }} }})")
        except OSError:
            pass
    apply_gtk(p)
    _nudge_qt6ct()
    if _in_hyprland() and _ini_top(_read_quiet(FCITX_CONF), "Theme") == FCITX_THEME:
        _quiet("fcitx5-remote", "--check", "-r")  # re-reads the fw13 theme (theme.conf links to our file)
    apply_vscode(p)


def _nudge_qt6ct():
    """Running Qt apps on qt6ct re-read their palette when something in ~/.config/qt6ct/ is replaced (it watches
    the directory, not our colour file), so replace qt6ct.conf with itself."""
    path = os.path.expanduser("~/.config/qt6ct/qt6ct.conf")
    try:
        text = _read(path)
        if text is not None:
            _atomic(path, text)
    except (OSError, UnicodeDecodeError):
        pass


def init():
    """Record Tokyo Night as the source if nothing is stored yet, put back any missing generated file (chezmoi
    seeds most of them; gtk3.css/gtk4.css/qt6ct-colors.conf are only written here, from the current palette; a
    deleted one would stop mako starting) and the fw13 GTK theme, and link the GTK 4 user gtk.css (see
    link_gtk(); its note is returned). Reloads nothing, so it is safe without a desktop (install, CI)."""
    data = store.load()
    if not isinstance(data.get("theme"), dict):
        data["theme"] = state()
        store.save(data)
    ensure_files()
    link_fcitx()
    return link_gtk()


def set_source(source, mode=None, scheme_type=None, wallpaper=None, pick=None):
    """Follow `source` ("tokyo-night" or "wallpaper"), store the choice, write the files and apply them.

    Unspecified options keep their stored value; the wallpaper defaults to ~/.config/hypr/wallpaper.jpg.
    Returns None, or an error message. The store is saved first; if writing the files then fails, the old
    store entry is put back, so the choice shown always matches the files (a file may be half-way only if
    that restore fails too).
    """
    if source not in SOURCES:
        return f"Unknown theme source {source}"
    s = state()
    s["source"] = source
    s["mode"] = mode if mode in MODES else s["mode"]
    s["type"] = scheme_type if scheme_type in TYPES else s["type"]
    s["pick"] = pick if pick in PICKS else s["pick"]
    if source == "wallpaper":
        from .hyprsettings import WALLPAPER
        path = wallpaper or WALLPAPER
        if not os.path.isfile(path):
            return "No wallpaper set"
        try:
            p = from_wallpaper(path, s["mode"], s["type"], s["pick"])
        except RuntimeError as e:
            return f"Could not read colours from the wallpaper: {e}"
        s["wallpaper"] = path
        s["palette"] = p
    else:
        p = _tokyo(s["mode"])
    data = store.load()
    old = data.get("theme")
    data["theme"] = s
    try:
        store.save(data)
    except OSError as e:
        return f"Could not save the theme: {e}"
    try:
        write(p, apply=False)
    except OSError as e:
        data["theme"] = old
        if old is None:
            data.pop("theme")
        try:
            store.save(data)
            write(palette(), apply=False)
        except OSError:
            pass
        return f"Could not write the theme files: {e}"
    reload(p)
    return None


def _glass_selftest():
    """Look → render() and palettes, in a throwaway store (nothing written to ~/.config, no matugen)."""
    import tempfile
    real = store.PATH
    store.PATH = os.path.join(tempfile.mkdtemp(), "settings.json")
    night, day = TOKYO_NIGHT["bg"], TOKYO_DAY["bg"]
    try:
        assert look() == "dark" and not glass()  # nothing stored, Tokyo Night
        off = render(TOKYO_NIGHT)
        assert f"@define-color bar_bg {night};" in off["waybar.css"] and "glass_bar    = false" in off["hypr.lua"]
        assert f"background={_h(night)}f2" in off["fuzzel.ini"] and f"background-color=#{_h(night)}ff" in off["mako"]
        assert "app_opacity = 1," in off["hypr.lua"] and "bar_sheen alpha(#ffffff, 0);" in off["waybar.css"]
        store.set(LOOK, {"look": "glossy"})
        assert "bar_sheen alpha(#ffffff, 0);" in render(TOKYO_NIGHT)["waybar.css"]
        store.set(LOOK, None)
        store.set(GLASS, True)  # the first Glass switch → Custom, glossy bar/menus/panels, apps in the palette's mode
        ls = look_state()
        assert ls["look"] == "custom" and ls["parts"] == {"bar": "glossy", "menus": "glossy", "panels": "glossy",
                                                          "apps": "dark"} and ls["clear"] == 55, ls
        assert set_look("glossy") is None and all(v == "glossy" for v in look_state()["parts"].values())
        on = render(TOKYO_NIGHT)
        assert f"@define-color bar_bg alpha({night}, 0.77);" in on["waybar.css"] and "glass_apps   = true" in on["hypr.lua"]  # 0.9 × 0.86
        assert "app_opacity = 0.86," in on["hypr.lua"] and all(line in on[n] for n, lines in REQUIRED.items()
                                                               for line in lines)
        assert set_look("light") == "light"  # apps light: the caller rebuilds the main palette in light
        store.set("theme", {"source": "tokyo-night", "mode": "light"})
        assert palette()["bg"] == day and look() == "light" and not glass()
        lt = render(palette())
        assert "dim_opacity 0.75" in lt["kitty.conf"] and "faint-opacity = 0.75" in lt["ghostty"]
        assert "dim_opacity" not in off["kitty.conf"]
        assert all(contrast(palette()[k], day) >= MIN_CONTRAST_LIGHT[k] - 0.05 for k in MIN_CONTRAST_LIGHT)
        assert set_look(part="bar", value="glossy") is None and look() == "custom"  # dark glass bar, light apps
        r = render(palette())
        assert f"@define-color bar_bg alpha({night}, 0.9);" in r["waybar.css"]  # apps light: the terminal's 0.9
        assert f"background={_h(day)}f2" in r["fuzzel.ini"] and f"background {day}" in r["kitty.conf"]
        assert set_look(part="apps", value="dark") == "dark"
        store.set("theme", {"source": "tokyo-night", "mode": "dark"})  # what the caller's set_source does
        assert set_look(clear=500) is None and look_state()["clear"] == GLASS_CLEAR[1]
        assert set_look("custom") is None and look_state()["parts"]["bar"] == "glossy"  # Custom keeps the parts
        assert set_look("glossy_light") == "light" and glass("apps") and part_mode("bar") == "light"
        store.set("theme", {"source": "tokyo-night", "mode": "light"})
        r = render(palette())
        assert f"@define-color bar_bg alpha({day}, 0.7);" in r["waybar.css"] and "glass_menus  = true" in r["hypr.lua"]  # 0.9 × 0.78 (See-through 90)
        store.set(LOOK, {"look": "glossy", "clear": 60})  # the terminal is the benchmark for every glossy part
        assert glass_alpha("apps") == 0.85 and window_alpha() == 0.9
        assert glass_alpha("bar") == glass_alpha("menus") == glass_alpha("panels") == 0.77  # 0.9 × 0.85
        store.set(LOOK, {"look": "custom", "parts": {"menus": "glossy", "apps": "dark"}})
        assert glass_alpha("menus") == 0.9 and glass_alpha("apps") == 1.0  # solid apps: the terminal is just 0.9
    finally:
        store.PATH = real
    print("fw13.theme: look self-check OK")


if __name__ == "__main__":  # python3 -m fw13.theme session-start|session-end (Hyprland login/logout hooks) | test
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "test":
        _glass_selftest()
    elif cmd == "session-start":
        msg = session_start()
        if msg:
            print("fw13.theme:", msg, file=sys.stderr)
    elif cmd == "session-end":
        session_end()
    else:
        sys.exit("usage: python3 -m fw13.theme session-start|session-end|test")

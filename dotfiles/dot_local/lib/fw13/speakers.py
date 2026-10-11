"""Speaker sound (Settings → Sound): EasyEffects driven without its window.

Presets in ~/.local/share/easyeffects/output: fw13-speakers (Framework's, louder), fw13-clear (soft, clear voices) and
fw13-custom, which this module writes from fw13-speakers plus the five sliders (store `speaker_eq`, dB). The chosen
one (store `speaker_preset`) goes into EasyEffects' autoload file for the built-in speakers (fw-speakers reads it at
login) and is loaded live; the on/off switch is EasyEffects' global bypass.
  python3 -m fw13.speakers test   self-check
"""
import copy
import glob
import json
import os
import shutil
import subprocess

from . import store

DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "easyeffects")
OUT = os.path.join(DATA, "output")
AUTOLOAD = os.path.join(DATA, "autoload", "output")
BASE, CUSTOM = "fw13-speakers", "fw13-custom"
PRESETS = (("fw13-speakers", "Framework"), ("fw13-clear", "Clear voice"), (CUSTOM, "Custom"))
# key, label, LSP filter type, Hz, quality; "level" = output gain on top of the Framework preset
BANDS = (("bass", "Bass", "Low-shelf", 150.0, 0.7), ("warmth", "Warmth", "Bell", 300.0, 1.0),
         ("voice", "Voice clarity", "Bell", 3000.0, 0.8), ("air", "Air", "High-shelf", 8000.0, 0.7))
SLIDERS = tuple((k, t) for k, t, *_r in BANDS) + (("level", "Level"),)
LIMIT = 6.0


def available():
    return shutil.which("easyeffects") is not None and os.path.isfile(os.path.join(OUT, BASE + ".json"))


def preset():
    p = store.get("speaker_preset")
    return p if p in dict(PRESETS) else BASE


def eq():
    v = store.get("speaker_eq")
    v = v if isinstance(v, dict) else {}
    return {k: max(-LIMIT, min(LIMIT, float(v.get(k, 0) or 0))) for k, _t in SLIDERS}


def build_custom(base, values):
    """The fw13-custom preset: `base` (fw13-speakers JSON) with one filter per band after its high-pass, and the
    level added to the convolver's output gain. Pure, for the self-check."""
    d = copy.deepcopy(base)
    o = d["output"]
    template = o["filter#0"]
    order = [p for p in o["plugins_order"] if not (p.startswith("filter#") and p != "filter#0")]
    at = order.index("filter#0") + 1
    for i, (key, _t, typ, hz, q) in enumerate(BANDS, start=1):
        f = copy.deepcopy(template)
        f.update({"type": typ, "frequency": hz, "gain": values[key], "quality": q, "slope": "x1", "bypass": False})
        o[f"filter#{i}"] = f
        order.insert(at + i - 1, f"filter#{i}")
    o["plugins_order"] = order
    o["convolver#0"]["output-gain"] = o["convolver#0"].get("output-gain", 0.0) + values["level"]
    return d


def _ee(*args):
    try:
        return subprocess.run(["easyeffects", *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def running():
    return subprocess.run(["pgrep", "-x", "easyeffects"], capture_output=True).returncode == 0


def enabled():
    """Effects on (global bypass off); True when it can't be asked."""
    return _ee("-b", "3") != "1" if running() else True


def set_enabled(on):
    _ee("-b", "2" if on else "1")


def _autoload(name):
    for f in glob.glob(os.path.join(AUTOLOAD, "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
            if d.get("device-profile") == "[Out] Speaker" and d.get("preset-name") != name:
                d["preset-name"] = name
                with open(f, "w") as fh:
                    json.dump(d, fh, indent=4)
        except (OSError, ValueError):
            pass


def apply(name=None, values=None):
    """Store the choice, write fw13-custom if it is the one, point the speakers' autoload at it and load it now."""
    name = name if name in dict(PRESETS) else preset()
    store.set("speaker_preset", name)
    if values is not None:
        store.set("speaker_eq", values)
    if name == CUSTOM:
        with open(os.path.join(OUT, BASE + ".json")) as f:
            base = json.load(f)
        tmp = os.path.join(OUT, f".{CUSTOM}.json.tmp")
        with open(tmp, "w") as f:
            json.dump(build_custom(base, eq()), f, indent=4)
        os.replace(tmp, os.path.join(OUT, CUSTOM + ".json"))
    _autoload(name)
    if running():
        _ee("-l", name)


def _test():
    base = {"output": {"plugins_order": ["filter#0", "convolver#0", "limiter#0"],
                       "filter#0": {"type": "High-pass", "frequency": 60.0, "gain": 0.0},
                       "convolver#0": {"output-gain": 15.5}, "limiter#0": {}}}
    vals = {"bass": -2.0, "warmth": 0.0, "voice": 3.0, "air": 1.0, "level": -1.5}
    d = build_custom(base, vals)["output"]
    assert d["plugins_order"] == ["filter#0", "filter#1", "filter#2", "filter#3", "filter#4", "convolver#0", "limiter#0"]
    assert d["filter#3"]["type"] == "Bell" and d["filter#3"]["frequency"] == 3000.0 and d["filter#3"]["gain"] == 3.0
    assert d["convolver#0"]["output-gain"] == 14.0 and base["output"]["convolver#0"]["output-gain"] == 15.5
    again = build_custom(build_custom(base, vals), vals)["output"]  # rebuilding from a custom preset doesn't stack
    assert again["plugins_order"].count("filter#1") == 1
    print("ok")


if __name__ == "__main__":
    _test()

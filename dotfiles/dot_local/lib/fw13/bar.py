"""Waybar refresh signals: one table for the custom modules' "signal" numbers in waybar/config.jsonc.

refresh(name) re-runs that module now (`pkill -RTMIN+N -x waybar`). mako's on-notify sends 12 itself (mako/config).

  python3 -m fw13.bar test   self-check: SIGNALS matches config.jsonc (the repo's, else ~/.config/waybar's)
"""
import json
import os
import re
import subprocess

SIGNALS = {"opencode": 9, "ws": 10, "notifications": 12, "vpn": 13, "profile": 14, "weather": 15,
           "caffeine": 16, "syncthing": 17}


def refresh(name):
    subprocess.run(["pkill", f"-RTMIN+{SIGNALS[name]}", "-x", "waybar"], check=False, stderr=subprocess.DEVNULL)


def selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    paths = [os.path.join(here, "..", "..", "..", "dot_config", "waybar", "config.jsonc"),
             os.path.expanduser("~/.config/waybar/config.jsonc")]
    path = next(p for p in paths if os.path.exists(p))
    conf = json.loads(re.sub(r"^\s*//.*$", "", open(path).read(), flags=re.M))
    bars = conf if isinstance(conf, list) else [conf]
    found = {}
    for bar in bars:
        for key, mod in bar.items():
            if isinstance(mod, dict) and "signal" in mod:
                found[re.sub(r"\d+$", "", key.removeprefix("custom/"))] = mod["signal"]
    assert found == SIGNALS, f"{path}: {found} != {SIGNALS}"
    print(f"bar: ok ({path})")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["test"]:
        selftest()
    else:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)

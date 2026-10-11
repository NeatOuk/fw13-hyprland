"""Jarvis' Claude settings (Settings → Jarvis): model and effort, kept in the store and passed to every `claude` run
(the panel's inline answers, Continue in terminal, fw-jarvis sessions). Empty = Claude Code's own default."""
import json
import os
import re
import subprocess
import time

from . import store

MODELS = [("", "Default (Claude Code's choice)"), ("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"),
          ("haiku", "Haiku")]  # aliases follow the newest model; a full model name can be typed too
EFFORTS = [("", "Default"), ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("xhigh", "Extra high"),
           ("max", "Max")]
_MODEL_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]*")


def check_model(text):
    """(value, error): '' is allowed (the default); anything else must look like an alias or a model id."""
    text = text.strip()
    if text and not _MODEL_OK.fullmatch(text):
        return None, "A model is an alias (opus, sonnet…) or a full name such as claude-opus-5-5"
    return text, None


def model():
    return check_model(str(store.get("jarvis_model") or ""))[0] or ""


def effort():
    e = store.get("jarvis_effort")
    return e if e in {k for k, _ in EFFORTS} else ""


def claude_args():
    """['--model', m] and ['--effort', e] for whichever are set."""
    out = []
    if model():
        out += ["--model", model()]
    if effort():
        out += ["--effort", effort()]
    return out


SECRET_WORDS = re.compile(r"psk|passw|secret|token", re.I)


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout


def _battery():
    from . import power
    b = power.battery()
    if not b:
        return "none"
    rate = f", {b.get('EnergyRate', 0):.1f} W" if b.get("State") in (2, 6) else ""
    return f"{b.get('Percentage', 0):.0f} %, {power.STATES.get(b.get('State'), 'unknown')}{rate}"


def _network():
    from . import net
    up = [f"{d['device']} ({d['type']}) {d['connection']}" for d in net.devices() if d["state"] == "connected"]
    return ", ".join(up) or "not connected"


def _vpn():
    from . import vpn
    on = [v["name"] for v in vpn.vpns() if v["active"]]
    return ", ".join(on) or "none connected"


def _failed():
    sys_units = _run("systemctl", "--failed", "--plain", "--no-legend").split("\n")
    user_units = _run("systemctl", "--user", "--failed", "--plain", "--no-legend").split("\n")
    names = [u.split()[0] for u in sys_units + user_units if u.strip()]
    return ", ".join(names[:5]) + (f" (+{len(names) - 5})" if len(names) > 5 else "") if names else "none"


def _disk():
    rows = _run("df", "-h", "--output=target,avail,pcent", "/", os.path.expanduser("~")).split("\n")[1:]
    return "; ".join(f"{t} {p.strip()} used, {a} free" for t, a, p in (r.split() for r in rows if r.strip()))


def _updates():
    path = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "fw13",
                        "updates.json")
    st = json.load(open(path))
    if "notified" not in st:
        return "none pending at the last check"
    return (f"{st['notified']} packages, {st.get('notified_fw', 0)} firmware "
            f"(as of {time.strftime('%a %H:%M', time.localtime(st.get('notified_at', 0)))})")


def _load():
    up = float(open("/proc/uptime").read().split()[0])
    return f"up {int(up // 3600)} h {int(up % 3600 // 60)} min, load {' '.join(open('/proc/loadavg').read().split()[:3])}"


def _top(field, unit):
    # comm only: full command lines can carry secrets
    rows = _run("ps", "-eo", f"comm,{field}", f"--sort=-{field}", "--no-headers").split("\n")[:3]
    out = []
    for r in rows:
        name, val = r.rsplit(None, 1)
        out.append(f"{name} {float(val) / 1024 / 1024:.1f} GB" if unit == "GB" else f"{name} {val} %")
    return ", ".join(out)


def _errors():
    seen = []
    for line in _run("journalctl", "-p", "err", "-b", "--since", "-2h", "-o", "short-iso", "-q",
                     "--no-pager").split("\n"):
        msg = re.sub(r"\[\d+\]", "", " ".join(line.split()[2:]))[:160]  # drop time, host and pids
        if msg and msg not in seen and not SECRET_WORDS.search(msg):
            seen.append(msg)
    return seen[-5:]


def snapshot():
    """A few short lines about the laptop right now, for the first question of a Jarvis conversation. Every part
    is best effort ("unknown" when it fails) and nothing secret goes in: no passwords, keys, env or command lines."""
    parts = [("Battery", _battery), ("Network", _network), ("VPN", _vpn), ("Failed units", _failed),
             ("Disk", _disk), ("Updates", _updates), ("Uptime", _load),
             ("Top CPU", lambda: _top("%cpu", "%")), ("Top memory", lambda: _top("rss", "GB"))]
    lines = []
    for name, fn in parts:
        try:
            lines.append(f"{name}: {fn()}")
        except Exception:  # noqa: BLE001 — one broken source must not lose the rest
            lines.append(f"{name}: unknown")
    try:
        errs = _errors()
        lines.append("Errors in the last 2 h:" + ("" if errs else " none"))
        lines += [f"  {e}" for e in errs]
    except Exception:  # noqa: BLE001
        lines.append("Errors in the last 2 h: unknown")
    return "\n".join(lines)


def selftest():
    t = time.time()
    snap = snapshot()
    took = time.time() - t
    print(snap)
    assert took < 1, f"snapshot took {took:.2f} s"
    assert len(snap.splitlines()) <= 15
    assert not SECRET_WORDS.search(snap), "secret-looking word in the snapshot"
    print(f"fw13.jarvis: self-check OK ({took:.2f} s)")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["test"]:
        selftest()
        sys.exit(0)  # fw-jarvis (bash): one argument per line
    args = claude_args()
    if args:  # nothing at all when unset: an empty line would become an empty argument
        print("\n".join(args))

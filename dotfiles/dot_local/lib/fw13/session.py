"""Reopen the apps left open: fw-workspaces' daemon saves the open windows (app + workspace, terminals with their
folder) once they've been unchanged for SETTLE seconds, and at the next login reopens them (nothing opens at login otherwise)
(store `session_restore`, Settings → Apps → Startup apps). Shutting down closes windows one by one, but the daemon is
stopped before they settle, so the last settled set is what comes back.

Apps are started from their launcher entry (`uwsm app -- <id>.desktop`), once per app: Chromium, VS Code, Obsidian…
reopen their own windows and tabs. Terminals are started once per window, in the folder their shell was in. Each new
window then moves to the workspace its app had, in order. Our own panels and windows without a launcher entry
(dialogs, games started by Steam) are left out.

  python3 -m fw13.session        what would be saved now
  python3 -m fw13.session test   self-check
"""
import json
import os
import sys
import tempfile

from . import apps, store

STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "fw13", "session.json")
KEY = "session_restore"
SETTLE = 10   # s without window changes before the set is saved
TERMINALS = {"kitty": "kitty", "com.mitchellh.ghostty": "ghostty"}   # window class → fw13.terminal name


def enabled():
    return bool(store.get(KEY))


def shell_cwd(pid):
    """The folder of the first child (the shell) of terminal `pid`; None if unknown."""
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            child = f.read().split()[0]
        return os.readlink(f"/proc/{child}/cwd")
    except (OSError, IndexError):
        return None


def entry_ids(entries):
    """{lower-case window class: desktop id} from StartupWMClass, else the id itself (kitty.desktop → kitty)."""
    out = {}
    for did, _path, keys in entries:
        out.setdefault(did[:-len(".desktop")].lower(), did)
    for did, _path, keys in entries:
        if keys.get("StartupWMClass"):
            out[keys["StartupWMClass"].lower()] = did
    return out


def snapshot(clients, ids, cwd=shell_cwd):
    """[{class, desktop | terminal + dir, workspace}] for the windows worth reopening, in workspace order."""
    out = []
    for c in sorted(clients, key=lambda c: (c.get("workspace", {}).get("id", 0), c.get("at", [0, 0]))):
        cls, ws = (c.get("class") or "").lower(), c.get("workspace", {}).get("id", 0)
        if not cls or ws <= 0 or cls.startswith(("fw-", "fw13")):   # special workspaces, our panels
            continue
        if cls in TERMINALS:
            out.append({"class": cls, "terminal": TERMINALS[cls], "dir": cwd(c.get("pid")), "workspace": ws})
        elif cls in ids:
            out.append({"class": cls, "desktop": ids[cls], "workspace": ws})
    return out


def launches(saved):
    """[(argv, class)] to start: terminals once per window, other apps once."""
    out, seen = [], set()
    for w in saved:
        if "terminal" in w:
            out.append((["fw-term", *(["--dir", w["dir"]] if w.get("dir") and os.path.isdir(w["dir"]) else [])],
                        w["class"]))
        elif w["class"] not in seen:
            seen.add(w["class"])
            out.append(([w["desktop"]], w["class"]))
    return out


def save(windows, path=STATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(windows, f)
    os.replace(tmp, path)


def load(path=STATE):
    try:
        with open(path) as f:
            data = json.load(f)
        return [w for w in data if isinstance(w, dict) and w.get("class") and w.get("workspace")]
    except (OSError, ValueError, TypeError):
        return []


def test():
    entries = [("chromium-browser.desktop", "", {"StartupWMClass": "Chromium-browser"}),
               ("kitty.desktop", "", {}), ("org.telegram.desktop.desktop", "", {})]
    ids = entry_ids(entries)
    clients = [{"class": "chromium-browser", "workspace": {"id": 11}, "pid": 1},
               {"class": "chromium-browser", "workspace": {"id": 2}, "pid": 2},
               {"class": "kitty", "workspace": {"id": 1}, "pid": 3},
               {"class": "kitty", "workspace": {"id": 1}, "pid": 4},
               {"class": "org.telegram.desktop", "workspace": {"id": 3}, "pid": 5},
               {"class": "fw-jarvis", "workspace": {"id": 1}, "pid": 6},
               {"class": "steam_app_42", "workspace": {"id": 4}, "pid": 7},
               {"class": "kitty", "workspace": {"id": -98}, "pid": 8}]
    snap = snapshot(clients, ids, cwd=lambda pid: "/" if pid == 3 else None)
    assert [(w["class"], w["workspace"]) for w in snap] == [
        ("kitty", 1), ("kitty", 1), ("chromium-browser", 2), ("org.telegram.desktop", 3), ("chromium-browser", 11)], snap
    plan = launches(snap)
    assert plan == [(["fw-term", "--dir", "/"], "kitty"), (["fw-term"], "kitty"),
                    (["chromium-browser.desktop"], "chromium-browser"),
                    (["org.telegram.desktop.desktop"], "org.telegram.desktop")], plan
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "s.json")
        save(snap, p)
        assert load(p) == snap
        with open(p, "w") as f:
            f.write("{broken")
        assert load(p) == []
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        from .hypr import hj
        print(json.dumps(snapshot(hj("clients"), entry_ids(apps.launcher_entries())), indent=1))

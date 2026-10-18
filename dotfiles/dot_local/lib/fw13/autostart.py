"""Startup apps: the XDG autostart entries uwsm starts at a Hyprland login (systemd-xdg-autostart-generator), with an
on/off switch each in Settings → Apps.

Off writes your own copy in ~/.config/autostart with Hyprland added to NotShowIn, so other desktops on this account
(GNOME, KDE) still start it (rule 3a); a copy made here carries X-fw13-Disabled=true and is deleted again by On.
Copies you or another app made are edited in place (only their NotShowIn line). Takes effect at the next login.

  python3 -m fw13.autostart        list: id, on/off, name
  python3 -m fw13.autostart test   self-check
"""
import os
import shutil
import sys
import tempfile

from .apps import parse_entry

DESKTOP = "Hyprland"
MARK = "X-fw13-Disabled=true"
# Off for good in Hyprland: chezmoi manages these copies (dotfiles/dot_config/autostart); {id: what replaces it}
REPLACED = {"blueman.desktop": "the bar's Bluetooth menu and fw-bt-agent",
            "nm-applet.desktop": "the bar's network menu",
            "com.cloudflare.WarpTaskbar.desktop": "the bar's cloud icon"}
# Needed by the desktop: shown, no switch
NEEDED = {"geoclue-demo-agent.desktop": "lets automatic time zone and night light find your location"}


def user_dir():
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "autostart")


def system_dirs():
    return [os.path.join(d, "autostart") for d in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":")]


def desktops(value):
    return [d for d in (value or "").split(";") if d]


def runs_here(keys, ignore_not_show=False):
    """Would this entry start in Hyprland? ignore_not_show: as if our Hyprland in NotShowIn weren't there."""
    if keys.get("Type", "Application") != "Application" or keys.get("Hidden") == "true":
        return False
    # systemd-xdg-autostart-generator's own skips (GNOME starts those itself, e.g. xdg-user-dirs)
    if keys.get("X-systemd-skip") == "true" or keys.get("X-GNOME-Autostart-enabled") == "false":
        return False
    only, nots = desktops(keys.get("OnlyShowIn")), desktops(keys.get("NotShowIn"))
    if only and DESKTOP not in only:
        return False
    if DESKTOP in nots and not ignore_not_show:
        return False
    try_exec = keys.get("TryExec") or (keys.get("Exec") or "").split(" ")[0]
    return bool(try_exec) and bool(shutil.which(try_exec) or os.path.isfile(try_exec))


def _read(path):
    try:
        with open(path, errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def entries(udir=None, sdirs=None):
    """[{id, name, on, user_path, system_path, fixed}] for every entry that starts, or would start, in Hyprland."""
    udir, sdirs = udir or user_dir(), sdirs or system_dirs()
    ids = set()
    for d in [udir] + sdirs:
        ids.update(f for f in (os.listdir(d) if os.path.isdir(d) else []) if f.endswith(".desktop"))
    out = []
    for did in sorted(ids):
        upath = os.path.join(udir, did)
        spath = next((p for p in (os.path.join(d, did) for d in sdirs) if os.path.isfile(p)), None)
        utext, stext = _read(upath), _read(spath) if spath else None
        eff = parse_entry(utext if utext is not None else stext or "")
        base = parse_entry(stext) if utext is not None and MARK in utext and stext else eff
        if not runs_here(base, ignore_not_show=utext is not None):
            continue
        fixed = (f"Off: {REPLACED[did]} does this" if did in REPLACED
                 else f"Needed: {NEEDED[did]}" if did in NEEDED else None)
        out.append({"id": did, "name": eff.get("Name", did[:-8]), "on": runs_here(eff),
                    "user_path": upath if utext is not None else None, "system_path": spath, "fixed": fixed})
    return out


def _set_not_show(text, on):
    """`text` with Hyprland removed from (on) or added to (off) NotShowIn in [Desktop Entry]."""
    lines, group, done = text.splitlines(), None, False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("["):
            if group == "[Desktop Entry]" and not done and not on:
                lines.insert(i, f"NotShowIn={DESKTOP};")
                done = True
                break
            group = s
        elif group == "[Desktop Entry]" and s.startswith("NotShowIn="):
            ds = [d for d in desktops(s.split("=", 1)[1]) if d != DESKTOP] + ([] if on else [DESKTOP])
            lines[i] = "NotShowIn=" + "".join(d + ";" for d in ds)
            done = True
    if not done and not on:
        lines.append(f"NotShowIn={DESKTOP};")
    return "\n".join(lines) + "\n"


def set_on(entry, on, udir=None):
    """Turn a startup app on or off for Hyprland logins."""
    if entry["fixed"]:
        raise ValueError(f"{entry['id']} can't be changed here")
    udir = udir or user_dir()
    path = entry["user_path"] or os.path.join(udir, entry["id"])
    text = _read(path) if entry["user_path"] else None
    if on and text is not None and MARK in text and entry["system_path"]:
        os.remove(path)   # our copy: the system entry runs again
        return
    if text is None:
        text = _read(entry["system_path"]) or ""
        text = text.replace("[Desktop Entry]\n", f"[Desktop Entry]\n# Turned off in Settings → Apps → Startup apps\n{MARK}\n", 1)
    os.makedirs(udir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(_set_not_show(text, on))
    os.replace(tmp, path)


def test():
    with tempfile.TemporaryDirectory() as t:
        u, s = os.path.join(t, "u"), os.path.join(t, "s")
        os.makedirs(u), os.makedirs(s)
        files = {f"{s}/a.desktop": "[Desktop Entry]\nName=A\nExec=sh -c x\n[Desktop Action x]\nExec=sh\n",
                 f"{s}/gnome.desktop": "[Desktop Entry]\nName=G\nExec=sh\nOnlyShowIn=GNOME;\n",
                 f"{s}/gone.desktop": "[Desktop Entry]\nName=Gone\nExec=/nonexistent/bin\n",
                 f"{s}/skip.desktop": "[Desktop Entry]\nName=S\nExec=sh\nX-systemd-skip=true\n",
                 f"{s}/kde.desktop": "[Desktop Entry]\nName=K\nExec=sh\nNotShowIn=KDE;\n",
                 f"{u}/mine.desktop": "[Desktop Entry]\nName=Mine\nExec=sh\n",
                 f"{u}/blueman.desktop": "[Desktop Entry]\nName=Blueman\nExec=sh\nNotShowIn=Hyprland;\n"}
        for p, text in files.items():
            with open(p, "w") as f:
                f.write(text)
        e = {x["id"]: x for x in entries(u, [s])}
        assert set(e) == {"a.desktop", "kde.desktop", "mine.desktop", "blueman.desktop"}, e
        assert e["a.desktop"]["on"] and not e["blueman.desktop"]["on"] and e["blueman.desktop"]["fixed"]
        set_on(e["a.desktop"], False, u)
        text = open(f"{u}/a.desktop").read()
        assert MARK in text and "NotShowIn=Hyprland;\n[Desktop Action x]" in text, text
        assert not {x["id"]: x for x in entries(u, [s])}["a.desktop"]["on"]
        set_on({x["id"]: x for x in entries(u, [s])}["a.desktop"], True, u)
        assert not os.path.exists(f"{u}/a.desktop")
        set_on(e["kde.desktop"], False, u)
        assert "NotShowIn=KDE;Hyprland;" in open(f"{u}/kde.desktop").read()
        set_on(e["mine.desktop"], False, u)
        assert open(f"{u}/mine.desktop").read().endswith("NotShowIn=Hyprland;\n")
        set_on({x["id"]: x for x in entries(u, [s])}["mine.desktop"], True, u)
        assert "NotShowIn=\n" in open(f"{u}/mine.desktop").read()
        assert {x["id"]: x for x in entries(u, [s])}["mine.desktop"]["on"]
        try:
            set_on(e["blueman.desktop"], True, u)
            raise AssertionError("fixed entry changed")
        except ValueError:
            pass
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        for x in entries():
            print(f"{x['id']:<55} {'on ' if x['on'] else 'off'} {x['name']}{'  (' + x['fixed'] + ')' if x['fixed'] else ''}")

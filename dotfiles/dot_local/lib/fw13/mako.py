"""mako notifications for the bar bell (fw-notifications) and the Notification Center (fw-notification-center):
current and past notifications, do-not-disturb, the "seen" mark behind the bell's unread count.

Unread = notifications newer than the `notif_seen` mark in fw13.store ({"mako": <pid>:<start time>, "id": N}, set
when the bell's menu or the Notification Center opens). mako numbers notifications from 1 again after a restart,
so the mark resets when the mako process it was taken from is gone (not when ids drop: `makoctl dismiss -h` or an
app closing its own notification removes the newest without a restart). fw-osd popups are left out everywhere.

  python3 -m fw13.mako test   self-check (parsing only, no mako needed)
"""
import html
import json
import os
import re
import subprocess

from . import bar as waybar, store

DND = "do-not-disturb"
SKIP_APPS = {"fw-osd"}
DESKTOP_ID = re.compile(r"[A-Za-z0-9._-]+")  # what gtk-launch gets: an app id, never a path or an option
BELL, BELL_SLASH = "", ""  # Font Awesome 6 Free: bell, bell-slash


def bar_refresh():
    waybar.refresh("notifications")


def makoctl(*args):
    try:
        r = subprocess.run(["makoctl", *args], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _plain(v):
    """A field's value: mako ≥ 1.9 prints plain JSON; older makoctl printed busctl's {"type": …, "data": …}."""
    if isinstance(v, dict) and "data" in v:
        return _plain(v["data"])
    return v


def _field(n, *names):
    for name in names:  # "app_name" today, "app-name" in the D-Bus dict / older makoctl
        if name in n:
            return _plain(n[name])
    return None


def notifications(cmd):
    """[{id, app, summary, body, actions, active}] from `makoctl list|history -j`; anything unreadable is skipped."""
    out = makoctl(cmd, "-j")
    try:
        data = json.loads(out) if out else []
    except ValueError:
        return []
    data = _plain(data)
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], list):  # busctl's [[…]]
        data = data[0]
    if not isinstance(data, list):
        return []
    result = []
    for n in data:
        if not isinstance(n, dict):
            continue
        try:
            nid = int(_field(n, "id"))
        except (TypeError, ValueError):
            continue
        app = str(_field(n, "app_name", "app-name") or "")
        if app in SKIP_APPS:
            continue
        actions = _field(n, "actions")
        desktop = _field(n, "desktop_entry", "desktop-entry")
        result.append({"id": nid, "app": app, "active": cmd == "list",
                       "desktop": desktop if isinstance(desktop, str) and DESKTOP_ID.fullmatch(desktop) else "",
                       "actions": actions if isinstance(actions, dict) else {},
                       "summary": str(_field(n, "summary") or ""), "body": str(_field(n, "body") or "")})
    return result


def everything():
    """Visible and dismissed notifications, newest first, each id once."""
    seen, result = set(), []
    for n in sorted(notifications("list") + notifications("history"), key=lambda n: -n["id"]):
        if n["id"] not in seen:
            seen.add(n["id"])
            result.append(n)
    return result


def dnd_on():
    return DND in (makoctl("mode") or "").split()


def plain_text(s):
    """mako bodies may hold Pango markup: drop tags, decode entities."""
    return html.unescape(re.sub(r"<[^>]*>", "", s))


def mako_instance():
    """"<pid>:<start time>" of the running mako (start time: a reused pid is a different process), or None."""
    r = subprocess.run(["pgrep", "-x", "-u", str(os.getuid()), "mako"], capture_output=True, text=True)
    pids = r.stdout.split()
    if len(pids) != 1:  # none, or one per seat/session: can't tell which one is ours
        return None
    try:
        with open(f"/proc/{pids[0]}/stat") as f:
            start = f.read().rsplit(")", 1)[1].split()[19]  # field 22 (starttime), counted after "(comm)"
    except (OSError, IndexError):
        return None
    return f"{pids[0]}:{start}"


def seen_mark():
    saved = store.get("notif_seen")
    if not isinstance(saved, dict):  # unset, or a bare id from an older version: adopt it for this mako
        saved = {"mako": None, "id": saved if isinstance(saved, int) else 0}
    mark, inst = saved.get("id") or 0, mako_instance()
    if inst and saved.get("mako") != inst:
        if saved.get("mako"):  # mako restarted: ids began again at 1
            mark = 0
        store.set("notif_seen", {"mako": inst, "id": mark})
    return mark


def mark_seen(nid):
    store.set("notif_seen", {"mako": mako_instance(), "id": nid})


def toggle_dnd():
    makoctl("mode", "-t", DND)
    bar_refresh()
    waybar.refresh("profile")  # fw-profile: DND off leaves Focus/Zen




def bar_refresh():
    waybar.refresh("notifications")


def copy(text):
    """Put text on the clipboard; wl-copy stays running to serve it, so don't wait."""
    try:
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        p.stdin.write(text.encode())
        p.stdin.close()
    except OSError:
        pass


def _test():
    global makoctl
    real = makoctl
    sample = json.dumps([{"id": 3, "app_name": "Telegram", "summary": "Hi", "body": "<b>a</b> &amp; b",
                          "actions": {"default": "View"}, "desktop_entry": "org.telegram.desktop"},
                         {"id": 4, "app_name": "Evil", "desktop_entry": "--help /tmp/x"},
                         {"id": 2, "app_name": "fw-osd", "summary": "vol"}, {"id": "x"}, "junk"])
    try:
        makoctl = lambda *a: sample if a[0] == "list" else "[]"  # noqa: E731
        items = everything()
        assert [n["id"] for n in items] == [4, 3] and items[1]["active"] and items[1]["actions"] == {"default": "View"}
        assert items[1]["desktop"] == "org.telegram.desktop" and items[0]["desktop"] == ""
        items = items[1:]
        assert plain_text(items[0]["body"]) == "a & b"
    finally:
        makoctl = real
    print("fw13.mako: self-check OK")


if __name__ == "__main__":
    import sys
    sys.exit(_test() if sys.argv[1:] == ["test"] else print(__doc__.strip()))

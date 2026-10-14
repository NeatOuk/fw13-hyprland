"""Syncthing (the user service syncthing.service) over its REST API, for Settings → Syncthing: status, plus adding,
pausing, sharing and removing devices and folders through Syncthing's own config endpoints (it validates and saves).

The GUI address and API key come from config.xml (<gui tls=…><address>, <apikey>), read at every call and never
logged: ~/.local/state/syncthing (Syncthing ≥ 1.27 / 2.x) or the older ~/.config/syncthing.

  python3 -m fw13.syncthing test   self-check (sample configs, formatting, no key / unreachable; live counts if running)
"""
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import store

UNIT = "syncthing.service"
CONFIGS = ("$XDG_STATE_HOME/syncthing/config.xml", "~/.local/state/syncthing/config.xml",
           "~/.config/syncthing/config.xml")
TIMEOUT = 3


class Error(Exception):
    """A one-line reason the API can't be used (shown dimmed on the page)."""


def installed():
    return bool(shutil.which("syncthing"))


def config_path():
    for p in CONFIGS:
        p = os.path.expanduser(os.path.expandvars(p))
        if "$" not in p and os.path.isfile(p):
            return p
    return None


def gui(xml_text):
    """(base URL, API key or None) from config.xml text. A wildcard listen address is reached on 127.0.0.1."""
    g = ET.fromstring(xml_text).find("gui")
    if g is None:
        raise Error("Syncthing's config has no GUI section")
    addr = (g.findtext("address") or "127.0.0.1:8384").strip()
    if addr.startswith("unix"):
        raise Error("Syncthing's GUI listens on a unix socket: not supported here")
    host, _, port = addr.rpartition(":")
    if host in ("", "0.0.0.0", "[::]"):
        host = "127.0.0.1"
    tls = g.get("tls", "false").lower() == "true"
    return f"{'https' if tls else 'http'}://{host}:{port}", (g.findtext("apikey") or "").strip() or None


def api(endpoint, method="GET", path=None, body=None, timeout=TIMEOUT):
    """JSON from the REST API (None for an empty body); `body` is sent as JSON. Error with a short reason otherwise."""
    path = path or config_path()
    if not path:
        raise Error("No Syncthing config found (it is created the first time Syncthing runs)")
    try:
        with open(path, encoding="utf-8") as f:
            url, key = gui(f.read())
    except (OSError, ET.ParseError) as e:
        raise Error(f"Can't read Syncthing's config: {e.__class__.__name__}") from None
    if not key:
        raise Error("Syncthing's config has no API key")
    headers = {"X-API-Key": key}
    data = None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(url + endpoint, data=data, method=method, headers=headers)
    # the GUI's TLS cert is self-signed; it's our own loopback service
    ctx = ssl._create_unverified_context() if url.startswith("https") else None  # noqa: S323
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            out = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace").strip().splitlines()[:1]  # Syncthing's own reason, e.g. a bad path
        raise Error(f"Syncthing answered {e.code} {e.reason}" + (f": {detail[0][:200]}" if detail else "")) from None
    except (urllib.error.URLError, OSError) as e:
        raise Error(f"Syncthing's API at {url} is not reachable") from e
    return json.loads(out) if out.strip() else None


def service():
    """(running, enabled) of the user unit."""
    def q(verb):
        return subprocess.run(["systemctl", "--user", verb, UNIT], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    return q("is-active") == "active", q("is-enabled") == "enabled"


def set_service(on):
    """Start + enable, or stop + disable, the user unit. (ok, message)."""
    r = subprocess.run(["systemctl", "--user", "enable" if on else "disable", "--now", UNIT],
                       capture_output=True, text=True, timeout=30)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


def rescan():
    api("/rest/db/scan", method="POST")


def _q(text):
    return urllib.parse.quote(text, safe="")


def check_id(text):
    """A pasted device ID → Syncthing's normalised form (it accepts any case, spaces, missing dashes); Error if bad."""
    res = api(f"/rest/svc/deviceid?id={_q(text.strip())}") or {}
    if "id" not in res:
        raise Error(f"Not a valid device ID: {res.get('error', 'unknown error')}")
    return res["id"]


def add_device(device_id, name):
    """Add a device with Syncthing's defaults for new devices (as its own "Add Device" does)."""
    dev = {**api("/rest/config/defaults/device"), "deviceID": device_id, "name": name.strip()}
    api("/rest/config/devices", "POST", body=dev)


def new_folder_id():
    """Random ID in Syncthing's own style (xxxxx-xxxxx); IDs must match on every device sharing the folder."""
    abc = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "-".join("".join(secrets.choice(abc) for _ in range(5)) for _ in range(2))


def add_folder(path, label, device_ids, folder_id=None):
    """Add a folder (created if missing) shared with `device_ids`, with Syncthing's defaults for new folders."""
    path = os.path.expanduser(path.strip())
    if not os.path.isabs(path):
        raise Error("The folder path must be absolute (or start with ~)")
    os.makedirs(path, exist_ok=True)
    f = api("/rest/config/defaults/folder")
    devices = list(f.get("devices") or [])  # the defaults hold this device
    devices += [{"deviceID": d} for d in device_ids if d not in {x["deviceID"] for x in devices}]
    api("/rest/config/folders", "POST", body={**f, "id": folder_id or new_folder_id(),
                                               "label": label.strip() or os.path.basename(path), "path": path,
                                               "devices": devices})


def set_paused(kind, ident, paused):
    """Pause or resume a device or folder (kind "device" / "folder")."""
    api(f"/rest/config/{kind}s/{_q(ident)}", "PATCH", body={"paused": bool(paused)})


def remove(kind, ident):
    """Remove a device or folder from Syncthing (a folder's files stay on disk)."""
    api(f"/rest/config/{kind}s/{_q(ident)}", "DELETE")


def share(folder_id, device_id, on):
    """Share a folder with a device, or stop sharing it."""
    f = api(f"/rest/config/folders/{_q(folder_id)}")
    devices = [d for d in f.get("devices") or [] if d["deviceID"] != device_id]
    if on:
        devices.append({"deviceID": device_id})
    api(f"/rest/config/folders/{_q(folder_id)}", "PATCH", body={"devices": devices})


def default_path(label):
    """Where an accepted folder goes unless the owner picks another place: ~/Sync/<label>."""
    safe = label.replace("/", "_").strip(". ") or "folder"
    return os.path.join(os.path.expanduser("~/Sync"), safe)


def pending():
    """Open requests: [{"kind": "device", "id", "name", "address"} | {"kind": "folder", "id", "label", "device"}]."""
    out = [{"kind": "device", "id": i, "name": v.get("name") or short_id(i), "address": v.get("address", "")}
           for i, v in (api("/rest/cluster/pending/devices") or {}).items()
           if i not in (store.get("syncthing_ignored") or [])]
    for fid, v in (api("/rest/cluster/pending/folders") or {}).items():
        out += [{"kind": "folder", "id": fid, "label": o.get("label") or fid, "device": dev}
                for dev, o in (v.get("offeredBy") or {}).items()]
    return out


def accept_folder(folder_id, label, device_id, path):
    """Accept a folder a device shares: share ours with it if we already have that folder ID, else add it at `path`."""
    if any(f["id"] == folder_id for f in api("/rest/config/folders")):
        share(folder_id, device_id, True)
    else:
        add_folder(path, label, [device_id], folder_id=folder_id)


def ignore_device(device_id):
    """Dismiss a device's request; Syncthing lists it again if it keeps asking, so it is also remembered in store
    `syncthing_ignored` and left out of pending() from then on."""
    api(f"/rest/cluster/pending/devices?device={_q(device_id)}", "DELETE")
    store.set("syncthing_ignored", sorted({*(store.get("syncthing_ignored") or []), device_id}))


def ignore_folder(folder_id, label, device_id):
    """Ignore a folder for good: Syncthing's own per-device ignoredFolders list (Remove there to undo)."""
    dev = api(f"/rest/config/devices/{_q(device_id)}")
    ignored = [x for x in dev.get("ignoredFolders") or [] if x.get("id") != folder_id]
    ignored.append({"id": folder_id, "label": label, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    api(f"/rest/config/devices/{_q(device_id)}", "PATCH", body={"ignoredFolders": ignored})


CONFLICT = re.compile(r"^(.*)\.sync-conflict-\d{8}-\d{6}-[A-Z0-9]{7}(\.[^/]*)?$")
SKIP_DIRS = {".stfolder", ".stversions", ".stignore"}


def is_conflict(path):
    return bool(CONFLICT.match(os.path.basename(path)))


def original(path):
    """notes.sync-conflict-20261014-101500-ABCDEFG.txt → notes.txt (same directory)."""
    m = CONFLICT.match(os.path.basename(path))
    return os.path.join(os.path.dirname(path), m.group(1) + (m.group(2) or "")) if m else path


def conflicts(folders, limit=100):
    """Conflict copies in the folders' paths: [{"folder": label, "path"}], at most `limit`.
    shortcut: walks the folders (no Syncthing API lists conflicts); fine for home-sized folders, cache it in callers."""
    out = []
    for f in folders:
        for root, dirs, files in os.walk(f["path"]):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            out += [{"folder": f["label"], "path": os.path.join(root, n)} for n in files if CONFLICT.match(n)]
            if len(out) >= limit:
                return out[:limit]
    return out


def _trash(path):
    from gi.repository import Gio
    Gio.File.new_for_path(path).trash(None)


def keep_conflict(path):
    """Use the conflict copy: the current file goes to the Trash, the copy takes its name."""
    orig = original(path)
    if orig == path or not os.path.exists(path):
        raise Error("Not a conflict copy (or already gone)")
    if os.path.exists(orig):
        _trash(orig)
    os.replace(path, orig)


def drop_conflict(path):
    """Keep the current file: the conflict copy goes to the Trash."""
    if not is_conflict(path):
        raise Error("Not a conflict copy")
    _trash(path)


def folder_errors(folder_id, limit=5):
    """[{"path", "error"}] of items that failed to sync, at most `limit`."""
    res = api(f"/rest/folder/errors?folder={_q(folder_id)}") or {}
    return (res.get("errors") or [])[:limit]


def short_id(device_id):
    """Syncthing's own short form: the first group of the device ID."""
    return device_id.split("-", 1)[0]


def seen(ts):
    """'never' or 'YYYY-MM-DD HH:MM' (Syncthing reports times in the local zone)."""
    return "never" if not ts or ts[:4] < "2000" else ts[:16].replace("T", " ")


def via(conn_type):
    """'relay' / 'direct' from a connection type like tcp-client, quic-server, relay-client."""
    return "relay" if conn_type.startswith("relay") else "direct"


def folder_state(cfg, st):
    """Text for a folder: paused / error … / syncing NN % / idle / scanning …, from its config + /rest/db/status."""
    if cfg.get("paused"):
        return "paused"
    if not st:
        return "unknown"
    state = st.get("state") or "unknown"
    if st.get("error") or "error" in state:
        return f"error: {st.get('error') or state}"
    if state.startswith("sync"):
        total = st.get("globalBytes") or 0
        pct = 100 * (total - (st.get("needBytes") or 0)) // total if total else 0
        return f"syncing {pct} %"
    return state


def snapshot():
    """Everything the page shows, in one call (several requests): version, my ID, other devices, folders."""
    me = api("/rest/system/status")["myID"]
    version = api("/rest/system/version")["version"]
    conns = (api("/rest/system/connections") or {}).get("connections", {})
    stats = api("/rest/stats/device") or {}
    devices = []
    for d in api("/rest/config/devices"):
        if d["deviceID"] == me:
            continue
        c = conns.get(d["deviceID"]) or {}
        devices.append({"name": d.get("name") or short_id(d["deviceID"]), "id": d["deviceID"],
                        "paused": bool(d.get("paused")), "connected": bool(c.get("connected")),
                        "via": via(c.get("type") or "") if c.get("connected") else None,
                        "seen": seen((stats.get(d["deviceID"]) or {}).get("lastSeen"))})
    folders = []
    for f in api("/rest/config/folders"):
        try:
            st = None if f.get("paused") else api(f"/rest/db/status?folder={urllib.parse.quote(f['id'])}")
        except Error:
            st = None
        shared = [d["deviceID"] for d in f.get("devices", []) if d.get("deviceID") != me]
        try:
            errors = folder_errors(f["id"]) if st and st.get("pullErrors") else []
        except Error:
            errors = []
        folders.append({"id": f["id"], "label": f.get("label") or f["id"], "path": f.get("path", ""),
                        "paused": bool(f.get("paused")), "state": folder_state(f, st),
                        "shared": len(shared), "devices": shared, "errors": errors,
                        "failing": (st or {}).get("pullErrors") or 0})
    return {"version": version, "id": me, "devices": devices, "folders": folders}


SAMPLE = """<configuration version="51">
  <device id="AAAAAAA-BBBBBBB" name="x"></device>
  <gui enabled="true" tls="{tls}" debugging="false">
    <address>{addr}</address>
    {key}
    <theme>default</theme>
  </gui>
</configuration>"""


def test():
    import tempfile
    assert gui(SAMPLE.format(tls="false", addr="127.0.0.1:8384", key="<apikey>k1</apikey>")) == \
        ("http://127.0.0.1:8384", "k1")
    assert gui(SAMPLE.format(tls="true", addr="0.0.0.0:9999", key="<apikey> k2 </apikey>")) == \
        ("https://127.0.0.1:9999", "k2")
    assert gui(SAMPLE.format(tls="false", addr="127.0.0.1:8384", key=""))[1] is None
    assert short_id("UST6SE2-7M6P4LI-XNCA64A") == "UST6SE2"
    assert seen("1970-01-01T07:00:00+07:00") == "never" and seen("2026-10-13T07:57:31.12+07:00") == "2026-10-13 07:57"
    fid = new_folder_id()
    assert len(fid) == 11 and fid[5] == "-" and fid.replace("-", "").isalnum() and fid != new_folder_id()
    assert default_path("Photos") == os.path.expanduser("~/Sync/Photos")
    assert default_path("a/b") == os.path.expanduser("~/Sync/a_b") and default_path("..").endswith("/folder")
    c = "/x/notes.sync-conflict-20261014-101500-ABCDEFG.txt"
    assert is_conflict(c) and original(c) == "/x/notes.txt" and not is_conflict("/x/notes.txt")
    assert original("/x/Makefile.sync-conflict-20261014-101500-ABCDEFG") == "/x/Makefile"
    assert original("/x/a.tar.sync-conflict-20261014-101500-ABC1234.gz") == "/x/a.tar.gz"
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "sub")); os.makedirs(os.path.join(d, ".stversions"))
        for n in ("sub/" + os.path.basename(c), ".stversions/" + os.path.basename(c), "plain.txt"):
            open(os.path.join(d, n), "w").close()
        assert [x["path"] for x in conflicts([{"label": "L", "path": d}])] == [os.path.join(d, "sub", os.path.basename(c))]
        try:
            drop_conflict(os.path.join(d, "plain.txt"))
            raise AssertionError("expected Error")
        except Error:
            pass
    assert _q("a b/c?") == "a%20b%2Fc%3F"
    assert via("relay-client") == "relay" and via("tcp-server") == "direct" and via("quic-client") == "direct"
    assert folder_state({"paused": True}, None) == "paused"
    assert folder_state({}, {"state": "idle"}) == "idle"
    assert folder_state({}, {"state": "syncing", "globalBytes": 200, "needBytes": 50}) == "syncing 75 %"
    assert folder_state({}, {"state": "sync-preparing", "globalBytes": 0}) == "syncing 0 %"
    assert folder_state({}, {"state": "error", "error": "folder path missing"}) == "error: folder path missing"
    assert folder_state({}, None) == "unknown"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "config.xml")
        for key, want in (("", "no API key"), ("<apikey>secret</apikey>", "not reachable")):
            with open(p, "w") as f:  # port 1 on loopback: nothing listens → refused at once
                f.write(SAMPLE.format(tls="false", addr="127.0.0.1:1", key=key))
            try:
                api("/rest/system/status", path=p)
                raise AssertionError("expected Error")
            except Error as e:
                assert want in str(e) and "secret" not in str(e), e
        try:
            api("/rest/system/status", path=os.path.join(d, "missing.xml"))
            raise AssertionError("expected Error")
        except Error as e:
            assert "Can't read" in str(e), e
    print("unit: ok")
    if installed() and service()[0]:  # live, read-only: counts only (never the key)
        try:
            s = snapshot()
            print(f"live: {s['version']}, my ID {short_id(s['id'])}, {len(s['devices'])} other device(s), "
                  f"{len(s['folders'])} folder(s): " + ", ".join(f"{f['label']} {f['state']}" for f in s["folders"]))
        except Error as e:
            print(f"live: {e}")
    else:
        print("live: skipped (Syncthing not installed or not running)")
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        sys.exit(__doc__)

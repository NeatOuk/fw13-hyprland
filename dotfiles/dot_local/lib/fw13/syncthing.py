"""Syncthing (the user service syncthing.service) over its REST API, for Settings → Syncthing. Read-only except
start/stop of the service and "Rescan all"; Syncthing's own configuration is never written.

The GUI address and API key come from config.xml (<gui tls=…><address>, <apikey>), read at every call and never
logged: ~/.local/state/syncthing (Syncthing ≥ 1.27 / 2.x) or the older ~/.config/syncthing.

  python3 -m fw13.syncthing test   self-check (sample configs, formatting, no key / unreachable; live counts if running)
"""
import json
import os
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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


def api(endpoint, method="GET", path=None):
    """JSON from the REST API (None for an empty body); Error with a short reason otherwise."""
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
    req = urllib.request.Request(url + endpoint, method=method, headers={"X-API-Key": key})
    # the GUI's TLS cert is self-signed; it's our own loopback service
    ctx = ssl._create_unverified_context() if url.startswith("https") else None  # noqa: S323
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise Error(f"Syncthing answered {e.code} {e.reason}") from None
    except (urllib.error.URLError, OSError) as e:
        raise Error(f"Syncthing's API at {url} is not reachable") from e
    return json.loads(body) if body.strip() else None


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
        folders.append({"label": f.get("label") or f["id"], "path": f.get("path", ""),
                        "state": folder_state(f, st),
                        "shared": sum(1 for d in f.get("devices", []) if d.get("deviceID") != me)})
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

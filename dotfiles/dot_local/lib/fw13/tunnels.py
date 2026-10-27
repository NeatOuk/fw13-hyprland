"""Direct office tunnels: an SSH SOCKS proxy through a jump host + a browser window that uses only it, so a site that
allows only the jump host's IP sees every request (downloads included) coming from there.

The tunnels live only in ~/.config/fw13/tunnels.json (hosts and user names are private: never in the chezmoi
source / git). A JSON list:
  [{"name": "Office app", "jump": "user@192.0.2.10", "url": "https://198.51.100.5/", "port": 1080}]
port (local SOCKS port on 127.0.0.1) is optional, default 1080 + the entry's index.

start() runs `ssh -N -D` in a terminal (fw-term), so a password or host-key question is answered there; the terminal
holds the tunnel, closing it (or stop()) ends it. open_browser() starts Chromium with its own profile per tunnel
(~/.cache/fw13-tunnel-<slug>), so the proxy applies even while the normal Chromium is open.
"""
import json
import os
import re
import socket
import subprocess
import time

CONFIG = os.path.expanduser("~/.config/fw13/tunnels.json")
RUNTIME = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
JUMP_RE = re.compile(r"^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9.:_-]+$")  # [user@]host; no spaces, no leading '-'


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "tunnel"


def parse(data):
    """Valid entries from the JSON list (bad ones dropped: they reach ssh's argv)."""
    out = []
    for i, t in enumerate(data if isinstance(data, list) else []):
        if not isinstance(t, dict):
            continue
        name, jump, url = t.get("name"), t.get("jump"), t.get("url")
        port = t.get("port", 1080 + i)
        if not (isinstance(name, str) and name.strip() and isinstance(jump, str) and JUMP_RE.match(jump)
                and not jump.startswith("-") and isinstance(url, str) and re.match(r"^https?://\S+$", url)
                and isinstance(port, int) and 1024 <= port <= 65535):
            continue
        out.append({"name": name.strip(), "jump": jump, "url": url, "port": port, "slug": slug(name)})
    return out


def load():
    try:
        with open(CONFIG) as f:
            return parse(json.load(f))
    except (OSError, ValueError):
        return []


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def pidfile(t):
    return os.path.join(RUNTIME, f"fw13-tunnel-{t['slug']}.pid")


def ssh_argv(t):
    return ["ssh", "-N", "-D", f"127.0.0.1:{t['port']}", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30", "--", t["jump"]]


def start(t):
    """ssh in a terminal; the shell writes its pid and execs ssh, so the pid is ssh's."""
    cmd = 'echo $$ > "$1"; shift; exec "$@"'
    subprocess.Popen(["fw-term", "--class", "fw-tunnel", "-e", "bash", "-c", cmd, "tunnel", pidfile(t), *ssh_argv(t)],
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(t):
    try:
        with open(pidfile(t)) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"ssh" not in f.read().split(b"\0")[0]:
                return
        os.kill(pid, 15)
    except (OSError, ValueError):
        pass


def browser_argv(t):
    return ["uwsm", "app", "--", "chromium-browser", f"--proxy-server=socks5://127.0.0.1:{t['port']}",
            f"--user-data-dir={os.path.expanduser('~/.cache/fw13-tunnel-' + t['slug'])}", "--no-first-run", t["url"]]


def open_browser(t):
    subprocess.Popen(browser_argv(t), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def connect_and_open(t, wait=120):
    """Start the tunnel unless it's up, wait for it (password typed in the terminal), then open the browser."""
    if not listening(t["port"]):
        start(t)
        end = time.time() + wait
        while not listening(t["port"]):
            if time.time() > end:
                return "the tunnel didn't come up (closed terminal, wrong password or host?)"
            time.sleep(0.5)
    open_browser(t)
    return None


def test():
    good = {"name": "Office App", "jump": "me@192.0.2.10", "url": "https://198.51.100.5/"}
    ts = parse([good, dict(good, jump="-oProxyCommand=x"), dict(good, jump="a b"), dict(good, url="file:///x"),
                dict(good, port=80), "x", dict(good, name="Two", port=2000)])
    assert [t["name"] for t in ts] == ["Office App", "Two"], ts
    assert ts[0]["port"] == 1080 and ts[1]["port"] == 2000 and ts[0]["slug"] == "office-app"
    assert ssh_argv(ts[0])[-2:] == ["--", "me@192.0.2.10"] and "127.0.0.1:1080" in ssh_argv(ts[0])
    b = browser_argv(ts[0])
    assert "--proxy-server=socks5://127.0.0.1:1080" in b and b[-1] == "https://198.51.100.5/"
    assert parse({"not": "a list"}) == []
    print("ok")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["test"]:
        test()

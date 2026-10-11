"""Jarvis' Claude settings (Settings → Jarvis): model and effort, kept in the store and passed to every `claude` run
(the panel's inline answers, Continue in terminal, fw-jarvis sessions). Empty = Claude Code's own default."""
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from . import agents as coding, store

MODELS = [("", "Default (Claude Code's choice)"), ("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"),
          ("haiku", "Haiku")]  # aliases follow the newest model; a full model name can be typed too
EFFORTS = [("", "Default"), ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("xhigh", "Extra high"),
           ("max", "Max")]
_MODEL_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]*")
JDIR = os.path.expanduser("~/jarvis")
MEMORY = os.path.join(JDIR, "MEMORY.md")  # not a chezmoi target: the owner's notes, read by every run via CLAUDE.md
NOTE_MAX = 300
# Claude Code keeps each conversation in ~/.claude/projects/<cwd with every other character as '-'>/<id>.jsonl
SESSIONS = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", JDIR))


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


def agents():
    """[(label, target)]: Claude, then the coding agent (OpenCode or Pi) on each Ollama server with a chosen model."""
    return [("Claude", "claude"), *coding.targets()]


def fallback_on():
    """Settings → Jarvis → When Claude is unreachable (on unless switched off)."""
    return store.get("jarvis_fallback") is not False


def online():
    """NetworkManager reports full connectivity. FW_JARVIS_CONNECTIVITY=none|limited|full overrides it (tests)."""
    state = os.environ.get("FW_JARVIS_CONNECTIVITY")
    if not state:
        try:
            state = _run("nmcli", "-t", "networking", "connectivity").strip()
        except (OSError, subprocess.TimeoutExpired):
            return True  # can't tell: let Claude try
    return state == "full"


def server_up(target):
    """The Ollama server behind a coding-agent target ("ollama-<name>/model") answers GET /api/tags within 1.5 s."""
    url = coding.server_url(target)
    if not url:
        return False
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=1.5):
            return True
    except (OSError, ValueError):
        return False


def fallback(targets):
    """The first (label, target) of the coding-agent ones whose server answers, or None."""
    return next(((lbl, t) for lbl, t in targets if t not in ("claude", "opencode") and server_up(t)), None)


RISK = {"risk": ["safe", "risky", "destructive"]}  # the panel's action-card badge


def check_laya_url(text):
    """(value, error): '' is allowed (unset); anything else is http(s)://host[:port], trailing '/' stripped."""
    text = text.strip().rstrip("/")
    if text and not coding.URL_RE.fullmatch(text):
        return None, "The address is http(s)://host[:port], such as http://laya:8000"
    return text, None


def laya_on():
    """Settings → Jarvis → Use Laya decision model (off unless switched on)."""
    return store.get("jarvis_laya") is True


def laya_url():
    return check_laya_url(str(store.get("jarvis_laya_url") or ""))[0] or ""


def laya_token():
    """The Bearer token from GNOME Keyring (service=laya), '' without one. Never stored or logged anywhere else."""
    try:
        r = subprocess.run(["secret-tool", "lookup", "service", "laya"], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def laya_save_token(token):
    """Error text or None. The token goes on stdin, never argv."""
    try:
        r = subprocess.run(["secret-tool", "store", "--label=Jarvis Laya token", "service", "laya"],
                           input=token, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Couldn't save the token: {e}"
    return None if r.returncode == 0 else "Couldn't save the token (is GNOME Keyring unlocked?)"


def laya_clear_token():
    try:
        subprocess.run(["secret-tool", "clear", "service", "laya"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _laya_post(url, token, text, schema, timeout):
    """The reply restricted to the schema's fields; raises on HTTP errors, bad JSON or an off-schema answer."""
    req = urllib.request.Request(url + "/classify", data=json.dumps({"text": text, "schema": schema}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        reply = json.loads(r.read())
    out = {k: reply[k] for k in schema}
    if any(out[k] not in choices for k, choices in schema.items()):
        raise ValueError("answer not in the schema")
    return out


def laya(text, schema, timeout=1.0):
    """{field: choice} from the Laya classifier, or None on any failure (off, no URL/token, error, timeout,
    off-schema answer): callers then behave exactly as without Laya. Advice only, never a gate."""
    if not laya_on() or not laya_url():
        return None
    token = laya_token()
    if not token:
        return None
    try:
        return _laya_post(laya_url(), token, text, schema, timeout)
    except Exception:  # noqa: BLE001 — any failure = no advice
        return None


def laya_test(url):
    """Settings → Jarvis → Test: 'OK · N ms' / 'Unauthorized' / 'Unreachable' / 'Server error' / 'No token'."""
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as r:
            if json.loads(r.read()).get("ok") is not True:
                return "Server error"
    except (urllib.error.HTTPError, ValueError, AttributeError):
        return "Server error"
    except OSError:
        return "Unreachable"
    token = laya_token()
    if not token:
        return "No token"
    t = time.monotonic()
    try:
        _laya_post(url, token, "ls -l", RISK, 3)
    except urllib.error.HTTPError as e:
        return "Unauthorized" if e.code in (401, 403) else "Server error"
    except OSError:
        return "Unreachable"
    except (ValueError, KeyError, TypeError):
        return "Server error"
    return f"OK · {int((time.monotonic() - t) * 1000)} ms"


def _laya_selftest():
    """laya() with HTTP and secret-tool mocked, in a throwaway store."""
    import io
    global laya_token
    real_open, real_token, real_path = urllib.request.urlopen, laya_token, store.PATH
    store.PATH = os.path.join(tempfile.mkdtemp(), "settings.json")
    schema = RISK

    def http(reply=b'{"risk": "safe"}', code=None, exc=None):
        def fake(req, timeout):
            if exc:
                raise exc
            if code:
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
            assert req.headers["Authorization"] == "Bearer t0k" and json.loads(req.data)["schema"] == schema
            return io.BytesIO(reply)
        urllib.request.urlopen = fake

    try:
        laya_token = lambda: "t0k"  # noqa: E731
        http()
        assert laya_on() is False and laya("ls", schema) is None  # off by default
        store.set("jarvis_laya", True)
        assert laya_on() is True and laya("ls", schema) is None  # no URL
        store.set("jarvis_laya_url", "http://laya:8000")
        assert laya("ls", schema) == {"risk": "safe"}
        laya_token = lambda: ""  # noqa: E731
        assert laya("ls", schema) is None  # no token
        laya_token = lambda: "t0k"  # noqa: E731
        for kw in ({"code": 401}, {"code": 500}, {"exc": TimeoutError()}, {"exc": urllib.error.URLError("down")},
                   {"reply": b'{"risk": "maybe"}'}, {"reply": b'{"other": "safe"}'}, {"reply": b"not json"},
                   {"reply": b'["safe"]'}):
            http(**kw)
            assert laya("ls", schema) is None, kw
        store.set("jarvis_laya", False)
        assert laya_on() is False
    finally:
        urllib.request.urlopen, laya_token, store.PATH = real_open, real_token, real_path
    assert check_laya_url(" https://laya.lan:8000/ ") == ("https://laya.lan:8000", None)
    assert check_laya_url("") == ("", None)
    for bad in ("laya:8000", "ftp://laya", "http://laya/classify", "http://a b", "http://laya:8000?x"):
        assert check_laya_url(bad)[1], bad


def check_note(text):
    """(note, error): one line, at most NOTE_MAX characters, no code fences."""
    multiline = "\n" in str(text).strip()
    text = " ".join(str(text).split())
    if not text:
        return None, "Empty note"
    if multiline or len(text) > NOTE_MAX or "```" in text:
        return None, f"A note is one line of at most {NOTE_MAX} characters, without code blocks"
    return text, None


def ensure_memory():
    os.makedirs(JDIR, exist_ok=True)
    if not os.path.exists(MEMORY):
        with open(MEMORY, "w") as f:
            f.write("")


def notes():
    """The memory's '- ' lines, in file order."""
    try:
        return [line.rstrip("\n") for line in open(MEMORY) if line.startswith("- ")]
    except OSError:
        return []


def remember(note):
    """Append '- YYYY-MM-DD note'; returns an error string or None."""
    note, err = check_note(note)
    if err:
        return err
    ensure_memory()
    with open(MEMORY, "a") as f:
        f.write(f"- {time.strftime('%Y-%m-%d')} {note}\n")
    return None


def forget(line):
    """Remove one note line (as notes() returned it); the rest of the file stays as it is."""
    try:
        lines = open(MEMORY).readlines()
    except OSError:
        return
    if line + "\n" in lines:
        lines.remove(line + "\n")
        tmp = MEMORY + ".tmp"
        with open(tmp, "w") as f:
            f.writelines(lines)
        os.replace(tmp, MEMORY)


def _first_prompt(path):
    with open(path) as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") != "user" or e.get("isMeta"):
                continue
            c = (e.get("message") or {}).get("content")
            if isinstance(c, list):
                c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):  # <bash-input> etc.
                return " ".join(c.rsplit("Question: ", 1)[-1].split())  # the owner's words, not the attachment
    return None


def sessions(limit=20):
    """[(session id, mtime, first question)] of Jarvis' Claude conversations, newest first."""
    try:
        files = [os.path.join(SESSIONS, f) for f in os.listdir(SESSIONS) if f.endswith(".jsonl")]
    except OSError:
        return []
    out = []
    for path in sorted(files, key=os.path.getmtime, reverse=True):
        try:
            q = _first_prompt(path)
        except OSError:
            continue
        if q:
            out.append((os.path.basename(path)[:-6], os.path.getmtime(path), q))
        if len(out) >= limit:
            break
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
    assert check_note("  restic repo is on the NAS  ") == ("restic repo is on the NAS", None)
    assert check_note("")[1] and check_note("x" * 301)[1] and check_note("a ```rm``` b")[1]
    assert check_note("two\nlines")[1]
    global MEMORY
    real, MEMORY = MEMORY, os.path.join(tempfile.mkdtemp(), "MEMORY.md")
    try:
        assert remember("uses the NAS") is None and remember("x" * 400)
        assert notes() == [f"- {time.strftime('%Y-%m-%d')} uses the NAS"]
        forget(notes()[0])
        assert notes() == [] and os.path.exists(MEMORY)
    finally:
        MEMORY = real
    for sid, when, q in sessions(5):
        assert len(sid) == 36 and when > 0 and q and "\n" not in q, (sid, q)
    print(f"sessions: {len(sessions())}")
    os.environ["FW_JARVIS_CONNECTIVITY"] = "none"
    assert not online()
    os.environ["FW_JARVIS_CONNECTIVITY"] = "full"
    assert online()
    assert not server_up("no-such-provider/model") and fallback([("Claude", "claude")]) is None
    print(f"fallback: {fallback(agents())}")
    _laya_selftest()
    print(f"fw13.jarvis: self-check OK ({took:.2f} s)")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["test"]:
        selftest()
        sys.exit(0)  # fw-jarvis (bash): one argument per line
    args = claude_args()
    if args:  # nothing at all when unset: an empty line would become an empty argument
        print("\n".join(args))

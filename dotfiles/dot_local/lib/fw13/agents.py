"""Coding agents (OpenCode, Pi) and the Ollama servers they share.

One choice, store `coding_agent` (opencode | pi, Settings → Coding agent), decides which agent the bar's >_ panel
(fw-opencode), Jarvis' "Open …" button and its Ollama fallback start. Both get the same servers and models:
~/.config/fw-opencode/servers ("name url" per line) + state.json (active server, chosen model and known models per
server) are written into OpenCode's config (opencode.json, merged in via OPENCODE_CONFIG) and Pi's
(~/.pi/agent/models.json providers `ollama-<name>` + settings.json defaultProvider/defaultModel; the user's other
entries in those two files are kept). Ollama Cloud appears when OLLAMA_API_KEY is set.

  python3 -m fw13.agents session TARGET [PROMPT]   the chosen agent's interactive argv, NUL-separated (fw-jarvis)
  python3 -m fw13.agents test                      self-check
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import bar as waybar, store

DIR = os.path.expanduser("~/.config/fw-opencode")
SERVERS = os.path.join(DIR, "servers")
STATE = os.path.join(DIR, "state.json")
OPENCODE_JSON = os.path.join(DIR, "opencode.json")
PI_DIR = os.environ.get("PI_CODING_AGENT_DIR") or os.path.expanduser("~/.pi/agent")
AGENTS = {"opencode": "OpenCode", "pi": "Pi"}
CLOUD = ("cloud", "https://ollama.com")
PREFIX = "ollama-"  # our provider ids in both agents' configs; other providers are the user's
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
URL_RE = re.compile(r"https?://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?")
PI_READ_ONLY = "read,grep,find,ls"  # Jarvis' inline answers only look


def key():
    return os.environ.get("OLLAMA_API_KEY", "")


def agent():
    a = store.get("coding_agent")
    return a if a in AGENTS else "opencode"


def name(a=None):
    return AGENTS[a or agent()]


def version(a):
    """The agent's version string, or None when it isn't installed."""
    try:
        r = subprocess.run([a, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or r.stderr).strip().splitlines()
    return out[0] if r.returncode == 0 and out else None


# --- servers + state ----------------------------------------------------------------------------
def servers():
    out = []
    try:
        for line in open(SERVERS):
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                out.append((parts[0], parts[1].rstrip("/")))
    except OSError:
        out.append(("laptop", "http://localhost:11434"))
    if key():
        out.append(CLOUD)
    return out


def save_servers(lst):
    os.makedirs(DIR, exist_ok=True)
    with open(SERVERS, "w") as f:
        f.write("# name url — managed by fw-opencode / Settings → Coding agent; editing by hand is fine\n")
        for n, url in lst:
            if (n, url) != CLOUD:
                f.write(f"{n} {url}\n")


def load_state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def save_state(st):
    _write_json(STATE, st)


def probe(server):
    """(online, [model names]) from <url>/api/tags."""
    n, url = server
    req = urllib.request.Request(url + "/api/tags")
    if (n, url) == CLOUD:
        req.add_header("Authorization", f"Bearer {key()}")
    try:
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return True, sorted(m["name"] for m in json.load(r).get("models", []))
    except (OSError, ValueError, KeyError):
        return False, []


def probe_all(lst):
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(lst, ex.map(probe, lst)))


def remember_probe(st, status):
    """Keep the models of the servers that answered; returns st."""
    for (n, _url), (online, models) in status.items():
        if online:
            st.setdefault("known", {})[n] = models
    return st


def provider_id(n):
    return PREFIX + n


def server_url(target):
    """The Ollama URL behind a target "ollama-<name>/<model>", or None."""
    return {provider_id(n): u for n, u in servers()}.get(target.split("/", 1)[0])


def check_server(n, url, lst):
    """(name, url, error): name [a-z0-9-] not used yet; URL http(s)://host[:port], http:// and :11434 added."""
    n, url = n.strip().lower(), url.strip().rstrip("/")
    if not NAME_RE.fullmatch(n):
        return n, url, "A name is lowercase letters, digits and -, such as nas"
    if n in (s[0] for s in lst):
        return n, url, f"There is already a server called {n}"
    if url and "://" not in url:
        url = "http://" + url
    if url and ":" not in url.split("://", 1)[1]:
        url += ":11434"
    if not URL_RE.fullmatch(url):
        return n, url, "The address is http(s)://host[:port], such as http://nas:11434"
    return n, url, None


def add_server(n, url):
    """Validate, save, probe once and regenerate. Returns (error, online, models)."""
    lst = servers()
    n, url, err = check_server(n, url, lst)
    if err:
        return err, False, []
    save_servers([s for s in lst if s != CLOUD] + [(n, url)])
    online, models = probe((n, url))
    st = load_state()
    if online:
        st.setdefault("known", {})[n] = models
    save_state(st)
    generate(st, servers())
    return None, online, models


def remove_server(n):
    if n in ("laptop", CLOUD[0]):  # the laptop's own Ollama; Cloud comes from OLLAMA_API_KEY
        return
    save_servers([s for s in servers() if s != CLOUD and s[0] != n])
    st = load_state()
    for k in ("known", "model"):
        st.get(k, {}).pop(n, None)
    if st.get("active") == n:
        st.pop("active")
    save_state(st)
    generate(st, servers())


def use(n, model=None):
    """Make `n` the active server (and `model` its model) for both agents."""
    st = load_state()
    st["active"] = n
    if model:
        st.setdefault("model", {})[n] = model
    save_state(st)
    generate(st, servers())


# --- config generation --------------------------------------------------------------------------
def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".fw13-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _merge(path, update):
    """Read a JSON object the user may edit too, apply update(obj), write it back. An unreadable file is left
    alone (never clobber the user's config)."""
    try:
        obj = json.load(open(path))
    except FileNotFoundError:
        obj = {}
    except (OSError, ValueError):
        print(f"fw13.agents: {path} is not valid JSON, left unchanged", file=sys.stderr)
        return
    if isinstance(obj, dict):
        _write_json(path, update(obj))


def opencode_config(st, lst):
    providers = {}
    for n, url in lst:
        opts = {"baseURL": f"{url}/v1"}
        if (n, url) == CLOUD:
            opts["apiKey"] = "{env:OLLAMA_API_KEY}"
        providers[provider_id(n)] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Ollama Cloud" if (n, url) == CLOUD else f"Ollama · {n}",
            "options": opts,
            "models": {m: {"name": m} for m in st.get("known", {}).get(n, [])},
        }
    conf = {"$schema": "https://opencode.ai/config.json", "autoupdate": False, "provider": providers}
    model = st.get("model", {}).get(st.get("active"))
    if model:
        conf["model"] = f"{provider_id(st['active'])}/{model}"
    return conf


def pi_providers(st, lst):
    """Pi's models.json providers: Ollama's OpenAI-compatible API; Ollama ignores the dummy key."""
    return {provider_id(n): {
        "baseUrl": f"{url}/v1",
        "api": "openai-completions",
        "apiKey": "$OLLAMA_API_KEY" if (n, url) == CLOUD else "ollama",
        "models": [{"id": m} for m in st.get("known", {}).get(n, [])],
    } for n, url in lst}


def generate(st, lst):
    """Write both agents' configs from the same servers/state (models from the last successful probe)."""
    _write_json(OPENCODE_JSON, opencode_config(st, lst))
    ours = pi_providers(st, lst)

    def models(obj):
        prov = {k: v for k, v in (obj.get("providers") or {}).items() if not k.startswith(PREFIX)}
        return {**obj, "providers": {**prov, **ours}}
    _merge(os.path.join(PI_DIR, "models.json"), models)
    active = st.get("active")
    model = st.get("model", {}).get(active)
    if model:
        _merge(os.path.join(PI_DIR, "settings.json"),
               lambda obj: {**obj, "defaultProvider": provider_id(active), "defaultModel": model})
    waybar.refresh("opencode")  # the bar label


def targets():
    """[(label, "ollama-<name>/<model>")] for every server with a chosen model, active first."""
    st = load_state()
    active = st.get("active")
    out = []
    for n, url in sorted(servers(), key=lambda s: s[0] != active):
        model = st.get("model", {}).get(n)
        if model:
            out.append((f"{name()} · {'Ollama Cloud' if (n, url) == CLOUD else n} · {model}",
                        f"{provider_id(n)}/{model}"))
    return out


# --- commands -----------------------------------------------------------------------------------
def run_argv(target, prompt, follow_up=False, a=None):
    """One-shot answer (Jarvis inline / fallback); a follow-up continues the last conversation in the cwd."""
    if (a or agent()) == "pi":
        return ["pi", "-p", *(["-c"] if follow_up else []), "--model", target, "--tools", PI_READ_ONLY, "--", prompt]
    return ["opencode", "run", *(["--continue"] if follow_up else []), "--model", target, prompt]


def session_argv(target=None, prompt=None, cont=False, a=None):
    """Interactive session; target "ollama-<name>/<model>" picks the model, anything else = the default one."""
    model = ["--model", target] if target and "/" in target else []
    if (a or agent()) == "pi":
        return ["pi", *(["-c"] if cont else []), *model, *(["--", prompt] if prompt else [])]
    return ["opencode", *(["--continue"] if cont else []), *model, *(["--prompt", prompt] if prompt else [])]


def selftest():
    global DIR, SERVERS, STATE, OPENCODE_JSON, PI_DIR
    saved = DIR, SERVERS, STATE, OPENCODE_JSON, PI_DIR
    tmp = tempfile.mkdtemp()
    DIR = os.path.join(tmp, "fw-opencode")
    SERVERS, STATE, OPENCODE_JSON = (os.path.join(DIR, f) for f in ("servers", "state.json", "opencode.json"))
    PI_DIR = os.path.join(tmp, "pi")
    try:
        lst = [("laptop", "http://localhost:11434"), ("nas", "http://nas:11434"), CLOUD]
        st = {"active": "nas", "model": {"nas": "qwen3:8b"}, "known": {"nas": ["qwen3:8b", "gemma4:26b"]}}
        _write_json(os.path.join(PI_DIR, "models.json"), {"providers": {"mine": {"baseUrl": "x"},
                                                                        "ollama-gone": {}}})
        _write_json(os.path.join(PI_DIR, "settings.json"), {"theme": "dark"})
        generate(st, lst)
        oc = json.load(open(OPENCODE_JSON))
        assert oc["model"] == "ollama-nas/qwen3:8b" and set(oc["provider"]) == {"ollama-laptop", "ollama-nas",
                                                                                "ollama-cloud"}, oc
        assert oc["provider"]["ollama-cloud"]["options"]["apiKey"] == "{env:OLLAMA_API_KEY}"
        pm = json.load(open(os.path.join(PI_DIR, "models.json")))["providers"]
        assert set(pm) == {"mine", "ollama-laptop", "ollama-nas", "ollama-cloud"}, pm  # ollama-gone dropped
        assert pm["ollama-nas"] == {"baseUrl": "http://nas:11434/v1", "api": "openai-completions",
                                    "apiKey": "ollama", "models": [{"id": "qwen3:8b"}, {"id": "gemma4:26b"}]}
        assert pm["ollama-cloud"]["apiKey"] == "$OLLAMA_API_KEY" and pm["ollama-cloud"]["baseUrl"].endswith("/v1")
        ps = json.load(open(os.path.join(PI_DIR, "settings.json")))
        assert ps == {"theme": "dark", "defaultProvider": "ollama-nas", "defaultModel": "qwen3:8b"}, ps
        with open(os.path.join(PI_DIR, "settings.json"), "w") as f:
            f.write("{broken")
        generate(st, lst)
        assert open(os.path.join(PI_DIR, "settings.json")).read() == "{broken"  # left alone
        assert check_server("NAS", "nas", lst[:1]) == ("nas", "http://nas:11434", None)
        assert check_server("kh6", "https://ai.example.org:8443/", [])[1:] == ("https://ai.example.org:8443", None)
        assert check_server("laptop", "http://x", lst)[2] and check_server("a b", "http://x", [])[2]
        assert check_server("x_y", "http://x", [])[2] and check_server("x", "ftp://x", [])[2]
        assert check_server("x", "http://x:1/path", [])[2] and check_server("x", "http://a b", [])[2]
        assert run_argv("ollama-nas/q:8b", "-hi", a="pi") == ["pi", "-p", "--model", "ollama-nas/q:8b", "--tools",
                                                              PI_READ_ONLY, "--", "-hi"]
        assert run_argv("t/m", "hi", True, a="opencode") == ["opencode", "run", "--continue", "--model", "t/m", "hi"]
        assert session_argv("opencode", a="pi") == ["pi"] and session_argv("t/m", cont=True, a="pi") == [
            "pi", "-c", "--model", "t/m"]
        assert session_argv("t/m", "do x", a="opencode") == ["opencode", "--model", "t/m", "--prompt", "do x"]
    finally:
        DIR, SERVERS, STATE, OPENCODE_JSON, PI_DIR = saved
        shutil.rmtree(tmp, ignore_errors=True)
    for a in AGENTS:
        print(f"{name(a)}: {version(a) or 'not installed'}")
    print(f"agent: {agent()}; targets: {targets()}")
    print("fw13.agents: self-check OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        selftest()
    elif sys.argv[1:2] == ["session"] and len(sys.argv) in (3, 4):
        sys.stdout.write("\0".join(session_argv(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)))
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

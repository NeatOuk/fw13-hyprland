"""The laptop's own Ollama service (localhost:11434) for Settings → Jarvis → Local models: status, models, GPU use.

Downloads run `ollama pull` in a terminal (it shows progress); removing uses the API. OpenCode / Jarvis pick the
laptop's models through fw-opencode's server list ("laptop" = this service).
  python3 -m fw13.ollama test   self-check
"""
import json
import re
import urllib.request

URL = "http://localhost:11434"
NAME_RE = re.compile(r"[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?")  # e.g. qwen3:8b, hf.co/user/repo:Q4_K_M


def _api(path, data=None, method=None, timeout=3):
    req = urllib.request.Request(URL + path, method=method,
                                 data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else {}


def state():
    """{"up": bool, "models": [{name, size, params, quant}], "loaded": {name: gpu share 0–1}}."""
    try:
        tags = _api("/api/tags")
        ps = _api("/api/ps")
    except (OSError, ValueError):
        return {"up": False, "models": [], "loaded": {}}
    models = [{"name": m["name"], "size": m.get("size", 0), "params": m.get("details", {}).get("parameter_size", ""),
               "quant": m.get("details", {}).get("quantization_level", "")} for m in tags.get("models", [])]
    loaded = {m["name"]: (m.get("size_vram", 0) / m["size"] if m.get("size") else 0) for m in ps.get("models", [])}
    return {"up": True, "models": sorted(models, key=lambda m: m["name"]), "loaded": loaded}


def remove(name):
    """Delete a model; None or an error message."""
    try:
        _api("/api/delete", {"model": name}, method="DELETE", timeout=30)
    except (OSError, ValueError) as e:
        return str(e)
    return None


def valid(name):
    return bool(NAME_RE.fullmatch(name or ""))


def gb(n):
    return f"{n / 1e9:.1f} GB"


if __name__ == "__main__":
    assert valid("qwen3:8b") and valid("qwen3:30b-a3b") and valid("hf.co/user/repo:Q4_K_M") and valid("llama3.2")
    assert not valid("qwen3; rm -rf ~") and not valid("") and not valid("-q")
    assert gb(18556699314) == "18.6 GB"
    print("ok")

"""Audio outputs/inputs and volume through PipeWire's wpctl."""
import json
import os
import re
import subprocess
import time

from . import store
from .hypr import sh

_ROW = re.compile(r"^\s*│?\s*(\*)?\s*(\d+)\.\s+(.+?)\s+\[vol:\s*([\d.]+)(\s+MUTED)?\]")
_FILTER = re.compile(r"^\s*│?\s*(\*)?\s*(\d+)\.\s+(\S+)\s+\[Audio/(Sink|Source)\]")  # virtual devices (filters)
_VOL = re.compile(r"Volume:\s*([\d.]+)(\s+\[MUTED\])?")


def devices():
    """{"sinks": [...], "sources": [...]}, each {id, name, default, volume (0–1.5), muted}."""
    out = {"sinks": [], "sources": []}
    section = None
    in_audio = False
    for line in sh("wpctl", "status").splitlines():
        if not line.startswith((" ", "│", "├", "└")):
            in_audio = line.strip() == "Audio"
            continue
        if not in_audio:
            continue
        head = re.search(r"[├└]─ (\w+):", line)
        if head:
            section = {"Sinks": "sinks", "Sources": "sources", "Filters": "filters"}.get(head.group(1))
            continue
        m = _ROW.match(line)
        if section in ("sinks", "sources") and m:
            out[section].append({"id": int(m.group(2)), "name": m.group(3).strip(), "default": bool(m.group(1)),
                                 "volume": float(m.group(4)), "muted": bool(m.group(5))})
        f = _FILTER.match(line)
        if section == "filters" and f:  # listed by node.name, without volume
            v = _VOL.search(sh("wpctl", "get-volume", f.group(2))) or _VOL.search("Volume: 1.0")
            out[f.group(4).lower() + "s"].append({
                "id": int(f.group(2)), "default": bool(f.group(1)), "volume": float(v.group(1)), "muted": bool(v.group(2)),
                "name": "Noise-cancelled microphone" if f.group(3) == NOISE_SOURCE else f.group(3)})
    return out


def apps():
    """Apps playing sound now: [{id, name, volume, muted}] (pw-dump streams; EasyEffects' own streams left out)."""
    try:
        objs = json.loads(sh("pw-dump") or "[]")
    except ValueError:
        return []
    out = []
    for o in objs:
        p = (o.get("info") or {}).get("props") or {}
        if not p.get("media.class", "").startswith("Stream/Output/Audio") or \
                "easyeffects" in (p.get("application.id", "") + p.get("application.process.binary", "")).lower():
            continue
        v = _VOL.search(sh("wpctl", "get-volume", str(o["id"]))) or _VOL.search("Volume: 1.0")
        out.append({"id": o["id"], "name": p.get("application.name") or p.get("media.name") or p.get("node.name", "?"),
                    "volume": float(v.group(1)), "muted": bool(v.group(2))})
    return out


def set_default(node_id):
    sh("wpctl", "set-default", str(node_id))


def set_volume(node_id, frac):
    sh("wpctl", "set-volume", "-l", "1.0", str(node_id), f"{max(0.0, min(frac, 1.0)):.2f}")


def set_mute(node_id, muted):
    sh("wpctl", "set-mute", str(node_id), "1" if muted else "0")


# Noise suppression: our PipeWire drop-in loads WebRTC's echo canceller as a virtual "Noise-cancelled microphone".
NOISE_CONF = os.path.expanduser("~/.config/pipewire/pipewire.conf.d/fw13-noise.conf")
NOISE_SOURCE = "fw13_noise_source"
NOISE_CONF_TEXT = f"""# Written by fw13 (Settings > Sound > Noise suppression); removed when switched off.
context.modules = [
  {{ name = libpipewire-module-echo-cancel
    args = {{
      library.name = aec/libspa-aec-webrtc
      # echo reference = the default output's monitor, so no extra speaker shows up
      monitor.mode = true
      aec.args = {{
        webrtc.noise_suppression = true
        webrtc.high_pass_filter = true
        # apps (browsers, call clients) run their own gain control
        webrtc.gain_control = false
      }}
      capture.props = {{ node.name = "fw13_noise_capture" node.passive = true }}
      source.props = {{ node.name = "{NOISE_SOURCE}" node.description = "Noise-cancelled microphone" }}
      sink.props = {{ node.name = "fw13_noise_sink" node.description = "Noise suppression (echo reference)" }}
      playback.props = {{ node.name = "fw13_noise_playback" }}
    }}
  }}
]
"""


def noise_suppression():
    return os.path.exists(NOISE_CONF)


def _pw():
    try:
        return json.loads(sh("pw-dump") or "[]")
    except ValueError:
        return []


def _source_ids(dump):
    """{node.name: id} of the audio sources."""
    return {o["info"]["props"].get("node.name"): o["id"] for o in dump
            if o.get("type", "").endswith(":Node") and (o.get("info") or {}).get("props", {}).get("media.class") == "Audio/Source"}


def _default_source(dump):
    for o in dump:
        for m in o.get("metadata") or []:
            if m.get("key") == "default.audio.source" and isinstance(m.get("value"), dict):
                return m["value"].get("name")
    return None


def _restart(wait_for=None):
    """Restart the audio services (sound blips); then wait up to 10 s for source `wait_for` and return its id."""
    subprocess.run(["systemctl", "--user", "restart", "pipewire", "pipewire-pulse", "wireplumber"], check=True)
    for _ in range(40 if wait_for else 0):
        time.sleep(0.25)
        nid = _source_ids(_pw()).get(wait_for)
        if nid is not None:
            return nid
    return None


def set_noise_suppression(on):
    """Write/remove our drop-in, restart PipeWire, make the matching mic the default. (ok, message)."""
    if on:
        prev = _default_source(_pw())
        if prev and prev != NOISE_SOURCE:
            store.set("noise_prev_source", prev)  # the physical mic to go back to
        os.makedirs(os.path.dirname(NOISE_CONF), exist_ok=True)
        with open(NOISE_CONF, "w") as f:
            f.write(NOISE_CONF_TEXT)
        nid = _restart(NOISE_SOURCE)
        if nid is None:  # leave nothing of ours behind
            os.unlink(NOISE_CONF)
            _restart()
            return False, "PipeWire did not create the noise-cancelled microphone"
    else:
        if os.path.exists(NOISE_CONF):
            os.unlink(NOISE_CONF)
            try:
                os.removedirs(os.path.dirname(NOISE_CONF))  # ~/.config/pipewire[/pipewire.conf.d] if we left them empty
            except OSError:
                pass
        prev = store.get("noise_prev_source")
        nid = _restart(prev) if prev else _restart()
        if nid is None:  # that mic is gone: WirePlumber picks one by itself
            return True, ""
    set_default(nid)
    return True, ""

"""Newer official releases of the apps install.sh builds or downloads itself, which dnf can't see.

Used by Settings → Apps. Each source is asked over the network (GitHub's API, Anthropic's apt index, telegram.org's
download redirect), so callers run check() in the background; a source that fails is just left out.

  python3 -m fw13.upstream        list: name, installed, version in install.sh, latest release
  python3 -m fw13.upstream test   self-check (offline)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")
# install.sh's pins: chezmoi's source is the whole repo and `chezmoi update` keeps it newest; install.sh's own clone next
INSTALL_SH = (os.path.join(HOME, ".local/share/chezmoi/install.sh"), os.path.join(HOME, ".local/share/fw13-hypr/install.sh"))
TIMEOUT = 15
CLAUDE_APT = "https://downloads.claude.ai/claude-desktop/apt/stable/dists/stable/main/binary-amd64/Packages"
TELEGRAM_DL = "https://telegram.org/dl/desktop/linux"


def vkey(v):
    return tuple(int(n) for n in re.findall(r"\d+", v or ""))


def _get(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "fw13-hypr"})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def gh_release(repo):
    with _get(f"https://api.github.com/repos/{repo}/releases/latest") as r:
        return json.load(r)["tag_name"].lstrip("v")


def gh_tag(repo):
    """Newest x.y.z tag (Ghostty publishes tags, no GitHub releases)."""
    with _get(f"https://api.github.com/repos/{repo}/tags?per_page=30") as r:
        tags = [t["name"].lstrip("v") for t in json.load(r)]
    return max((t for t in tags if re.fullmatch(r"\d+(\.\d+)+", t)), key=vkey)


def apt_entry(text, package):
    """{field: value} of the highest Version of `package` in an apt Packages index."""
    entries = [dict(ln.split(": ", 1) for ln in block.splitlines() if ": " in ln) for block in text.split("\n\n")]
    return max((e for e in entries if e.get("Package") == package), key=lambda e: vkey(e.get("Version")))


def apt_version(text, package):
    return apt_entry(text, package)["Version"]


def update_argv(entry, script):
    """install.sh run that updates Claude Desktop to an apt index entry; the entry comes off the network, so check it."""
    ver, sha = entry.get("Version", ""), entry.get("SHA256", "")
    if not re.fullmatch(r"\d+(\.\d+)+", ver) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("unexpected entry in Anthropic's package index")
    return ["env", f"CLAUDE_DESKTOP_VERSION={ver}", f"CLAUDE_DESKTOP_SHA256={sha}", "bash", script,
            "--update-claude-desktop"]


def claude_desktop_update():
    """argv for Settings → Apps → Claude Desktop → Update…; needs the network."""
    script = next((p for p in INSTALL_SH if os.path.exists(p)), None)
    if not script:
        raise FileNotFoundError("install.sh not found")
    with _get(CLAUDE_APT) as r:
        return update_argv(apt_entry(r.read().decode(), "claude-desktop"), script)


def claude_desktop():
    with _get(CLAUDE_APT) as r:
        return apt_version(r.read().decode(), "claude-desktop")


def telegram():
    """The version in telegram.org's download redirect, which is also what install.sh builds."""
    with _get(TELEGRAM_DL, "HEAD") as r:
        return re.search(r"-x64-([\d.]+)\.tar\.xz$", r.geturl()).group(1)


# (package or file that shows it's installed, name, install.sh pin variable or None = the installer takes the latest,
#  latest release)
SOURCES = (
    ("claude-desktop-official", "Claude Desktop", "CLAUDE_DESKTOP_VERSION", claude_desktop),
    ("telegram-desktop-official", "Telegram", None, telegram),
    ("ghostty-official", "Ghostty", "GHOSTTY_VERSION", lambda: gh_tag("ghostty-org/ghostty")),
    ("dbeaver-ce", "DBeaver", "DBEAVER_VERSION", lambda: gh_release("dbeaver/dbeaver")),
    ("obsidian-official", "Obsidian", "OBSIDIAN_VERSION", lambda: gh_release("obsidianmd/obsidian-releases")),
    ("/usr/local/bin/framework_tool", "framework_tool", "FWTOOL_VERSION",
     lambda: gh_release("FrameworkComputer/framework-system")),
    ("/opt/scrcpy", "scrcpy", "SCRCPY_VERSION", lambda: gh_release("Genymobile/scrcpy")),
)


def pins(text):
    """{VAR: version} from install.sh's `VAR="${VAR:-x}"` lines."""
    return {m[0]: m[2].lstrip("v") for m in re.findall(r'^(\w+)="\$\{(\w+):-([^}]*)\}"', text, re.M) if m[0] == m[1]}


def read_pins():
    for path in INSTALL_SH:
        try:
            with open(path) as f:
                return pins(f.read())
        except OSError:
            continue
    return {}


def installed(what, pin):
    """Installed version, None when not installed. shortcut: files outside rpm are taken to be at install.sh's pin
    (the installer re-downloads them whenever they don't match it); read their --version if that ever drifts."""
    if what.startswith("/"):
        return pin if os.path.exists(what) else None
    if not shutil.which("rpm"):
        return None
    p = subprocess.run(["rpm", "-q", "--qf", "%{VERSION}", what], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def verdict(name, have, pin, latest):
    """{name, installed, latest, target, note} when there is something newer than `have`, else None."""
    target = latest if pin is None else pin
    newer = vkey(latest) > vkey(have)
    if not newer and vkey(target) <= vkey(have):
        return None
    if vkey(target) > vkey(have):
        note = f"re-run the installer to update to {target}"
        if vkey(latest) > vkey(target):
            note += f" ({latest} is out, not in fw13-hypr yet)"
    else:
        note = f"{latest} is out; fw13-hypr still installs {target}, the installer will update it once it's bumped"
    return {"name": name, "installed": have, "latest": latest, "target": target, "note": note}


def check():
    """{package or path: verdict} for every installed app with a newer release; needs the network."""
    pinned, out = read_pins(), {}
    for what, name, var, latest in SOURCES:
        pin = pinned.get(var) if var else None
        have = installed(what, pin)
        if not have:
            continue
        try:
            v = verdict(name, have, pin, latest())
        except Exception:  # noqa: BLE001 — offline, rate-limited or a changed page: that source just reports nothing
            continue
        if v:
            out[what] = v
    return out


def test():
    assert vkey("v1.10.2") > vkey("1.9.9") and vkey("2.37337.1") > vkey("1.17377.0")
    assert apt_version("Package: x\nVersion: 9\n\nPackage: claude-desktop\nVersion: 1.2.0\n\n"
                       "Package: claude-desktop\nVersion: 1.10.0\n", "claude-desktop") == "1.10.0"
    sha = "a" * 64
    argv = update_argv(apt_entry(f"Package: claude-desktop\nVersion: 3.1.0\nSHA256: {sha}\n", "claude-desktop"), "/i.sh")
    assert argv[1:3] == ["CLAUDE_DESKTOP_VERSION=3.1.0", f"CLAUDE_DESKTOP_SHA256={sha}"] and argv[-2:] == ["/i.sh", "--update-claude-desktop"]
    for bad in ({"Version": "3.1.0; rm -rf ~", "SHA256": sha}, {"Version": "3.1.0", "SHA256": "zz"}, {}):
        try:
            update_argv(bad, "/i.sh")
            raise AssertionError(bad)
        except ValueError:
            pass
    assert pins('A="${A:-v0.6.6}"\nB="${C:-1}"\nGHOSTTY_VERSION="${GHOSTTY_VERSION:-1.3.1}"\n') == \
        {"A": "0.6.6", "GHOSTTY_VERSION": "1.3.1"}
    assert verdict("x", "1.0", "1.0", "1.0") is None
    assert "re-run the installer to update to 7.3" in verdict("t", "7.2", None, "7.3")["note"]
    assert "not in fw13-hypr yet" in verdict("x", "1.0", "1.1", "1.2")["note"]
    assert "once it's bumped" in verdict("x", "1.1", "1.1", "1.2")["note"]
    assert verdict("x", "1.2", "1.1", "1.1") is None  # installed newer than the pin: nothing to do
    checkout = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../install.sh")  # run from the repo
    have = pins(open(checkout).read()) if os.path.exists(checkout) else read_pins()
    assert {v for _, _, v, _ in SOURCES if v} <= set(have) or not have, "a pin variable is gone"
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        for k, v in check().items():
            print(f"{v['name']}: {v['installed']} → {v['latest']} ({v['note']})")

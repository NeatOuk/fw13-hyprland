"""Apps the launcher shows (+ Flatpak apps): where each came from, whether it's ours, pending updates.

Used by fw-launcher (how many entries fuzzel lists) and Settings → Apps.

  python3 -m fw13.apps            list: id, source, protected note
  python3 -m fw13.apps test       self-check
"""
import glob
import os
import shlex
import subprocess
import sys

HOME = os.path.expanduser("~")
# packages/*.txt: chezmoi's source is the whole repo (.chezmoiroot = dotfiles), updated by every `chezmoi update`;
# install.sh's own checkout is the fallback (and the union covers either being older)
PACKAGE_LISTS = (os.path.join(HOME, ".local/share/chezmoi/packages"), os.path.join(HOME, ".local/share/fw13-hypr/packages"))
# install.sh builds or installs these itself, outside packages/*.txt
BUILT = {"telegram-desktop-official", "ghostty-official", "citadel", "citadel-helper", "dbeaver-ce",
         "claude-desktop-official"}  # + downloaded RPMs
OUR_FLATPAKS = {"org.localsend.localsend_app"}
# Apps the installer chose that nothing else in the desktop needs: Uninstall… removes them (+ the extra packages that
# only serve them) and records every name in SKIP_FILE, which install.sh skips from then on.
# {package or Flatpak id: (extra packages, note for the row)}
OPTIONAL = {
    "steam": (("steam-devices",), ""),
    "lutris": ((), "its games and Wine runners stay in ~/.local/share/lutris"),
    "telegram-desktop-official": ((), ""),
    "chromium": ((), "the default browser for links and SUPER+B: links fall back to another browser, SUPER+B stops"),
    "code": ((), "SUPER+SHIFT+C opens it"),
    "RemoteDesktopManager": ((), ""),
    "ghostty-official": ((), "the terminal falls back to kitty"),
    "citadel": (("citadel-helper",), "the outbound firewall goes with it"),
    "cloudflare-warp": ((), "the bar's cloud icon hides itself"),
    "easyeffects": (("lsp-plugins-lv2", "lv2-calf-plugins"), "Settings → Sound loses Speaker sound"),
    "org.localsend.localsend_app": ((), ""),
    "dbeaver-ce": ((), "saved connections stay in ~/.local/share/DBeaverData"),
    "claude-desktop-official": ((), "your sign-in and settings stay in ~/.config/Claude"),
    "neovim": ((), "LazyVim's config stays in ~/.config/nvim"),
    "syncthing": ((), "file sync stops; its folders and settings stay in ~/.local/state/syncthing"),
    # no launcher entry: listed by entryless() when installed
    "ollama": ((), "removing it stops and disables ollama.service; Jarvis' offline fallback and the laptop's OpenCode "
                    "server go with it; downloaded models stay in /var/lib/ollama (sudo rm -rf it to free the space)"),
    "android-tools": ((), "scrcpy (installed by the installer) needs its adb and stops working"),
}
NAMES = {"ollama": "Ollama (local AI models)", "android-tools": "adb and fastboot (Android tools)"}  # entryless rows
OPTIONAL_LC = {k.lower(): k for k in OPTIONAL}  # rpm names come back as packaged; dnf matches case-insensitively
SKIP_FILE = os.path.join(HOME, ".config/fw13/skip-packages")
GNOME_NEEDS = {"gnome-software", "nautilus", "gnome-control-center", "ptyxis", "loupe", "papers",
               "gnome-text-editor", "showtime", "decibels"}
OUR_DIR = os.path.join(HOME, ".local/share/fw13/")
# (word in Exec or path, who installed it) for entries no package owns
INSTALLERS = (("steam", "Steam"), ("lutris", "Lutris"), ("heroic", "Heroic"), ("wine", "Wine"),
              ("--app-id=", "Chromium (web app)"), ("jetbrains", "JetBrains Toolbox"))


def data_dirs():
    dirs = [os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share")]
    return dirs + (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")


def parse_entry(text):
    """Keys of the [Desktop Entry] group (comments and other groups ignored; the first value of a key wins)."""
    keys, group = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            group = line
        elif group == "[Desktop Entry]" and "=" in line:
            k, v = line.split("=", 1)
            keys.setdefault(k.strip(), v.strip())
    return keys


def visible(keys):
    return keys.get("Type") == "Application" and keys.get("NoDisplay") != "true" and keys.get("Hidden") != "true"


def launcher_entries():
    """[(desktop id, path, keys)] as fuzzel lists them: one per desktop id, first data dir wins, visible only."""
    seen, out = set(), []
    for d in data_dirs():
        base = os.path.join(d, "applications")
        for f in sorted(glob.glob(os.path.join(base, "**", "*.desktop"), recursive=True)):
            did = os.path.relpath(f, base).replace("/", "-")
            if did in seen:
                continue
            seen.add(did)
            try:
                with open(f, errors="ignore") as fh:
                    keys = parse_entry(fh.read())
            except OSError:
                continue
            if visible(keys):
                out.append((did, f, keys))
    return out


def rpm_owners(paths):
    """{path: package name} for the paths rpm owns; one rpm call."""
    if not paths:
        return {}
    try:
        p = subprocess.run(["rpm", "-qf", "--qf", "%{NAME}\n", *paths], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    lines = p.stdout.splitlines()
    if len(lines) != len(paths):  # a file with two owners shifts the lines: ask one by one
        return {k: v for path in paths for k, v in rpm_owners_one(path).items()}
    return {path: line for path, line in zip(paths, lines) if " " not in line}  # "file … is not owned by any package"


def rpm_owners_one(path):
    try:
        p = subprocess.run(["rpm", "-qf", "--qf", "%{NAME}\n", path], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    line = (p.stdout.splitlines() or [""])[0]
    return {path: line} if p.returncode == 0 and line and " " not in line else {}


def installer_packages():
    """Package names (lower case: dnf finds `thunar` as Thunar) in this installer's packages/*.txt ('#' comment
    lines, names split on whitespace) + what install.sh builds itself."""
    names = set(BUILT)
    for d in PACKAGE_LISTS:
        for f in glob.glob(os.path.join(d, "*.txt")):
            try:
                with open(f) as fh:
                    names.update(w.lower() for line in fh if not line.lstrip().startswith("#") for w in line.split())
            except OSError:
                continue
    return names


def flatpaks():
    """[{id, name, installation, version}] from `flatpak list --app`; [] without flatpak."""
    try:
        out = subprocess.run(["flatpak", "list", "--app", "--columns=application,name,installation,version"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows = [(line.split("\t") + ["", "", "", ""])[:4] for line in out.splitlines() if line.strip()]
    return [{"id": a, "name": n or a, "installation": i, "version": v} for a, n, i, v in rows]


def flatpak_updates():
    """{(installation, app id): new version}; needs the network, so callers run it in the background.
    A failing installation (offline, no remote) just adds nothing."""
    ups = {}
    for inst in ("user", "system"):
        try:
            p = subprocess.run(["flatpak", "remote-ls", "--updates", "--app", f"--{inst}",
                                "--columns=application,version"], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in p.stdout.splitlines() if p.returncode == 0 else []:
            app, _, ver = line.partition("\t")
            if app.strip():
                ups[(inst, app.strip())] = ver.strip()
    return ups


def other_installer(path, keys):
    hay = f"{path} {keys.get('Exec', '')}".lower()
    return next((who for word, who in INSTALLERS if word in hay), None)


def optional_key(pkg, flatpak_id):
    return OPTIONAL_LC.get((flatpak_id or pkg or "").lower())


def protected(did, path, pkg, flatpak_id, ours):
    """Why an app can't be uninstalled here, or None."""
    if optional_key(pkg, flatpak_id):
        return None
    if did.startswith(("fw-", "fw13-")) or path.startswith(OUR_DIR) or (pkg or "").lower() in ours \
            or flatpak_id in OUR_FLATPAKS:
        return "part of this desktop"
    if pkg in GNOME_NEEDS:
        return "GNOME needs it"
    return None


def classify(entries, owners, fps, ours):
    """Apps: [{id, name, icon, kind ('rpm'|'flatpak'|'other'), package, installation, source, protected}]."""
    by_id = {f["id"]: f for f in fps}
    apps, shown = [], set()
    for did, path, keys in entries:
        fid = did[:-len(".desktop")]
        # an app's extra entries are named <app id>.<something>
        fp = next((by_id[a] for a in sorted(by_id, key=len, reverse=True) if fid == a or fid.startswith(a + ".")),
                  None) if "/flatpak/exports/" in path else None
        pkg = None if fp else owners.get(path)
        app = {"id": did, "name": keys.get("Name", fid), "icon": keys.get("Icon", ""), "package": pkg,
               "installation": fp and fp["installation"], "flatpak": fp and fp["id"]}
        if fp:
            shown.add(fp["id"])
            app.update(kind="flatpak", source=f"Flatpak ({fp['installation']})")
        elif pkg:
            app.update(kind="rpm", source=f"Package {pkg}")
        else:
            who = other_installer(path, keys)
            ours_file = did.startswith(("fw-", "fw13-")) or path.startswith(OUR_DIR)
            app.update(kind="other", source="fw13-hypr" if ours_file else f"Installed by {who}" if who
                       else "Installed by hand")
        app["protected"] = protected(did, path, pkg, fp and fp["id"], ours)
        app["optional"] = optional_key(pkg, fp and fp["id"])
        apps.append(app)
    for fp in fps:  # Flatpak apps without a launcher entry
        if fp["id"] not in shown:
            apps.append({"id": fp["id"], "name": fp["name"], "icon": fp["id"], "package": None, "kind": "flatpak",
                         "flatpak": fp["id"], "installation": fp["installation"], "source": f"Flatpak ({fp['installation']})",
                         "protected": protected(fp["id"], "", None, fp["id"], ours),
                         "optional": optional_key(None, fp["id"])})
    return apps


def entryless(apps, have):
    """Rows for the installed OPTIONAL packages (`have`) that no launcher entry showed, e.g. ollama, android-tools."""
    shown = {(a.get("package") or "").lower() for a in apps}
    return [{"id": k, "name": NAMES.get(k, k), "icon": "", "package": k, "kind": "rpm", "installation": None,
             "flatpak": None, "source": f"Package {k}", "protected": None, "optional": k}
            for k in OPTIONAL if "." not in k and k in have and k.lower() not in shown]


def needed_by(pkg):
    """Installed packages that require `pkg` directly (`rpm -e --test`: read-only, no root)."""
    try:
        p = subprocess.run(["rpm", "-e", "--test", pkg], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    # "\tfcitx5-data = 5.1 is needed by (installed) fcitx5-5.1.23-1.fc44.x86_64"
    return {line.rsplit(" ", 1)[1].rsplit("-", 2)[0] for line in p.stderr.splitlines()
            if "is needed by (installed)" in line}


def guard_deps(apps, ours, needed=needed_by):
    """Packages one of ours needs directly are protected too (dnf remove would take ours with them)."""
    out = []
    for app in apps:
        hit = sorted(n for n in needed(app["package"]) if n.lower() in ours) \
            if app["kind"] == "rpm" and not app["protected"] else []
        out.append({**app, "protected": f"part of this desktop (needed by {hit[0]})"} if hit else app)
    return out


def rpm_installed(names):
    """The names of `names` that are installed (one rpm call)."""
    if not names:
        return set()
    try:
        out = subprocess.run(["rpm", "-q", "--qf", "%{NAME}\n", *names], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line for line in out.splitlines() if " " not in line}  # "package x is not installed"


def installed():
    entries = launcher_entries()
    owners = rpm_owners([p for _d, p, _k in entries if "/flatpak/exports/" not in p])
    ours = installer_packages()
    apps = classify(entries, owners, flatpaks(), ours)
    apps = guard_deps(apps + entryless(apps, rpm_installed(sorted(k for k in OPTIONAL if "." not in k))), ours)
    have = rpm_installed(sorted({x for e, _n in OPTIONAL.values() for x in e}))
    return [{**a, "extras": [x for x in OPTIONAL[a["optional"]][0] if x in have]} if a.get("optional") else a
            for a in apps]


def skipped():
    """Names in SKIP_FILE (what Uninstall… recorded), in file order."""
    try:
        with open(SKIP_FILE) as fh:
            return list(dict.fromkeys(w for w in (line.strip() for line in fh) if w and not w.startswith("#")))
    except OSError:
        return []


def unskip(name):
    """Take a name out of SKIP_FILE: the next install.sh run installs it again."""
    rest = [n for n in skipped() if n != name]
    tmp = SKIP_FILE + ".tmp"
    with open(tmp, "w") as fh:
        fh.writelines(n + "\n" for n in rest)
    os.replace(tmp, SKIP_FILE)


def optional_script(app):
    """bash: remove the app interactively, then record its names in SKIP_FILE only if that worked and it's gone."""
    key = app["optional"]
    names = [key, *OPTIONAL[key][0]]
    q = shlex.quote
    if app["kind"] == "flatpak":
        inst = f"--{app['installation']}"
        remove, gone = ["flatpak", "uninstall", inst, app["flatpak"]], f"! flatpak info {inst} {q(app['flatpak'])} >/dev/null 2>&1"
    else:
        remove = ["sudo", "dnf", "remove", app["package"], *app.get("extras", ())]
        gone = f"! rpm -q --quiet {q(app['package'])}"
    f = q(SKIP_FILE)
    return (f"{shlex.join(remove)} && {gone} && mkdir -p {q(os.path.dirname(SKIP_FILE))} && "
            f"for n in {' '.join(map(q, names))}; do grep -qxF -- \"$n\" {f} 2>/dev/null || echo \"$n\" >> {f}; done && "
            f"echo {q('Removed. install.sh will skip ' + ', '.join(names) + ' from now on (Settings → Apps → Removed apps undoes that).')}")


def remove_all_script(apps):
    """bash: "Remove pre-installed apps" = every OPTIONAL app still installed, in one dnf transaction (one y/N) plus a
    flatpak uninstall each; every app's names are recorded in SKIP_FILE only once that app is really gone. None if
    nothing is left to remove."""
    q, f = shlex.quote, shlex.quote(SKIP_FILE)
    opt = {a["optional"]: a for a in apps if a.get("optional")}
    rpms = [a for a in opt.values() if a["kind"] == "rpm"]
    fps = [a for a in opt.values() if a["kind"] == "flatpak"]
    if not (rpms or fps):
        return None

    def record(key, gone):
        names = " ".join(map(q, [key, *OPTIONAL[key][0]]))
        return (f"if {gone}; then for n in {names}; do grep -qxF -- \"$n\" {f} 2>/dev/null || echo \"$n\" >> {f}; "
                f"done; fi")
    steps = [f"mkdir -p {q(os.path.dirname(SKIP_FILE))}"]
    if rpms:
        pkgs = [x for a in rpms for x in (a["package"], *a.get("extras", ()))]
        steps.append(f"{shlex.join(['sudo', 'dnf', 'remove', *pkgs])} || true")
        steps += [record(a["optional"], f"! rpm -q --quiet {q(a['package'])}") for a in rpms]
    for a in fps:
        inst = f"--{a['installation']}"
        steps.append(f"{shlex.join(['flatpak', 'uninstall', inst, a['flatpak']])} || true")
        steps.append(record(a["optional"], f"! flatpak info {inst} {q(a['flatpak'])} >/dev/null 2>&1"))
    steps.append(f"echo {q('Done. What was removed is skipped by install.sh from now on (Settings → Apps → Removed apps undoes that).')}")
    return "; ".join(steps)


def uninstall_argv(app):
    """Terminal command that removes the app (dnf/flatpak ask y/N themselves), or None."""
    if app["protected"]:
        return None
    if app.get("optional"):
        return ["bash", "-c", optional_script(app)]
    if app["kind"] == "rpm":
        return ["sudo", "dnf", "remove", app["package"]]
    if app["kind"] == "flatpak":
        return ["flatpak", "uninstall", f"--{app['installation']}", app["flatpak"]]
    return None


def test():
    test_remove_all()
    lo = "#\n# This file is part of the LibreOffice project.\n#\n[Desktop Entry]\nType=Application\nName=Writer\n" \
         "Name[fr]=Writer FR\nExec=libreoffice --writer\n\n[Desktop Action new]\nName=New\nExec=other\n"
    k = parse_entry(lo)
    assert k["Name"] == "Writer" and k["Exec"] == "libreoffice --writer" and visible(k), k
    assert not visible(parse_entry("[Desktop Entry]\nType=Application\nNoDisplay=true\n"))
    assert not visible(parse_entry("[Desktop Entry]\nType=Link\n"))
    assert not visible(parse_entry("[Other]\nType=Application\n"))
    assert parse_entry("[Desktop Entry]\nName = Spaced\n")["Name"] == "Spaced"
    ours = {"chromium", "code"}
    fps = [{"id": "org.localsend.localsend_app", "name": "LocalSend", "installation": "user", "version": "1"},
           {"id": "org.example.App", "name": "Example", "installation": "system", "version": "2"},
           {"id": "org.example.NoEntry", "name": "No entry", "installation": "user", "version": "3"}]
    fpdir = "/var/lib/flatpak/exports/share/applications/"
    entries = [("chromium-browser.desktop", "/usr/share/applications/chromium-browser.desktop", {"Name": "Chromium"}),
               ("gimp.desktop", "/usr/share/applications/gimp.desktop", {"Name": "GIMP"}),
               ("org.gnome.Nautilus.desktop", "/usr/share/applications/org.gnome.Nautilus.desktop", {"Name": "Files"}),
               ("fw-settings.desktop", f"{HOME}/.local/share/applications/fw-settings.desktop", {"Name": "Settings"}),
               ("fw13-calc.desktop", f"{OUR_DIR}hyprland/applications/fw13-calc.desktop", {"Name": "Calc"}),
               ("Terraria.desktop", f"{HOME}/.local/share/applications/Terraria.desktop",
                {"Name": "Terraria", "Exec": "steam steam://rungameid/105600"}),
               ("Mine.desktop", f"{HOME}/.local/share/applications/Mine.desktop", {"Name": "Mine", "Exec": "mine"}),
               ("org.localsend.localsend_app.desktop", f"{HOME}/.local/share/flatpak/exports/share/applications/"
                "org.localsend.localsend_app.desktop", {"Name": "LocalSend"}),
               ("org.example.App.desktop", fpdir + "org.example.App.desktop", {"Name": "Example"})]
    owners = {"/usr/share/applications/chromium-browser.desktop": "chromium",
              "/usr/share/applications/gimp.desktop": "gimp",
              "/usr/share/applications/org.gnome.Nautilus.desktop": "nautilus"}
    a = {x["id"]: x for x in classify(entries, owners, fps, ours)}
    assert a["chromium-browser.desktop"]["protected"] is None and a["chromium-browser.desktop"]["optional"] == "chromium"
    assert a["gimp.desktop"]["optional"] is None
    assert a["gimp.desktop"]["protected"] is None and a["gimp.desktop"]["source"] == "Package gimp"
    assert uninstall_argv(a["gimp.desktop"]) == ["sudo", "dnf", "remove", "gimp"]
    assert a["org.gnome.Nautilus.desktop"]["protected"] == "GNOME needs it"
    assert a["fw-settings.desktop"]["protected"] and a["fw13-calc.desktop"]["protected"]
    assert a["Terraria.desktop"]["source"] == "Installed by Steam" and uninstall_argv(a["Terraria.desktop"]) is None
    assert a["Mine.desktop"]["source"] == "Installed by hand"
    ls = a["org.localsend.localsend_app.desktop"]
    assert ls["protected"] is None and ls["optional"] == "org.localsend.localsend_app"
    assert uninstall_argv(a["org.example.App.desktop"]) == ["flatpak", "uninstall", "--system", "org.example.App"]
    assert uninstall_argv(a["org.example.NoEntry"]) == ["flatpak", "uninstall", "--user", "org.example.NoEntry"]
    g = {x["id"]: x for x in guard_deps(list(a.values()), {"fcitx5"}, lambda p: {"fcitx5"} if p == "gimp" else set())}
    assert g["gimp.desktop"]["protected"] == "part of this desktop (needed by fcitx5)" and a["gimp.desktop"]["protected"] is None
    assert classify(entries, {"/usr/share/applications/gimp.desktop": "Thunar"}, [], {"thunar"})[1]["protected"]
    assert "-y" not in sum((uninstall_argv(x) or [] for x in a.values()), [])
    test_optional(a)
    bare = {x["id"]: x for x in entryless(list(a.values()), {"chromium", "ollama", "android-tools"})}
    assert set(bare) == {"ollama", "android-tools"}, bare  # chromium has its launcher row already
    assert bare["ollama"]["name"] == "Ollama (local AI models)" and bare["ollama"]["optional"] == "ollama"
    assert uninstall_argv(bare["android-tools"])[:2] == ["bash", "-c"]
    assert "sudo dnf remove ollama" in remove_all_script(list(bare.values()))
    real = installer_packages()
    assert {"chromium", "code"} <= real or not any(os.path.isdir(d) for d in PACKAGE_LISTS), "package lists not read"
    assert not any(w.startswith("#") for w in real)
    print("ok")


def test_remove_all():
    rpm = {"optional": "steam", "kind": "rpm", "package": "steam", "extras": ["steam-devices"]}
    fp = {"optional": "org.localsend.localsend_app", "kind": "flatpak", "installation": "user",
          "flatpak": "org.localsend.localsend_app"}
    core = {"kind": "rpm", "package": "thunar", "protected": "part of this desktop"}
    sc = remove_all_script([rpm, fp, core, dict(rpm)])
    assert sc.count("sudo dnf remove") == 1 and "steam steam-devices" in sc and "thunar" not in sc and " -y" not in sc
    assert "flatpak uninstall --user org.localsend.localsend_app" in sc
    assert remove_all_script([core]) is None


def test_optional(a):
    import tempfile
    global SKIP_FILE
    # core vs optional for the installer's real package names (packages/*.txt + BUILT)
    real = installer_packages()
    if any(os.path.isdir(d) for d in PACKAGE_LISTS):
        rpm_keys = [k for k in OPTIONAL if "." not in k]
        missing = [n for k in rpm_keys for n in (k, *OPTIONAL[k][0]) if n.lower() not in real]
        assert not missing, f"OPTIONAL names not in packages/*.txt: {missing}"
        for core in ("waybar", "kitty", "fuzzel", "mako", "hyprland", "gamescope", "nss-tools", "gnome-keyring"):
            assert core in real and protected(f"{core}.desktop", "", core, None, real) == "part of this desktop", core
    for k in OPTIONAL:
        fp = k if "." in k else None
        assert protected(f"{k}.desktop", "", None if fp else k, fp, real | {k.lower()}) is None, k
    assert optional_key("remotedesktopmanager", None) == "RemoteDesktopManager"
    # the uninstall command: interactive, records only after success and once the app is gone
    with tempfile.TemporaryDirectory() as t:
        stubs = os.path.join(t, "bin")
        os.mkdir(stubs)
        for name, body in (("sudo", 'echo "$@" >> "$T/ran"; exit "${RC:-0}"'), ("rpm", 'exit "${GONE:-1}"'),
                           ("flatpak", 'echo "$@" >> "$T/ran"; [ "$1" = info ] && exit "${GONE:-1}"; exit "${RC:-0}"')):
            with open(os.path.join(stubs, name), "w") as fh:
                fh.write(f"#!/bin/sh\n{body}\n")
            os.chmod(os.path.join(stubs, name), 0o755)
        saved, SKIP_FILE = SKIP_FILE, os.path.join(t, "cfg/fw13/skip-packages")
        try:
            steam = {"kind": "rpm", "package": "steam", "optional": "steam", "protected": None, "extras": ["steam-devices"]}

            def run(app, **env):
                argv = uninstall_argv(app)
                assert argv[:2] == ["bash", "-c"] and "-y" not in shlex.split(argv[2].split("&&")[0]), argv
                subprocess.run(argv, env={**os.environ, "PATH": f"{stubs}:/usr/bin:/bin", "T": t, **env},
                               capture_output=True, timeout=10)
            run(steam, RC="1")
            assert not os.path.exists(SKIP_FILE), "recorded after dnf failed"
            run(steam, GONE="0")
            assert not os.path.exists(SKIP_FILE), "recorded while still installed"
            run(steam)
            run(steam)
            assert skipped() == ["steam", "steam-devices"] and open(SKIP_FILE).read() == "steam\nsteam-devices\n"
            assert open(os.path.join(t, "ran")).read().splitlines()[0] == "dnf remove steam steam-devices"
            run({**a["org.localsend.localsend_app.desktop"]})
            assert skipped()[-1] == "org.localsend.localsend_app"
            assert "uninstall --user org.localsend.localsend_app" in open(os.path.join(t, "ran")).read()
            with open(SKIP_FILE, "a") as fh:
                fh.write("\n# comment\n  code  \nsteam\n")
            assert skipped() == ["steam", "steam-devices", "org.localsend.localsend_app", "code"]
            unskip("steam")
            assert skipped() == ["steam-devices", "org.localsend.localsend_app", "code"]
        finally:
            SKIP_FILE = saved


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        for x in installed():
            print(f"{x['id']:50} {x['source']:40} {x['protected'] or ''}")

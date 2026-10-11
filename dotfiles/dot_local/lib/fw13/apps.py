"""Apps the launcher shows (+ Flatpak apps): where each came from, whether it's ours, pending updates.

Used by fw-launcher (how many entries fuzzel lists) and Settings → Apps.

  python3 -m fw13.apps            list: id, source, protected note
  python3 -m fw13.apps test       self-check
"""
import glob
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
# packages/*.txt: chezmoi's source is the whole repo (.chezmoiroot = dotfiles), updated by every `chezmoi update`;
# install.sh's own checkout is the fallback (and the union covers either being older)
PACKAGE_LISTS = (os.path.join(HOME, ".local/share/chezmoi/packages"), os.path.join(HOME, ".local/share/fw13-hypr/packages"))
# install.sh builds or installs these itself, outside packages/*.txt
BUILT = {"telegram-desktop-official", "ghostty-official", "citadel", "citadel-helper"}
OUR_FLATPAKS = {"org.localsend.localsend_app"}
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


def protected(did, path, pkg, flatpak_id, ours):
    """Why an app can't be uninstalled here, or None."""
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
        apps.append(app)
    for fp in fps:  # Flatpak apps without a launcher entry
        if fp["id"] not in shown:
            apps.append({"id": fp["id"], "name": fp["name"], "icon": fp["id"], "package": None, "kind": "flatpak",
                         "flatpak": fp["id"], "installation": fp["installation"], "source": f"Flatpak ({fp['installation']})",
                         "protected": protected(fp["id"], "", None, fp["id"], ours)})
    return apps


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


def installed():
    entries = launcher_entries()
    owners = rpm_owners([p for _d, p, _k in entries if "/flatpak/exports/" not in p])
    ours = installer_packages()
    return guard_deps(classify(entries, owners, flatpaks(), ours), ours)


def uninstall_argv(app):
    """Terminal command that removes the app (dnf/flatpak ask y/N themselves), or None."""
    if app["protected"]:
        return None
    if app["kind"] == "rpm":
        return ["sudo", "dnf", "remove", app["package"]]
    if app["kind"] == "flatpak":
        return ["flatpak", "uninstall", f"--{app['installation']}", app["flatpak"]]
    return None


def test():
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
    assert a["chromium-browser.desktop"]["protected"] == "part of this desktop"
    assert a["gimp.desktop"]["protected"] is None and a["gimp.desktop"]["source"] == "Package gimp"
    assert uninstall_argv(a["gimp.desktop"]) == ["sudo", "dnf", "remove", "gimp"]
    assert a["org.gnome.Nautilus.desktop"]["protected"] == "GNOME needs it"
    assert a["fw-settings.desktop"]["protected"] and a["fw13-calc.desktop"]["protected"]
    assert a["Terraria.desktop"]["source"] == "Installed by Steam" and uninstall_argv(a["Terraria.desktop"]) is None
    assert a["Mine.desktop"]["source"] == "Installed by hand"
    assert a["org.localsend.localsend_app.desktop"]["protected"] == "part of this desktop"
    assert uninstall_argv(a["org.example.App.desktop"]) == ["flatpak", "uninstall", "--system", "org.example.App"]
    assert uninstall_argv(a["org.example.NoEntry"]) == ["flatpak", "uninstall", "--user", "org.example.NoEntry"]
    g = {x["id"]: x for x in guard_deps(list(a.values()), {"fcitx5"}, lambda p: {"fcitx5"} if p == "gimp" else set())}
    assert g["gimp.desktop"]["protected"] == "part of this desktop (needed by fcitx5)" and a["gimp.desktop"]["protected"] is None
    assert classify(entries, {"/usr/share/applications/gimp.desktop": "Thunar"}, [], {"thunar"})[1]["protected"]
    assert "-y" not in sum((uninstall_argv(x) or [] for x in a.values()), [])
    real = installer_packages()
    assert {"chromium", "code"} <= real or not any(os.path.isdir(d) for d in PACKAGE_LISTS), "package lists not read"
    assert not any(w.startswith("#") for w in real)
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        for x in installed():
            print(f"{x['id']:50} {x['source']:40} {x['protected'] or ''}")

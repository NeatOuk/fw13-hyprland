# CLAUDE.md

For AI agents working here. How each script, module, page and root helper works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) + each file's docstring. Read them before changing a component; keep them accurate in the same commit.

## fw13-hypr

ML4W-style **installer** (`install.sh`) that adds a Hyprland (uwsm) desktop on top of **any regular Fedora ≥44** — Workstation/GNOME, KDE, spins, or Minimal — for a **Framework Laptop 13, AMD Ryzen AI 9 HX 370** (Radeon 890M, MediaTek MT7925). No custom image/ISO. Fedora only (user decision). Atomic editions are refused in preflight.

## Hard rules

1. **Ask before adding ANY package**, including weak deps, helpers, and "obvious" utilities. Propose name + source + why; wait for approval. Never slip one in through a script (e.g. `jq`, `libnotify`, `rsync`) — use what's already installed (see `fw-notify` using `gdbus`).
2. **Prefer official sources**, in this order: Fedora repos → vendor's own repo (Microsoft, mise) → RPM Fusion → COPR → upstream installer → Flathub. State the source tier when proposing.
3. **Weak deps off for our installs only** (`dnf --setopt=install_weak_deps=False`); never change the user's global dnf.conf. Anything needed must be listed in `packages/*.txt`. Keep the explicit firmware lines (amd-gpu, amd-ucode, mt7xxx) — on Minimal they'd otherwise be missing.
3a. **Never remove or replace the user's existing stack** (DE, display manager, power daemon). Detect and adapt. **One exception (user decision): the login screen is always greetd + tuigreet** (`15-login.txt`); an existing GDM/SDDM is disabled, not removed (`KEEP_DM=1` keeps it and only adds the session; GDM 50 has no DefaultSession key, an older line is removed). power-profiles-daemon present → skip tuned (`61-power.txt`). Only sanctioned swap: ffmpeg-free → ffmpeg (`--allowerasing`).
3b. **Idempotent**: re-running must be safe.
4. **Never install apps on Flathub** without per-app approval. The remote is added; the only approved app is LocalSend (see Package sources), everything else stays off.
5. **No secrets in git.** Credentials (Chromium OAuth, restic repo/password) come from chezmoi `promptStringOnce` in `dotfiles/.chezmoi.toml.tmpl` and render into `private_` (0600) files.
6. **Timeshift = whole system + /home, mode auto-detected** in `fw-timeshift-setup`: btrfs mode iff `/` is subvol `@`; otherwise rsync (Fedora's default `root`/`home` names). Scheduled by **Timeshift's own /etc/cron.d jobs** (it writes them itself when a `schedule_*` flag is on; cronie is a dependency of Fedora's package) — user decision; the old fw-timeshift timer is removed by install.sh. Timeshift's restore can't mount Fedora's `root` subvolume (it hard-codes `@`), so rsync-mode restores go through `fw-timeshift-restore`.
7. Hardware is AMD. Do not add Intel-specific packages/params.
8. Visual style: clean/minimal, Tokyo Night by default or colours from the wallpaper (matugen, `fw13.theme`), flat borders, thin bar. **Keys stay simple and conventional** — do not port Omarchy's (or any distro's) keymap. Omarchy-*style* bar menus are OK (user decision): bar icons open fuzzel menus (`fw-control-center [section]`, `fw-system-menu`), not big GUI apps; GUI tools stay on right/middle-click.

## Layout (details: docs/ARCHITECTURE.md)

```
install.sh                   installer; packages/NN-*.txt (one per line, '#' lines only), repos/*.repo, rpm/*.spec
                             optional groups = OPT_GROUPS/GROUP_INFO at its top (files + `on <group>` steps); core = the rest
system/                      root side: usr/local/bin/fw-* helpers, systemd units, udev, modprobe, geoclue, polkit, Chromium policy
dotfiles/                    chezmoi source (.chezmoiroot); .chezmoi.toml.tmpl = one-time prompts; jarvis/ = Jarvis briefing
  dot_config/hypr/*.lua      Hyprland Lua config (hyprland.lua require()s the rest); hyprlock/hypridle/hyprpaper keep .conf
  dot_local/lib/fw13/        shared Python library; pages/ = Settings pages (PAGES in pages/__init__.py)
  dot_local/bin/executable_fw-*  bar modules, panels, menus, user daemons, Settings app (fw-settings)
docs/                        APPS.md (user guide: apps, Settings, bar, keys, backups), ARCHITECTURE.md, FIRST-INSTALL.md (hardware checklist), screenshots/
.github/workflows/test.yml   lint → ./install.sh --ci in fedora:44 (+ weekly); no screenshot job (removed, user decision)
```

## Package sources (current)

Build/download mechanics for the non-repo sources: docs/ARCHITECTURE.md → Installer.

| Source | Packages / notes |
|---|---|
| Fedora | everything else, incl. qalculate (fw-calc), udisks2 + dnf5-plugins (fw-health), fuse3 (`restic mount`), gcr (SSH agent), libsecret (secret-tool: Jarvis Laya token; user decision), strongswan (IPsec VPN, FortiGate IKEv2 PSK + EAP), nm-connection-editor + NetworkManager-{openvpn,openconnect,vpnc}-gnome (user decision), easyeffects + lsp-plugins-lv2 + lv2-calf-plugins (user decision), android-tools (adb), syncthing (user service, no port opened; user decision); ollama (system service, local models); dev: podman, distrobox, gh, neovim + ripgrep + fd-find + tree-sitter-cli + gcc (LazyVim; user decision). swayosd not in F44 → dropped (keys use wpctl/brightnessctl) |
| COPR `lionheartp/Hyprland` | hyprland, hyprlock, hypridle, hyprpaper, hyprpolkitagent, hyprpicker, hyprsunset, hyprland-guiutils, xdg-desktop-portal-hyprland. Hyprland was **retired from Fedora in F43**; the COPR builds F44+ only (hence the ≥44 preflight); `HYPR_COPR=…` swaps it (`HYPR_COPR=` = Fedora only). Also matugen 4.2.0 as `'matugen >= 4'` only when `HYPR_COPR` is set (F44's 3.1.0 rejects `--prefer`/`-t scheme-*`; a COPR without 4.x fails loudly; else Tokyo Night only) |
| RPM Fusion | steam, steam-devices, ffmpeg, gstreamer1-plugins-bad-freeworld |
| Vendor | `code` (Microsoft), `mise` (mise.jdx.dev/rpm), `RemoteDesktopManager` (Devolutions on Cloudsmith, user decision; ~1.2 GB; needs `gnome-keyring`, in 30-apps), `cloudflare-warp` (`97-warp.txt` + hard dep `nss-tools` from Fedora; enables `warp-svc`) |
| mise (user) | node LTS, chezmoi, starship, opencode (self-update off), **Pi** `"npm:@earendil-works/pi-coding-agent"` (user decision; old @mariozechner name deprecated), uv, kubectl 1.34 (user decision), lazygit (LazyVim's git screen; user decision) |
| Built as RPMs (owner's repos) | **Citadel** outbound firewall: `citadel` (NeatOuk/citadel-app `main`) + `citadel-helper` (`v1.3.2`); user phase enables `citadel.service` + `citadel enforce on` (user decision); helper's polkit rule lets wheel in without a password (by design) |
| Official binary repackaged | **Telegram Desktop** (user decision: official build as RPM `telegram-desktop-official`, self-updater off), **Claude Desktop** (user decision: Anthropic's .deb from its apt pool → RPM `claude-desktop-official`, version + sha256 pinned, group `claude-desktop`; Cowork: qemu-system-x86-core + edk2-ovmf + virtiofsd from Fedora in 73-cowork.txt, vhost_vsock in /etc/modules-load.d) |
| Official release, built | **Ghostty** (user decision: official source, not a COPR) → `ghostty-official`, pinned sha256; group `ghostty` (`GHOSTTY=0` skips for one run) |
| Upstream release binaries | **framework_tool** (user decision; not in Fedora), **scrcpy** (user decision: official release, not a COPR; uses Fedora's adb), **DBeaver CE** (user decision: official RPM from GitHub releases, not Flathub; group `database`; bundles its JRE, no deps); all sha256-pinned |
| Flathub (user remote) | **LocalSend** only (user decision; `--user`; port 53317 not opened (user decision): send only) |
| Upstream installer | Claude Code (`claude.ai/install.sh` → `~/.local/bin/claude`, self-updating; mise npm skipped its postinstall) |

Pinned binaries: bump version + sha256 together. Apps the user removed via Settings → Apps are listed in `~/.config/fw13/skip-packages` and skipped by install.sh.

Declined by the user — do not re-propose unless asked: `mesa-va-drivers-freeworld`, toolbox, Docker CE, ProtonUp-Qt, Nerd Fonts, snapper/btrfs-assistant, Qt5 removal, CJK font removal, swayosd COPR, Arch support, bootc/ISO image, a single-process shell (Quickshell/AGS/DankMaterialShell replacing Waybar/fuzzel/mako/our panels), pavucontrol (removed, user decision; per-app volume is in Settings → Sound), Teams for Linux (added then removed Oct 2026: too buggy), Google Chrome (Oct 2026: memory; Google Password Manager passkeys go through the phone's QR code in Chromium instead), and the other ideas from the Oct 2026 comparison with ML4W/JaKooLit/Omarchy/end-4/HyDE/Caelestia (overview with live previews, theme gallery, OCR, DDC/CI brightness, clamshell handling, bar weather/reminders): the current design stays.

## Commands

```bash
./install.sh                     # full install (interactive)
./install.sh --ci                # what CI runs in a fedora container (root, non-interactive)
./install.sh --user-only         # re-apply dotfiles/mise/shell only
./install.sh --print-plan [--minimal|--with=a,b|--without=a,b]   # groups, package lists, steps; changes nothing (checkout only: refuses to fetch the repo)
T=$(mktemp -d); HOME=$T XDG_CONFIG_HOME=$T/.config XDG_DATA_HOME=$T/.local/share XDG_STATE_HOME=$T/.local/state XDG_CACHE_HOME=$T/.cache \
  chezmoi init --source=$PWD --apply --exclude=scripts   # dry-run dotfiles into a throwaway home (isolate every XDG dir)
XDG_RUNTIME_DIR=$(mktemp -d) Hyprland --verify-config -c "$T/.config/hypr/hyprland.lua"   # check the rendered Lua config
# lint, as CI does: split scripts by shebang, shellcheck the bash ones, ast-parse the Python ones
sh=() py=()
for f in install.sh system/usr/local/bin/* dotfiles/dot_local/bin/executable_*; do
  case "$(head -1 "$f")" in *python3*) py+=("$f") ;; *) sh+=("$f") ;; esac
done
shellcheck -S warning "${sh[@]}"
shellcheck -S warning -s bash dotfiles/dot_config/uwsm/env-hyprland   # sourced by uwsm, no shebang
python3 -c 'import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' "${py[@]}" $(find dotfiles/dot_local/lib -name '*.py')
```

Self-checks: `PYTHONPATH=dotfiles/dot_local/lib python3 -m fw13.<module> test` (apps agents jarvis nightlight timezone speakers syncthing pages.search; `fw13.ollama` takes no arg) and `fw-<x> test` (battery-warn updates caffeine usb bt-agent syncthing vpn active-app jarvis-panel).

There is no unit-test suite: verification is lint + dry-run + self-checks + CI install (`.github/workflows/test.yml`) + the hardware checklist in `docs/FIRST-INSTALL.md`. Local dotfile edits are not what `chezmoi update` applies (it pulls the pushed repo), so push before testing on the machine. `CONTRIBUTING.md` has the commit conventions (`feat(area):`, `fix(area):`, `chore:`, `docs:`; update README (install/update) or docs/APPS.md (features, Settings, keys), this file and docs/ARCHITECTURE.md in the same change) and the roadmap.

**Commits (user decision):** commit (and push) every change as soon as it is made, one change per commit; never add `Co-Authored-By` or other attribution/session trailers to commit messages.

Package-resolution failures are intended to fail loudly — fix the name (and ask the user if it means a source change); never add `--skip-unavailable`.

## Conventions

- **Hyprland config is Lua** (hyprlang `.conf` deprecated since 0.55, dropped soon). API for the installed version: `/usr/share/hypr/stubs/hl.meta.lua`; example: `/usr/share/hypr/hyprland.lua`. `hl.bind("SUPER + X", hl.dsp.…, { repeating/locked/mouse = true })`, `hl.window_rule({ name, match = { class = … }, float = true })`, `hl.on("hyprland.start", …)` for autostart.
- **hyprctl in Lua mode**: `hyprctl dispatch '<lua dispatcher>'` (old `dispatch workspace 2` → "Invalid dispatcher"); `hyprctl eval '<lua>'` replaces `keyword`/`--batch`. Quote Lua strings from Python with `json.dumps`. The config manager is chosen at Hyprland start: switching .conf↔.lua needs a re-login, not `hyprctl reload`.
- `Hyprland --verify-config -c <hyprland.lua>` checks syntax + unknown keys (not dispatcher args — test those, see below).
- **Live tests never act on the active window** (it's the user's terminal): always pass `window = "address:0x…"` for a verified throwaway window, and never selector-less close/move/scratchpad.
- **Stop processes by PID, never `pkill -f <pattern>`** from an agent's shell: the tool runs `bash -c '<whole command>'`, so the pattern matches that shell and kills it. Read the helper's pidfile in `$XDG_RUNTIME_DIR` and check `/proc/$pid/cmdline`, or use `pgrep -x <name>`.
- **App windows tile** (user decision): new apps and tools get no float/size/center window rule; only inherent popups (progress dialogs) and Jarvis task windows float. Ask before adding a float rule.
- Launch GUI apps through uwsm: `uwsm app -- <cmd>`; fuzzel uses `--launch-prefix="uwsm app -- "`. Terminals always through `fw-term` (kitty or Ghostty).
- Session env goes in `dotfiles/dot_config/environment.d/` (read by systemd --user), not Hyprland `env =`.
- Icons: **Font Awesome 6 Free/Brands only** (no Nerd Font codepoints ≥ U+F0000). One exception (user decision): the bar's launcher button is Framework's gear, `framework-logo.svg` generated by fw13.theme in the accent colour (path from Simple Icons, CC0) and drawn as a waybar CSS background. Fonts: JetBrains Mono, Noto (incl. Khmer).
- Notifications from scripts: `fw-notify "title" "body"` (gdbus), not `notify-send`.
- **Theme files** live in `~/.config/fw13/theme/` and base configs reference them (`source`/`@import`/`include`; hyprpaper reads desktop.jpg there; hyprlock is a tuigreet-style text box without a picture (user decision), so lock.jpg is rendered but unused); a new themed app gets a generated file there, not colours in its config. **Colour rule:** colour literals live only in theme.py TOKYO_NIGHT, the create_ seeds of `~/.config/fw13/theme/` and hypr/theme.lua's documented fallback; base configs (hypr, hyprlock, waybar, fuzzel, mako, kitty, ghostty, ui_*) include the generated files, never hard-code hex. A user's own `~/.config/gtk-4.0/gtk.css` (no fw13 marker line) is never clobbered. GSettings/gtk.css and other app theming changes happen only inside Hyprland and are restored at logout (rule 3a: GNOME/KDE share the account).
- chezmoi naming: `dot_`, `private_`, `executable_`, `create_` (create-once, e.g. `hypr/local.lua`, `hypr/displays.lua`, `fcitx5/profile`), `modify_` (keeps distro `.bashrc`), `run_onchange_after_`. `~/.config` has exactly one source dir (`dot_config/`) — put private subdirs under it as `private_<name>`.
- Prompt strings in `.chezmoi.toml.tmpl` must not contain commas (breaks `--promptString`), and are duplicated verbatim in `install.sh`'s CI `--promptString` args — change both together.
- Secret-dependent files are skipped via `dotfiles/.chezmoiignore` when their prompt was left blank (Chromium OAuth env, restic env + timer). New secret-backed files need a matching ignore rule.
- Outside `--ci`, the user phase runs `chezmoi init --apply "$REPO_URL"` then `chezmoi update --init` (re-runs pull new dotfiles and re-render chezmoi.toml from the newer template; promptStringOnce keeps values, a new key prompts once even with `--yes`; tables without a prompt, like `restic_creds`, are written back by the template) — it applies the **pushed** repo, not the local tree. Test local dotfile edits with the temp-HOME dry-run in Commands.
- Scripts are bash unless they need a GUI (`fw-display-panel`: Python + GTK3 + GtkLayerShell; pin `gi.require_version` for Gtk **and** Gdk 3.0 or Gdk 4 loads). Shell scripts: `#!/usr/bin/env bash`, `set -euo pipefail`; must pass `shellcheck -S warning`. Build package arg lists with `mapfile`, not `$(...)`. Wrap `eval "$(mise activate bash)"` in `set +u`.

## Verification before declaring done

- `bash -n` on every script; JSON-parse `waybar/config.jsonc` (strip `//` comments) and TOML-parse mise/starship — the python snippet in the CI `lint` job does both.
- `Hyprland --verify-config` on the rendered `hyprland.lua`; duplicate-keybind check via `hyprctl -j binds` (88 binds today, 1 of them in the "remote" submap; every bind carries { description = … } for fw-keys).
- chezmoi dry-run into a temp HOME, both with secrets blank and filled.
- CI green on fedora:44; read the install report in the job summary (added count, size, top 25, Hypr provenance).
- Hardware-only checks (cannot be done in CI/VM): MT7925 Wi-Fi/BT, VA-API (`vainfo` via distrobox), fingerprint, suspend/resume, tuned-ppd profiles, ambient light sensor, Steam + gamescope.

## Known unverified

Package names resolved on Fedora 44 + lionheartp in the first CI build (only swayosd failed → dropped). Unverified: whether the COPR ships `hyprland-uwsm.desktop` (installer adds one in /usr/local/share/wayland-sessions if not), Timeshift rsync filter behaviour on a real system, EasyEffects' `flat` fallback preset for non-speaker outputs.

## License

GPL-3.0-only (`LICENSE`). Third-party packages keep their own licenses.

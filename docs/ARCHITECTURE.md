# Architecture

Component map of fw13-hyprland with the per-feature details. The rules (packages, sources,
user decisions, conventions, verification) are in [CLAUDE.md](../CLAUDE.md); this file is the
"how does X work" reference. Keep it accurate in the same commit as the change.

Paths: `lib/fw13/…` = `dotfiles/dot_local/lib/fw13/…` (→ `~/.local/lib/fw13`), `fw-…` scripts =
`dotfiles/dot_local/bin/executable_fw-…` (→ `~/.local/bin`), "store `x`" = key `x` in
`~/.config/fw13/settings.json` (lib/fw13/store.py).

## Installer

- **install.sh**: preflight → repos → packages → system files → login/power → fingerprint/services → user phase → report.
  - Skips the names in `~/.config/fw13/skip-packages` (Settings → Apps → Uninstall… of an optional app; logs "skipped (removed by you)").
  - Flags: `--yes --ci --system-only --user-only`; env: `HYPR_COPR`, `REPO_URL`, `CHECKOUT`.
  - Warns (banner + before Done) when neither gnome-shell nor plasma-workspace is installed: GNOME recommended, never installed.
- **packages/NN-\*.txt**: one package per line, `#` comments on their own line only (`pkgs()` splits on whitespace); `15-login`, `61-power` conditional; matugen is installed separately as `'matugen >= 4'` (needs the COPR).
- **repos/\*.repo**: vendor repos (vscode, mise, cloudflare-warp, devolutions-rdm).
- **rpm/**: specs we build locally: `telegram-desktop-official.spec` (`build_telegram_rpm` in install.sh).

### Package source details (sources and decisions: CLAUDE.md → Package sources)

- Vendor repo files: `repos/vscode.repo` (packages.microsoft.com), `repos/mise.repo` (mise.jdx.dev/rpm), `repos/devolutions-rdm.repo` (Devolutions' repo on Cloudsmith), `repos/cloudflare-warp.repo` (pkg.cloudflareclient.com).
- mise tools live in the user's `~/.config/mise/config.toml`. Pi = pi.dev, github.com/earendil-works/pi, MIT.
- gcr provides gcr-ssh-agent; strongswan is driven via swanctl; ollama runs as a system service.
- LocalSend `org.localsend.localsend_app` is not in Fedora.

### Built or downloaded by install.sh

- **Citadel** (`build_citadel_rpm`): `citadel` (github.com/NeatOuk/citadel-app, `main`, release stamped `.gitYYYYMMDD.<sha>`) + `citadel-helper` (github.com/NeatOuk/citadel-helper, tag `v1.3.2`), built with their own .spec files (no prebuilt packages exist); build tools + PySide6 in `packages/95-citadel.txt`. Override with `CITADEL_APP_REF`/`CITADEL_HELPER_REF`. User phase enables `citadel.service` and `citadel enforce on`. The helper's polkit rule lets wheel use it without a password (by design).
- **Telegram Desktop** (`build_telegram_rpm`): reads the version from telegram.org's download redirect, downloads the tarball (no checksum is published: HTTPS only) plus the launcher entry, D-Bus service and icons from github.com/telegramdesktop/tdesktop at the same tag, and builds `telegram-desktop-official` (`/opt/telegram`, `/usr/bin/Telegram`, `Conflicts: telegram-desktop`). Its self-updater is off via `/opt/telegram/externalupdater.d` (7.x reads it next to the binary, not in /etc; while the updater is on, Telegram writes its own `org.telegram.desktop._<hash>.desktop`, removed by the user phase). Re-running install.sh rebuilds when telegram.org has a newer version, otherwise it's a no-op.
- **Ghostty** (`build_ghostty_rpm`): downloads `release.files.ghostty.org/<v>/ghostty-<v>.tar.gz`, checks the pinned `GHOSTTY_SHA256` (verified once against the release's minisign signature), builds with the exact Zig from `build.zig.zon`'s `minimum_zig_version` (ziglang.org tarball checked against its index.json; Fedora 44's zig 0.16 is too new) and installs `ghostty-official` (`Conflicts: ghostty`; terminfo files the system already owns are dropped). Build deps in `packages/98-ghostty.txt`. `GHOSTTY=0` skips; bump = new `GHOSTTY_VERSION` + verified sha256.
- **framework_tool**: release binary from github.com/FrameworkComputer/framework-system into `/usr/local/bin`, checked against the pinned `FWTOOL_SHA256` (GitHub's asset digest); bump `FWTOOL_VERSION` + sha256 together; skipped when the installed file already matches.
- **scrcpy**: downloads `scrcpy-linux-x86_64-$SCRCPY_VERSION.tar.gz` (github.com/Genymobile/scrcpy), checks the pinned `SCRCPY_SHA256` (GitHub's asset digest), installs it to /opt/scrcpy (stamp /opt/scrcpy/.version) with a /usr/local/bin/scrcpy wrapper setting `ADB=/usr/bin/adb` (Fedora's android-tools, 70-dev.txt; the bundled adb is not installed), a launcher entry in /usr/local/share/applications and the man page; phones are reachable without root through systemd's 70-uaccess (ADB/Fastboot); bump version + sha256 together.
- **LocalSend**: `flatpak install --user org.localsend.localsend_app`; port 53317 is not opened, so the laptop can send but not receive.
- **Claude Code**: `curl -fsSL https://claude.ai/install.sh | bash` → `~/.local/bin/claude`, self-updating (mise npm skipped the package's postinstall, so no binary).
- **Chromium policies**: links `/etc/chromium/policies/managed/fw13-theme.json` to `~/.config/fw13/theme/chromium-policy.json` (see Theming); installs the recommended policy `system/etc/chromium/policies/recommended/fw13-memory.json` = Memory Saver on, maximum savings, user can still change it.

## Root side (`system/`)

### system/usr/local/bin/

- **fw-vpn-ctl**: root side of the bar VPN toggle (see fw-vpn).
- **fw-vpn-config** `show <name>|write|delete <name>` (Python): root side of the strongSwan form in Settings → Network → VPN (pages/vpn_edit.py). pkexec action `org.fw13.vpn-config`, `auth_admin_keep`. `show` = non-secret fields + has_psk/has_password; `write` = JSON on stdin, validated, rendered from a FortiGate IKEv2 PSK+EAP template, 0600, old file → `<name>.conf.bak`, `swanctl --load-all`.
- **fw-timeshift-setup**: Timeshift config, mode auto-detected (CLAUDE.md rule 6).
- **fw-hibernate-setup** `[--dry-run] [undo | delay 1|3|never]`: y/N per step, idempotent.
  - Top-level subvol `swap` at /swap, RAM-sized `btrfs filesystem mkswapfile`, semanage swapfile_t + /swap var_t (logind must search it, else CanHibernate = AccessDenied), fstab pri=10 below zram, Timeshift exclude `/swap/***`, `dracut.conf.d/fw13-resume.conf`.
  - UEFI + systemd >= 255 → HibernateLocation EFI var, no `resume=` (grubby only without EFI). Refuses lockdown/non-btrfs/no space.
  - `delay` writes sleep.conf.d HibernateDelaySec + HibernateOnACPower=no + logind.conf.d HandleLidSwitch=suspend-then-hibernate/ExternalPower=suspend (battery only); fw-idle's battery suspend follows that file. Settings → Power "When the battery is very low" + "Then hibernate after". fw-system-menu shows Hibernate only when CanHibernate = yes.
- **fw-timeshift-restore**: rsync-mode restore on Fedora's root/home btrfs: snapshot root, rsync onto the copy, swap by rename; kernels side by side + grubby; holds Timeshift's lock; undo.
- **fw-health-root**: root health facts, plus `luks` {tpm2, pin} / null and `secure_boot` from the EFI var.
- **fw-disk-unlock** `password|tpm-pin|tpm`: Settings → Security via `sudo` in fw-term. `systemd-cryptenroll --wipe-slot=tpm2 [--tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=yes]`; refuses without a password/recovery slot, never removes it; `tpm` refused unless Secure Boot is on (PCR 7 is constant otherwise; the page hides it too). `tpm2-device=auto` in the volume's crypttab line (backup `crypttab.fw13.bak`) or `rd.luks.options` via grubby; `/etc/dracut.conf.d/fw13-tpm2.conf` adds tpm2-tss (removed for password); `dracut -f --regenerate-all`.
- **fw-charge-limit** (root, no args): copies `charge_control_end_threshold` into the Framework EC with `framework_tool --charge-limit` — the kernel threshold alone is not enforced on the FW13 AMD, it charged past 80 %. Run by fw-charge-limit.service at boot, the Mains udev rule, and Settings → Power's switch via pkexec: action `org.fw13.charge-limit` in `system/usr/share/polkit-1/actions/org.fw13.power.policy`, rule `50-fw13-power.rules` = wheel at the laptop, no password.
- **fw-power-profile**: performance on AC, balanced on battery, via the PowerProfiles D-Bus API (PPD or tuned-ppd); a hand-picked profile lasts until the next plug/unplug. Run by fw-power-profile.service (boot) + `system/etc/udev/rules.d/90-fw-power-profile.rules` (Mains change).

### system/etc/

- **geoclue/conf.d/90-fw13-timezone.conf**: `[fw13-timezone]` allowed + `system=true`, so fw13.timezone gets a location without a GeoClue agent (none runs in Hyprland).
- **modprobe.d/fw13-charge-control.conf**: `cros_charge_control probe_with_fwk_charge_control=1` (the kernel skips Framework otherwise) → charge limit in UPower / power panel.
- **systemd/system/**: fw-health-root.{service,timer} (:30 hourly → `/var/lib/fw13/health-root.json`, 0644; install.sh copies the folder only if it has files), fw-power-profile.service, fw-charge-limit.service.
- **polkit-1/rules.d/50-fw13-vpn.rules** + `usr/share/polkit-1/actions/org.fw13.vpn.policy`: see fw-vpn.

## Dotfiles (`dotfiles/`, chezmoi source, `.chezmoiroot = dotfiles`)

- **.chezmoi.toml.tmpl**: one-time prompts (secrets) — never commit values.
- **dot_config/hypr/\*.lua**: `hyprland.lua` require()s monitors/displays/autostart/looknfeel(+theme)/input/windows/bindings/settings (fw-settings-generated)/local (Lua config; hyprlock/hypridle/hyprpaper keep their own .conf).
- **hypr/hyprlock.conf.tmpl**: tuigreet-style text box without a picture (user decision): console black/grey `$fw_tty_*` = theme.TTY, 80-column box on a 13x29 grid (16 pt; hyprlock sizes are physical pixels), hostname/user from chezmoi; lock.jpg is still rendered but unused.
- **dot_claude/modify_settings.json**: Claude Code statusLine for fw-claude-limits.
- **jarvis/**: `AGENTS.md` (Jarvis briefing incl. the What/Why/How rule for root actions), `CLAUDE.md` (imports `@MEMORY.md`).
- **dot_local/share/easyeffects**: Framework's FW13 preset + IR and our presets (see fw-speakers).

### Shared Python library (lib/fw13 → ~/.local/lib/fw13; scripts `sys.path.insert` ~/.local/lib)

- **hypr**: Lua hyprctl helpers.
- **bar**: `SIGNALS` = the waybar custom modules' `"signal"` numbers (config.jsonc), `refresh(name)` = `pkill -RTMIN+N -x waybar`; imported `as waybar` (several scripts have their own `bar()`). `python3 -m fw13.bar test` checks the table against config.jsonc.
- **panel**: single instance via `$XDG_RUNTIME_DIR/<name>.pid` checked against `/proc/<pid>/cmdline` (`running`/`close`/`claim`/`release`) for the layer-shell panels, fw-workspaces and fw-autobrightness; `right_margin(width)` centres a bar panel under the pointer. `python3 -m fw13.panel test` self-check.
- **displays**, **system**, **ui_display**.
- **store**: `~/.config/fw13/settings.json`.
- **ui_theme**: flat CSS (incl. `.found` for search hits).
- **power**: power readouts + `tuning()` (read-only CPU driver/EPP/boost/platform profile/ABM/tuned readout); `warn_levels()` for fw-battery-warn.
- **als**: light sensor via SensorProxy + auto-brightness curve.
- **health**: fw-hwcheck hardware group + fw-health daily group; expected Framework values in one table, non-Framework → SKIP; `root_facts()`.
- **notify**: shared notification + session_env; crash-watch and health use it; `launch()`, `on_action()`.
- **sound**: wpctl; filter sources listed too; `apps()` = per-app volume (pw-dump Stream/Output/Audio, EasyEffects' own skipped). Noise suppression = our drop-in `~/.config/pipewire/pipewire.conf.d/fw13-noise.conf`: libpipewire-module-echo-cancel, aec/libspa-aec-webrtc, monitor.mode (no extra sink), source `fw13_noise_source` "Noise-cancelled microphone"; restart pipewire/pipewire-pulse/wireplumber, set it default, previous default in store `noise_prev_source` restored when off; Settings → Sound → Input.
- **net**: nmcli; passwd-file, never argv. **bt**: org.bluez via Gio.
- **hyprsettings**: settings.lua: verify-config in a temp copy, then write + `hl.config` live.
- **idle**: owns hypridle.conf; plugged-in and battery timeouts, store `idle_*[_battery]`, listeners call `fw-idle <action> ac|battery`.
- **terminal**: backend of fw-term.
- **vpn**, **warp**: backends of fw-vpn and fw-warp-panel.
- **apps** (Settings → Apps):
  - `launcher_entries()` = what fuzzel lists (desktop ids over XDG_DATA_HOME + XDG_DATA_DIRS, first wins, `[Desktop Entry] Type=Application`, not NoDisplay/Hidden; fw-launcher counts with it); source via one `rpm -qf` / `flatpak list --app` / Exec+path (Steam, Lutris, Wine…).
  - OPTIONAL = {app package or Flatpak id: (extra packages, note)}: steam(+steam-devices), lutris, telegram-desktop-official, chromium, code, RemoteDesktopManager, ghostty-official, citadel(+citadel-helper), cloudflare-warp, easyeffects(+lsp-plugins-lv2, lv2-calf-plugins), LocalSend; build deps stay. They get Uninstall… = fw-term `bash -c` (`sudo dnf remove <pkg> <installed extras>` / flatpak uninstall, never -y) that appends every name to `~/.config/fw13/skip-packages` only after success and once rpm/flatpak no longer has it; install.sh skips those names (pkgs() filter, Telegram/Ghostty/Citadel builds, WARP repo + warp-svc, LocalSend); Apps → Removed apps = `apps.unskip()`.
  - "Remove pre-installed apps…" = `apps.remove_all_script()`: every installed OPTIONAL app in one interactive `sudo dnf remove` + a flatpak uninstall each, each recorded in skip-packages only once gone.
  - Everything else protected = packages/*.txt read from chezmoi's source (`~/.local/share/chezmoi/packages`, the whole repo) ∪ install.sh's checkout + BUILT rpms + LocalSend, packages one of those needs directly (`rpm -e --test`, read-only), fw-*/fw13-* entries, GNOME_NEEDS (gnome-software, nautilus, control-center, ptyxis, default viewers).
  - Updates from `system.package_upgrades()` (shared with `package_updates()`) + `flatpak remote-ls --updates` (bg, network).
  - pages/apps.py: Uninstall… = fw-term `sudo dnf remove <pkg>` / `flatpak uninstall --user|--system <id>` (never -y), Update all… = fw-updates apply (also `flatpak update --system` when system apps exist), list re-read when Settings regains focus. `python3 -m fw13.apps test` self-check.
- **theme**:
  - Font: store `font`, one monospace family from `fc-list :spacing=mono` (`theme.fonts()`), Settings → Appearance; written into the generated files (waybar.css, fuzzel.ini [main], mako, hyprlock `$fw_font`, kitty.conf, ghostty) and ui_theme/ui_display, so base configs hold no font except kitty/ghostty defaults. `ensure_files` also rewrites a generated file of ours that lacks a line in `theme.REQUIRED`.
  - Palette: matugen from the wallpaper (store `theme.pick`: `colourful` = `--prefer saturation`, `0`–`3` = `--source-color-index`; Appearance → Colour from + candidate swatches from `--show-source-colors`, `wallpaper.candidates()` cached) or TOKYO_NIGHT → generated files in `~/.config/fw13/theme/` + live reload.
  - GTK: "fw13" theme in `~/.local/share/themes` = adw-gtk3[-dark] + gtk3/gtk4.css, set via GSettings only inside Hyprland, `python3 -m fw13.theme session-start|session-end` from fw-theme-session.service. Qt: qt6ct via uwsm/env-hyprland.
- **wallpaper**: library `~/Pictures/Wallpapers`, thumbnails `~/.cache/fw13/thumbs`, effects; renders desktop.jpg/lock.jpg from the untouched original, palette from a small copy of it; hyprpaper restart = `pkill -x` + uwsm app.
- **setup**: My Framework page (id `fw13`, `fw-settings fw13`) backend: chezmoi.toml `[data.chromium|restic|ollama]` rewritten 0600 under a lock + `chezmoi apply --exclude=scripts <targets>`; files removed only when unchanged from what chezmoi wrote; restic via env= only, timer state in store `restic_timer_off` honoured by run_onchange_after_restic-enable; shell via AccountsService SetShell. Also owns optional `[data.restic_creds]` (S3 keys only; AWS_* rendered only for s3:; restic-backup.service is a template adding `-o sftp.args=-oBatchMode=yes` for sftp:). `fingerprints`, `login_screen`.
- **defaultapps**: each Hyprland login + chezmoi run_onchange: GNOME apps (except SHOW_IDS: GNOME Software, user decision) and other-desktop-only entries hidden via NoDisplay copies in `~/.local/share/fw13/hyprland/applications` (our own fw-calc/fw-emoji entries there carry no marker and are left alone), on XDG_DATA_DIRS for Hyprland only (uwsm/env-hyprland; fuzzel ignores NotShowIn/OnlyShowIn); defaults in `~/.config/hyprland-mimeapps.list`: Thunar, Chromium, GNOME viewers; types the user set in mimeapps.list are left out.
- **nightlight**: hyprsunset on/switch + schedule: store `nightlight_schedule` off/sun/custom, `nightlight_from`/`nightlight_to`; Settings → Display → Schedule. `python3 -m fw13.nightlight tick` from fw-nightlight.timer every 5 min acts only at a change-over (store `nightlight_applied` {session, on}), so SUPER+N wins until the next one; a new Hyprland session applies it once; during Zen the change-over goes into `profile_saved`; sun = `weather.sun_today()` (sunrise/sunset in the same forecast request), 19:00/06:30 without a city or offline. `python3 -m fw13.nightlight test` self-check.
- **weather**: Open-Meteo via urllib: geocoding-api once per city → store `weather_place`, forecast cached 30 min in `~/.cache/fw13/weather.json`, stale = last value dimmed; store `weather_city`/`weather_units`; Settings → System → Weather.
- **timezone**: automatic time zone, store `timezone_auto`, off by default; Settings → System → Date & time switch. User service fw-timezone (Hyprland only via ExecCondition; `python3 -m fw13.timezone watch`) checks 30 s after start, 15 s after NetworkManager StateChanged → 70 and every 6 h: GeoClue2 client (CreateClient, DesktopId fw13-timezone, accuracy CITY, LocationUpdated, 30 s timeout) → Open-Meteo forecast timezone=auto → zone under /usr/share/zoneinfo → timedate1 SetTimezone(interactive=false) + notify "Time zone changed to X"; polkit asking for a password → notify only. `check` = read-only dry run, `test` self-check.
- **agents** (coding agent): store `coding_agent` opencode|pi (default opencode) → the >_ panel's Open, Jarvis' Open button, fallback and Continue in terminal via `run_argv()`/`session_argv()` (`python3 -m fw13.agents session TARGET [PROMPT]` = NUL-separated argv for fw-jarvis). Servers `~/.config/fw-opencode/servers` + state.json (active, model, known per server) → `generate()` writes OpenCode's opencode.json (OPENCODE_CONFIG) and Pi's `~/.pi/agent/models.json` (providers `ollama-<name>`, api openai-completions, baseUrl `<url>/v1`, dummy apiKey `ollama`, Cloud `$OLLAMA_API_KEY`) + settings.json defaultProvider/defaultModel, merged: the user's other keys/providers kept, an invalid file left alone. `check_server()`: name `[a-z0-9-]`, URL http(s)://host[:port]; laptop can't be removed. `python3 -m fw13.agents test`.
- **ollama**: localhost:11434 `/api/tags`, `/api/ps` (size_vram/size → "loaded on the GPU"), `/api/delete` for Remove; Download… = `ollama pull <name>` in fw-term, name checked by NAME_RE; the 890M runs models on ROCm with no override (49/49 layers offloaded for qwen3:30b-a3b). `python3 -m fw13.ollama` self-check.
- **jarvis**: store `jarvis_model`/`jarvis_effort` → `jarvis.claude_args()` = `--model`/`--effort` for the panel's `claude` runs, Continue in terminal and `fw-jarvis` via `python3 -m fw13.jarvis`. `snapshot()` (+ memory helpers and `sessions()`, see fw-jarvis-panel) = ≤ 15 lines of battery/network/VPN/failed units/df/updates.json/load/top comm by CPU and RSS/last journal errors (lines with psk/password/secret/token dropped, no argv), taken in the background when the panel opens (retaken if older than 60 s) and appended to the first question's system prompt (OpenCode: the prompt). `python3 -m fw13.jarvis test` self-check (< 1 s, no secret words).
- **speakers**: see fw-speakers.

### Settings pages (lib/fw13/pages, list in pages/__init__.py PAGES)

- **Search** (pages/common.py + pages/search.py): `Page.heading()`/`row()` record (section, text, hint, widget) in `page.index` (cleared by `clear()`, async re-renders re-record, `Page.on_index` re-runs the results), so new rows are indexed automatically — only rows built with `add_widget()` are not (a sub-block sets `self.section = "Section › Sub"` + `_indexed()` its label, e.g. Power → Screen & sleep › Plugged in / On battery, so (section, text) stays unique). The first search builds the unopened pages one per idle call (~1 s total, read-only, same as opening them; a page whose build raises is skipped with a traceback on stderr). `hits()` = all words, case-insensitive, over page title/id + section + text + hint + a short SYNONYMS list for words no label has; results "Page › Section › Row" in the page area; click/Enter opens the page, scrolls to the row and adds ui_theme's `.found` for 1.6 s (debounced 150 ms after the page's last index change for 3 s, so System/Security's background re-render after refresh() is revealed again). Self-check skips 'fan' without framework_tool: `PYTHONPATH=~/.local/lib python3 -m fw13.pages.search test`.
- **sound**: devices, per-app volume = `sound.apps()` with wpctl volume/mute — no pavucontrol (removed, user decision); Speaker sound (fw-speakers); Input noise suppression.
- **security** (before System): fingerprint (`setup.fingerprints`, enrol/remove in fw-term), lock pointer to Power + Lock now, LUKS unlock combo + Secure Boot from `health.root_facts()` (no password to open), Citadel via `system.citadel_status()` (shared with `warp.citadel_note`), SSH keys, login screen (`setup.login_screen`). No VPN section: every VPN setting is in Network; strongSwan rows say when the toggle needs no password.
  - SSH: gcr-ssh-agent.socket started (not enabled) and `SSH_AUTH_SOCK=$XDG_RUNTIME_DIR/gcr/ssh` exported by uwsm/env-hyprland when gcr is installed and SSH_AUTH_SOCK is unset, so other desktops are untouched; status via `ssh-add -l` on the session's SSH_AUTH_SOCK (the user's own agent if set, else gcr's; Add to agent uses the same); `~/.ssh/*.pub` + `ssh-keygen -lf`; Add to agent = ssh-add in fw-term, Copy = wl-copy, Create key… = `ssh-keygen -t ed25519` in fw-term.
- **framework** = Hardware sections at the top of My Framework (pages/fw13.py): fan mode/fp LED via `pkexec framework_tool`, fan rpm from cros_ec hwmon, keyboard backlight via brightnessctl, read-only reports in fw-term with sudo; no flashing/remap/EC reboot.
- **agent** (after Jarvis): Settings → Coding agent over fw13.agents: OpenCode/Pi radio (versions in bg, not installed = greyed) → store `coding_agent`; server list (`probe_all` in bg, which also refreshes known models + regenerates both configs), Add server (`check_server`) / Remove (not laptop/Cloud), Server + Model combos → `agents.use()`; pointer rows to Jarvis (Local models) and My Framework (Ollama Cloud key).
- **jarvis**: Settings → Jarvis: model/effort, Memory list/remove + Open file, offline fallback switch, Local models (Ollama) over fw13.ollama.
- **vpn_edit**: strongSwan form (fw-vpn-config).
- **apps**: see apps above.

### Theming

- Generated in `~/.config/fw13/theme/`: hypr.lua hyprlock.conf waybar.css fuzzel.ini mako kitty.conf (create_ seeds) + ghostty gtk3.css gtk4.css qt6ct-colors.conf fcitx5-theme.conf framework-logo.svg (written by `theme.init`/`ensure_files`) + desktop.jpg lock.jpg (fw13.wallpaper).
- Session-only app theming (`session_start`/`session_end`, Hyprland only):
  - fcitx5 Theme=fw13 in classicui.conf (old values restored).
  - Chromium `extensions.theme.system_theme=1` once per profile when unset and Chromium isn't running; opt-in Appearance switch `chromium_gtk_force` also replaces a theme the user chose and writes `~/.config/fw13/theme/chromium-policy.json` = BrowserThemeColor from the accent, re-read live via SIGHUP (install.sh links the managed policy to it).
  - VS Code `workbench.colorCustomizations` (on by default, Appearance switch, strict JSON only, removed at logout).
  - TUIs follow the terminal's 16 colours (kitty.conf / ghostty in `~/.config/fw13/theme/`; Ghostty reloads on SIGUSR2) (btop color_theme TTY via create_btop.conf, FZF_DEFAULT_OPTS/BAT_THEME in uwsm/env-hyprland).
- Colour rule: colour literals live only in theme.py TOKYO_NIGHT, the create_ seeds of `~/.config/fw13/theme/` and hypr/theme.lua's documented fallback (used only if the generated hypr.lua is missing or broken); base configs (hypr, hyprlock, waybar, fuzzel, mako, kitty, ghostty, ui_*) include the generated files, never hard-code hex.

### Scripts (dot_local/bin/executable_fw-\*)

- **capture**: Print region / Shift+Print screen; Alt+Shift+4 snip / Alt+Shift+3 window → swappy (`dot_config/swappy/config`); window picker = `slurp -r` over the clients on every monitor's visible workspaces.
- **record**, **notify** (gdbus), **system-menu**, **control-center**, **power-panel**, **nightlight**.
- **display-panel**: layer-shell popup around fw13.ui_display.
- **idle**: hypridle actions guarded by power source; suspend → suspend-then-hibernate when fw-hibernate-setup's sleep drop-in exists.
- **clipboard**: SUPER+V: cliphist pick → paste via `fw-clip-key paste` into the window captured before fuzzel opened.
- **clip-key** `copy|cut|paste`: SUPER+C copy / SUPER+X cut, paste for fw-clipboard and fw-emoji: `hl.dsp.send_shortcut` to the focused window (or `FW_CLIP_WINDOW`), Ctrl+Shift+C/V in terminals (by program), no cut there; key must be lowercase; VS Code moved to SUPER+SHIFT+C.
- **settings**: Settings app: Gtk.Application, single instance, `fw-settings [page] [--toggle]`; pages in lib/fw13/pages (see Settings pages).
- **workspaces**: Python daemon: per-screen ranges eDP 1–9, others 11–19…; SUPER+N goes through it; login layout; bar dots custom/ws1–9: the first store `workspaces_shown` (1–9, default 5, Settings → Appearance → Workspaces) persistent and always shown, higher ones only while used; `fw-workspaces apply` re-binds after a change.
- **jarvis** / **jarvis-panel**:
  - SUPER+A → jarvis-panel: layer-shell Ask box, inline answers via `claude -p --output-format stream-json`, read-only tools + `--add-dir /` with secret paths denied.
  - Changes only as ```` ```jarvis-action``` ```` JSON cards (What/Why/How, Run/Skip) that the panel runs with `bash -c` on Run (root cards via `pkexec`, `sudo` stripped: polkit asks for password/fingerprint) and feeds back via `--resume`; a card with `settings` = a page id from pages/__init__.py instead of `command` is an Open Settings → page button (unknown ids dropped). `fw-jarvis-panel test` self-check.
  - Each answer may end with a ```` ```jarvis-followups``` ```` JSON list shown as buttons; Enter while an answer is open asks a follow-up in the same conversation ("New question" starts afresh); an empty panel shows STARTERS as chips (each a fresh question).
  - `--image PATH` (SUPER+ALT+A → `fw-jarvis shot`: slurp + grim into `$XDG_RUNTIME_DIR/fw-jarvis-shot.png`, 0600) and `--text-from-selection` (SUPER+CTRL+A → `fw-jarvis selection`: wl-paste --primary, else the clipboard, read before the panel opens) add the screenshot path (Claude Reads it) or the quoted text to the first question.
  - Memory = `~/jarvis/MEMORY.md` (never a chezmoi target: created empty by the panel/fw-jarvis, imported by dotfiles/jarvis/CLAUDE.md `@MEMORY.md`); a ```` ```jarvis-remember``` ```` {"note"} block → Remember Save/Skip row → `jarvis.remember()` appends `- YYYY-MM-DD note` (check_note: one line, ≤ 300 chars, no fences); Settings → Jarvis → Memory lists/removes (`jarvis.forget()` rewrites the file) + Open file.
  - History button = fuzzel (`--layer overlay`) over `jarvis.sessions()` (last 20 `~/.claude/projects/-home-<user>-jarvis/*.jsonl` by mtime, first real user prompt) → resumes that session id (Claude only).
  - Offline fallback (store `jarvis_fallback`, default on, Settings → Jarvis switch naming the server): a fresh Claude question when `jarvis.online()` is false (`nmcli -t networking connectivity` ≠ full; FW_JARVIS_CONNECTIVITY overrides for tests), or a Claude run that ends with no text and a connection/auth error (UNREACHABLE_RE), goes to `jarvis.fallback(agents)` = the first coding-agent target (`ollama-<server>/<model>`) whose server (`agents.server_url`) answers GET /api/tags within 1.5 s, run via `agents.run_argv` (`opencode run` / `pi -p --tools read,grep,find,ls`; follow-ups `--continue` / `-c`) with the status "Claude unreachable: answering with …"; none → "…, and no Ollama server reachable"; no model download.
  - Continue = `claude --resume <session>`; `fw-jarvis repo|crash|open|diagnose|menu` for the terminal sessions; working folder `~/jarvis` (created if missing; all agent runs and "Continue in terminal" start there) with the briefing dotfiles/jarvis/AGENTS.md incl. the What/Why/How rule for root actions.
  - "Ask Jarvis" notification action = `notify.launch(fw-jarvis-panel --ask …)` in fw-battery-warn 20/10 % (`notify.on_action` in its main loop, nid → argv), fw-updates' package notice and fw-vpn's failed connect (`fw-vpn --failed <name> <error>` spawned: send + wait, so the menu returns); fw-health keeps Diagnose; each sender's `test` asserts its argv.
- **speakers** (Settings → Sound → Speaker sound = lib/fw13/speakers.py): on/off = EasyEffects global bypass; Sound = Framework (`fw13-speakers`) / Clear voice (`fw13-clear`) / Custom (`fw13-custom`, rebuilt from fw13-speakers + 4 filters Bass 150 Hz low-shelf, Warmth 300 Hz, Voice 3 kHz, Air 8 kHz high-shelf ±6 dB and Level on the convolver gain; store `speaker_preset`/`speaker_eq`; debounced 350 ms, autoload file + `easyeffects -l`), so EasyEffects' own (unthemed, KDE) window is never needed; `python3 -m fw13.speakers test`.
  - Hyprland autostart fw-speakers: writes `~/.local/share/easyeffects/autoload/output/<…__Speaker__sink>:[Out] Speaker.json` → preset `fw13-speakers` (user decision; convolver output-gain 15.5 dB instead of Framework's 6: the IR cuts 500 Hz–2 kHz by 5–12 dB, so voices measured ~9 dB quieter than bypass; now within 1 dB (sink-monitor test, tones at -20 dBFS)) = Framework's official FW13 EasyEffects preset + IR from github.com/FrameworkComputer/linux-docs (GPL-3.0, shipped in dot_local/share/easyeffects); sets EasyEffects' output fallback preset `flat` (empty) for other outputs (unverified) and `[Window] showTrayIcon=false` (user decision), then `easyeffects --service-mode`.
  - Also shipped: `fw13-clear` = Framework's preset without loudness/bass: high-pass 120 Hz, -3 dB at 300 Hz, +3 dB at 3 kHz, +1.5 dB shelf at 8 kHz, convolver at 0 dB, no multiband compressor, limiter without gain boost.
  - Packages easyeffects + lsp-plugins-lv2 + lv2-calf-plugins (user decision).
- **crash-watch**: user service; journal coredump/unit-failed → notify → Diagnose.
- **battery-warn**: user service fw-battery-warn, Hyprland only via ExecCondition: UPower PropertiesChanged + 60 s check → once per discharge at each level of store `battery_warn` (`power.warn_levels()`, Settings → Power → On battery → Warn at: 20,10,5 / 10,5 / off); 20 % normal with TimeToEmpty, 10/5 % critical, mako `[app-name=fw-battery urgency=critical]` shown under DND; 5 % names UPower's critical action; reset on AC. `fw-battery-warn test` self-check.
- **usb**: user service fw-usb, Hyprland only via ExecCondition: UDisks2 InterfacesAdded → a Filesystem on a non-HintSystem block whose drive is Removable/Ejectable/usb/sdio (Drive "/" = loop/zram/LUKS cleartext skipped; encrypted sticks skipped) → Filesystem.Mount unless already mounted → notify 'USB drive "LABEL" (size)' Open (thunar via notify.launch) / Eject (Unmount every mounted fs of the drive, Drive.PowerOff → "Safe to unplug"); nothing auto-mounts in Hyprland otherwise (no thunar-volman). `fw-usb check` lists current matches, `fw-usb test` self-check.
- **opencode**: the >_ panel: Ollama server list + active server/model over lib/fw13/agents.py; opens the chosen coding agent.
- **claude-limits**: statusLine rate_limits → bar; settings via `dot_claude/modify_settings.json`.
- **menu-anchor**: bar menus open below the clicked icon via `FW_BAR=1`.
- **term**: `fw-term [--class C] [--hold] [--dir D] [-e cmd…]` → lib/fw13/terminal.py: kitty (default) or Ghostty from store `terminal`, Settings → My Framework → Terminal; every terminal launch goes through it, Python via `fw-term` too; classes must be GTK app ids for Ghostty: `fw13.jarvis` (floats), `fw13.btop`.
- **wallpaper**: SUPER+W: layer-shell picker strip, pidfile toggle; `fw-wallpaper set|add|effects` CLI.
- **osd**: volume/mic/brightness popup: mako progress hint, id reused via `$XDG_RUNTIME_DIR/fw-osd.id`, `[app-name=fw-osd]` shown under DND.
- **notifications**: bar bell custom/notifications, signal 12 from mako on-notify; fuzzel history/DND/dismiss all; unread via store `notif_seen` {mako pid:starttime, id}.
- **profile**: bar custom/profile left of the clock, signal 14: fuzzel Normal/Focus/Zen. Focus = mako DND (bell's mode; bell DND off → leaves the profile, fw-notifications sends 14 too); Zen = DND + gaps_in/gaps_out/border_size/rounding 0 via `hyprctl eval` (`hyprsettings.call`) + hyprsunset; values before Zen + night-light state in store `profile_saved`, put back on leaving; store `profile` counts only for `profile_session` = HYPRLAND_INSTANCE_SIGNATURE, so a new login is Normal; `hyprctl reload` re-applies settings.lua gaps during Zen.
- **caffeine**: bar custom/caffeine left of the profile, signal 16, SUPER+SHIFT+K: keep awake = `systemd-inhibit --what=idle:sleep --who=fw-caffeine sleep infinity`, pid in `$XDG_RUNTIME_DIR/fw-caffeine.pid` (mtime = since, /proc cmdline checked before kill); hypridle skips listeners while a logind idle lock is held (ignore_systemd_inhibit default); `--bar` (interval 60) turns it off with a notification on battery below 20 %. `fw-caffeine test` self-check.
- **weather**: bar custom/weather right of the clock, signal 15, interval 1800: `fw-weather --bar` → lib/fw13/weather.py; city falls back to the time zone's (`weather.tz_city()`), `{"text": ""}` hides it without one; click = `fw-settings system`.
- **active-app**: bar custom/app right of the gear: long-running, Hyprland .socket2 activewindow events → launcher Name via `apps.launcher_entries()` (StartupWMClass / desktop id / last dotted part), else the tidied class; hidden on an empty workspace; tooltip = title. `fw-active-app test`.
- **launcher**: SUPER+Space + the bar gear: fuzzel on the focused screen, `--lines` = the number of launcher apps (desktop ids over the XDG data dirs, `[Desktop Entry] Type=Application`, not NoDisplay/Hidden), at most ~80 % of its height (row heights measured per scale).
- **keys**: SUPER+K or SUPER+/: cheat sheet = `hyprctl -j binds` descriptions in fuzzel, numbered runs folded; new binds need a description.
- **calc**: SUPER+=: fuzzel loop over `qalc -t`, argv only; ast fallback.
- **emoji**: SUPER+.: GTK3 emoji data, paste like clipboard.
- **autobrightness**: user service, off by default; manual change pauses until wake/login; hypridle hooks pause/resume.
- **hwcheck**: `--first-login` once, store `hwcheck_shown`.
- **health**: fw-health.timer 15 min after login then daily; reports in `~/.local/state/fw13/health/`, keep 14; notify only on changed findings or weekly; `--timer` only under systemd.
- **updates**: fw-updates.timer 20 min after login then daily.
  - `--check` = `system.package_updates()` = `dnf5 -q --cacheonly check-upgrade` (no root/network) + `system.firmware_updates()` (fwupdmgr get-updates, fwupd-refresh.timer's metadata); notify Update now/Later when either count changed or daily (firmware only → Open Settings); state `~/.local/state/fw13/updates.json`. `fw-updates test` self-check.
  - `apply` in fw-term: `sudo timeshift --create` (fw-timeshift-setup if no /etc/timeshift/timeshift.json), failed snapshot stops unless `y`, then `dnf upgrade --refresh`, `flatpak update --user` (+ `--system` when system apps exist), needs-restarting, then points to Settings → System → Firmware updates if fwupd has any. Settings → System → Software updates also shows the firmware count.
- **vpn** (Python): bar shield custom/vpn, signal 13, over lib/fw13/vpn.py = every VPN: NetworkManager's (nmcli, kind from vpn.service-type) + strongSwan's `/etc/strongswan/swanctl/conf.d/<name>.conf`; hidden without any. Click = fuzzel list (● connected) → connect/disconnect, last row + right-click = Settings → Network; NM VPN without saved secrets → `nmcli --ask` in fw-term. strongSwan state from route table 220 (no root) + the names we brought up in `$XDG_RUNTIME_DIR/fw-vpn-swan`; strongSwan toggle = `pkexec /usr/local/bin/fw-vpn-ctl up|down <name>` (root wrapper: name must be an existing conf.d file, no other args; action `system/usr/share/polkit-1/actions/org.fw13.vpn.policy` with exec.path, rule `system/etc/polkit-1/rules.d/50-fw13-vpn.rules`: wheel + active local session → no password); falls back to pkexec swanctl if the wrapper is missing.
- **warp-panel**: bar cloud icon: layer-shell WARP panel over lib/fw13/warp.py = `warp-cli --accept-tos -j`, only after the user accepted Cloudflare's ToS in the panel (store `warp_tos`); `--bar` JSON, signal 11; `--toggle` on right-click; Zero Trust join via `registration new <team>` + browser; "Consumer only" settings greyed/hidden for Zero Trust; Cloudflare's own warp-taskbar hidden in Hyprland via `dot_config/autostart` NotShowIn.

### Waybar signals

11 warp-panel, 12 notifications, 13 vpn, 14 profile, 15 weather, 16 caffeine.

## Docs and CI

- **docs/screenshots/**: README screenshots (bar, Settings Appearance/Power, Jarvis, cheat sheet, lock), taken on the laptop, cropped to our own UI, 256-colour PNG.
- **docs/FIRST-INSTALL.md**: what a fresh Framework install looks like + Stage 7 hardware checklist. CONTRIBUTING.md (dev quick start, roadmap), CODE_OF_CONDUCT.md.
- **.github/workflows/test.yml**: lint (shellcheck + config syntax) → install (`./install.sh --ci` in fedora:44, weekly cron too); no screenshot job (removed, user decision).

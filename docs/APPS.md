# Apps & features

What fw13-hypr gives you once it is installed. Installing, updating and testing are in the [README](../README.md); per-component internals in [ARCHITECTURE.md](ARCHITECTURE.md).

**Contents:** [The bar](#the-bar) · [Keys](#keys) · [Settings](#settings) · [Desktop](#desktop) · [Jarvis & AI](#jarvis--ai) · [Apps](#apps) · [Backups](#backups)

> **Three keys to remember:** **SUPER+Space** opens the launcher, **SUPER+I** opens Settings, **SUPER+/** lists every shortcut.

---

## The bar

A thin bar per screen: launcher, the focused app's name and workspaces on the left · profile, clock and weather in the middle · tray and status on the right. Bar menus open right below the icon you clicked; clicking the same icon again closes them.

| Icon | Click | Right-click / other |
|---|---|---|
| Framework gear | App launcher | |
| Workspace circles | Go to that workspace (one row per screen) | |
| Coffee cup | **Keep awake** on / off | |
| Profile | **Normal**, **Focus** or **Zen** | |
| Clock · weather | Weather opens Settings → System | |
| REMOTE | Shown while remote mode is on (Super+Alt+R leaves) | |
| Syncthing | **Syncthing menu**: status, folders (pick one to open it), devices, turn Syncthing on/off, Rescan all, web UI (icon always shown: dim when up to date or stopped; sync %, problem or paused) | Right-click: Settings → Syncthing |
| Bluetooth | Connected devices (with battery), paired ones to connect | Settings → Bluetooth |
| Wi-Fi | Networks, the connected one first | Settings → Network |
| Shield | **Cloudflare \| VPN** panel | Settings → Network |
| Volume | Volume menu | Middle-click: Settings → Sound |
| Display | **Display panel** | Scroll: brightness |
| ✱ | Claude plan limits (5-hour and weekly %, reset times) | |
| `>_` | Coding agent and Ollama servers | |
| Battery | **Power panel** (tooltip: power draw in watts) | |
| Bell | Notification history, Do not disturb, Dismiss all | Toggles Do not disturb |
| Power | Lock / suspend / log out / reboot / shut down | |

Inside Claude Code the status line shows these limits too, in 6 "Label: value" lines, a thin line between each pair: Model · Effort · Advisor · Thinking · Fast · Style · version / Session · Open (time since it started) · Working (time Claude spent) · Cost · Lines changed / Repo · Branch · Unpushed (Behind only when there is something to pull) · Changed files · Last commit / Context gauge (tokens) · prompt Cache (warm or cold, hits, when it expires) / 5h and 7d gauges with time to reset / Battery · CPU · RAM · Disk free · Syncthing. Click 5h or 7d to open claude.ai's usage page.

<details>
<summary><b>Power panel, display panel and the shield panel</b></summary>

- **Power panel** (battery icon): charge state, time to full or empty, power profile, an 80 % charge limit toggle, battery health and the CPU/power tuning in effect (driver, energy preference, platform profile, panel power saving, tuned profile).
- **Display panel** (display icon): a brightness slider for the laptop screen, and for each connected monitor its position (drag it), refresh rate and scale. **Apply** asks you to keep the change and reverts after 15 seconds otherwise; kept layouts are saved in `~/.config/hypr/displays.conf`, per monitor model. **Auto-brightness** from the light sensor is off by default (here or in Settings → Display); changing brightness yourself pauses it until the next wake or login.
- **Shield panel**, two pages. The shield is accent-coloured when WARP or a VPN is connected and yellow while connecting. Without Cloudflare WARP installed, the panel has only the VPN page.
  - **Cloudflare:** on/off, mode, DNS filter and protocol, exit IP and Cloudflare location, tunnel endpoint, handshake, latency, loss and traffic, account (free, WARP+ key, or **Join organization** for Cloudflare Zero Trust: you sign in in the browser), the split-tunnel include/exclude list, fallback domains, trusted networks and your organization's policy. It asks you to accept Cloudflare's Terms of Service once before talking to WARP. Settings your Zero Trust organization controls are shown but greyed out. Cloudflare's own tray app is hidden in Hyprland (the panel's **Cloudflare app** button starts it). With Citadel enforcing, allow `warp-svc` at its gate the first time.
  - **VPN:** every VPN with **Connect** / **Disconnect**, and **Add or edit…** for Settings → Network. strongSwan connections (a file in `/etc/strongswan/swanctl/conf.d/<name>.conf`, connection and child both named `<name>`, secrets inside, root-only) connect without a password for an admin (wheel) user at the laptop, through the root helper `fw-vpn-ctl` that can only bring that one connection up or down (polkit rule `50-fw13-vpn.rules`). The tooltip lists the networks the tunnel carries.

</details>

**Profiles.** **Focus** turns on Do not disturb; **Zen** also drops gaps, borders and rounding and turns night light on. Leaving Zen puts them back as they were; turning Do not disturb off on the bell leaves Focus/Zen; each login starts in Normal.

**Keep awake** (also SUPER+Shift+K) stops the screen from dimming and locking and the laptop from sleeping until you click it again or log out (closing the lid still suspends). It turns itself off with a notification when the battery drops below 20 %.

**Weather** shows an icon and the temperature for the city set in Settings → System → **Weather** (hidden until you set one; type `Paris, US` to pick between places with the same name). The tooltip shows today and the next two days. Data from [Open-Meteo](https://open-meteo.com) (no account), refreshed every 30 minutes; offline it shows the last value, dimmed. With Citadel enforcing, allow `python3` to reach open-meteo.com the first time.

---

## Keys

Press **SUPER+/** (or SUPER+K) for a searchable cheat sheet; it also lists your own binds in `hypr/local.lua` that have a `description`.

**Apps**

| Key | Action |
|---|---|
| SUPER+Return / Space | Terminal (kitty or Ghostty, Settings → My Framework) / launcher |
| SUPER+B / E / Shift+C | Chromium / Files / VS Code |
| SUPER+A / Alt+A / Ctrl+A | Jarvis / ask about a screen region / ask about the selected text |
| SUPER+Shift+A / T / B | Claude Code / btop / Timeshift |
| SUPER+I | Settings |
| SUPER+V | Clipboard history (the picked item is pasted into the window you were in) |
| SUPER+. / = | Emoji picker (pasted) / calculator (Enter copies the result) |
| SUPER+W | Wallpaper picker |

**Windows**

| Key | Action |
|---|---|
| SUPER+Q / Shift+Q | Close / force quit (kills the app at once, no save prompt) |
| SUPER+F / T / J / P | Fullscreen / float / change split / pseudo-tile |
| SUPER+Arrows (+Shift / +Ctrl) | Focus / move / resize |
| SUPER+S / Shift+S | Scratchpad / send window to scratchpad |
| SUPER+C / X | Copy / cut in the focused window (Ctrl+Shift+C in terminals; no cut there) |

**Workspaces & screens**

| Key | Action |
|---|---|
| SUPER+1..9 (+Shift) | Go to workspace / move window there (each screen has its own 1–9) |
| SUPER+Tab | Previous workspace |
| Ctrl+← / → | Previous / next workspace on this screen (so Ctrl+arrow no longer jumps by word) |
| 3-finger swipe | Switch workspace |
| Super+Alt+R | **Remote mode**: every key, Super included, goes to the window (e.g. Command in a Remote Desktop Manager session to a Mac) until Super+Alt+R again. Turns on by itself while Remote Desktop Manager is focused and off when you click another window |

**Capture**

| Key | Action |
|---|---|
| Print / Shift+Print | Region shot / full shot |
| Alt+Print / SUPER+Print | Start or stop recording / color picker |
| Alt+Shift+4 / 3 | Snip a region / click a window → annotate in swappy (Ctrl+C copies, Ctrl+S saves to ~/Pictures/Screenshots) |

**System**

| Key | Action |
|---|---|
| SUPER+L / Escape | Lock / power menu |
| SUPER+N | Night light |
| SUPER+Shift+K | Keep awake on / off |
| SUPER+, (+Shift) | Dismiss notification (all) |
| Ctrl+Space | Switch to/from Khmer (fcitx5, the standard Khmer NiDA layout, as on Windows, macOS and phones) |

Volume, mic and brightness keys show a small bar at the bottom of the screen (also during Do not disturb).

---

## Settings

**SUPER+I** or "Settings" in the launcher opens the **Settings** app, in the same flat style, as a normal tiled window. The search box (**Ctrl+F**) finds any setting, not just page names ("hibernate", "night light", "warn at", "ssh", "wifi"): matches show as *Page › Section › Setting*, and clicking one (or Enter for the first) opens the page at that setting and highlights it.

Appearance and Input are saved to `~/.config/hypr/settings.lua`, checked by Hyprland before it's used; your `local.lua` still wins over it. GNOME's own settings stay in the GNOME session.

| Page | What's there |
|---|---|
| [Network](#network) | Wi-Fi, Ethernet, every VPN (add, edit, delete) |
| [Bluetooth](#bluetooth) | Devices, pairing |
| [Sound](#sound) | Devices, per-app volume, speaker sound, noise suppression |
| [Display](#display) | Brightness, screens, scale, night light schedule |
| [Power](#power) | Profiles, charge limit, timeouts, battery warnings, hibernate |
| [Appearance](#appearance--input) | Wallpaper, theme, font, terminal look, gaps, workspaces |
| [Input](#appearance--input) | Touchpad, keyboard, Khmer |
| [Security](#security) | Fingerprint, disk unlock, Secure Boot, SSH keys |
| [System](#system) | Date and time, updates, weather city |
| [Coding agent](#coding-agent--jarvis) | OpenCode or Pi, Ollama servers |
| [Jarvis](#coding-agent--jarvis) | Model, fallback, local models, memory |
| [Apps](#apps-page) | Every app, updates, uninstall |
| [Syncthing](#syncthing) | Devices, folders, requests, conflicts |
| [My Framework](#my-framework) | Hardware, backups, keys, login shell |

### Network

Wi-Fi (connect, forget, hidden networks; passwords never appear in a command line), Ethernet, and every VPN in one list: NetworkManager's OpenVPN, OpenConnect (FortiGate SSL / AnyConnect / GlobalProtect), Cisco IPsec and WireGuard, plus strongSwan IKEv2. Each VPN has Connect / Disconnect, **Edit…** and **Delete** (after a Yes/No question).

<details>
<summary>Adding and editing VPNs</summary>

- **IKEv2 (FortiGate / strongSwan)…** opens a form: name, server, gateway ID, your ID, username, password, pre-shared key, networks. It asks for your password, keeps the previous file as `<name>.conf.bak`, never shows the password and key, and leaves them unchanged when left empty.
- **OpenVPN file (.ovpn)…** imports the profile as is, with its certificates, then asks once for the username, password and key passphrase it needs and saves them in the VPN's root-only profile, so connecting doesn't ask again (**Skip** asks on each connect instead). **Save password…** saves or changes them later.
- **WireGuard file…** and **OpenConnect, Cisco… or another file** go through nm-connection-editor, as does **Edit…** for NetworkManager VPNs.

</details>

### Bluetooth

On/off, your devices (connect, forget, battery), scan and pair. When a device shows a code to confirm, a notification asks **Pair** / **Reject**; a device that needs a PIN typed here gets a prompt.

### Sound

Output and input devices, volume, per-app volume (every app playing sound, with mute), **Speaker sound** (see [Apps](#apps)), and **Noise suppression** for the microphone. Noise suppression is off by default: on adds a *Noise-cancelled microphone* from PipeWire's WebRTC echo canceller and makes it the default; off removes it and the previous microphone is the default again (switching restarts the audio for a moment).

### Display

Brightness, arrange screens, refresh rate, scale, and night light with a **Schedule**: Off, Sunset to sunrise for the weather city (19:00 to 06:30 when offline or without one), or Custom times. It checks every 5 minutes and changes only at the switch-over times, so SUPER+N wins until the next one; Zen keeps it on.

### Power

| Setting | What it does |
|---|---|
| Profile | Follows the charger (balanced on AC, power saver on battery); each profile has a one-line description |
| 80 % charge limit | Set in Framework's own battery controller too (at boot, on plug-in and when you flip the switch) |
| Screen & sleep | Timeouts, separately for plugged in and on battery |
| Warn at | 20, 10 and 5 %; 10 and 5 %; or off. 20 % is a normal notification with the time left; 10 and 5 % stay up until dismissed and show even in Focus/Zen; 5 % says what the laptop does at 2 %. Warnings reset when you plug in |
| Sleep report | After 30 min or more asleep on battery: the battery used, and per hour. When it drained fast and deep sleep was short, it says something kept the laptop awake |
| Screen at 60 Hz | On battery (on by default, only with a faster built-in screen): the 120 Hz panel drops to 60 Hz when unplugged |
| Hibernate | Opt-in, see below |

<details>
<summary>Hibernate</summary>

*When the battery is very low* shows whether hibernate is ready (logind CanHibernate). **Set up hibernate…** opens a terminal running `sudo fw-hibernate-setup`, which explains and asks before each step: a btrfs subvolume `swap` mounted at `/swap`, a RAM-sized swapfile (after zram, SELinux-labelled, left out of Timeshift), and dracut's resume module (systemd finds the swapfile through an EFI variable, so no kernel argument). It refuses with kernel lockdown (Secure Boot), on non-btrfs or without the space; `--dry-run` shows the plan, `undo` reverses it.

Once ready, **Then hibernate after** 1 h / 3 h / never makes idle sleep and the lid suspend-then-hibernate on battery (plugged in, they only suspend; a laptop suspended on AC starts the countdown once unplugged). At the critical battery level the laptop suspends and then hibernates, and the power menu gets **Hibernate**.

</details>

### Appearance & Input

**Appearance:** wallpaper (effect: none, blur, dim, grey, blur + dim), theme (colors from the wallpaper, dark or light, or Tokyo Night), **Colour from** (the most colourful part (default), most of the image, or one of its 4 main colours shown as swatches), font (one fixed-width font for the bar, launcher, notifications, lock screen, panels and terminals; JetBrains Mono by default), **Terminal** (font size, background opacity, padding, line spacing, cursor shape (block, beam, underline) and blink, bold text and ligatures, for kitty and Ghostty; open windows change at once), gaps, borders, and how many workspaces each bar shows (1–9; higher ones appear while in use). Details in [Look & theme](#look--theme).

**Input:** touchpad, key repeat, keyboard layouts, input methods (Khmer).

### Security

| Section | What's there |
|---|---|
| Fingerprint | Enrolled count, enrol, remove all |
| Lock screen | Lock now; timeouts are in Power |
| Disk encryption | How the LUKS disk unlocks at boot: **Password only**, **TPM + PIN** or **TPM automatic** |
| Secure Boot | On/off (changed in the BIOS, F2) |
| Citadel | The firewall's state, Open Citadel |
| SSH keys | Agent status, your keys, Add to agent, Copy public key, Create key… |
| Login screen | |

Root-only facts come from the hourly `fw-health-root`, so opening the page never asks for a password.

<details>
<summary>Disk unlock and SSH keys in detail</summary>

- **Disk unlock:** the choice opens a terminal running `sudo fw-disk-unlock`, which asks for your disk passphrase, enrols the TPM (PCR 7), updates `/etc/crypttab` (or the kernel line), adds dracut's TPM module and rebuilds the initramfs of every installed kernel. **TPM automatic** is offered only with Secure Boot on, and only guards against the disk leaving the laptop, so TPM + PIN is the safer choice. The passphrase is never removed and stays the fallback.
- **SSH keys:** whether the SSH agent runs (Fedora's `gcr-ssh-agent`, or your own when `SSH_AUTH_SOCK` was already set) and how many keys it holds; each `~/.ssh/*.pub` with its fingerprint. **Add to agent** runs `ssh-add` in a terminal that asks the passphrase; without a key, **Create key…** runs `ssh-keygen -t ed25519` in a terminal.

</details>

### System

Date, time zone (or **Set time zone automatically**), automatic time, device name, weather city and °C/°F for the bar, software updates (count from dnf's cache, **Snapshot + update…**), firmware updates (fwupd), about this computer.

### Coding agent & Jarvis

**Coding agent:** OpenCode or **Pi** (with their versions) for the `>_` icon, Jarvis's Open button and its Ollama fallback; your Ollama servers with online status and model count (**Add server**, **Remove**); the default server and model for both agents.

**Jarvis:** the Claude **model** (an alias such as opus/sonnet, or a full name) and **effort** (low to max; empty = Claude Code's default), the Ollama fallback when Claude is unreachable, an optional **Laya decision model** (your self-hosted classifier: URL, token kept in GNOME Keyring, Test) that puts a safe / risky / destructive badge on Jarvis's action cards (advice only: nothing runs without Run), **Local models (Ollama)** (the laptop's models with size and whether they're loaded on the GPU, **Download…**, **Remove**; the Radeon 890M runs them through ROCm) and Jarvis's **memory** notes.

### Apps page

Every app in the launcher plus Flatpak apps, with where it came from (a Fedora/vendor package, also when its launcher entry was customised in `~/.local/share/applications`; Flatpak; Steam/Lutris; or *Installed by hand*: no package owns it, e.g. an AppImage you added) and **Update available → version**; apps with updates come first. Apps the installer builds itself (Claude Desktop, Telegram, Ghostty, DBeaver, Obsidian, plus framework_tool and scrcpy) are checked against their official releases too; dnf can't update them, so the row says whether re-running the installer updates it or the new release isn't in fw13-hypr yet. **Check now**, **Update all…** (the same snapshot-first update as System) and **Uninstall…**, which opens a terminal running `sudo dnf remove <package>` or `flatpak uninstall <app>`: both list what goes and ask first.

<details>
<summary>Pre-installed apps</summary>

**Startup apps** lists what starts when you log in to Hyprland (the XDG autostart entries uwsm runs), each with a switch; GNOME or KDE on the same account keep their own list. Changes apply at the next login. **Reopen apps left open** brings back, at login, the apps you had open when you shut down or logged out, each on its workspace (terminals in the folder they were in; Chromium, VS Code and Obsidian reopen their own windows and tabs); with it off, a login opens no apps. Tray apps the bar replaces (network, Bluetooth, Cloudflare) stay off, and the location agent that automatic time zone needs stays on.

**Remove pre-installed apps… → Remove all…** takes out every optional app this desktop installed in one go (one list to confirm). The optional apps (Steam, Lutris, Telegram, Chromium, VS Code, Remote Desktop Manager, Ghostty, DBeaver, Citadel, Cloudflare WARP, Easy Effects, LocalSend, Claude Desktop, Obsidian) can be uninstalled one by one too, and re-running `install.sh` then skips them (`~/.config/fw13/skip-packages`). **Removed apps** lists them with **Reinstall on next installer run**, which needs the app's group selected. Removing Chromium leaves links and SUPER+B without their browser. The rest of the desktop (and packages it needs), our own tools and GNOME's core apps (Files, Software, Settings, Ptyxis, the default viewers) are marked and have no Uninstall button.

</details>

### Syncthing

Shown when Syncthing is installed. On/off for the service (also at login), version, this device's ID with **Copy**, your devices (connected direct or via relay, or last seen) and folders (path, idle / syncing NN % / error / paused, shared with how many devices), **Open full UI** and **Rescan all**; refreshed every 3 seconds while open.

| You want to… | How |
|---|---|
| Add a device | **Add device…**, paste the other device's ID |
| Add a folder | **Add folder…**, pick it and who to share with |
| Manage | Devices: **Pause/Resume**, **Remove**. Folders: **Open**, **Share…**, **Pause/Resume**, **Remove** (files stay) |
| Answer a request | A notification offers **Accept** / **Ignore** (a folder asks where to put it, `~/Sync/<name>` by default); open ones are under **Requests** |
| Fix problems | **Sync errors** lists failing files; **Conflicts** lists `*.sync-conflict-*` copies with **Open**, **Keep this copy**, **Delete** (both to the Trash, so undoable); a notification tells you when either appears |
| Save battery or data | **Pause on battery** and **Pause on metered connections** (off by default) pause every device and resume only the ones they paused |

The full UI is still there for versioning, ignore patterns and bandwidth.

### My Framework

**Hardware:** a **Touch screen** switch (only on touch models; the touchpad keeps working), touchpad **haptic feedback** strength (Off to 100 %) and **click force** (light, medium, firm; haptic touchpad only), live fan speed and fan mode (automatic or a fixed 25–100 %), keyboard backlight, fingerprint-reader LED brightness, the power-off delay, and reports from `framework_tool` (firmware versions, battery and charger, temperatures, privacy switches, USB-C ports, input modules, chassis-open count, expansion cards, deep-sleep count, controller log). Changes ask for your password through polkit; reports open in a terminal. The controller can't be read without your password, so each choice shows what was last set here (the fan mode only until the next restart, when the controller goes back to automatic). The keyboard backlight stays at the level you left it when the laptop wakes from sleep (Framework's keyboard controller would switch it back on); its changes are logged in `journalctl --user -u fw-battery-warn`.

**What the installer asked once:** Chromium sign-in keys, the Ollama Cloud key, restic off-site backups (see [Backups](#backups)) and your login shell (bash, zsh or fish). Keys are typed into hidden fields, never shown again, and stored only in `~/.config/chezmoi/chezmoi.toml` and the private files made from it; new keys take effect after you log out and back in. It also shows where your dotfiles come from (**Update dotfiles**, **Re-run user setup**).

---

## Desktop

### Look & theme

Colors follow your wallpaper (Material You, by [matugen](https://github.com/InioX/matugen)) or the fixed Tokyo Night palette, with flat square borders, small gaps, and a lock screen styled like the text login (tuigreet).

The theme recolors window borders, the bar, launcher, notifications, terminal, lock screen, our panels and GTK/Qt apps (GTK 3 at once; libadwaita and Qt apps when they next start; Qt apps need one re-login the first time). Also themed: terminal tools through the terminal's 16 colors (prompt, git, btop, fzf, bat), Chromium (its GTK theme at login, unless you picked one), the Khmer input popup, admin apps that run as root (also in GNOME), and VS Code if you turn on Settings → Appearance → VS Code (off by default, since Settings Sync could copy the colors). For Claude Code pick `/theme` → dark-ansi, for OpenCode the `system` theme. Steam and web pages keep their own look.

**Boot menu (GRUB):** your wallpaper blurred and dimmed, the entries on a rounded card in the theme's colours with the selected one on an accent bar and Framework's gear above, shown for 3 seconds at every start (↑ ↓ to pick an older kernel, `e` to edit). The installer sets it up once; after changing the wallpaper or theme, `sudo fw-grub-theme` redraws it. If you set your own `GRUB_THEME`, it is left alone. Undo: `sudo cp /etc/default/grub.fw13-orig /etc/default/grub && sudo grub2-mkconfig -o /boot/grub2/grub.cfg`.

<details>
<summary>Where the colors live</summary>

The generated colors live in `~/.config/fw13/theme/`. Your own `~/.config/gtk-4.0/gtk.css` is never overwritten, and GNOME/KDE on the same account get their GTK settings back when you log out of Hyprland. The Citadel window follows after a restart; its tray icon is drawn by Citadel itself. Wallpaper colors need matugen 4 from the Hyprland COPR (Fedora's 3.1.0 is too old); installed with `HYPR_COPR=` empty, it stays Tokyo Night.

</details>

**Wallpapers** live in `~/Pictures/Wallpapers`. The installer puts 20 pictures there from the [ML4W Wallpaper Collection](https://github.com/mylinuxforwork/wallpaper) by Stephan Raabe (GPL-2.0, thanks!); delete any you don't want and they stay deleted. Originals are never changed (the desktop and lock images are rendered from them). SUPER+W opens a strip of them: click (or arrows + Enter) to use one, **+ Add…** copies pictures in. Settings → Appearance has the full gallery. From a terminal: `fw-wallpaper set|add <files>`, `fw-wallpaper effects <desktop> <lock>`.

### Terminal & shell

**Prompt** (Starship): folder (from the git repo root), branch and changes with counts (`~` modified, `+` staged, `?` new, `-` deleted, `»` renamed, `≡` stashed, `!` conflict, `⇡`/`⇣` commits to push/pull), language versions only inside projects, `☸ k8s` only in folders with Kubernetes files, how long a slow command took, `✘ 1` after a failure, `⬢ name` inside a distrobox, the hostname over SSH, 🔒 in read-only folders. At the right edge, a dim reminder of the fzf keys (Settings → Appearance → Terminal → Key hints turns it off; new terminals).

| Keys / command | Does |
|---|---|
| Ctrl+R | Search your history as you type (fzf) |
| Ctrl+T / Alt+C | Pick a file into the command line / jump into a folder (from the current folder: no hidden or dependency folders, .gitignore respected, 5 levels deep outside a git repo) |
| `**` then Tab | fzf completion: `vim **`, `cd src/**`, `kill **`, `ssh **` |
| Tab / Shift+Tab | Complete (case-insensitive), cycling through the matches |
| `ll`, `la`, `..`, `...`, `mkcd dir` | Long list, with hidden files, up one/two folders, make a folder and enter it |
| `cat` | `bat` with syntax colours, when bat is installed |
| `git st`, `git lg`, `git amend`, `git unstage` | Short status, graph log, add to the last commit, unstage |

History is big, has no duplicates and is shared between open terminals. Git defaults (`~/.config/git/config`; your `~/.gitconfig` wins): new repos use `main`, `pull` rebases, the first `push` sets the upstream, deleted remote branches are pruned, and resolved conflicts are remembered. Window look (font size, opacity, cursor, ligatures…): Settings → Appearance → Terminal.

### Default apps

| Opens in | |
|---|---|
| Folders | GNOME Files |
| Links | Chromium |
| Pictures, PDFs, text, video, music | GNOME's Image Viewer, Document Viewer, Text Editor, Video Player, Audio Player |

These defaults are Hyprland-only (`~/.config/hyprland-mimeapps.list`); a default you set yourself (Files → Open With… → Always use for this file type) wins from the next login. Inside Hyprland the launcher hides GNOME's own apps (Maps, Weather, Text Editor, GNOME Settings…), Qt6 Settings, Calf, Fcitx 5 Configuration, the keyboard layout viewer and entries meant for other desktops; they stay installed and visible in GNOME.

**Chromium Memory Saver** is on with maximum savings, so background tabs sleep sooner (a recommended policy in `/etc/chromium/policies/recommended/fw13-memory.json`; change it in `chrome://settings/performance`).

### Screens

Each screen has its own workspaces 1–9 and its own row of circles in the bar. Unplugging a monitor moves its windows into the first free workspaces of the screen they land on; a monitor plugged back in starts empty.

### Notices that come to you

| Notice | When | What you can do |
|---|---|---|
| **USB drive** "STICK" (32.0 GB) | You plug in a stick, SD card or USB disk (mounted under `/run/media/$USER/`) | **Open** in Files; **Eject** unmounts and powers it off, then says **Safe to unplug** (or why not) |
| **Software updates** | 20 min after login, then daily, when the count changed or a day passed | **Update now**: a Timeshift snapshot first (only the newest update snapshot is kept), then `dnf upgrade`, `flatpak update`, and whether a reboot is needed |
| **Low battery** | 20, 10 and 5 % | **Ask Jarvis** |
| **Health** | 15 min after login, then daily, only when something is wrong | **Diagnose** (Jarvis reads the report) |
| **Crash** | An app crashes or a service fails | **Diagnose**, you pick which agent reads it |
| **Time zone changed** | Automatic time zone is on and you moved | |

<details>
<summary>Details: USB, updates, health, time zone</summary>

- **USB:** drives already plugged in at login and encrypted (LUKS) sticks are left alone: open those in Files. Hyprland only (GNOME and KDE do this themselves); `fw-usb check` lists what would trigger.
- **Updates:** `fw-updates --check` counts pending updates from dnf's cache (no password, no download; Fedora's `dnf-makecache.timer` refreshes it) plus firmware from fwupd, e.g. *33 package updates · 1 firmware update (Fingerprint Sensor 01000334)*. If the snapshot fails, the update stops unless you type `y`. Firmware is installed from Settings → System → **Firmware updates** (needs AC power and a reboot). From a terminal: `fw-updates apply`.
- **Health:** at the first Hyprland login `fw-hwcheck` checks the Framework hardware (CPU driver, GPU, Wi-Fi, Bluetooth, battery and charge limit, firmware, fingerprint, light sensor, deep sleep, power profiles) and lists what to try by hand. `fw-health` then checks failed services, disk space, backups, reboot needed, firmware updates, battery wear, SSD health and new crashes. Reports are in `~/.local/state/fw13/health/`. Silence noisy crashes in `~/.config/fw-crash-watch/ignore`.
- **Time zone:** off by default (Settings → System). It locates you with GeoClue (nearby Wi-Fi, else your IP, through BeaconDB), turns that into a time zone with [Open-Meteo](https://open-meteo.com), and checks at login, when you join a network and every 6 hours. A VPN can make the IP-based guess wrong; if the change would need your password, it only tells you. `PYTHONPATH=~/.local/lib python3 -m fw13.timezone check` shows what it would set.

</details>

---

## Jarvis & AI

**SUPER+A** opens **Jarvis**: type a question and the answer appears in the panel (Claude, or your coding agent on one of your Ollama servers).

| | |
|---|---|
| **Start fast** | An empty panel offers starter buttons (battery drain, slowness, disk space, recent changes, health check) |
| **Knows the laptop** | The first question of a conversation comes with a short snapshot (battery, network, VPN, failed services, disk, updates, load, busiest processes, recent errors; never passwords or command lines) |
| **Look at things** | SUPER+Alt+A asks about a screen region; SUPER+Ctrl+A about the selected text (explain, fix, translate) |
| **Remembers** | Say "remember …" (or accept a suggested note) and press Save; notes live in `~/jarvis/MEMORY.md` and Settings → Jarvis → Memory |
| **History** | Reopens one of the last 20 Claude conversations; Enter continues it |
| **Offline** | Without internet, or when Claude can't be reached, it answers with the first of your Ollama servers that responds (turn off in Settings → Jarvis) |
| **Safe changes** | It reads files, logs and settings (not key and password files). Changes come one step at a time as a card with **What / Why / How** and **Run** / **Skip**; nothing runs until you press Run, and the output goes back to Jarvis. When the fix is a setting, the card opens the right Settings page instead |
| **Bigger jobs** | **Continue in terminal** opens the same conversation as a full session. Other buttons start a repo task, diagnose the last crash, or open Claude or the coding agent |

**`>_` coding agent:** manages Ollama servers for **OpenCode** or **Pi** (one choice for the icon, Jarvis's Open button and its fallback; both get the same servers and models): the laptop's own Ollama, your self-hosted servers (add/remove, online status, model list) and Ollama Cloud (key asked once during install), and the default server and model.

---

## Apps

| App | What it is |
|---|---|
| **Files** | GNOME Files (Nautilus): search as you type, tabs (Ctrl+T), path bar (Ctrl+L), hidden files (Ctrl+H) |
| **Claude Desktop** | Chat, Claude Code (visual diffs, terminal, app preview) and **Cowork**. Anthropic's official Linux build (Ubuntu/Debian only, Linux support in beta) repackaged as an RPM (`claude-desktop-official`, version and checksum pinned); re-run the installer to update. Cowork runs tasks in a small VM (Fedora's QEMU, OVMF and virtiofsd; the vsock module loads at boot). Group `claude-desktop` |
| **Obsidian** | Markdown notes in plain folders (vaults). The official build repackaged as an RPM (`obsidian-official`, version and checksum pinned); Obsidian updates itself in-app, re-running the installer updates the app around it. To sync a vault, add its folder in Settings → Syncthing. Group `obsidian` |
| **Neovim** | With [LazyVim](https://www.lazyvim.org) (`nvim`): file finder, search (ripgrep, fd), syntax parsers, language servers through Mason, lazygit (`<leader>gg`), Tokyo Night. `~/.config/nvim` is created once and then yours (plugins in `lua/plugins/`, extras with `:LazyExtras`) |
| **DBeaver CE** | Databases (PostgreSQL, MySQL, SQLite…). Official RPM, checksum-pinned, bundles its own Java. Runs on XWayland with a dark theme (Window → Preferences → User Interface → Appearance). Group `database` |
| **Remote Desktop Manager** | Devolutions' RDP, SSH, VNC and more (their repo). Start it from the launcher (it goes through `fw-rdm`, which makes it draw and scales it per screen). While its entry editor is open it keeps the mouse inside; close it or move focus with Super+←/→ (or Super+1–9). While it is focused, remote mode is on by itself, so Super+Q, Command shortcuts and the rest go to the remote session; Super+Alt+R gives the keys back to Fedora (or click another window). Group `remote` |
| **Speakers** | **EasyEffects** with **Framework's FW13 preset** for the built-in speakers (room correction, compressor, limiter; +9.5 dB so voices stay as loud; a softer `fw13-clear` too; from [FrameworkComputer/linux-docs](https://github.com/FrameworkComputer/linux-docs), GPL-3.0). Off, Framework / Clear voice, or your own Bass, Warmth, Voice clarity, Air and Level in Settings → Sound → Speaker sound |
| **Android** | `adb`/`fastboot` and **scrcpy** (official release, checksum-pinned) to show and control your phone: turn on USB debugging, plug it in, run `scrcpy` or pick it in the launcher |
| **Syncthing** | File sync between your devices, as your user service; managed in [Settings → Syncthing](#syncthing), full UI at 127.0.0.1:8384. No firewall port is opened (it connects out or through relays) |
| **Telegram** | The official build from telegram.org as an RPM (`telegram-desktop-official`); its updater is off, re-run the installer to update |
| **Citadel** | Outbound firewall: when an app connects somewhere new it asks (Allow once / Always / Block); answers become per-app policies. **Enforcement is on**. Built from [citadel-app](https://github.com/NeatOuk/citadel-app) and [citadel-helper](https://github.com/NeatOuk/citadel-helper); `citadel enforce off` or Citadel → Settings turns blocking off |
| **Games** | Steam (RPM Fusion) with gamescope, GameMode and MangoHud, and **Lutris** for Windows launchers: for **Battle.net** search it in Lutris, Install, sign in (runs through Wine; can break briefly after a Battle.net update) |
| **Framework tool** | `framework_tool` (official, checksum-pinned) in `/usr/local/bin`: firmware versions, charge limit, fan, keyboard backlight and other EC settings, e.g. `sudo framework_tool --versions` |

---

## Backups

**Timeshift** snapshots the system, not your home folder (that's restic's job, below), so a snapshot is the size of the system (~20 GB), not of your files. Run `sudo fw-timeshift-setup` (the installer offers to). It picks the mode by itself:

| Disk layout | Mode |
|---|---|
| btrfs with `@`/`@home` subvolumes | **btrfs** (instant, no extra space) |
| Fedora's default btrfs (`root`/`home`), ext4, xfs | **rsync** (copies files, then incremental) |

There is no schedule: a snapshot is taken **before each update** (Settings → Update, the update notice, `fw-updates apply`), and only the newest of those is kept. Snapshots you make yourself in Timeshift stay until you delete them; a schedule can still be turned on in Timeshift's settings. It also leaves out `/var/cache`, containers, Ollama's models and the logs. To restore on Fedora's default layout, use `sudo fw-timeshift-restore` (Timeshift's own restore only works on the `@` layout); on an `@` layout, `sudo timeshift --restore` or `timeshift-launcher` (`SUPER+Shift+B`).

**Restoring the system** (Fedora's default layout, rsync mode):

```bash
sudo fw-timeshift-restore --list            # snapshots
sudo fw-timeshift-restore <snapshot>        # dry run: shows what would change
sudo fw-timeshift-restore real <snapshot>   # restore, then reboot
sudo fw-timeshift-restore undo              # go back to the system from before the restore
```

It copies the current system, restores the snapshot onto the copy and swaps the two only if that worked, so the running system is never overwritten. It keeps `/home`, Wi-Fi/VPN connections, Bluetooth pairings, fingerprints and Timeshift's settings, and holds Timeshift's lock so scheduled snapshots wait. The snapshot's kernel is added next to the current ones and made the default. The first boot relabels SELinux (several minutes, then one automatic reboot). The old system stays as subvolume `root.fw-before` until you delete it.

**Off-laptop: restic** backs up your home folder daily (user systemd timer, encrypted, keeps 7 daily / 4 weekly / 6 monthly). Configure it with the restic prompt during install or in Settings → My Framework, which has presets for a **NAS over SFTP** and **Backblaze B2 (S3)**; S3 keys (also Wasabi, R2, MinIO) are entered there, never in a file by hand. Settings → My Framework → Restore opens a terminal with the repository loaded: `restic snapshots`, `restic mount ~/restic-mnt` to browse, or `restic restore latest --target ~/restore --include ~/path`.

> Keep the restic repository password in a password manager: without it the backup can't be read.

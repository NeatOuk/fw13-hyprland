# Security policy

## Supported versions

Only the latest release and `main` get fixes. Re-running `install.sh` (or `chezmoi update --init`) brings an installed laptop up to date.

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately through GitHub: **Security → Report a vulnerability** on this repository ([direct link](https://github.com/NeatOuk/fw13-hyprland/security/advisories/new)).

Include what you found, how to reproduce it, and the impact you expect. This is a one-person project, so replies are best effort; you'll get an answer once the report has been read, and credit in the fix unless you'd rather not.

## What's in scope

Things this repository adds to a Fedora system, in particular:

- **Root helpers** in `system/usr/local/bin/` (`fw-vpn-ctl`, `fw-vpn-config`, `fw-charge-limit`, `fw-power-profile`, `fw-disk-unlock`, `fw-hibernate-setup`, `fw-timeshift-*`, `fw-health-root`) and the **polkit rules and actions** that let wheel users run some of them without a password (`50-fw13-vpn.rules`, `50-fw13-power.rules`)
- **Secret handling**: chezmoi prompts and the `private_` files they render (Chromium OAuth, restic, Ollama Cloud key), VPN passwords, the Jarvis Laya token in GNOME Keyring; anything that puts a secret on a command line, in a log or in a world-readable file
- **Downloads in `install.sh`**: pinned versions and sha256 checks for repackaged or upstream binaries (Claude Desktop, Telegram, Ghostty, scrcpy, framework_tool, DBeaver), and the vendor repos it adds
- **Jarvis**: anything that lets a command run without the owner pressing **Run**, or lets it read key and password files

## Out of scope

Bugs in the packages we install (Hyprland, Fedora packages, vendor apps): report those upstream. The Citadel firewall has its own repositories ([citadel-app](https://github.com/NeatOuk/citadel-app), [citadel-helper](https://github.com/NeatOuk/citadel-helper)); its helper's passwordless polkit rule for wheel is by design.

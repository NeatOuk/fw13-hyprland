## What and why

<!-- What changes for the user, and why. Link the issue: "Closes #123". -->

## How it was tested

<!-- What you ran and on which machine (Framework 13 AMD, other laptop, VM, CI only). -->

## Checklist

- [ ] One feature or fix per commit, with a conventional prefix (`feat(area):`, `fix(area):`, `docs:`, `chore:`)
- [ ] No new package, or the package was agreed in an issue first (name and source)
- [ ] Lint passes: `shellcheck -S warning` on the bash scripts, `ast.parse` on the Python ones (see [CONTRIBUTING.md](../CONTRIBUTING.md))
- [ ] Hyprland changes: `Hyprland --verify-config` on the rendered config, no duplicate binds, every bind has a `description`
- [ ] Dotfile changes: chezmoi dry-run into a throwaway home, with secrets blank and filled
- [ ] Re-running `install.sh` is still safe, and GNOME/KDE on the same account is unaffected
- [ ] No secrets in git or on a command line
- [ ] Docs updated in the same change: docs/APPS.md (features, Settings, keys), README (install), docs/ARCHITECTURE.md (components), CLAUDE.md (rules)
- [ ] Hardware-only behaviour not yet verified is on the checklist in docs/FIRST-INSTALL.md

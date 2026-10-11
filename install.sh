#!/usr/bin/env bash
# fw13-hypr installer — Hyprland desktop for Fedora (Workstation, KDE, any spin, or Minimal).
# Run as your normal user (it uses sudo where needed). Safe to re-run.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/NeatOuk/fw13-hyprland/main/install.sh)
#
# Flags:
#   --yes           don't ask for confirmation
#   --ci            non-interactive test mode (containers): skips services, fingerprint,
#                   Timeshift, shell change, Flathub; applies dotfiles from the local checkout
#   --system-only   only the sudo part (packages, repos, system files)
#   --user-only     only the per-user part (dotfiles, mise, shell)
#   --minimal       core desktop only, no optional groups (see GROUP_INFO below)
#   --with=a,b      add optional groups;  --without=a,b  leave them out (the choice is saved, re-runs keep it)
#   --print-plan    print the groups, package lists and steps this run would do, then exit (changes nothing; needs a checkout)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/NeatOuk/fw13-hyprland}"
CHECKOUT="${CHECKOUT:-$HOME/.local/share/fw13-hypr}"
HYPR_COPR="${HYPR_COPR-lionheartp/Hyprland}"
# Citadel outbound firewall + its root helper: built from the owner's repos as RPMs (no prebuilt packages).
CITADEL_APP_REPO="${CITADEL_APP_REPO:-https://github.com/NeatOuk/citadel-app.git}"
CITADEL_APP_REF="${CITADEL_APP_REF:-main}"
CITADEL_HELPER_REPO="${CITADEL_HELPER_REPO:-https://github.com/NeatOuk/citadel-helper.git}"
CITADEL_HELPER_REF="${CITADEL_HELPER_REF:-v1.3.2}"
# Ghostty (Settings → My Framework → Terminal): built from the official release tarball. The sha256 is pinned per version
# (checked once against the release's minisign signature, key in Ghostty's PACKAGING.md). GHOSTTY=0 skips it.
GHOSTTY="${GHOSTTY:-1}"
GHOSTTY_VERSION="${GHOSTTY_VERSION:-1.3.1}"
GHOSTTY_SHA256="${GHOSTTY_SHA256:-3349d25600ffbda281197a18314f7d18791969cffe9474f0ff16a45a9ebfccdb}"
# framework_tool (Framework's official EC/firmware CLI, github.com/FrameworkComputer/framework-system; user decision):
# the release binary → /usr/local/bin, sha256 pinned per version (GitHub's asset digest). Bump both together.
FWTOOL_VERSION="${FWTOOL_VERSION:-v0.6.6}"
FWTOOL_SHA256="${FWTOOL_SHA256:-ebc2f3ca300dac6f484c02d058833372ff8dd3c23f2a74b63c774f8dc2f86171}"
# scrcpy (Android screen mirroring; user decision: Genymobile's official Linux release, not a COPR): the tarball →
# /opt/scrcpy, sha256 pinned (GitHub's asset digest), a /usr/local/bin/scrcpy wrapper that uses Fedora's adb
# (android-tools, 70-dev.txt) instead of the bundled one, so two adb versions never fight over the phone.
SCRCPY_VERSION="${SCRCPY_VERSION:-v5.0.1}"
SCRCPY_SHA256="${SCRCPY_SHA256:-9f969d30cc574816077edecda65719c1c70b0aee1df1ba5fa00779ac07b8fd6e}"
STATE_DIR="$HOME/.local/state/fw13-hypr"

# Optional groups: everything else is core (what the desktop itself needs). A group owns its packages/*.txt files and
# the repo, build, download and service steps that test `on <group>` below. An unselected group is skipped, never
# removed (rule 3a). Order = prompt order. GROUP_INFO[g] = "<packages/*.txt files>|<one-line description>".
OPT_GROUPS=(games ai android remote warp firewall messaging ghostty localsend)
declare -A GROUP_INFO=(
  [games]="40-gaming.txt|Steam, Lutris, gamescope, MangoHud, GameMode"
  [ai]="71-ai.txt|Ollama: local models for OpenCode and Jarvis (ollama.service)"
  [android]="72-android.txt|adb/fastboot + scrcpy phone mirroring (official release)"
  [remote]="31-remote.txt|Remote Desktop Manager (Devolutions repo, ~1.2 GB)"
  [warp]="97-warp.txt|Cloudflare WARP + the bar's cloud icon (Cloudflare repo, warp-svc)"
  [firewall]="94-rpm-build.txt 95-citadel.txt|Citadel outbound firewall, built from source"
  [messaging]="94-rpm-build.txt|Telegram Desktop, official telegram.org build as an RPM"
  [ghostty]="94-rpm-build.txt 98-ghostty.txt|Ghostty terminal, built from the official release (kitty stays)"
  [localsend]="|LocalSend file sharing (Flathub, send only)"
)
# The saved choice: one group per line. Absent = every group (today's full install).
GROUPS_FILE="$HOME/.config/fw13/install-groups"

YES=0 CI=0 DO_SYSTEM=1 DO_USER=1 PLAN=0 MINIMAL=0 WITH="" WITHOUT=""
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --ci) CI=1; YES=1 ;;
    --system-only) DO_USER=0 ;;
    --user-only) DO_SYSTEM=0 ;;
    --minimal) MINIMAL=1 ;;
    --with=*) WITH="$WITH,${a#*=}" ;;
    --without=*) WITHOUT="$WITHOUT,${a#*=}" ;;
    --print-plan) PLAN=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx %s\033[0m\n' "$*"; exit 1; }
ask()  { [[ $YES == 1 ]] && return 0; read -rp "$1 [Y/n] " r; [[ "${r,,}" != n ]]; }
# Apps you removed with Settings → Apps → Uninstall… (optional ones only) are listed here, one name per line, and
# skipped from then on; Settings → Apps → Removed apps takes a name out again. Absent under --ci (root's home).
SKIP_FILE="$HOME/.config/fw13/skip-packages"
skipped() { [[ -r $SKIP_FILE ]] && grep -qxF -- "$1" "$SKIP_FILE"; }
pkgs() {
  grep -hv '^\s*#' "$@" | tr -s ' \t' '\n' | sed '/^$/d' \
    | if [[ -s $SKIP_FILE ]]; then grep -vxF -f "$SKIP_FILE" || true; else cat; fi
}
SUDO=sudo; [[ $EUID -eq 0 ]] && SUDO=""

# --- Optional groups -----------------------------------------------------------
SELECTED=()
on() { [[ " ${SELECTED[*]} " == *" $1 "* ]]; }
# valid_groups "a,b c": every name is a group (lower case)
valid_groups() { local - g; set -f; for g in ${1//,/ }; do [[ -n ${GROUP_INFO[${g,,}]+x} ]] || return 1; done; }
group_words() { local - g; set -f; for g in ${1//,/ }; do echo "${g,,}"; done; }
# Base = the saved choice (else all); --ci = all; --minimal = none; then --with/--without. Asked once interactively
# (no --yes/--ci/--print-plan, no group flags, system phase), Enter keeping the base. save_groups stores it.
CHOSEN=()
choose_groups() {
  local base=() add=() drop=() g ans
  if [[ $CI == 0 && -r $GROUPS_FILE ]]; then mapfile -t base < <(grep -v '^\s*\(#\|$\)' "$GROUPS_FILE" || true)
  else base=("${OPT_GROUPS[@]}"); fi
  [[ $MINIMAL == 1 ]] && base=()
  valid_groups "$WITH$WITHOUT" || die "unknown group in --with/--without (groups: ${OPT_GROUPS[*]})"
  mapfile -t add < <(group_words "$WITH")
  mapfile -t drop < <(group_words "$WITHOUT")
  if [[ $YES == 0 && $PLAN == 0 && $DO_SYSTEM == 1 && $MINIMAL == 0 && -z $WITH$WITHOUT ]]; then
    SELECTED=("${base[@]}")
    echo; echo "Optional groups (the core desktop is always installed):"
    for g in "${OPT_GROUPS[@]}"; do printf '  %-10s %-4s %s\n' "$g" "$(on "$g" && echo '[x]' || echo '[ ]')" "${GROUP_INFO[$g]#*|}"; done
    while :; do
      read -rp "Enter = as marked; or list the groups to install (e.g. \"games ai\"), \"all\" or \"none\": " ans
      case "${ans,,}" in
        "") break ;;
        all) base=("${OPT_GROUPS[@]}"); break ;;
        none) base=(); break ;;
        *) valid_groups "$ans" && { mapfile -t base < <(group_words "$ans"); break; }
           warn "unknown group in: $ans (groups: ${OPT_GROUPS[*]})" ;;
      esac
    done
  fi
  SELECTED=()
  for g in "${OPT_GROUPS[@]}"; do   # keeps GROUPS order, drops duplicates
    [[ " ${base[*]} ${add[*]} " == *" $g "* && " ${drop[*]} " != *" $g "* ]] && SELECTED+=("$g")
  done
  CHOSEN=("${SELECTED[@]}")
  if [[ $GHOSTTY == 0 ]]; then   # GHOSTTY=0: this run only (a loop, not printf | grep: an empty list must stay empty)
    SELECTED=(); for g in "${CHOSEN[@]}"; do [[ $g == ghostty ]] || SELECTED+=("$g"); done
  fi
  return 0
}
save_groups() {
  mkdir -p "${GROUPS_FILE%/*}"
  { echo "# fw13-hypr optional groups, one per line (install.sh --with/--without/--minimal rewrite this)"
    if (( ${#CHOSEN[@]} )); then printf '%s\n' "${CHOSEN[@]}"; fi; } > "$GROUPS_FILE"
}
# The package lists for one dnf transaction: core + the selected groups' files (each once). 40-gaming (own transaction)
# and 50-codecs (--allowerasing) are installed separately.
package_lists() {
  local f out=(00-core.txt 10-desktop.txt 20-input-fonts.txt 30-apps.txt 60-framework.txt 70-dev.txt 80-shells.txt 90-backup.txt 96-theme.txt) g
  use_greetd && out+=(15-login.txt)
  has_ppd || out+=(61-power.txt)
  for g in "${SELECTED[@]}"; do
    for f in ${GROUP_INFO[$g]%%|*}; do [[ $f == 40-gaming.txt || " ${out[*]} " == *" $f "* ]] || out+=("$f"); done
  done
  printf '%s\n' "${out[@]}"
}
# repos/*.repo files for this run: the vendor repos of unselected (or removed) groups are left out
repo_files() {
  local r
  for r in repos/*.repo; do
    r=${r#repos/}
    case $r in
      devolutions-rdm.repo) on remote || continue ;;
      cloudflare-warp.repo) on warp && ! skipped cloudflare-warp || continue ;;
    esac
    echo "$r"
  done
}
# --print-plan: what this run would install and do, without doing any of it
print_plan() {
  local lists g
  mapfile -t lists < <(package_lists)
  echo "optional groups: ${SELECTED[*]:-none (core only)}"
  echo "not selected:    $(for g in "${OPT_GROUPS[@]}"; do on "$g" || printf '%s ' "$g"; done)"
  [[ -s $SKIP_FILE ]] && echo "skipped (removed by you): $(grep -v '^\s*$' "$SKIP_FILE" | paste -sd' ')"
  echo "repos: $(repo_files | paste -sd' ')"
  echo "lists: ${lists[*]}"
  echo "packages: $(cd packages && pkgs "${lists[@]}" | paste -sd' ')"
  on games && echo "packages (gaming): $(cd packages && pkgs 40-gaming.txt | paste -sd' ')"
  echo "packages (codecs, --allowerasing): $(cd packages && pkgs 50-codecs.txt | paste -sd' ')"
  echo "steps:"
  on firewall && ! skipped citadel && echo "  build citadel + citadel-helper RPMs; user: enable citadel.service, citadel enforce on"
  on messaging && ! skipped telegram-desktop-official && echo "  build telegram-desktop-official RPM"
  on ghostty && ! skipped ghostty-official && echo "  build ghostty-official $GHOSTTY_VERSION RPM"
  echo "  framework_tool $FWTOOL_VERSION download (if not current)"
  on android && echo "  scrcpy $SCRCPY_VERSION download into /opt/scrcpy (if not current)"
  on ai && echo "  enable ollama.service"
  on warp && ! skipped cloudflare-warp && echo "  enable warp-svc.service"
  on localsend && ! skipped org.localsend.localsend_app && echo "  flatpak install --user LocalSend"
  echo "saved choice: $GROUPS_FILE ($([[ -r $GROUPS_FILE ]] && echo "$(grep -vc '^\s*\(#\|$\)' "$GROUPS_FILE" || true) groups" || echo "absent = all"))"
}

# --- Preflight ---------------------------------------------------------------
[[ -r /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" == fedora ]] || die "Fedora only (found: ${ID:-unknown})."
[[ -e /run/ostree-booted ]] && die "This is an Atomic/image-based Fedora (Silverblue/Kinoite/...). Use Workstation, KDE, a spin, or Minimal."
FEDORA="$(rpm -E %fedora)"
(( FEDORA >= 44 )) || die "Fedora 44 or newer required (found $FEDORA) — COPR lionheartp/Hyprland has no builds for older releases."
[[ $EUID -ne 0 || $CI == 1 ]] || die "Run as your normal user, not root (sudo is used where needed)."

# Locate the repo: run from a checkout, or clone one.
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
if [[ ! -f "$SRC/packages/00-core.txt" ]]; then
  [[ $PLAN == 0 ]] || die "--print-plan changes nothing, so it needs a checkout: git clone $REPO_URL && cd fw13-hyprland && ./install.sh --print-plan"
  say "Fetching $REPO_URL"
  command -v git >/dev/null || $SUDO dnf -y install git
  if [[ -d "$CHECKOUT/.git" ]]; then git -C "$CHECKOUT" pull --ff-only; else git clone --depth 1 "$REPO_URL" "$CHECKOUT"; fi
  SRC="$CHECKOUT"
fi
cd "$SRC"

has_dm() { [[ -e /etc/systemd/system/display-manager.service ]]; }
current_dm() { basename "$(readlink -f /etc/systemd/system/display-manager.service)" .service; }
# Login screen: greetd + tuigreet (a plain text login that matches the desktop), also replacing GDM/SDDM (user
# decision, an exception to rule 3a: the old one is only disabled, not removed). KEEP_DM=1 keeps an existing one.
use_greetd() { [[ ${KEEP_DM:-0} != 1 ]] || ! has_dm; }
has_ppd() { rpm -q power-profiles-daemon >/dev/null 2>&1; }
# Hyprland alone has no file mounting, printing or document viewers; a GNOME or KDE install brings them.
bare_install() { ! rpm -q --quiet gnome-shell && ! rpm -q --quiet plasma-workspace; }
recommend_gnome() { warn "No GNOME or KDE found: install GNOME first for file mounting, printing and viewers: sudo dnf group install workstation-product-environment"; }

choose_groups
[[ $PLAN == 1 ]] && { print_plan; exit 0; }

cat <<EOF

fw13-hypr installer — Fedora ${FEDORA} (${VARIANT_ID:-${VARIANT:-unknown edition}})
  Optional:     ${SELECTED[*]:-none (core only)}  (choose with --minimal / --with= / --without=)
  Adds repos:   RPM Fusion free+nonfree, COPR ${HYPR_COPR:-<none>}, Microsoft (VS Code), mise$(on remote && echo ", Devolutions (RDM)")$(on warp && ! skipped cloudflare-warp && echo ", Cloudflare (WARP)")
  Login screen: $(if ! use_greetd; then echo "keep existing $(current_dm) — adds a 'Hyprland (uwsm)' session (KEEP_DM=1)"; elif has_dm && [[ $(current_dm) != greetd ]]; then echo "greetd + tuigreet text login; disables $(current_dm) (not removed; KEEP_DM=1 keeps it)"; else echo "greetd + tuigreet text login"; fi)
  Power:        $(has_ppd && echo "keep power-profiles-daemon" || echo "install tuned + tuned-ppd")
  Removes:      nothing (ffmpeg-free is swapped for RPM Fusion ffmpeg)
EOF
bare_install && recommend_gnome
ask "Continue?" || exit 0
save_groups

mkdir -p "$STATE_DIR"

# ============================================================================
# build_citadel_rpm <name> <repo> <ref> <spec path in repo> → prints the built RPM's path.
# Builds as the normal user in $STATE_DIR/citadel; the tarball is what the spec's Source0 expects
# (<name>-<version>.tar.gz with a <name>-<version>/ prefix). Untagged refs get a dated git release
# (1.git<YYYYMMDD>.<sha>.fcNN) so a re-run picks up new commits as an upgrade.
build_citadel_rpm() {
  local name=$1 repo=$2 ref=$3 spec=$4 top="$STATE_DIR/citadel" src ver dist
  src="$top/src/$name"
  if [[ -d "$src/.git" ]]; then git -C "$src" fetch -q --depth 1 origin "$ref" && git -C "$src" -c advice.detachedHead=false checkout -q FETCH_HEAD
  else git -c advice.detachedHead=false clone -q --depth 1 --branch "$ref" "$repo" "$src"; fi
  ver="$(awk '/^Version:/ {print $2; exit}' "$src/$spec")"
  mkdir -p "$top"/{SOURCES,RPMS,BUILD,SRPMS,SPECS}
  git -C "$src" archive --format=tar.gz --prefix="$name-$ver/" -o "$top/SOURCES/$name-$ver.tar.gz" HEAD
  if git -C "$src" describe --exact-match --tags HEAD >/dev/null 2>&1; then dist=".fc$FEDORA"
  else dist=".git$(git -C "$src" log -1 --format=%cd --date=format:%Y%m%d).$(git -C "$src" rev-parse --short HEAD).fc$FEDORA"; fi
  rpmbuild -bb --quiet --define "_topdir $top" --define "dist $dist" "$src/$spec" >&2 || return 1
  ls -t "$top"/RPMS/noarch/"${name%-app}"-[0-9]*"$dist".noarch.rpm 2>/dev/null | head -1
}

# ============================================================================
# build_telegram_rpm → prints the built RPM's path, or nothing when the installed one is already current.
# Telegram Desktop from telegram.org (user decision: the official build, packaged as an RPM so dnf owns it).
# The tarball's version comes from telegram.org's redirect; launcher entry, D-Bus service and icons come from
# Telegram's own repo at the same tag. Spec: rpm/telegram-desktop-official.spec.
build_telegram_rpm() {
  local top="$STATE_DIR/telegram" url ver have rel f
  url="$(curl -fsIL -o /dev/null -w '%{url_effective}' https://telegram.org/dl/desktop/linux)" || return 1
  ver="${url##*-x64-}"; ver="${ver%.tar.xz}"
  [[ $ver =~ ^[0-9]+(\.[0-9]+)+$ ]] || { warn "unexpected Telegram download URL: $url" >&2; return 1; }
  rel="$(sed -n 's/^Release:[[:space:]]*\([0-9]*\).*/\1/p' rpm/telegram-desktop-official.spec)"   # a spec fix rebuilds too
  have="$(rpm -q --qf '%{VERSION}-%{RELEASE}' telegram-desktop-official 2>/dev/null || true)"
  [[ ${have%%.fc*} == "$ver-$rel" ]] && return 0
  mkdir -p "$top"/{SOURCES,RPMS,BUILD,SRPMS,SPECS}
  curl -fsSL -o "$top/SOURCES/td-setup-linux-x64-$ver.tar.xz" "$url" || return 1
  local gh="https://raw.githubusercontent.com/telegramdesktop/tdesktop/v$ver"
  for f in lib/xdg/org.telegram.desktop.desktop lib/xdg/org.telegram.desktop.service \
           Telegram/Resources/art/icon{16,32,48,64,128,256,512}.png; do
    curl -fsSL -o "$top/SOURCES/${f##*/}" "$gh/$f" || return 1
  done
  rpmbuild -bb --quiet --define "_topdir $top" --define "tg_version $ver" --define "dist .fc$FEDORA" \
    rpm/telegram-desktop-official.spec >&2 || return 1
  ls -t "$top"/RPMS/x86_64/telegram-desktop-official-"$ver"-*.rpm 2>/dev/null | head -1
}

# ============================================================================
# build_ghostty_rpm → prints the built RPM's path, or nothing when the installed one is already current.
# The release tarball must match GHOSTTY_SHA256. Ghostty builds with one exact Zig version (minimum_zig_version in
# build.zig.zon; Fedora's zig is newer), so that Zig comes from ziglang.org, checked against its index.json, and is
# only used for the build. Spec: rpm/ghostty-official.spec.
build_ghostty_rpm() {
  local top="$STATE_DIR/ghostty" ver=$GHOSTTY_VERSION have tarball zv zdir arch=x86_64-linux
  have="$(rpm -q --qf '%{VERSION}' ghostty-official 2>/dev/null || true)"
  [[ $have == "$ver" ]] && return 0
  mkdir -p "$top"/{SOURCES,RPMS,BUILD,SRPMS,SPECS,zig-cache}
  tarball="$top/SOURCES/ghostty-$ver.tar.gz"
  # Only the RPM path may reach stdout (the caller captures it): checksum output goes to stderr or nowhere.
  if ! echo "$GHOSTTY_SHA256  $tarball" | sha256sum -c --quiet >/dev/null 2>&1; then
    curl -fsSL -o "$tarball" "https://release.files.ghostty.org/$ver/ghostty-$ver.tar.gz" || return 1
    echo "$GHOSTTY_SHA256  $tarball" | sha256sum -c --quiet >&2 \
      || { warn "ghostty-$ver.tar.gz doesn't match GHOSTTY_SHA256" >&2; rm -f "$tarball"; return 1; }
  fi
  zv="$(tar -xzOf "$tarball" "ghostty-$ver/build.zig.zon" | sed -n 's/.*minimum_zig_version = "\([0-9.]*\)".*/\1/p')"
  [[ $zv =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { warn "no minimum_zig_version in ghostty-$ver" >&2; return 1; }
  zdir="$top/zig-$zv"
  if [[ ! -x $zdir/zig ]]; then
    local url sum
    { read -r url; read -r sum; } < <(curl -fsSL https://ziglang.org/download/index.json | python3 -c '
import json, sys
d = json.load(sys.stdin)[sys.argv[1]][sys.argv[2]]
print(d["tarball"]); print(d["shasum"])' "$zv" "$arch") || { warn "Zig $zv isn't in ziglang.org's index" >&2; return 1; }
    curl -fsSL -o "$top/zig.tar.xz" "$url" || return 1
    echo "$sum  $top/zig.tar.xz" | sha256sum -c --quiet >&2 || { warn "Zig $zv download doesn't match its checksum" >&2; return 1; }
    mkdir -p "$zdir" && tar -xJf "$top/zig.tar.xz" -C "$zdir" --strip-components=1 && rm -f "$top/zig.tar.xz"
  fi
  rpmbuild -bb --quiet --define "_topdir $top" --define "gh_version $ver" --define "dist .fc$FEDORA" \
    --define "zig $zdir/zig" --define "zig_cache $top/zig-cache" rpm/ghostty-official.spec >&2 || return 1
  ls -t "$top"/RPMS/x86_64/ghostty-official-"$ver"-*.rpm 2>/dev/null | head -1
}

system_phase() {
  rpm -qa --qf '%{NAME}\n' | sort > "$STATE_DIR/rpms-before.txt"
  local DNF="$SUDO dnf -y --setopt=install_weak_deps=False"

  say "Repositories"
  $SUDO dnf -y install dnf5-plugins
  rpm -q rpmfusion-free-release >/dev/null 2>&1 || $SUDO dnf -y install \
    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA}.noarch.rpm" \
    "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA}.noarch.rpm"
  $SUDO dnf config-manager setopt fedora-cisco-openh264.enabled=1 || true
  [[ -n "$HYPR_COPR" ]] && $SUDO dnf -y copr enable "$HYPR_COPR"
  local r
  for r in $(repo_files); do $SUDO install -m 0644 "repos/$r" /etc/yum.repos.d/; done

  say "Packages (weak dependencies off — only what's listed)"
  [[ -s $SKIP_FILE ]] && echo "skipped (removed by you): $(grep -v '^\s*$' "$SKIP_FILE" | paste -sd' ')"
  echo "optional groups: ${SELECTED[*]:-none (core only)}"
  local lists main gaming=() codecs
  mapfile -t lists < <(package_lists)
  (( ${#lists[@]} )) || die "no package lists (package_lists failed)"   # pkgs with no files would read stdin
  mapfile -t main   < <(cd packages && pkgs "${lists[@]}")
  on games && mapfile -t gaming < <(cd packages && pkgs 40-gaming.txt)
  mapfile -t codecs < <(cd packages && pkgs 50-codecs.txt)
  $DNF install "${main[@]}"
  (( ${#gaming[@]} )) && $DNF install "${gaming[@]}"
  $DNF install --allowerasing "${codecs[@]}"
  # matugen (wallpaper → Material You colours): fw13.theme needs 4.x (--prefer, -t scheme-*, colors[role][mode]).
  # Fedora 44 ships 3.1.0, which rejects those flags, so the version is pinned: a COPR without matugen 4
  # fails here loudly instead of quietly installing Fedora's. lionheartp/Hyprland has 4.2.0.
  if [[ -n "$HYPR_COPR" ]]; then
    $DNF install 'matugen >= 4'
  else
    warn "HYPR_COPR is empty: no matugen 4 (Fedora's 3.1.0 is too old), so the theme stays Tokyo Night"
  fi

  if ! on firewall; then :
  elif skipped citadel; then echo "Citadel: skipped (removed by you)"; else
    say "Citadel (outbound firewall) + citadel-helper — built from source as RPMs"
    local rpms=()
    mapfile -t rpms < <(build_citadel_rpm citadel-app "$CITADEL_APP_REPO" "$CITADEL_APP_REF" linux/packaging/rpm/citadel.spec
                        build_citadel_rpm citadel-helper "$CITADEL_HELPER_REPO" "$CITADEL_HELPER_REF" packaging/rpm/citadel-helper.spec)
    (( ${#rpms[@]} == 2 )) || die "Citadel RPM build failed (see above)"
    $DNF install "${rpms[@]}"   # same version: no-op; newer build: upgrade
  fi

  if ! on messaging; then :
  elif skipped telegram-desktop-official; then echo "Telegram: skipped (removed by you)"; else
    say "Telegram Desktop — official telegram.org build, packaged as an RPM"
    local tg
    tg="$(build_telegram_rpm)" || die "Telegram RPM build failed (see above)"
    if [[ -n $tg ]]; then $DNF install "$tg"; else echo "telegram-desktop-official is current"; fi
  fi

  if ! on ghostty; then :
  elif skipped ghostty-official; then echo "Ghostty: skipped (removed by you)"
  else
    say "Ghostty — built from the official release (Settings → My Framework → Terminal)"
    local gt
    gt="$(build_ghostty_rpm)" || die "Ghostty RPM build failed (see above)"
    if [[ -n $gt ]]; then $DNF install "$gt"; else echo "ghostty-official is current"; fi
  fi

  say "System files"
  $SUDO install -m 0755 system/usr/local/bin/* /usr/local/bin/
  compgen -G 'system/etc/systemd/system/*' >/dev/null && $SUDO install -m 0644 system/etc/systemd/system/* /etc/systemd/system/
  $SUDO install -m 0644 system/etc/udev/rules.d/* /etc/udev/rules.d/   # charger plug / unplug → fw-power-profile
  $SUDO install -m 0644 system/etc/modprobe.d/* /etc/modprobe.d/   # battery charge limit (cros_charge_control on Framework); used from the next boot
  # Bar VPN toggle without a password: pkexec fw-vpn-ctl (action file) + rule for wheel in an active local session
  $SUDO install -D -m 0644 system/usr/share/polkit-1/actions/org.fw13.vpn.policy /usr/share/polkit-1/actions/org.fw13.vpn.policy
  $SUDO install -D -m 0644 system/etc/polkit-1/rules.d/50-fw13-vpn.rules /etc/polkit-1/rules.d/50-fw13-vpn.rules
  $SUDO install -D -m 0644 system/usr/share/polkit-1/actions/org.fw13.power.policy /usr/share/polkit-1/actions/org.fw13.power.policy
  $SUDO install -D -m 0644 system/etc/polkit-1/rules.d/50-fw13-power.rules /etc/polkit-1/rules.d/50-fw13-power.rules
  # Automatic time zone (fw13.timezone): Hyprland has no GeoClue agent, so our client is allowed as a system app
  $SUDO install -D -m 0644 system/etc/geoclue/conf.d/90-fw13-timezone.conf /etc/geoclue/conf.d/90-fw13-timezone.conf
  [[ $CI == 1 ]] || $SUDO udevadm control --reload
  if ! echo "$FWTOOL_SHA256  /usr/local/bin/framework_tool" | sha256sum -c --status 2>/dev/null; then
    say "framework_tool $FWTOOL_VERSION (Framework's EC/firmware CLI)"
    local fwt; fwt="$(mktemp)"
    curl -fsSL -o "$fwt" "https://github.com/FrameworkComputer/framework-system/releases/download/$FWTOOL_VERSION/framework_tool" \
      && echo "$FWTOOL_SHA256  $fwt" | sha256sum -c --status || { rm -f "$fwt"; die "framework_tool download failed or checksum mismatch"; }
    $SUDO install -m 0755 "$fwt" /usr/local/bin/framework_tool; rm -f "$fwt"
  fi
  if on android && [[ $(cat /opt/scrcpy/.version 2>/dev/null) != "$SCRCPY_VERSION" ]]; then
    say "scrcpy $SCRCPY_VERSION (Android screen mirroring, official release)"
    local sct; sct="$(mktemp -d)"
    curl -fsSL -o "$sct/s.tgz" "https://github.com/Genymobile/scrcpy/releases/download/$SCRCPY_VERSION/scrcpy-linux-x86_64-$SCRCPY_VERSION.tar.gz" \
      && echo "$SCRCPY_SHA256  $sct/s.tgz" | sha256sum -c --status || { rm -rf "$sct"; die "scrcpy download failed or checksum mismatch"; }
    tar -xzf "$sct/s.tgz" -C "$sct" --strip-components=1
    $SUDO install -d /opt/scrcpy
    for f in scrcpy scrcpy-server scrcpy.png disconnected.png LICENSE; do
      $SUDO install -m "$([[ $f == scrcpy ]] && echo 0755 || echo 0644)" "$sct/$f" "/opt/scrcpy/$f"
    done
    $SUDO install -D -m 0644 "$sct/scrcpy.1" /usr/local/share/man/man1/scrcpy.1
    $SUDO install -d /usr/local/share/applications
    printf '#!/bin/sh\n# scrcpy from /opt/scrcpy (install.sh), with Fedora'"'"'s adb\nexport ADB=/usr/bin/adb SCRCPY_SERVER_PATH=/opt/scrcpy/scrcpy-server SCRCPY_ICON_PATH=/opt/scrcpy/scrcpy.png\nexec /opt/scrcpy/scrcpy "$@"\n' \
      | $SUDO tee /usr/local/bin/scrcpy >/dev/null
    $SUDO chmod 0755 /usr/local/bin/scrcpy
    printf '[Desktop Entry]\nType=Application\nName=scrcpy\nComment=Show and control an Android phone (USB debugging on)\nExec=scrcpy\nIcon=/opt/scrcpy/scrcpy.png\nTerminal=false\nCategories=Utility;\n' \
      | $SUDO tee /usr/local/share/applications/scrcpy.desktop >/dev/null
    echo "$SCRCPY_VERSION" | $SUDO tee /opt/scrcpy/.version >/dev/null
    rm -rf "$sct"
  fi
  # Timeshift schedules itself (its own /etc/cron.d jobs); our old fw-timeshift timer ran every check a second time.
  if [[ -e /etc/systemd/system/fw-timeshift.timer ]]; then
    [[ $CI == 1 ]] || $SUDO systemctl disable --now fw-timeshift.timer 2>/dev/null || true
    $SUDO rm -f /etc/systemd/system/fw-timeshift.timer /etc/systemd/system/fw-timeshift.service
  fi
  # Chromium follows the theme colour through its BrowserThemeColor policy: the managed-policy file is a link to a
  # file fw13.theme rewrites in the user's home (Appearance → Chromium switch); it stays "{}" until the switch is on.
  $SUDO install -d -m 0755 /etc/chromium/policies/managed
  $SUDO ln -sfn "$HOME/.config/fw13/theme/chromium-policy.json" /etc/chromium/policies/managed/fw13-theme.json
  # Memory Saver on, maximum savings, as a recommended default: chrome://settings/performance can still turn it off.
  $SUDO install -D -m 0644 system/etc/chromium/policies/recommended/fw13-memory.json /etc/chromium/policies/recommended/fw13-memory.json
  # Hide the plain "Hyprland" login entry: only "Hyprland (uwsm)" should be picked.
  $SUDO install -D -m 0644 system/usr/local/share/wayland-sessions/hyprland.desktop /usr/local/share/wayland-sessions/hyprland.desktop
  # Hyprland session for GDM/SDDM/greetd, if the package didn't ship one
  if [[ ! -e /usr/share/wayland-sessions/hyprland-uwsm.desktop ]]; then
    $SUDO install -d /usr/local/share/wayland-sessions
    $SUDO tee /usr/local/share/wayland-sessions/hyprland-uwsm.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Hyprland (uwsm)
Comment=Hyprland managed by uwsm
Exec=uwsm start hyprland.desktop
Type=Application
DesktopNames=Hyprland
EOF
  fi

  # An earlier version added "DefaultSession=hyprland-uwsm.desktop" to GDM's custom.conf. GDM 50 has no such key (it
  # remembers each user's last session instead), so take that exact line out again.
  if [[ -f /etc/gdm/custom.conf ]] && grep -qx 'DefaultSession=hyprland-uwsm.desktop' /etc/gdm/custom.conf; then
    $SUDO sed -i '/^DefaultSession=hyprland-uwsm\.desktop$/d' /etc/gdm/custom.conf
  fi

  if use_greetd; then
    say "Login: greetd + tuigreet"
    local cfg=/etc/greetd/config.toml
    $SUDO sed -i 's|^command *=.*|command = "tuigreet --time --remember --remember-session --asterisks --sessions /usr/share/wayland-sessions:/usr/local/share/wayland-sessions --cmd \\"uwsm start hyprland.desktop\\""|' "$cfg"
    local gu; gu="$(awk -F'"' '/^user *=/{print $2}' "$cfg")"
    echo "d /var/cache/tuigreet 0755 ${gu:-greetd} ${gu:-greetd} -" | $SUDO tee /etc/tmpfiles.d/tuigreet.conf >/dev/null
    if [[ $CI != 1 ]]; then
      $SUDO systemd-tmpfiles --create /etc/tmpfiles.d/tuigreet.conf
      # Only one service can own the login screen (display-manager.service): disable the old one (GDM/SDDM stay
      # installed; switch back with: sudo systemctl disable greetd && sudo systemctl enable gdm). Takes effect at boot.
      if has_dm && [[ $(current_dm) != greetd ]]; then $SUDO systemctl disable "$(current_dm).service"; fi
      $SUDO systemctl enable greetd.service
      $SUDO systemctl set-default graphical.target
    fi
  fi

  if [[ $CI == 0 ]]; then
    say "Fingerprint for sudo/login/polkit"
    $SUDO authselect enable-feature with-fingerprint || warn "authselect not available — skipping"

    say "Services"
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now bluetooth.service fwupd-refresh.timer
    $SUDO systemctl enable --now fw-health-root.timer  # root-only facts (Timeshift snapshots) for fw-health
    has_ppd || $SUDO systemctl enable --now tuned.service
    $SUDO systemctl enable --now fw-power-profile.service  # performance on AC, balanced on battery (+ udev rule)
    $SUDO systemctl enable fw-charge-limit.service  # Settings' charge limit into the Framework EC at boot (+ udev rule)
    if on ai; then $SUDO systemctl enable --now ollama.service; fi   # local models for OpenCode (fw-opencode)
    if on warp && ! skipped cloudflare-warp; then $SUDO systemctl enable --now warp-svc.service; fi  # Cloudflare WARP daemon; register/connect from the bar panel
  fi

  rpm -qa --qf '%{NAME}\n' | sort > "$STATE_DIR/rpms-after.txt"
  report
}

# Bloat report: exactly what this installer added to this machine.
report() {
  local added size
  added="$(comm -13 "$STATE_DIR/rpms-before.txt" "$STATE_DIR/rpms-after.txt")"
  size="$( [[ -n "$added" ]] && rpm -q --qf '%{SIZE}\n' $added | awk '{s+=$1} END {printf "%.2f GB", s/1024/1024/1024}' || echo 0)"
  {
    echo "# fw13-hypr install report — $(date -u +%FT%TZ), Fedora $FEDORA ${VARIANT_ID:-}"
    echo "packages on system: $(wc -l < "$STATE_DIR/rpms-after.txt")"
    echo "added by installer: $(printf '%s\n' "$added" | sed '/^$/d' | wc -l)  ($size)"
    echo
    echo "## Largest 25 added (MB)"
    [[ -n "$added" ]] && rpm -q --qf '%{SIZE} %{NAME}.%{ARCH}\n' $added | sort -rn | awk 'NR<=25 {printf "%8.1f  %s\n", $1/1048576, $2}'
    echo
    echo "## Hyprland stack provenance"
    rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE}  packager=%{PACKAGER}\n' \
      hyprland hyprlock hypridle hyprpaper hyprpolkitagent xdg-desktop-portal-hyprland uwsm 2>/dev/null || true
  } > "$STATE_DIR/install-report.txt"
  cat "$STATE_DIR/install-report.txt"
}

# ============================================================================
# Apps started as root through pkexec/sudo (Timeshift, other admin GTK tools) read root's GTK settings, not yours, so
# they'd stay plain Adwaita. Point root at your generated fw13 theme (it follows the wallpaper and light/dark): a link
# into root's theme path, root's GSettings gtk-theme (GTK on Wayland reads it before settings.ini) and a settings.ini
# fallback. User decision: always, also in the GNOME session. A theme root was given by hand is left alone.
root_theme() {
  local theme="$HOME/.local/share/themes/fw13" current
  [[ -f $theme/gtk-3.0/gtk.css ]] || { warn "no fw13 GTK theme yet (log in to Hyprland once, then re-run --user-only)"; return 0; }
  say "Admin apps (run as root) use the fw13 theme"
  $SUDO install -d -m 0755 /root/.local/share/themes /root/.config/gtk-3.0
  $SUDO ln -sfn "$theme" /root/.local/share/themes/fw13
  if ! $SUDO test -e /root/.config/gtk-3.0/settings.ini || $SUDO grep -q '^# fw13' /root/.config/gtk-3.0/settings.ini; then
    printf '# fw13: root GTK apps use the fw13 theme (install.sh root_theme)\n[Settings]\ngtk-theme-name=fw13\n' \
      | $SUDO tee /root/.config/gtk-3.0/settings.ini >/dev/null
  fi
  current="$($SUDO -H dbus-run-session -- gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null || true)"
  if [[ $current == "'Adwaita'" || $current == "'fw13'" ]]; then
    $SUDO -H dbus-run-session -- gsettings set org.gnome.desktop.interface gtk-theme fw13 \
      || warn "couldn't set root's GTK theme"
  else
    warn "root has its own GTK theme ($current): left alone"
  fi
}

user_phase() {
  say "mise tools (node, chezmoi, starship)"
  set +u; eval "$(mise activate bash)"; set -u

  say "Dotfiles (chezmoi)"
  if [[ $CI == 1 ]]; then
    mise exec chezmoi@latest -- chezmoi init --source="$SRC" --apply \
      --promptString "Chromium GOOGLE_API_KEY (blank to skip)=" \
      --promptString "Chromium GOOGLE_DEFAULT_CLIENT_ID=" \
      --promptString "Chromium GOOGLE_DEFAULT_CLIENT_SECRET=" \
      --promptString "restic repository (e.g. sftp:nas:/backup/fw13 / s3:...; blank to skip)=" \
      --promptString "restic repository password=" \
      --promptString "Ollama Cloud API key for OpenCode (blank to skip)="
  else
    mise exec chezmoi@latest -- chezmoi init --apply "$REPO_URL"
    # init doesn't pull an existing source dir; update does (no-op on a fresh install).
    # --init: also re-render chezmoi.toml from the (possibly newer) template; promptStringOnce keeps saved values and
    # asks only for keys that are new.
    mise exec chezmoi@latest -- chezmoi update --init
  fi
  mise install node
  mise install

  # Anthropic's native installer: puts the real binary in ~/.local/bin and keeps it updated itself.
  # (The npm package via mise skipped its postinstall step, leaving no binary.)
  # Older installs had Claude Code from mise (npm package, or mise's own `claude` tool); their shims would
  # shadow ~/.local/bin/claude and run an old copy that can't update itself.
  if [[ -d "$HOME/.local/share/mise/installs/npm-anthropic-ai-claude-code" ]]; then
    mise uninstall --all npm:@anthropic-ai/claude-code
  fi
  if [[ -d "$HOME/.local/share/mise/installs/claude" ]]; then
    mise uninstall --all claude
  fi
  mise reshim
  if [[ -x "$HOME/.local/bin/claude" ]]; then
    say "Claude Code already installed (updates itself)"
  else
    say "Claude Code (Anthropic native installer)"
    curl -fsSL https://claude.ai/install.sh | bash
  fi

  [[ $CI == 1 ]] && return 0

  say "Login shell"
  local choices=() s
  for s in zsh fish bash; do command -v "$s" >/dev/null && choices+=("$s"); done
  PS3="Shell [1-${#choices[@]}]: "
  select s in "${choices[@]}"; do [[ -n "${s:-}" ]] && break; done
  [[ "$(getent passwd "$USER" | cut -d: -f7)" == "$(command -v "$s")" ]] || $SUDO usermod --shell "$(command -v "$s")" "$USER"

  say "User services"
  systemctl --user enable podman.socket || true

  root_theme



  if on firewall && command -v citadel-daemon >/dev/null; then
    say "Citadel: start the service and enforce (blocks what you block or don't answer)"
    systemctl --user daemon-reload
    systemctl --user enable --now citadel.service || warn "citadel.service didn't start — check: systemctl --user status citadel"
    for _ in {1..20}; do [[ -S "$XDG_RUNTIME_DIR/citadel/daemon.sock" ]] && break; sleep 0.5; done
    citadel enforce on || warn "couldn't turn Citadel enforcement on — open Citadel → Settings → Enforcement"
  fi

  # Telegram wrote its own launcher entry while its updater was on (spec release 1); the packaged one replaces it.
  rm -f "$HOME"/.local/share/applications/org.telegram.desktop._*.desktop

  say "Flathub remote$(on localsend && echo " + LocalSend (the only approved Flathub app)")"
  flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  # LocalSend (file sharing to nearby devices) isn't in Fedora; user-approved Flathub app. Receiving needs inbound
  # 53317/tcp+udp, which the installer leaves closed (firewall untouched, user decision).
  if ! on localsend; then :
  elif skipped org.localsend.localsend_app; then echo "LocalSend: skipped (removed by you)"
  else flatpak install --user -y --noninteractive flathub org.localsend.localsend_app || warn "LocalSend (Flathub) didn't install — retry: flatpak install --user flathub org.localsend.localsend_app"; fi

  # Only when nothing is enrolled: fprintd-enroll replaces an existing print, and an interrupted run leaves none.
  if ! fprintd-list "$USER" 2>/dev/null | grep -q ' - #[0-9]' && ask "Enroll a fingerprint now?"; then fprintd-enroll || warn "fingerprint enroll failed — retry later: fprintd-enroll"; fi
  if ask "Set up Timeshift snapshots now?"; then $SUDO fw-timeshift-setup || warn "retry later: sudo fw-timeshift-setup"; fi

  say "Firmware (LVFS)"
  fwupdmgr refresh --force >/dev/null 2>&1 || true
  fwupdmgr get-updates || true
}

[[ $DO_SYSTEM == 1 ]] && system_phase
[[ $DO_USER == 1 ]] && user_phase

bare_install && recommend_gnome
say "Done. Reboot, then pick 'Hyprland (uwsm)' at the login screen.  Report: $STATE_DIR/install-report.txt"

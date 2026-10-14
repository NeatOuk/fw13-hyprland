# Claude Desktop: Anthropic's official Linux build (published only as a .deb for Ubuntu/Debian), repackaged as an RPM
# by install.sh (group claude-desktop; version + sha256 pinned there). Source0 is the .deb from Anthropic's apt pool
# (downloads.claude.ai/claude-desktop/apt/stable/pool/main/c/claude-desktop/). Its maintainer scripts are not run:
# they register the apt repo and an Ubuntu AppArmor profile (nothing to do on Fedora); the GNOME search provider and
# the MIME types they copy are shipped as files here. chrome-sandbox keeps 0755: Fedora allows unprivileged user
# namespaces, so Chromium's namespace sandbox works without the SUID helper. No self-updater on Linux; updates come
# from bumping the pin in install.sh. Cowork's QEMU, OVMF and virtiofsd come from packages/73-cowork.txt (same group).
%global debug_package %{nil}
%global __strip /bin/true
%global _build_id_links none
%global __brp_check_rpaths %{nil}
# ~600 MB of payload: fast zstd, not Fedora's level 19 (minutes of CPU for a package that never leaves this machine)
%global _binary_payload w3.zstdio
# Bundled Electron libraries (libffmpeg, libvulkan, swiftshader) must not become package provides/requires
%global __provides_exclude_from ^/usr/lib/claude-desktop/.*$
%global __requires_exclude_from ^/usr/lib/claude-desktop/.*$

Name:           claude-desktop-official
Version:        %{cd_version}
Release:        1%{?dist}
Summary:        Claude Desktop (Anthropic's official build)
License:        LicenseRef-Anthropic-Proprietary
URL:            https://code.claude.com/docs/en/desktop-linux
ExclusiveArch:  x86_64
Source0:        claude-desktop_%{cd_version}_amd64.deb
BuildRequires:  binutils
# The .deb's Depends, by their Fedora names
Requires:       gtk3 libnotify nss xdg-utils at-spi2-core libdrm mesa-libgbm libxcb libsecret glib2 libXtst libuuid
Requires:       pipewire-libs xdg-desktop-portal hicolor-icon-theme
# Anthropic's own RPM, should one ship: one or the other
Conflicts:      claude-desktop

%description
Claude Desktop (Chat, Cowork, Claude Code), the official Linux build from Anthropic, packaged so dnf tracks and
removes it. Re-run the fw13-hyprland installer to update.

%prep
%setup -q -c -T
ar x %{SOURCE0}
tar -xf data.tar.*

%build

%install
cp -a usr %{buildroot}/
rm -rf %{buildroot}%{_datadir}/lintian
chmod 0755 %{buildroot}/usr/lib/claude-desktop/chrome-sandbox
res=%{buildroot}/usr/lib/claude-desktop/resources
install -Dm0644 $res/gnome-search-provider/com.anthropic.Claude.search-provider.ini \
  %{buildroot}%{_datadir}/gnome-shell/search-providers/com.anthropic.Claude.search-provider.ini
install -Dm0644 $res/gnome-search-provider/com.anthropic.Claude.SearchProvider.service \
  %{buildroot}%{_datadir}/dbus-1/services/com.anthropic.Claude.SearchProvider.service
install -Dm0644 $res/linux-mime/com.anthropic.Claude.xml %{buildroot}%{_datadir}/mime/packages/com.anthropic.Claude.xml
# `ccd` terminal launcher, when the build ships one (the .deb's postinst links it the same way)
if [ -x $res/bin/ccd ]; then ln -s ../lib/claude-desktop/resources/bin/ccd %{buildroot}%{_bindir}/ccd; fi
# file list: everything installed (the ccd link only exists in some builds)
(cd %{buildroot} && find . -mindepth 1 \( -type f -o -type l \) | sed 's|^\.||' | grep -v '^/usr/lib/claude-desktop/') \
  > %{_builddir}/files.list

%files -f %{_builddir}/files.list
/usr/lib/claude-desktop

%changelog
* Wed Oct 14 2026 fw13-hyprland - %{cd_version}-1
- Official .deb repackaged (maintainer scripts' apt/AppArmor parts dropped, search provider + MIME types as files)

# Obsidian: the official Linux .deb from github.com/obsidianmd/obsidian-releases, repackaged as an RPM by install.sh
# (group obsidian; version + sha256 pinned there, the sha256 is GitHub's asset digest). The .deb's maintainer scripts
# are not run: they link /usr/bin/obsidian (done here), pick the SUID sandbox only without user namespaces (Fedora has
# them: chrome-sandbox keeps 0755) and load an Ubuntu AppArmor profile (nothing to do on Fedora). Obsidian updates its
# own app files in-app (into ~/.config/obsidian); a pin bump updates the Electron shell around them.
%global debug_package %{nil}
%global __strip /bin/true
%global _build_id_links none
%global __brp_check_rpaths %{nil}
%global _binary_payload w3.zstdio
# Bundled Electron libraries must not become package provides/requires
%global __provides_exclude_from ^/opt/Obsidian/.*$
%global __requires_exclude_from ^/opt/Obsidian/.*$

Name:           obsidian-official
Version:        %{ob_version}
Release:        1%{?dist}
Summary:        Obsidian (the official build from obsidian.md)
License:        LicenseRef-Obsidian-Proprietary
URL:            https://obsidian.md
ExclusiveArch:  x86_64
Source0:        obsidian_%{ob_version}_amd64.deb
BuildRequires:  binutils
# The .deb's Depends, by their Fedora names (Recommends libappindicator3 left out: the tray icon isn't needed)
Requires:       gtk3 libnotify nss libXScrnSaver libXtst xdg-utils at-spi2-core libuuid libsecret
# Obsidian's own RPM, should one ship: one or the other
Conflicts:      obsidian

%description
Obsidian, the Markdown knowledge base, as built by Obsidian (Dynalist Inc.), packaged so dnf tracks and removes it.
Re-run the fw13-hyprland installer to update the app shell; Obsidian updates its own core in-app.

%prep
%setup -q -c -T
ar x %{SOURCE0}
tar -xf data.tar.*

%build

%install
cp -a usr opt %{buildroot}/
rm -rf %{buildroot}%{_datadir}/doc/obsidian
chmod 0755 %{buildroot}/opt/Obsidian/chrome-sandbox
rm -f %{buildroot}/opt/Obsidian/resources/apparmor-profile
install -d %{buildroot}%{_bindir}
ln -s /opt/Obsidian/obsidian %{buildroot}%{_bindir}/obsidian
(cd %{buildroot} && find . -mindepth 1 \( -type f -o -type l \) | sed 's|^\.||' | grep -v '^/opt/Obsidian/') \
  > %{_builddir}/files.list

%files -f %{_builddir}/files.list
/opt/Obsidian

%changelog
* Sun Oct 18 2026 fw13-hyprland - %{ob_version}-1
- Official .deb repackaged (maintainer scripts' alternatives/AppArmor parts dropped, /usr/bin/obsidian as a link)

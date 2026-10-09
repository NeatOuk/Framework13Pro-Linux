# Ghostty: built from the official, minisign-signed release tarball (release.files.ghostty.org) by install.sh
# (build_ghostty_rpm), which checks the tarball against a pinned sha256 and builds with the exact Zig the release
# asks for (minimum_zig_version in build.zig.zon), downloaded from ziglang.org and checked against its index.json.
# Ghostty itself publishes no Linux packages; Fedora only has community builds (COPR, Terra).
%global debug_package %{nil}
%global _build_id_links none

Name:           ghostty-official
Version:        %{gh_version}
Release:        1%{?dist}
Summary:        Ghostty terminal emulator (built from the official release)
License:        MIT
URL:            https://ghostty.org/
ExclusiveArch:  x86_64
Source0:        ghostty-%{version}.tar.gz
# The COPR/Terra builds of the same app: one or the other, never both (same binary, desktop entry, D-Bus name)
Conflicts:      ghostty

%description
Ghostty, built from the official signed release tarball and packaged so dnf tracks and removes it.
Re-run the fw13-hyprland installer to update.

%prep
%setup -q -n ghostty-%{version}

%build
# Dependencies come from Zig's package cache (filled from the network on the first build, reused after).
export ZIG_GLOBAL_CACHE_DIR=%{zig_cache}
DESTDIR=%{_builddir}/ghostty-root %{zig} build --prefix %{_prefix} -Doptimize=ReleaseFast -Dcpu=baseline

%install
cp -a %{_builddir}/ghostty-root/. %{buildroot}/
# Fedora's ncurses-term may already ship Ghostty's terminfo: keep the system's copy instead of a file conflict.
find %{buildroot}%{_datadir}/terminfo -type f 2>/dev/null | while read -r f; do
  rel=${f#%{buildroot}}
  if [ -e "$rel" ] && ! rpm -qf "$rel" 2>/dev/null | grep -q '^ghostty-official-'; then rm -f "$f"; fi
done
# Everything Ghostty installs, except its own data folder (owned whole below)
( cd %{buildroot} && find . \( -type f -o -type l \) ! -path './usr/share/ghostty/*' | sed 's|^\.||' ) > %{_builddir}/ghostty.files

%files -f %{_builddir}/ghostty.files
%{_datadir}/ghostty

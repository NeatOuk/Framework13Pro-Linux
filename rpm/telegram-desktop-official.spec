# Telegram Desktop: the official binary from telegram.org, repackaged as an RPM by install.sh (build_telegram_rpm).
# Source0 is telegram.org's own build (td.telegram.org/linux-x64/td-setup-linux-x64-<version>.tar.xz); the launcher entry,
# D-Bus service and icons come from Telegram's repo (github.com/telegramdesktop/tdesktop) at the same tag.
# Telegram's self-updater is turned off through its externalupdater.d hook (the binary lives in root-owned /opt, so it
# couldn't update itself anyway); updates come from re-running install.sh, which rebuilds when telegram.org has a newer one.
%global debug_package %{nil}
%global __strip /bin/true
%global _build_id_links none
%global __brp_check_rpaths %{nil}

Name:           telegram-desktop-official
Version:        %{tg_version}
Release:        1%{?dist}
Summary:        Telegram Desktop (official telegram.org build)
License:        GPL-3.0-only WITH OpenSSL-exception
URL:            https://desktop.telegram.org/
ExclusiveArch:  x86_64
Source0:        td-setup-linux-x64-%{version}.tar.xz
Source1:        org.telegram.desktop.desktop
Source2:        org.telegram.desktop.service
Source3:        icon16.png
Source4:        icon32.png
Source5:        icon48.png
Source6:        icon64.png
Source7:        icon128.png
Source8:        icon256.png
Source9:        icon512.png
Requires:       hicolor-icon-theme
# RPM Fusion's build of the same app: one or the other, never both (same binary name, launcher and D-Bus name)
Conflicts:      telegram-desktop

%description
Telegram Desktop, the official build published on telegram.org, packaged so dnf tracks and removes it.
Its built-in updater is disabled; re-run the fw13-hyprland installer to update.

%prep
%setup -q -n Telegram

%build

%install
install -Dm0755 Telegram %{buildroot}/opt/telegram/Telegram
install -d %{buildroot}%{_bindir}
ln -s /opt/telegram/Telegram %{buildroot}%{_bindir}/Telegram
install -Dm0644 %{SOURCE1} %{buildroot}%{_datadir}/applications/org.telegram.desktop.desktop
install -Dm0644 %{SOURCE2} %{buildroot}%{_datadir}/dbus-1/services/org.telegram.desktop.service
install -Dm0644 %{SOURCE3} %{buildroot}%{_datadir}/icons/hicolor/16x16/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE4} %{buildroot}%{_datadir}/icons/hicolor/32x32/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE5} %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE6} %{buildroot}%{_datadir}/icons/hicolor/64x64/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE7} %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE8} %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/org.telegram.desktop.png
install -Dm0644 %{SOURCE9} %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/org.telegram.desktop.png
# Telegram skips its own updater for the executables listed here (it checks the XDG config dirs and /etc)
for d in %{_sysconfdir}/tdesktop %{_sysconfdir}/xdg/tdesktop; do
  install -d %{buildroot}$d/externalupdater.d
  printf '%s\n' /opt/telegram/Telegram %{_bindir}/Telegram > %{buildroot}$d/externalupdater.d/telegram-desktop-official.conf
done

%files
/opt/telegram
%{_bindir}/Telegram
%{_datadir}/applications/org.telegram.desktop.desktop
%{_datadir}/dbus-1/services/org.telegram.desktop.service
%{_datadir}/icons/hicolor/*/apps/org.telegram.desktop.png
%config(noreplace) %{_sysconfdir}/tdesktop/externalupdater.d/telegram-desktop-official.conf
%config(noreplace) %{_sysconfdir}/xdg/tdesktop/externalupdater.d/telegram-desktop-official.conf
%dir %{_sysconfdir}/tdesktop
%dir %{_sysconfdir}/tdesktop/externalupdater.d
%dir %{_sysconfdir}/xdg/tdesktop
%dir %{_sysconfdir}/xdg/tdesktop/externalupdater.d

%changelog
* Thu Oct 08 2026 fw13-hyprland - %{tg_version}-1
- Official telegram.org build, repackaged

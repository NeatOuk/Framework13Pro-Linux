#!/usr/bin/env bash
# Runs inside the image build. Fails loudly if any package is missing,
# so a renamed/retired package is caught at build time, never on the laptop.
set -euxo pipefail

FEDORA="$(rpm -E %fedora)"
pkgs() { grep -hv '^\s*#' "$@" | tr -s ' \t' '\n' | sed '/^$/d'; }

# --- Debloat: never pull weak (optional) dependencies ---------------------
# Anything needed is listed explicitly in packages/*.txt.
dnf config-manager setopt install_weak_deps=False 2>/dev/null \
  || echo 'install_weak_deps=False' >> /etc/dnf/dnf.conf

# --- Repositories ---------------------------------------------------------
dnf -y install dnf5-plugins

dnf -y install \
  "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA}.noarch.rpm" \
  "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA}.noarch.rpm"

dnf config-manager setopt fedora-cisco-openh264.enabled=1 || true

if [[ -n "${HYPR_COPR:-}" ]]; then
  dnf -y copr enable "${HYPR_COPR}"
fi

# --- Packages -------------------------------------------------------------
cd /tmp/packages
dnf -y install $(pkgs 00-core.txt)
dnf -y install $(pkgs 10-desktop.txt 20-input-fonts.txt 30-apps.txt 60-framework.txt 70-dev.txt 80-shells.txt 90-backup.txt)
dnf -y install $(pkgs 40-gaming.txt)
dnf -y install --allowerasing $(pkgs 50-codecs.txt)

# --- Login: greetd + tuigreet -> uwsm -> Hyprland --------------------------
GREETD_CFG=/etc/greetd/config.toml
sed -i 's|^command *=.*|command = "tuigreet --time --remember --remember-session --asterisks --sessions /usr/share/wayland-sessions --cmd \\"uwsm start hyprland.desktop\\""|' "$GREETD_CFG"
GREETER_USER="$(awk -F'"' '/^user *=/{print $2}' "$GREETD_CFG")"
echo "d /var/cache/tuigreet 0755 ${GREETER_USER:-greetd} ${GREETER_USER:-greetd} -" \
  > /usr/lib/tmpfiles.d/tuigreet.conf

# --- Fingerprint for sudo / login / polkit --------------------------------
if command -v authselect >/dev/null; then
  authselect current >/dev/null 2>&1 || authselect select local --force
  authselect enable-feature with-fingerprint
fi

# --- Services -------------------------------------------------------------
systemctl set-default graphical.target
systemctl enable greetd.service NetworkManager.service bluetooth.service tuned.service \
                 fwupd-refresh.timer fw-timeshift.timer
systemctl --global enable podman.socket   # Docker-API socket for tools that expect Docker

# --- Manifest: provenance + bloat report ---------------------------------
M=/usr/share/fw13-hypr-manifest.txt
{
  echo "# fw13-hypr image manifest — built $(date -u +%FT%TZ), Fedora ${FEDORA}, HYPR_COPR=${HYPR_COPR:-none}"
  echo
  echo "## Totals"
  echo "packages: $(rpm -qa | wc -l)  (i686: $(rpm -qa --qf '%{ARCH}\n' | grep -c i686))"
  echo "installed size: $(rpm -qa --qf '%{SIZE}\n' | awk '{s+=$1} END {printf "%.2f GB", s/1024/1024/1024}')"
  echo
  echo "## Largest 30 packages (MB)"
  rpm -qa --qf '%{SIZE} %{NAME}.%{ARCH}\n' | sort -rn | head -30 | awk '{printf "%8.1f  %s\n", $1/1048576, $2}'
  echo
  echo "## Size by source repo (MB)"
  dnf repoquery --installed --qf '%{from_repo} %{size}\n' 2>/dev/null \
    | awk '{s[$1]+=$2} END {for (r in s) printf "%8.1f  %s\n", s[r]/1048576, r}' | sort -rn
  echo
  echo "## Hyprland stack provenance"
  rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE}  vendor=%{VENDOR}  packager=%{PACKAGER}\n' \
    $(pkgs 10-desktop.txt | grep -E '^(hypr|xdg-desktop-portal-hyprland|uwsm)')
} > "$M"
cat "$M"

dnf clean all

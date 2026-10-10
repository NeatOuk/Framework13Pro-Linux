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
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/NeatOuk/fw13-hyprland}"
CHECKOUT="${CHECKOUT:-$HOME/.local/share/fw13-hypr}"
HYPR_COPR="${HYPR_COPR-lionheartp/Hyprland}"
# Citadel outbound firewall + its root helper: built from the owner's repos as RPMs (no prebuilt packages).
CITADEL_APP_REPO="${CITADEL_APP_REPO:-https://github.com/NeatOuk/citadel-app.git}"
CITADEL_APP_REF="${CITADEL_APP_REF:-main}"
CITADEL_HELPER_REPO="${CITADEL_HELPER_REPO:-https://github.com/NeatOuk/citadel-helper.git}"
CITADEL_HELPER_REF="${CITADEL_HELPER_REF:-v1.3.2}"
# Ghostty (Settings → fw13 → Terminal): built from the official release tarball. The sha256 is pinned per version
# (checked once against the release's minisign signature, key in Ghostty's PACKAGING.md). GHOSTTY=0 skips it.
GHOSTTY="${GHOSTTY:-1}"
GHOSTTY_VERSION="${GHOSTTY_VERSION:-1.3.1}"
GHOSTTY_SHA256="${GHOSTTY_SHA256:-3349d25600ffbda281197a18314f7d18791969cffe9474f0ff16a45a9ebfccdb}"
STATE_DIR="$HOME/.local/state/fw13-hypr"

YES=0 CI=0 DO_SYSTEM=1 DO_USER=1
for a in "$@"; do
  case "$a" in
    --yes) YES=1 ;;
    --ci) CI=1; YES=1 ;;
    --system-only) DO_USER=0 ;;
    --user-only) DO_SYSTEM=0 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx %s\033[0m\n' "$*"; exit 1; }
ask()  { [[ $YES == 1 ]] && return 0; read -rp "$1 [Y/n] " r; [[ "${r,,}" != n ]]; }
pkgs() { grep -hv '^\s*#' "$@" | tr -s ' \t' '\n' | sed '/^$/d'; }
SUDO=sudo; [[ $EUID -eq 0 ]] && SUDO=""

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

cat <<EOF

fw13-hypr installer — Fedora ${FEDORA} (${VARIANT_ID:-${VARIANT:-unknown edition}})
  Adds repos:   RPM Fusion free+nonfree, COPR ${HYPR_COPR:-<none>}, Microsoft (VS Code), mise, Devolutions (RDM)
  Login screen: $(if ! use_greetd; then echo "keep existing $(current_dm) — adds a 'Hyprland (uwsm)' session (KEEP_DM=1)"; elif has_dm && [[ $(current_dm) != greetd ]]; then echo "greetd + tuigreet text login; disables $(current_dm) (not removed; KEEP_DM=1 keeps it)"; else echo "greetd + tuigreet text login"; fi)
  Power:        $(has_ppd && echo "keep power-profiles-daemon" || echo "install tuned + tuned-ppd")
  Removes:      nothing (ffmpeg-free is swapped for RPM Fusion ffmpeg)
EOF
ask "Continue?" || exit 0

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
  $SUDO install -m 0644 repos/*.repo /etc/yum.repos.d/

  say "Packages (weak dependencies off — only what's listed)"
  local lists=(00-core.txt 10-desktop.txt 20-input-fonts.txt 30-apps.txt 60-framework.txt 70-dev.txt 80-shells.txt 90-backup.txt 95-citadel.txt 96-theme.txt 97-warp.txt)
  use_greetd && lists+=(15-login.txt)
  has_ppd || lists+=(61-power.txt)
  [[ $GHOSTTY == 0 ]] || lists+=(98-ghostty.txt)
  local main gaming codecs
  mapfile -t main   < <(cd packages && pkgs "${lists[@]}")
  mapfile -t gaming < <(cd packages && pkgs 40-gaming.txt)
  mapfile -t codecs < <(cd packages && pkgs 50-codecs.txt)
  $DNF install "${main[@]}"
  $DNF install "${gaming[@]}"
  $DNF install --allowerasing "${codecs[@]}"
  # matugen (wallpaper → Material You colours): fw13.theme needs 4.x (--prefer, -t scheme-*, colors[role][mode]).
  # Fedora 44 ships 3.1.0, which rejects those flags, so the version is pinned: a COPR without matugen 4
  # fails here loudly instead of quietly installing Fedora's. lionheartp/Hyprland has 4.2.0.
  if [[ -n "$HYPR_COPR" ]]; then
    $DNF install 'matugen >= 4'
  else
    warn "HYPR_COPR is empty: no matugen 4 (Fedora's 3.1.0 is too old), so the theme stays Tokyo Night"
  fi

  say "Citadel (outbound firewall) + citadel-helper — built from source as RPMs"
  local rpms=()
  mapfile -t rpms < <(build_citadel_rpm citadel-app "$CITADEL_APP_REPO" "$CITADEL_APP_REF" linux/packaging/rpm/citadel.spec
                      build_citadel_rpm citadel-helper "$CITADEL_HELPER_REPO" "$CITADEL_HELPER_REF" packaging/rpm/citadel-helper.spec)
  (( ${#rpms[@]} == 2 )) || die "Citadel RPM build failed (see above)"
  $DNF install "${rpms[@]}"   # same version: no-op; newer build: upgrade

  say "Telegram Desktop — official telegram.org build, packaged as an RPM"
  local tg
  tg="$(build_telegram_rpm)" || die "Telegram RPM build failed (see above)"
  if [[ -n $tg ]]; then $DNF install "$tg"; else echo "telegram-desktop-official is current"; fi

  if [[ $GHOSTTY != 0 ]]; then
    say "Ghostty — built from the official release (Settings → fw13 → Terminal)"
    local gt
    gt="$(build_ghostty_rpm)" || die "Ghostty RPM build failed (see above)"
    if [[ -n $gt ]]; then $DNF install "$gt"; else echo "ghostty-official is current"; fi
  fi

  say "System files"
  $SUDO install -m 0755 system/usr/local/bin/* /usr/local/bin/
  compgen -G 'system/etc/systemd/system/*' >/dev/null && $SUDO install -m 0644 system/etc/systemd/system/* /etc/systemd/system/
  $SUDO install -m 0644 system/etc/udev/rules.d/* /etc/udev/rules.d/   # charger plug / unplug → fw-power-profile
  $SUDO install -m 0644 system/etc/modprobe.d/* /etc/modprobe.d/   # battery charge limit (cros_charge_control on Framework); used from the next boot
  [[ $CI == 1 ]] || $SUDO udevadm control --reload
  # Timeshift schedules itself (its own /etc/cron.d jobs); our old fw-timeshift timer ran every check a second time.
  if [[ -e /etc/systemd/system/fw-timeshift.timer ]]; then
    [[ $CI == 1 ]] || $SUDO systemctl disable --now fw-timeshift.timer 2>/dev/null || true
    $SUDO rm -f /etc/systemd/system/fw-timeshift.timer /etc/systemd/system/fw-timeshift.service
  fi
  # Chromium follows the theme colour through its BrowserThemeColor policy: the managed-policy file is a link to a
  # file fw13.theme rewrites in the user's home (Appearance → Chromium switch); it stays "{}" until the switch is on.
  $SUDO install -d -m 0755 /etc/chromium/policies/managed
  $SUDO ln -sfn "$HOME/.config/fw13/theme/chromium-policy.json" /etc/chromium/policies/managed/fw13-theme.json
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
    $SUDO systemctl enable --now ollama.service   # local models for OpenCode (fw-opencode)
    $SUDO systemctl enable --now warp-svc.service  # Cloudflare WARP daemon; register/connect from the bar panel
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



  if command -v citadel-daemon >/dev/null; then
    say "Citadel: start the service and enforce (blocks what you block or don't answer)"
    systemctl --user daemon-reload
    systemctl --user enable --now citadel.service || warn "citadel.service didn't start — check: systemctl --user status citadel"
    for _ in {1..20}; do [[ -S "$XDG_RUNTIME_DIR/citadel/daemon.sock" ]] && break; sleep 0.5; done
    citadel enforce on || warn "couldn't turn Citadel enforcement on — open Citadel → Settings → Enforcement"
  fi

  # Telegram wrote its own launcher entry while its updater was on (spec release 1); the packaged one replaces it.
  rm -f "$HOME"/.local/share/applications/org.telegram.desktop._*.desktop

  say "Flathub remote + LocalSend (the only approved Flathub app)"
  flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  # LocalSend (file sharing to nearby devices) isn't in Fedora; user-approved Flathub app. Receiving needs inbound
  # 53317/tcp+udp, which the installer leaves closed (firewall untouched, user decision).
  flatpak install --user -y --noninteractive flathub org.localsend.localsend_app || warn "LocalSend (Flathub) didn't install — retry: flatpak install --user flathub org.localsend.localsend_app"

  # Only when nothing is enrolled: fprintd-enroll replaces an existing print, and an interrupted run leaves none.
  if ! fprintd-list "$USER" 2>/dev/null | grep -q ' - #[0-9]' && ask "Enroll a fingerprint now?"; then fprintd-enroll || warn "fingerprint enroll failed — retry later: fprintd-enroll"; fi
  if ask "Set up Timeshift snapshots now?"; then $SUDO fw-timeshift-setup || warn "retry later: sudo fw-timeshift-setup"; fi

  say "Firmware (LVFS)"
  fwupdmgr refresh --force >/dev/null 2>&1 || true
  fwupdmgr get-updates || true
}

[[ $DO_SYSTEM == 1 ]] && system_phase
[[ $DO_USER == 1 ]] && user_phase

say "Done. Reboot, then pick 'Hyprland (uwsm)' at the login screen.  Report: $STATE_DIR/install-report.txt"

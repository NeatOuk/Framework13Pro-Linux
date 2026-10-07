#!/usr/bin/env bash
# fw13-hypr installer — Hyprland desktop for Fedora (Workstation, KDE, any spin, or Minimal).
# Run as your normal user (it uses sudo where needed). Safe to re-run.
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/NeatOuk/Framework13Pro-Linux/main/install.sh)
#
# Flags:
#   --yes           don't ask for confirmation
#   --ci            non-interactive test mode (containers): skips services, fingerprint,
#                   Timeshift, shell change, Flathub; applies dotfiles from the local checkout
#   --system-only   only the sudo part (packages, repos, system files)
#   --user-only     only the per-user part (dotfiles, mise, shell)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/NeatOuk/Framework13Pro-Linux}"
CHECKOUT="${CHECKOUT:-$HOME/.local/share/fw13-hypr}"
HYPR_COPR="${HYPR_COPR-lionheartp/Hyprland}"
# Citadel outbound firewall + its root helper: built from the owner's repos as RPMs (no prebuilt packages).
CITADEL_APP_REPO="${CITADEL_APP_REPO:-https://github.com/NeatOuk/citadel-app.git}"
CITADEL_APP_REF="${CITADEL_APP_REF:-main}"
CITADEL_HELPER_REPO="${CITADEL_HELPER_REPO:-https://github.com/NeatOuk/citadel-helper.git}"
CITADEL_HELPER_REF="${CITADEL_HELPER_REF:-v1.3.2}"
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
has_ppd() { rpm -q power-profiles-daemon >/dev/null 2>&1; }

cat <<EOF

fw13-hypr installer — Fedora ${FEDORA} (${VARIANT_ID:-${VARIANT:-unknown edition}})
  Adds repos:   RPM Fusion free+nonfree, COPR ${HYPR_COPR:-<none>}, Microsoft (VS Code), mise
  Login screen: $(has_dm && echo "keep existing $(readlink -f /etc/systemd/system/display-manager.service | xargs basename) — adds a 'Hyprland (uwsm)' session" || echo "install greetd + tuigreet")
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
  local lists=(00-core.txt 10-desktop.txt 20-input-fonts.txt 30-apps.txt 60-framework.txt 70-dev.txt 80-shells.txt 90-backup.txt 95-citadel.txt)
  has_dm  || lists+=(15-login.txt)
  has_ppd || lists+=(61-power.txt)
  local main gaming codecs
  mapfile -t main   < <(cd packages && pkgs "${lists[@]}")
  mapfile -t gaming < <(cd packages && pkgs 40-gaming.txt)
  mapfile -t codecs < <(cd packages && pkgs 50-codecs.txt)
  $DNF install "${main[@]}"
  $DNF install "${gaming[@]}"
  $DNF install --allowerasing "${codecs[@]}"

  say "Citadel (outbound firewall) + citadel-helper — built from source as RPMs"
  local rpms=()
  mapfile -t rpms < <(build_citadel_rpm citadel-app "$CITADEL_APP_REPO" "$CITADEL_APP_REF" linux/packaging/rpm/citadel.spec
                      build_citadel_rpm citadel-helper "$CITADEL_HELPER_REPO" "$CITADEL_HELPER_REF" packaging/rpm/citadel-helper.spec)
  (( ${#rpms[@]} == 2 )) || die "Citadel RPM build failed (see above)"
  $DNF install "${rpms[@]}"   # same version: no-op; newer build: upgrade

  say "System files"
  $SUDO install -m 0755 system/usr/local/bin/* /usr/local/bin/
  $SUDO install -m 0644 system/etc/systemd/system/* /etc/systemd/system/
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

  if ! has_dm; then
    say "Login: greetd + tuigreet"
    local cfg=/etc/greetd/config.toml
    $SUDO sed -i 's|^command *=.*|command = "tuigreet --time --remember --remember-session --asterisks --sessions /usr/share/wayland-sessions:/usr/local/share/wayland-sessions --cmd \\"uwsm start hyprland.desktop\\""|' "$cfg"
    local gu; gu="$(awk -F'"' '/^user *=/{print $2}' "$cfg")"
    echo "d /var/cache/tuigreet 0755 ${gu:-greetd} ${gu:-greetd} -" | $SUDO tee /etc/tmpfiles.d/tuigreet.conf >/dev/null
    [[ $CI == 1 ]] || { $SUDO systemd-tmpfiles --create /etc/tmpfiles.d/tuigreet.conf; $SUDO systemctl enable greetd.service; $SUDO systemctl set-default graphical.target; }
  fi

  if [[ $CI == 0 ]]; then
    say "Fingerprint for sudo/login/polkit"
    $SUDO authselect enable-feature with-fingerprint || warn "authselect not available — skipping"

    say "Services"
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now bluetooth.service fwupd-refresh.timer fw-timeshift.timer
    has_ppd || $SUDO systemctl enable --now tuned.service
    $SUDO systemctl enable --now ollama.service   # local models for OpenCode (fw-opencode)
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
user_phase() {
  say "mise tools (node, chezmoi, starship)"
  set +u; eval "$(mise activate bash)"; set -u

  say "Dotfiles (chezmoi)"
  if [[ $CI == 1 ]]; then
    mise exec chezmoi@latest -- chezmoi init --source="$SRC" --apply \
      --promptString "Chromium GOOGLE_API_KEY (blank to skip)=" \
      --promptString "Chromium GOOGLE_DEFAULT_CLIENT_ID=" \
      --promptString "Chromium GOOGLE_DEFAULT_CLIENT_SECRET=" \
      --promptString "restic repository (e.g. sftp:nas:/backup/fw13 / s3:... / b2:...; blank to skip)=" \
      --promptString "restic repository password=" \
      --promptString "Ollama Cloud API key for OpenCode (blank to skip)="
  else
    mise exec chezmoi@latest -- chezmoi init --apply "$REPO_URL"
    # init doesn't pull an existing source dir; update does (no-op on a fresh install).
    mise exec chezmoi@latest -- chezmoi update
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

  if command -v citadel-daemon >/dev/null; then
    say "Citadel: start the service and enforce (blocks what you block or don't answer)"
    systemctl --user daemon-reload
    systemctl --user enable --now citadel.service || warn "citadel.service didn't start — check: systemctl --user status citadel"
    for _ in {1..20}; do [[ -S "$XDG_RUNTIME_DIR/citadel/daemon.sock" ]] && break; sleep 0.5; done
    citadel enforce on || warn "couldn't turn Citadel enforcement on — open Citadel → Settings → Enforcement"
  fi

  say "Flathub remote (no apps installed)"
  flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

  if ask "Enroll a fingerprint now?"; then fprintd-enroll || warn "fingerprint enroll failed — retry later: fprintd-enroll"; fi
  if ask "Set up Timeshift snapshots now?"; then $SUDO fw-timeshift-setup || warn "retry later: sudo fw-timeshift-setup"; fi

  say "Firmware (LVFS)"
  fwupdmgr refresh --force >/dev/null 2>&1 || true
  fwupdmgr get-updates || true
}

[[ $DO_SYSTEM == 1 ]] && system_phase
[[ $DO_USER == 1 ]] && user_phase

say "Done. Reboot, then pick 'Hyprland (uwsm)' at the login screen.  Report: $STATE_DIR/install-report.txt"

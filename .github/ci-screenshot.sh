#!/usr/bin/env bash
# Runs inside a privileged fedora:44 container with the host's vkms /dev/dri.
# Installs, starts Hyprland as root (container), launches the autostart apps by hand
# (no systemd → no uwsm), and saves shot/desktop.png + logs.
set -euo pipefail
mkdir -p shot
dnf -y -q install git
./install.sh --ci > shot/install.log 2>&1 || { tail -50 shot/install.log; exit 1; }

export XDG_RUNTIME_DIR=/tmp/xdg LIBSEAT_BACKEND=noop
install -d -m 0700 "$XDG_RUNTIME_DIR"
ls -l /dev/dri

# Try the vkms DRM output first, then the headless backend.
start_hyprland() {
  [[ -n ${hypr_pid:-} ]] && kill "$hypr_pid" 2>/dev/null || true
  rm -rf "$XDG_RUNTIME_DIR"/hypr "$XDG_RUNTIME_DIR"/wayland-*
  env "$2" Hyprland --i-am-really-stupid > "shot/hyprland-$1.log" 2>&1 &
  hypr_pid=$!
  local _
  for _ in $(seq 20); do
    sigs=("$XDG_RUNTIME_DIR"/hypr/*/.socket.sock)
    [[ -e ${sigs[0]} ]] && return 0
    sleep 1
  done
  return 1
}
if start_hyprland drm FW_CI=1; then
  echo "Hyprland up on vkms (DRM)"
elif start_hyprland headless HYPRLAND_HEADLESS_ONLY=1; then
  echo "Hyprland up on headless backend"
  hyprctl_headless=1
else
  tail -20 shot/hyprland-*.log; cat /root/.cache/hyprland/hyprlandCrashReport*.txt 2>/dev/null | head -40
  exit 1
fi

HYPRLAND_INSTANCE_SIGNATURE="$(basename "$(dirname "${sigs[0]}")")"
export HYPRLAND_INSTANCE_SIGNATURE
[[ -n ${hyprctl_headless:-} ]] && hyprctl output create headless
for app in hyprpaper waybar mako kitty; do hyprctl dispatch exec "$app"; done
sleep 10
hyprctl monitors > shot/monitors.txt
socks=("$XDG_RUNTIME_DIR"/wayland-[0-9])  # skip the .lock file
WAYLAND_DISPLAY="$(basename "${socks[0]}")" grim shot/desktop.png
echo "saved shot/desktop.png"

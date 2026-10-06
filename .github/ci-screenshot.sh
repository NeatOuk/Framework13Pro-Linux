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
mapfile -t outputs < <(hyprctl monitors | awk '/^Monitor/{print $2}')
for o in "${outputs[@]}"; do hyprctl keyword monitor "$o,1920x1080@60,auto,1"; done
sleep 2  # let the mode change settle before clients bind outputs
socks=("$XDG_RUNTIME_DIR"/wayland-[0-9])  # skip the .lock file
export WAYLAND_DISPLAY="${socks[0]##*/}"
# No systemd user session in the container → start a session bus for waybar/mako
# with what's already installed (dbus-broker + systemd-socket-activate).
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemd-socket-activate -l "$XDG_RUNTIME_DIR/bus" dbus-broker-launch --scope user > shot/dbus.log 2>&1 &
sleep 1
for app in hyprpaper waybar mako kitty; do "$app" > "shot/$app.log" 2>&1 & done
sleep 10
for app in hyprpaper waybar mako kitty; do
  if [[ -n "$(hyprctl clients | grep -i "class: $app" || true)$(hyprctl layers | grep -i "namespace: $app" || true)" ]]; then echo "running  $app"; else echo "NOT VISIBLE $app"; fi
done | tee shot/apps.txt
hyprctl monitors > shot/monitors.txt
ok=0
for o in "${outputs[@]}"; do
  if timeout 30 grim -o "$o" "shot/desktop-$o.png"; then echo "saved shot/desktop-$o.png"; ok=1
  else echo "grim timed out/failed on $o"; fi
done
(( ok ))
hyprctl configerrors | tee shot/configerrors.txt
# A clean config prints nothing (or a blank line).
[[ -z "$(tr -d '[:space:]' < shot/configerrors.txt)" ]] || { echo "Hyprland config errors above"; exit 1; }

-- mako (notifications) is not started here: its systemd unit (mako.service, enabled by
-- run_onchange_after_session-services.sh) follows graphical-session.target under uwsm.
hl.on("hyprland.start", function()
  hl.exec_cmd("uwsm app -- waybar")
  hl.exec_cmd("uwsm app -- hyprpaper")
  hl.exec_cmd("uwsm app -- hypridle")
  hl.exec_cmd("systemctl --user start hyprpolkitagent")
  -- blueman-applet stays for its pairing agent (AuthAgent); its tray icon is off — the bar's bluetooth module
  -- replaces it. All three plugins must go: ShowConnected pulls StatusIcon back in, and StatusNotifierItem is
  -- the Wayland tray item itself. (/etc/xdg/autostart/blueman.desktop is hidden in Hyprland: dot_config/autostart.)
  hl.exec_cmd([[gsettings set org.blueman.general plugin-list "['!StatusIcon', '!StatusNotifierItem', '!ShowConnected']" && uwsm app -- blueman-applet]])
  hl.exec_cmd("uwsm app -- fcitx5 -d --replace")
  hl.exec_cmd("uwsm app -- wl-paste --watch cliphist store")
  -- Per-screen workspace ranges + login layout (kitty on the laptop's 1, Chromium on the monitor's 1)
  hl.exec_cmd("uwsm app -- fw-workspaces daemon")
  -- GNOME's apps hidden from the launcher in Hyprland only; Thunar / Chromium / GNOME viewers as defaults
  -- (~/.config/hyprland-mimeapps.list). Rerun at each login so package updates are picked up (fw13.defaultapps).
  hl.exec_cmd("env PYTHONPATH=$HOME/.local/lib python3 -m fw13.defaultapps")
  -- First Hyprland login only (store key hwcheck_shown): hardware check notification, "Open" shows it in kitty
  hl.exec_cmd("uwsm app -- fw-hwcheck --first-login")
end)

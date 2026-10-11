#!/bin/sh
# User services tied to the graphical session (no user systemd, e.g. CI containers: skip).
#  - fw-crash-watch: crash/failed-service notifications (Diagnose with Jarvis)
#  - mako: notifications; its own unit follows graphical-session.target under uwsm (not started from Hyprland)
#  - fw-theme-session: GTK theme/colour scheme set at Hyprland login, handed back at logout (fw13.theme)
#  - fw-autobrightness: ambient-light brightness (Hyprland only, off until Settings → Display turns it on)
#  - fw-battery-warn: low-battery notifications at 20/10/5 % (Hyprland only; levels in Settings → Power)
#  - fw-health.timer: health report 15 min after login, then daily (fw-health --timer; notifies in Hyprland only)
#  - fw-updates.timer: dnf update check 20 min after login, then daily (fw-updates --check; Update now = snapshot first)
systemctl --user show-environment >/dev/null 2>&1 || exit 0
systemctl --user daemon-reload
systemctl --user enable fw-crash-watch.service mako.service fw-theme-session.service fw-autobrightness.service \
  fw-battery-warn.service
systemctl --user enable --now fw-health.timer fw-updates.timer
systemctl --user reset-failed mako.service 2>/dev/null || true
systemctl --user restart fw-crash-watch.service 2>/dev/null || true
systemctl --user restart fw-battery-warn.service 2>/dev/null || true

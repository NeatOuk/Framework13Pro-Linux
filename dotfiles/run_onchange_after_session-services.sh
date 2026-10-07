#!/bin/sh
# User services tied to the graphical session (no user systemd, e.g. CI containers: skip).
#  - fw-crash-watch: crash/failed-service notifications (Diagnose with Jarvis)
#  - mako: notifications; its own unit follows graphical-session.target under uwsm (not started from Hyprland)
systemctl --user show-environment >/dev/null 2>&1 || exit 0
systemctl --user daemon-reload
systemctl --user enable fw-crash-watch.service mako.service
systemctl --user reset-failed mako.service 2>/dev/null || true
systemctl --user restart fw-crash-watch.service 2>/dev/null || true

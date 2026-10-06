#!/bin/sh
# Enable the crash watcher (no user systemd, e.g. CI containers: skip).
systemctl --user show-environment >/dev/null 2>&1 || exit 0
systemctl --user daemon-reload
systemctl --user enable fw-crash-watch.service
systemctl --user restart fw-crash-watch.service 2>/dev/null || true

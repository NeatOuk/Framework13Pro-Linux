#!/usr/bin/env bash
# Point an existing bootc/Fedora Atomic system at the locally built image.
# Next reboot boots it; the previous deployment stays as rollback (bootc rollback).
set -euo pipefail
IMAGE="${IMAGE:-localhost/fw13-hypr:latest}"
sudo bootc switch --transport containers-storage "$IMAGE"
echo "Reboot to use $IMAGE.  Undo: sudo bootc rollback"

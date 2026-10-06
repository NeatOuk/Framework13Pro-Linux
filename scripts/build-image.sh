#!/usr/bin/env bash
# Build the OS image locally with podman (works on the laptop itself or any Fedora box).
set -euo pipefail
cd "$(dirname "$0")/../image"
IMAGE="${IMAGE:-localhost/fw13-hypr:latest}"
sudo podman build \
  --build-arg FEDORA_VERSION="${FEDORA_VERSION:-44}" \
  --build-arg HYPR_COPR="${HYPR_COPR-lionheartp/Hyprland}" \
  -t "$IMAGE" .
echo "Built $IMAGE"

#!/usr/bin/env bash
# Build an installer ISO from the image (fresh install on the Framework).
# Uses bootc-image-builder, the official bootc project tool.
set -euo pipefail
IMAGE="${IMAGE:-localhost/fw13-hypr:latest}"
OUT="${OUT:-$(pwd)/output}"
mkdir -p "$OUT"
sudo podman run --rm -it --privileged --pull=newer \
  --security-opt label=type:unconfined_t \
  -v "$OUT":/output \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  quay.io/centos-bootc/bootc-image-builder:latest \
  --type anaconda-iso --rootfs btrfs --local "$IMAGE"
echo "ISO: $OUT/bootiso/install.iso"

#!/usr/bin/env bash
# Print the build-time manifest: package count, size, top 30, size per repo, Hypr provenance.
# Works on a built image, or on the running laptop with no args.
set -euo pipefail
IMAGE="${1:-}"
if [[ -n "$IMAGE" ]]; then
  sudo podman run --rm "$IMAGE" cat /usr/share/fw13-hypr-manifest.txt
else
  cat /usr/share/fw13-hypr-manifest.txt
fi

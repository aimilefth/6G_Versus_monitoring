#!/usr/bin/env bash
set -euo pipefail

# Build/push an ARM64 image (Jetson AGX Orin is linux/arm64)
# Requires Docker Buildx: https://docs.docker.com/build/buildx/
IMAGE_NAME="${IMAGE_NAME:-aimilefth/6gversus-monitoring:agx-orin}"

docker buildx build \
  --platform linux/arm64 \
  -t "${IMAGE_NAME}" \
  --push \
  . 2>&1 | tee build.log

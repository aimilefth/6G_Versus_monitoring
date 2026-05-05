#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-aimilefth/6gversus-monitoring:agx-orin-vapp}"

docker buildx build \
--platform amd64 \
-t "${IMAGE_NAME}" \
--push \
. 2>&1 | tee build.log

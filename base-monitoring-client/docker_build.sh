#!/usr/bin/env bash
set -euo pipefail

docker buildx build -t aimilefth/base-monitoring-client --platform linux/amd64,linux/arm64 --push . 2>&1 | tee build.log
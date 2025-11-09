#!/usr/bin/env bash
set -euo pipefail

docker build -t aimilefth/base-monitoring-client --push . 2>&1 | tee build.log
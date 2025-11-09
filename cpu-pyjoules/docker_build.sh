#!/usr/bin/env bash
set -euo pipefail

docker build -t aimilefth/cpu-pyjoules --push . 2>&1 | tee build.log

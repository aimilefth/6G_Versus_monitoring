#!/usr/bin/env bash
set -euo pipefail

docker build -t aimilefth/cpu-pyjoules --pull --push . 2>&1 | tee build.log

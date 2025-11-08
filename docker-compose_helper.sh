#!/usr/bin/env bash
set -euo pipefail

# load .env if it exists, but skip UID/GID because bash has UID readonly
if [[ -f .env ]]; then
  while IFS='=' read -r key val; do
    # skip empty lines and comments
    [[ -z "$key" ]] && continue
    [[ "$key" =~ ^# ]] && continue

    # skip UID/GID to avoid "readonly variable"
    if [[ "$key" == "UID" || "$key" == "GID" ]]; then
      continue
    fi

    export "$key=$val"
  done < .env
fi

PRIVILEGED="${PRIVILEGED:-false}"

if [[ "$PRIVILEGED" =~ ^([Tt]rue|TRUE|true)$ ]]; then
  echo "[*] Running in PRIVILEGED mode (from .env)"
  docker compose \
    -f docker-compose.yml \
    -f docker-compose.privileged.yml \
    "$@"
else
  echo "[*] Running in normal AppArmor mode"
  docker compose \
    -f docker-compose.yml \
    "$@"
fi

#!/usr/bin/env bash
set -euo pipefail

# This script installs the custom AppArmor profile that allows
# containers to read /sys/devices/virtual/powercap for pyjoules.
# Must be run with sudo.

PROFILE_NAME="docker-pyjoules"
PROFILE_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_SRC_FILE="${PROFILE_SRC_DIR}/${PROFILE_NAME}"
PROFILE_DST_DIR="/etc/apparmor.d/containers"
PROFILE_DST_FILE="${PROFILE_DST_DIR}/${PROFILE_NAME}"

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "This script must be run as root (use: sudo $0)"
    exit 1
  fi
}

install_profile() {
  echo "[*] Ensuring target directory exists: ${PROFILE_DST_DIR}"
  mkdir -p "${PROFILE_DST_DIR}"

  echo "[*] Copying profile ${PROFILE_SRC_FILE} -> ${PROFILE_DST_FILE}"
  cp "${PROFILE_SRC_FILE}" "${PROFILE_DST_FILE}"

  echo "[*] Loading profile into AppArmor..."
  apparmor_parser -r -W "${PROFILE_DST_FILE}"
}

verify_profile() {
  echo "[*] Verifying profile is loaded..."
  if aa-status | grep -q "^${PROFILE_NAME}\b"; then
    echo "[+] Profile '${PROFILE_NAME}' is loaded."
  else
    echo "[!] Profile '${PROFILE_NAME}' not found in aa-status output!"
    aa-status || true
    exit 1
  fi
}

print_next_steps() {
  cat <<'EOF'

Next steps:

1. Make sure your docker-compose service for the pyjoules container has:

    security_opt:
      - apparmor=docker-pyjoules
      - systempaths=unconfined

2. Make sure you bind the RAPL paths:

    volumes:
      - /sys/class/powercap:/sys/class/powercap:ro
      - /sys/devices/virtual/powercap:/sys/devices/virtual/powercap:ro

3. Recreate the container:

    docker compose up -d --force-recreate pyjoules-metrics-client-remote-write

EOF
}

main() {
  require_root
  install_profile
  verify_profile
  print_next_steps
}

main "$@"

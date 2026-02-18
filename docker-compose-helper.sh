#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick compose implementation:
# - Prefer Docker Compose v2 plugin: "docker compose"
# - Fall back to legacy v1 binary: "docker-compose"
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "ERROR: Neither 'docker compose' (compose plugin) nor 'docker-compose' is available." >&2
  echo "Install one of:" >&2
  echo "  - Ubuntu/Debian: sudo apt-get install docker-compose-plugin" >&2
  echo "  - or legacy: sudo apt-get install docker-compose" >&2
  exit 2
fi

usage() {
  cat <<'EOF'
Usage:
  ./docker-compose-helper.sh -s <stack> [-s <stack> ...] <compose-cmd> [args...]

Examples:
  ./docker-compose-helper.sh -s server up -d
  ./docker-compose-helper.sh -s cpu-pyjoules up -d
  ./docker-compose-helper.sh -s server -s cpu-pyjoules up -d
  ./docker-compose-helper.sh -s cpu-pyjoules logs -f
  ./docker-compose-helper.sh -s server -s cpu-pyjoules down

Stacks are directories in repo root containing docker-compose.yml and .env
(e.g. ./server/docker-compose.yml, ./cpu-pyjoules/docker-compose.yml)
EOF
}

stacks=()

# Parse one or more -s flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--stack)
      [[ $# -ge 2 ]] || { echo "ERROR: missing value for $1" >&2; usage; exit 2; }
      stacks+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

[[ ${#stacks[@]} -gt 0 ]] || { echo "ERROR: no stacks specified (-s ...)" >&2; usage; exit 2; }
[[ $# -gt 0 ]] || { echo "ERROR: no docker compose command given (e.g. up -d)" >&2; usage; exit 2; }

compose_cmd="$1"
shift
compose_args=("$compose_cmd" "$@")

get_env_value() {
  # $1: env file path, $2: key
  # prints value or empty
  local file="$1"
  local key="$2"
  [[ -f "$file" ]] || return 0
  # last occurrence wins; trim CR; strip surrounding quotes
  local line
  line="$(grep -E "^[[:space:]]*${key}=" "$file" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 0
  local val="${line#*=}"
  val="${val%%#*}"            # drop inline comments
  val="$(echo -n "$val" | tr -d '\r')"
  val="${val%\"}"; val="${val#\"}"
  val="${val%\'}"; val="${val#\'}"
  echo -n "$val"
}

run_stack() {
  local stack="$1"
  local dir="${ROOT_DIR}/${stack}"

  [[ -d "$dir" ]] || { echo "ERROR: stack directory not found: $stack" >&2; exit 2; }
  [[ -f "$dir/docker-compose.yml" ]] || { echo "ERROR: missing $stack/docker-compose.yml" >&2; exit 2; }

  pushd "$dir" >/dev/null

  local files=(-f docker-compose.yml)

  # privileged overlay only for cpu-pyjoules (template for future clients)
  if [[ "$stack" == "cpu-pyjoules" ]]; then
    local priv
    priv="$(get_env_value ".env" "PRIVILEGED")"
    priv="${priv:-false}"

    if [[ "$priv" =~ ^([Tt]rue|TRUE|true)$ ]]; then
      echo "[*] $stack: PRIVILEGED=true → adding docker-compose.privileged.yml"
      [[ -f docker-compose.privileged.yml ]] || { echo "ERROR: missing docker-compose.privileged.yml in $stack" >&2; exit 2; }
      files+=(-f docker-compose.privileged.yml)
    else
      echo "[*] $stack: normal AppArmor mode"
    fi
  else
    echo "[*] $stack"
  fi

  "${COMPOSE_CMD[@]}" "${files[@]}" "${compose_args[@]}"
  popd >/dev/null
}

# If command is "down"/"stop", it’s usually nicer to stop clients before server:
if [[ "$compose_cmd" == "down" || "$compose_cmd" == "stop" ]]; then
  for (( i=${#stacks[@]}-1; i>=0; i-- )); do
    run_stack "${stacks[i]}"
  done
else
  for s in "${stacks[@]}"; do
    run_stack "$s"
  done
fi

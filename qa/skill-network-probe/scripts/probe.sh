#!/bin/sh
set -u

check_command() {
  name=$1
  if command -v "$name" >/dev/null 2>&1; then
    printf '%s path: %s\n' "$name" "$(command -v "$name")"
  else
    printf '%s: missing\n' "$name"
    return 1
  fi
}

status=0
check_command curl || status=1
check_command ssh || status=1

if command -v curl >/dev/null 2>&1; then
  curl --version | sed -n '1p'
fi
if command -v ssh >/dev/null 2>&1; then
  ssh -V 2>&1 | sed -n '1p'
fi

if [ -n "${CURL_URL:-}" ]; then
  printf '\nHTTP probe: %s\n' "$CURL_URL"
  if curl --location --head --max-time 12 --silent --show-error --output /dev/null --write-out 'HTTP status: %{http_code}\n' "$CURL_URL"; then
    printf 'HTTP transport: reachable\n'
  else
    printf 'HTTP transport: failed\n'
    status=1
  fi
fi

if [ -n "${SSH_TARGET:-}" ]; then
  case "$SSH_TARGET" in
    *@*) ;;
    *) printf 'SSH_TARGET must use user@host format\n'; exit 2 ;;
  esac
  port=${SSH_PORT:-22}
  case "$port" in
    *[!0-9]*|'') printf 'SSH_PORT must be numeric\n'; exit 2 ;;
  esac
  printf '\nSSH probe: %s port %s\n' "$SSH_TARGET" "$port"
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o ConnectionAttempts=1 \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -p "$port" "$SSH_TARGET" true
  ssh_status=$?
  printf 'SSH command exit status: %s\n' "$ssh_status"
  if [ "$ssh_status" -ne 0 ]; then
    printf 'Inspect the SSH message above to distinguish connectivity from authentication.\n'
    status=1
  fi
fi

exit "$status"

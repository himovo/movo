#!/usr/bin/env bash
set -euo pipefail

secret_file="${ASKAI_RUNTIME_SECRETS_FILE:-/run/askai-secrets/runtime.env}"
if [[ -r "${secret_file}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${secret_file}"
  set +a
fi

exec "$@"

#!/bin/sh
set -eu

secret_file="${ASKAI_RUNTIME_SECRETS_FILE:-/run/askai-secrets/runtime.env}"
if [ -r "$secret_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$secret_file"
  set +a
fi

runtime_token="${DSH_RUNTIME_HOST_TOKEN:-}"
if [ "${#runtime_token}" -lt 32 ]; then
  echo "DSH_RUNTIME_HOST_TOKEN is missing or too short." >&2
  exit 1
fi

mkdir -p /data/dsh-runtime
chown -R node:node /data/dsh-runtime
exec gosu node "$@"

#!/usr/bin/env bash
set -euo pipefail

load_runtime_secrets() {
  local secret_file="${ASKAI_RUNTIME_SECRETS_FILE:-/run/askai-secrets/runtime.env}"
  if [[ -r "${secret_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${secret_file}"
    set +a
  fi
}

load_runtime_secrets

start_worker() {
  celery -A app.workers.celery_app:celery_app worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --queues="${MOVO_DOC_PROCESSING_CELERY_QUEUE:-${ASKAI_DOC_PROCESSING_CELERY_QUEUE:-document_processing}}" \
    --concurrency="${MOVO_DOC_PROCESSING_WORKER_CONCURRENCY:-${ASKAI_DOC_PROCESSING_WORKER_CONCURRENCY:-2}}"
}

case "${1:-api}" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8200}" --proxy-headers
    ;;
  worker)
    start_worker
    ;;
  all)
    start_worker &
    worker_pid="$!"
    trap 'kill "${worker_pid}" 2>/dev/null || true; wait "${worker_pid}" 2>/dev/null || true' EXIT INT TERM
    uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8200}" --proxy-headers
    ;;
  *)
    exec "$@"
    ;;
esac

#!/usr/bin/env bash

movo_pull_images_serially() {
  local policy="${1:-missing}"
  local max_attempts="${MOVO_PULL_RETRIES:-3}"
  local retry_delay="${MOVO_PULL_RETRY_DELAY_SECONDS:-3}"
  local attempt

  if [[ ! "${max_attempts}" =~ ^[1-9][0-9]*$ ]]; then
    max_attempts=3
  fi
  if [[ ! "${retry_delay}" =~ ^[0-9]+$ ]]; then
    retry_delay=3
  fi

  for ((attempt = 1; attempt <= max_attempts; attempt += 1)); do
    movo_msg pulling_images "${attempt}" "${max_attempts}"
    if movo_compose --parallel 1 pull --policy "${policy}"; then
      return 0
    fi
    if ((attempt < max_attempts)); then
      movo_msg pull_retry "${attempt}" "${max_attempts}" "${retry_delay}" >&2
      sleep "${retry_delay}"
    fi
  done

  movo_msg pull_failed >&2
  return 1
}

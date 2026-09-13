#!/usr/bin/env bash

movo_pull_images_serially() {
  local policy="${1:-missing}"
  local retry_delay="${MOVO_PULL_RETRY_DELAY_SECONDS:-3}"
  local attempt=1
  local pull_status

  if [[ ! "${retry_delay}" =~ ^[0-9]+$ ]]; then
    retry_delay=3
  fi

  while true; do
    movo_msg pulling_images "${attempt}"
    if movo_compose --parallel 1 pull --policy "${policy}"; then
      return 0
    else
      pull_status=$?
    fi
    if [[ "${pull_status}" -eq 130 || "${pull_status}" -eq 143 ]]; then
      return "${pull_status}"
    fi

    movo_msg pull_retry "${attempt}" "${retry_delay}" >&2
    sleep "${retry_delay}"
    attempt=$((attempt + 1))
  done
}

#!/usr/bin/env bash

movo_pull_missing_images() {
  local images image
  images="$(movo_compose config --images)" || return 1
  local missing=()
  while IFS= read -r image; do
    [[ -n "${image}" ]] || continue
    if ! "${DOCKER_BIN}" image inspect "${image}" >/dev/null 2>&1; then
      missing+=("${image}")
    fi
  done <<< "$(printf '%s\n' "${images}" | sort -u)"
  if [[ ${#missing[@]} -eq 0 ]]; then
    movo_msg local_images_ready
    return 0
  fi
  for image in "${missing[@]}"; do
    if [[ "${MOVO_OFFLINE_ONLY:-$(dotenv_value MOVO_OFFLINE_ONLY)}" == 1 ]]; then
      movo_msg missing_image_unavailable "${image}" >&2
      return 1
    fi
    movo_msg pulling_missing_image "${image}"
    if ! "${DOCKER_BIN}" pull "${image}"; then
      movo_msg missing_image_unavailable "${image}" >&2
      return 1
    fi
  done
}

movo_pull_images_serially() {
  local policy="${1:-missing}"
  if [[ "${policy}" == missing ]]; then
    movo_pull_missing_images
    return $?
  fi
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

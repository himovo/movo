#!/usr/bin/env bash

MOVO_COMPOSE_COMMAND=()

movo_compose_version_supported() {
  local version="$1"
  if [[ "${version}" =~ ^(Docker[[:space:]]Compose|docker-compose)[[:space:]]version[[:space:]]v?([0-9]+)\.([0-9]+) ]]; then
    [[ "${BASH_REMATCH[2]}" -ge 2 ]]
  else
    return 1
  fi
}

movo_detect_compose() {
  local version
  MOVO_COMPOSE_COMMAND=()
  version="$("${DOCKER_BIN}" compose version 2>/dev/null)" || version=""
  if movo_compose_version_supported "${version}"; then
    MOVO_COMPOSE_COMMAND=("${DOCKER_BIN}" compose)
    return 0
  fi
  version="$(docker-compose version 2>/dev/null)" || version=""
  if movo_compose_version_supported "${version}"; then
    MOVO_COMPOSE_COMMAND=(docker-compose)
    return 0
  fi
  movo_msg compose_missing >&2
  return 1
}

movo_compose_command() {
  if [[ ${#MOVO_COMPOSE_COMMAND[@]} -eq 0 ]]; then
    movo_detect_compose || return 1
  fi
  "${MOVO_COMPOSE_COMMAND[@]}" "$@"
}

#!/usr/bin/env bash

movo_sandbox_defaults() {
  COMPOSE_PROFILES="${COMPOSE_PROFILES:-$(dotenv_value COMPOSE_PROFILES)}"
  MOVO_SANDBOX_MANAGER_URL="${MOVO_SANDBOX_MANAGER_URL:-$(dotenv_value MOVO_SANDBOX_MANAGER_URL)}"
  COMPOSE_PROFILES="${COMPOSE_PROFILES:-sandbox}"
  MOVO_SANDBOX_MANAGER_URL="${MOVO_SANDBOX_MANAGER_URL:-http://sandbox-manager:8300}"
  export COMPOSE_PROFILES MOVO_SANDBOX_MANAGER_URL
}

movo_sandbox_preflight() {
  local profiles configured_url engine_version major
  profiles="${COMPOSE_PROFILES:-$(dotenv_value COMPOSE_PROFILES)}"
  configured_url="${MOVO_SANDBOX_MANAGER_URL:-$(dotenv_value MOVO_SANDBOX_MANAGER_URL)}"
  if [[ ",${profiles}," != *,sandbox,* && -z "${configured_url}" ]]; then
    return 0
  fi
  if [[ ",${profiles}," != *,sandbox,* || "${configured_url}" != "http://sandbox-manager:8300" ]]; then
    movo_msg sandbox_config_mismatch >&2
    return 2
  fi
  engine_version="$("${DOCKER_BIN}" version --format '{{.Server.Version}}' 2>/dev/null || true)"
  major="${engine_version%%.*}"
  if [[ ! "${major}" =~ ^[0-9]+$ || "${major}" -lt 26 ]]; then
    movo_msg sandbox_engine_old "${engine_version:-unknown}" >&2
    return 2
  fi
}

movo_sandbox_enabled() {
  local profiles
  profiles="${COMPOSE_PROFILES:-$(dotenv_value COMPOSE_PROFILES)}"
  [[ ",${profiles}," == *,sandbox,* ]]
}

movo_sandbox_start() {
  if ! movo_sandbox_enabled; then
    return 0
  fi
  local configured_image
  configured_image="${MOVO_SANDBOX_SCRIPT_IMAGE:-$(dotenv_value MOVO_SANDBOX_SCRIPT_IMAGE)}"
  if [[ " $* " == *" --build "* && -z "${configured_image}" ]]; then
    movo_compose build sandbox-script || return 1
  else
    local script_image
    script_image="${configured_image:-${MOVO_IMAGE_PREFIX}-sandbox-script:${MOVO_VERSION}}"
    if ! "${DOCKER_BIN}" image inspect "${script_image}" >/dev/null 2>&1; then
      if [[ "${MOVO_OFFLINE_ONLY:-$(dotenv_value MOVO_OFFLINE_ONLY)}" == 1 ]]; then
        movo_msg missing_image_unavailable "${script_image}" >&2
        return 1
      fi
      if [[ -n "${configured_image}" ]]; then
        "${DOCKER_BIN}" pull "${script_image}" || return 1
      else
        movo_compose pull sandbox-script || return 1
      fi
    fi
  fi
  movo_compose up -d "$@" sandbox-manager || return 1
  local container_id status attempt
  container_id="$(movo_compose ps -q sandbox-manager)"
  for attempt in $(seq 1 30); do
    status="$("${DOCKER_BIN}" inspect --format '{{.State.Health.Status}}' "${container_id}" 2>/dev/null || true)"
    if [[ "${status}" == healthy ]]; then
      return 0
    fi
    if [[ "${status}" == unhealthy ]]; then
      break
    fi
    sleep 2
  done
  movo_msg sandbox_unavailable >&2
  return 1
}

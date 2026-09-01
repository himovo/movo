#!/usr/bin/env bash

MOVO_DSH_PACKAGE_JSON="${ROOT_DIR}/services/chat-api/dsh/runtime-host/package.json"

movo_target_dsh_version() {
  sed -n 's/.*"@deepseek-ai\/dsh"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "${MOVO_DSH_PACKAGE_JSON}" | head -n 1
}

movo_has_build_flag() {
  local argument
  for argument in "$@"; do
    if [[ "${argument}" == "--build" ]]; then
      return 0
    fi
  done
  return 1
}

movo_print_dsh_build_target() {
  local version
  version="$(movo_target_dsh_version)"
  if [[ -n "${version}" ]]; then
    movo_msg dsh_build_target "${version}"
  fi
}

movo_print_running_dsh_version() {
  local container_id version
  container_id="$("${DOCKER_BIN}" compose ps -q dsh-runtime-host 2>/dev/null || true)"
  if [[ -z "${container_id}" ]]; then
    return 0
  fi
  version="$("${DOCKER_BIN}" compose exec -T dsh-runtime-host \
    node -p "require('@deepseek-ai/dsh/package.json').version" 2>/dev/null || true)"
  if [[ -n "${version}" ]]; then
    movo_msg dsh_running_version "${version}"
  fi
}

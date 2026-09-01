#!/usr/bin/env bash

MOVO_COMPOSE_BUILD=false

movo_compose() {
  local compose_args=(-f "${ROOT_DIR}/docker-compose.yml")
  if [[ "${MOVO_COMPOSE_BUILD}" == "true" ]]; then
    compose_args+=(-f "${ROOT_DIR}/docker-compose.build.yml")
  fi
  "${DOCKER_BIN}" compose "${compose_args[@]}" "$@"
}

movo_github_image_prefix() {
  local origin path
  origin="$(git -C "${ROOT_DIR}" remote get-url origin 2>/dev/null || true)"
  case "${origin}" in
    git@github.com:*) path="${origin#git@github.com:}" ;;
    https://github.com/*) path="${origin#https://github.com/}" ;;
    ssh://git@github.com/*) path="${origin#ssh://git@github.com/}" ;;
    *) return 1 ;;
  esac
  path="${path%.git}"
  path="${path%/}"
  if [[ "${path}" != */* ]]; then
    return 1
  fi
  printf 'ghcr.io/%s' "$(printf '%s' "${path}" | tr '[:upper:]' '[:lower:]')"
}

movo_local_images_available() {
  local suffix
  for suffix in dsh-runtime-host chat-api admin-api document-api document-worker user-web admin-web; do
    if ! "${DOCKER_BIN}" image inspect "movo-${suffix}:${MOVO_VERSION:-latest}" >/dev/null 2>&1; then
      return 1
    fi
  done
}

movo_export_shared_document_image() {
  MOVO_DOCUMENT_API_IMAGE="${MOVO_IMAGE_PREFIX}-document-parser:${MOVO_VERSION}"
  MOVO_DOCUMENT_WORKER_IMAGE="${MOVO_DOCUMENT_API_IMAGE}"
  export MOVO_DOCUMENT_API_IMAGE MOVO_DOCUMENT_WORKER_IMAGE
}

movo_configure_images() {
  local source_build="${1:-false}"
  local configured_prefix="${MOVO_IMAGE_PREFIX:-$(dotenv_value MOVO_IMAGE_PREFIX)}"
  MOVO_VERSION="${MOVO_VERSION:-$(dotenv_value MOVO_VERSION)}"
  MOVO_VERSION="${MOVO_VERSION:-latest}"
  export MOVO_VERSION

  if [[ "${source_build}" == "true" ]]; then
    MOVO_COMPOSE_BUILD=true
    MOVO_IMAGE_PREFIX="${configured_prefix:-movo}"
    export MOVO_IMAGE_PREFIX
    movo_export_shared_document_image
    return 0
  fi
  if [[ -n "${configured_prefix}" ]]; then
    MOVO_IMAGE_PREFIX="${configured_prefix%/}"
    export MOVO_IMAGE_PREFIX
    movo_export_shared_document_image
    return 0
  fi
  if MOVO_IMAGE_PREFIX="$(movo_github_image_prefix)"; then
    export MOVO_IMAGE_PREFIX
    movo_export_shared_document_image
    return 0
  fi
  if movo_local_images_available; then
    MOVO_USING_LOCAL_IMAGES=true
    MOVO_IMAGE_PREFIX=movo
    MOVO_DOCUMENT_API_IMAGE="movo-document-api:${MOVO_VERSION}"
    MOVO_DOCUMENT_WORKER_IMAGE="movo-document-worker:${MOVO_VERSION}"
    export MOVO_IMAGE_PREFIX MOVO_USING_LOCAL_IMAGES
    export MOVO_DOCUMENT_API_IMAGE MOVO_DOCUMENT_WORKER_IMAGE
    movo_msg using_local_images
    return 0
  fi
  movo_msg image_source_missing >&2
  return 1
}

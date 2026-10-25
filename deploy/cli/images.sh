#!/usr/bin/env bash

MOVO_COMPOSE_BUILD=false
MOVO_DEFAULT_IMAGE_PREFIX=ghcr.io/himovo/movo
MOVO_CHINA_IMAGE_PREFIX=registry.cn-beijing.aliyuncs.com/himovo-cn/movo

movo_configure_mirror() {
  case "${MOVO_MIRROR:-}" in
    '') ;;
    global)
      MOVO_IMAGE_PREFIX="${MOVO_DEFAULT_IMAGE_PREFIX}"
      MOVO_MONGO_IMAGE=mongo:6.0.20
      MOVO_REDIS_IMAGE=redis:7.4.2-alpine
      MOVO_WEAVIATE_IMAGE=semitechnologies/weaviate:1.25.7
      MOVO_ALPINE_IMAGE=alpine:3.21
      export MOVO_IMAGE_PREFIX MOVO_MONGO_IMAGE MOVO_REDIS_IMAGE MOVO_WEAVIATE_IMAGE MOVO_ALPINE_IMAGE
      ;;
    cn)
      MOVO_IMAGE_PREFIX="${MOVO_CHINA_IMAGE_PREFIX}"
      MOVO_MONGO_IMAGE="registry.cn-beijing.aliyuncs.com/himovo-cn/movo-mongo:6.0.20"
      MOVO_REDIS_IMAGE="registry.cn-beijing.aliyuncs.com/himovo-cn/movo-redis:7.4.2-alpine"
      MOVO_WEAVIATE_IMAGE="registry.cn-beijing.aliyuncs.com/himovo-cn/movo-weaviate:1.25.7"
      MOVO_ALPINE_IMAGE="registry.cn-beijing.aliyuncs.com/himovo-cn/movo-alpine:3.21"
      export MOVO_IMAGE_PREFIX MOVO_MONGO_IMAGE MOVO_REDIS_IMAGE MOVO_WEAVIATE_IMAGE MOVO_ALPINE_IMAGE
      ;;
    *) printf 'Unknown mirror: %s (expected global or cn)\n' "${MOVO_MIRROR}" >&2; return 2 ;;
  esac
}

movo_compose() {
  local compose_args=(-f "${ROOT_DIR}/docker-compose.yml")
  if [[ "${MOVO_COMPOSE_BUILD}" == "true" ]]; then
    compose_args+=(-f "${ROOT_DIR}/docker-compose.build.yml")
  fi
  "${DOCKER_BIN}" compose "${compose_args[@]}" "$@"
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
    MOVO_IMAGE_PREFIX="${MOVO_BUILD_IMAGE_PREFIX:-movo}"
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
  MOVO_IMAGE_PREFIX="${MOVO_DEFAULT_IMAGE_PREFIX}"
  export MOVO_IMAGE_PREFIX
  movo_export_shared_document_image
}

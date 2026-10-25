#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

official_prefix="ghcr.io/himovo/movo"
image_suffixes=(
  dsh-runtime-host
  chat-api
  admin-api
  document-parser
  user-web
  admin-web
  gateway
)

compose_images() {
  env \
    -u MOVO_IMAGE_PREFIX \
    -u MOVO_VERSION \
    -u MOVO_MONGO_IMAGE \
    -u MOVO_REDIS_IMAGE \
    -u MOVO_WEAVIATE_IMAGE \
    -u MOVO_ALPINE_IMAGE \
    -u MOVO_DOCUMENT_API_IMAGE \
    -u MOVO_DOCUMENT_WORKER_IMAGE \
    docker compose --env-file /dev/null "$@" config --images
}

prebuilt_images="$(compose_images -f docker-compose.yml)"
for suffix in "${image_suffixes[@]}"; do
  grep -Fxq "${official_prefix}-${suffix}:latest" <<<"${prebuilt_images}"
done
for image in alpine:3.21 mongo:6.0.20 redis:7.4.2-alpine semitechnologies/weaviate:1.25.7; do
  grep -Fxq "${image}" <<<"${prebuilt_images}"
done

china_prefix="registry.cn-beijing.aliyuncs.com/himovo-cn/movo"
china_images="$(
  env -u MOVO_VERSION -u MOVO_DOCUMENT_API_IMAGE -u MOVO_DOCUMENT_WORKER_IMAGE \
  MOVO_IMAGE_PREFIX="${china_prefix}" \
  MOVO_MONGO_IMAGE="${china_prefix}-mongo:6.0.20" \
  MOVO_REDIS_IMAGE="${china_prefix}-redis:7.4.2-alpine" \
  MOVO_WEAVIATE_IMAGE="${china_prefix}-weaviate:1.25.7" \
  MOVO_ALPINE_IMAGE="${china_prefix}-alpine:3.21" \
    docker compose --env-file /dev/null -f docker-compose.yml config --images
)"
for suffix in "${image_suffixes[@]}"; do
  grep -Fxq "${china_prefix}-${suffix}:latest" <<<"${china_images}"
done
for image in "${china_prefix}-mongo:6.0.20" "${china_prefix}-redis:7.4.2-alpine" \
  "${china_prefix}-weaviate:1.25.7" "${china_prefix}-alpine:3.21"; do
  grep -Fxq "${image}" <<<"${china_images}"
done

source_images="$(
  env -u MOVO_DOCUMENT_API_IMAGE -u MOVO_DOCUMENT_WORKER_IMAGE \
    MOVO_IMAGE_PREFIX=movo MOVO_VERSION=latest docker compose --env-file /dev/null \
    -f docker-compose.yml -f docker-compose.build.yml config --images
)"
for suffix in "${image_suffixes[@]}"; do
  grep -Fxq "movo-${suffix}:latest" <<<"${source_images}"
done

(
  unset MOVO_IMAGE_PREFIX MOVO_VERSION MOVO_BUILD_IMAGE_PREFIX
  ROOT_DIR="${ROOT_DIR}"
  DOCKER_BIN=docker
  # shellcheck source=../deploy/cli/images.sh
  source "${ROOT_DIR}/deploy/cli/images.sh"
  dotenv_value() { printf ''; }

  movo_configure_images false
  [[ "${MOVO_IMAGE_PREFIX}" == "${official_prefix}" ]]

  unset MOVO_IMAGE_PREFIX MOVO_DOCUMENT_API_IMAGE MOVO_DOCUMENT_WORKER_IMAGE
  movo_configure_images true
  [[ "${MOVO_IMAGE_PREFIX}" == "movo" ]]
  [[ "${MOVO_DOCUMENT_API_IMAGE}" == "movo-document-parser:latest" ]]

  unset MOVO_IMAGE_PREFIX MOVO_DOCUMENT_API_IMAGE MOVO_DOCUMENT_WORKER_IMAGE
  MOVO_MIRROR=cn
  movo_configure_mirror
  movo_configure_images false
  [[ "${MOVO_IMAGE_PREFIX}" == "${china_prefix}" ]]
  [[ "${MOVO_ALPINE_IMAGE}" == "${china_prefix}-alpine:3.21" ]]

  MOVO_MIRROR=global
  movo_configure_mirror
  movo_configure_images false
  [[ "${MOVO_IMAGE_PREFIX}" == "${official_prefix}" ]]
  [[ "${MOVO_ALPINE_IMAGE}" == "alpine:3.21" ]]
)

printf 'Compose image modes are valid.\n'

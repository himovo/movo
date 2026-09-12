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
    -u MOVO_DOCUMENT_API_IMAGE \
    -u MOVO_DOCUMENT_WORKER_IMAGE \
    docker compose --env-file /dev/null "$@" config --images
}

prebuilt_images="$(compose_images -f docker-compose.yml)"
for suffix in "${image_suffixes[@]}"; do
  grep -Fxq "${official_prefix}-${suffix}:latest" <<<"${prebuilt_images}"
done

source_images="$(
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
)

printf 'Compose image modes are valid.\n'

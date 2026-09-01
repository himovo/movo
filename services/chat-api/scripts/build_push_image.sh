#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

ENVIRONMENT="${ENVIRONMENT:-test}"
REGISTRY="${REGISTRY:-ghcr.io}"
REGISTRY_NAMESPACE="${REGISTRY_NAMESPACE:-}"
IMAGE_NAME="${IMAGE_NAME:-movo-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
LOCAL_IMAGE="${LOCAL_IMAGE:-${IMAGE_NAME}}"
PLATFORM="${PLATFORM:-}"
DOCKERFILE="${DOCKERFILE:-services/chat-api/Dockerfile}"
CONTEXT_DIR="${CONTEXT_DIR:-services/chat-api}"
PUSH="${PUSH:-true}"
NO_CACHE="${NO_CACHE:-true}"

if [[ -z "${REGISTRY_NAMESPACE}" ]]; then
  echo "ERROR: set REGISTRY_NAMESPACE to the target registry owner or organization." >&2
  exit 2
fi
IMAGE_REF="${REGISTRY%/}/${REGISTRY_NAMESPACE#/}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Backend image build"
echo "  environment: ${ENVIRONMENT}"
echo "  image:       ${IMAGE_REF}"
echo "  local:       ${LOCAL_IMAGE}:latest"
echo "  dockerfile:  ${DOCKERFILE}"
echo "  context:     ${CONTEXT_DIR}"
echo "  platform:    ${PLATFORM:-default}"
echo "  no-cache:    ${NO_CACHE}"
echo "  push:        ${PUSH}"

cd "${ROOT_DIR}"

build_args=()
if [[ -n "${PLATFORM}" ]]; then
  build_args+=(--platform "${PLATFORM}")
fi
if [[ "${NO_CACHE}" == "true" ]]; then
  build_args+=(--no-cache)
fi

docker build \
  "${build_args[@]}" \
  -f "${DOCKERFILE}" \
  -t "${LOCAL_IMAGE}" \
  "${CONTEXT_DIR}"

docker tag "${LOCAL_IMAGE}:latest" "${IMAGE_REF}"

if [[ "${PUSH}" == "true" ]]; then
  docker push "${IMAGE_REF}"
fi

echo "Done: ${IMAGE_REF}"

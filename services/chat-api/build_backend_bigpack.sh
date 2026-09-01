#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- Defaults ----------
ENVIRONMENT="${ENVIRONMENT:-test}"
REGISTRY="${REGISTRY:-ghcr.io}"
REGISTRY_NAMESPACE="${REGISTRY_NAMESPACE:-}"
IMAGE_NAME="${IMAGE_NAME:-movo-backend}"
IMAGE_TAG="${IMAGE_TAG:-dev-0.0.1}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
CONTEXT_DIR="${CONTEXT_DIR:-.}"
PLATFORM="${PLATFORM:-}"
NO_CACHE="${NO_CACHE:-true}"
PUSH="${PUSH:-true}"
SAVE_TAR="${SAVE_TAR:-false}"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"
BUILD_MEMORY="${BUILD_MEMORY:-}"
BUILD_MEMORY_SWAP="${BUILD_MEMORY_SWAP:-}"
VERIFY_MARKER="${VERIFY_MARKER:-spreadsheet_export_skill_applied}"
VERIFY_MARKER_FILE="${VERIFY_MARKER_FILE:-app/runtime/subagents/runtime.py}"

if [[ -z "${REGISTRY_NAMESPACE}" ]]; then
  echo "ERROR: set REGISTRY_NAMESPACE to the target registry owner or organization." >&2
  exit 2
fi
IMAGE_REF="${REGISTRY%/}/${REGISTRY_NAMESPACE#/}/${IMAGE_NAME}:${IMAGE_TAG}"
LOCAL_TAG="${IMAGE_NAME}:${IMAGE_TAG}"
TAR_FILE="${OUTPUT_DIR}/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

cd "${ROOT_DIR}"

GIT_COMMIT="$(cd "${ROOT_DIR}/.." && git rev-parse HEAD 2>/dev/null || true)"
GIT_STATUS="$(cd "${ROOT_DIR}/.." && git status --short 2>/dev/null || true)"

echo "=== Backend big package build ==="
echo "environment : ${ENVIRONMENT}"
echo "image       : ${IMAGE_REF}"
echo "dockerfile  : ${DOCKERFILE}"
echo "context     : ${CONTEXT_DIR}"
echo "platform    : ${PLATFORM:-default}"
echo "no-cache    : ${NO_CACHE}"
echo "push        : ${PUSH}"
echo "save-tar    : ${SAVE_TAR}"
echo "memory      : ${BUILD_MEMORY:-default}"
echo "memory-swap : ${BUILD_MEMORY_SWAP:-default}"
echo "git commit  : ${GIT_COMMIT:-unknown}"
if [[ -n "${GIT_STATUS}" ]]; then
  echo "git status  : dirty"
  echo "${GIT_STATUS}"
else
  echo "git status  : clean"
fi

if [[ -n "${VERIFY_MARKER}" ]]; then
  host_verify_file="${CONTEXT_DIR%/}/${VERIFY_MARKER_FILE}"
  if [[ ! -f "${host_verify_file}" ]]; then
    echo "ERROR: verify file not found: ${host_verify_file}" >&2
    exit 1
  fi
  if ! grep -q "${VERIFY_MARKER}" "${host_verify_file}"; then
    echo "ERROR: verify marker not found before build: ${VERIFY_MARKER} in ${host_verify_file}" >&2
    exit 1
  fi
  echo "verify host : found '${VERIFY_MARKER}' in ${host_verify_file}"
fi

build_args=()
if [[ -n "${PLATFORM}" ]]; then
  build_args+=(--platform "${PLATFORM}")
fi
if [[ "${NO_CACHE}" == "true" ]]; then
  build_args+=(--no-cache)
fi
if [[ -n "${BUILD_MEMORY}" ]]; then
  build_args+=(--memory "${BUILD_MEMORY}")
fi
if [[ -n "${BUILD_MEMORY_SWAP}" ]]; then
  build_args+=(--memory-swap "${BUILD_MEMORY_SWAP}")
fi

docker build \
  "${build_args[@]}" \
  -f "${DOCKERFILE}" \
  -t "${LOCAL_TAG}" \
  "${CONTEXT_DIR}"

docker tag "${LOCAL_TAG}" "${IMAGE_REF}"

if [[ -n "${VERIFY_MARKER}" ]]; then
  container_verify_file="/app/${VERIFY_MARKER_FILE}"
  echo "Verifying built image contains marker..."
  docker run --rm --entrypoint grep "${LOCAL_TAG}" -n "${VERIFY_MARKER}" "${container_verify_file}"
  echo "verify image: found '${VERIFY_MARKER}' in ${container_verify_file}"
fi

if [[ "${PUSH}" == "true" ]]; then
  echo "Pushing ${IMAGE_REF} ..."
  docker push "${IMAGE_REF}"
fi

if [[ "${SAVE_TAR}" == "true" ]]; then
  mkdir -p "${OUTPUT_DIR}"
  echo "Saving image tarball -> ${TAR_FILE} ..."
  docker save "${IMAGE_REF}" | gzip > "${TAR_FILE}"
  echo "Tarball ready: ${TAR_FILE}"
fi

echo "Done: ${IMAGE_REF}"

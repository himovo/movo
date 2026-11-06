#!/usr/bin/env bash
set -Eeuo pipefail

# Copy the pinned public build bases into one ACR repository. The source mirror
# is used only by this maintenance job; normal MOVO builds consume ACR directly.
registry="${MOVO_CN_BUILD_BASE_REGISTRY:-registry.cn-beijing.aliyuncs.com/himovo-cn/movo-build-base}"
source_prefix="${MOVO_CN_BUILD_BASE_SOURCE:-m.daocloud.io/docker.io/library}"
retry_limit="${MOVO_CN_BUILD_BASE_RETRIES:-8}"
retry_delay="${MOVO_CN_BUILD_BASE_RETRY_DELAY_SECONDS:-15}"

images=(
  "node-20-slim:node:20-slim"
  "node-22-bookworm-slim:node:22-bookworm-slim"
  "node-24-bookworm-slim:node:24-bookworm-slim"
  "python-3.10-slim-bookworm:python:3.10-slim-bookworm"
  "nginx-1.31.6-trixie:nginx:1.31.6-trixie"
)

require_platform() {
  local image="$1" architecture="$2"
  docker buildx imagetools inspect --raw "${image}" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
architecture, image = sys.argv[1:]
manifests = payload.get("manifests", [])
if not any(item.get("platform", {}).get("os") == "linux" and item.get("platform", {}).get("architecture") == architecture for item in manifests):
    raise SystemExit(f"Missing linux/{architecture}: {image}")
' "${architecture}" "${image}"
}

retry() {
  local attempt=1
  until "$@"; do
    if (( attempt >= retry_limit )); then
      printf '[cn-build-base] Failed after %s attempts: %s\n' "${attempt}" "$*" >&2
      return 1
    fi
    printf '[cn-build-base] Retry %s/%s after %ss: %s\n' \
      "$((attempt + 1))" "${retry_limit}" "${retry_delay}" "$*" >&2
    sleep "${retry_delay}"
    attempt=$((attempt + 1))
  done
}

copy_platform() {
  local source="$1" target="$2" architecture="$3"
  local dockerfile
  dockerfile=$'ARG SOURCE_IMAGE\nFROM ${SOURCE_IMAGE}\n'
  retry bash -c 'printf "%s" "$1" | docker buildx build \
    --platform "linux/$2" \
    --build-arg "SOURCE_IMAGE=$3" \
    --tag "$4-$2" \
    --provenance=false \
    --sbom=false \
    --push -' _ "${dockerfile}" "${architecture}" "${source}" "${target}"
}

for entry in "${images[@]}"; do
  target_tag="${entry%%:*}"
  source_name="${entry#*:}"
  source="${source_prefix}/${source_name}"
  target="${registry}:${target_tag}"
  if [[ "${MOVO_CN_BUILD_BASE_FORCE:-false}" != "true" ]] \
      && docker buildx imagetools inspect "${target}" >/dev/null 2>&1 \
      && require_platform "${target}" amd64 \
      && require_platform "${target}" arm64; then
    printf '[cn-build-base] Reuse verified %s\n' "${target}"
    continue
  fi
  printf '[cn-build-base] Sync %s -> %s\n' "${source}" "${target}"
  copy_platform "${source}" "${target}" amd64
  copy_platform "${source}" "${target}" arm64
  retry docker buildx imagetools create --tag "${target}" \
    "${target}-amd64" "${target}-arm64"
  require_platform "${target}" amd64
  require_platform "${target}" arm64
done

printf '[cn-build-base] Published and verified all build bases.\n'

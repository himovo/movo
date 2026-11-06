#!/usr/bin/env bash
set -Eeuo pipefail

# Copy the pinned public build bases into one ACR repository. The source mirror
# is used only by this maintenance job; normal MOVO builds consume ACR directly.
registry="${MOVO_CN_BUILD_BASE_REGISTRY:-registry.cn-beijing.aliyuncs.com/himovo-cn/movo-build-base}"
source_prefix="${MOVO_CN_BUILD_BASE_SOURCE:-m.daocloud.io/docker.io/library}"

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
  docker buildx imagetools create --tag "${target}" "${source}"
  require_platform "${target}" amd64
  require_platform "${target}" arm64
done

printf '[cn-build-base] Published and verified all build bases.\n'

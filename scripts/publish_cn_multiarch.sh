#!/usr/bin/env bash
set -Eeuo pipefail

# Merge independently built ACR images into one tag per service. Run only after
# both native-architecture candidate pipelines have succeeded for the same SHA.
source_sha="${1:-${MOVO_CN_SOURCE_SHA:-}}"
if [[ ! "${source_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Usage: %s <40-character candidate commit SHA>\n' "$0" >&2
  exit 2
fi

registry="registry.cn-beijing.aliyuncs.com/himovo-cn/movo"
services=(user-web dsh-runtime-host chat-api admin-api document-parser admin-web gateway)
infra=("mongo:6.0.20" "redis:7.4.2-alpine" "weaviate:1.25.7" "alpine:3.21")

require_platform() {
  local image="$1" arch="$2" manifest
  manifest="$(docker buildx imagetools inspect --raw "${image}")"
  printf '%s' "${manifest}" | python3 -c '
import json, sys
manifest = json.load(sys.stdin)
arch = sys.argv[1]
platforms = [item.get("platform", {}) for item in manifest.get("manifests", [])]
if platforms:
    ok = any(p.get("os") == "linux" and p.get("architecture") == arch for p in platforms)
else:
    # A single-platform manifest has no platform descriptor. Inspect its config
    # through Docker instead of guessing from a successful registry lookup.
    ok = False
if not ok:
    sys.exit(f"Missing linux/{arch}: {sys.argv[2]}")
' "${arch}" "${image}"
}

stage() {
  local image="$1" amd="$2" arm="$3" staged="$4"
  printf '[cn-multiarch] Check %s\n' "${image}"
  require_platform "${amd}" amd64
  require_platform "${arm}" arm64
  docker buildx imagetools create --tag "${staged}" "${amd}" "${arm}"
  require_platform "${staged}" amd64
  require_platform "${staged}" arm64
}

# Preserve the pre-existing amd64-only infrastructure tags before changing
# those tags to multi-architecture indexes. Subsequent runs reuse the copies.
for entry in "${infra[@]}"; do
  name="${entry%%:*}"
  version="${entry#*:}"
  image="${registry}-${name}"
  amd="${image}:amd64-${version}"
  if ! docker buildx imagetools inspect "${amd}" >/dev/null 2>&1; then
    printf '[cn-multiarch] Preserve amd64 %s\n' "${image}:${version}"
    docker buildx imagetools create --tag "${amd}" "${image}:${version}"
  fi
  require_platform "${amd}" amd64
done

# Build and validate every staged index before touching any public tag.
for name in "${services[@]}"; do
  image="${registry}-${name}"
  stage "${image}" "${image}:candidate-amd64-${source_sha}" \
    "${image}:candidate-arm64-${source_sha}" "${image}:candidate-multiarch-${source_sha}"
done
for entry in "${infra[@]}"; do
  name="${entry%%:*}"
  version="${entry#*:}"
  image="${registry}-${name}"
  stage "${image}" "${image}:amd64-${version}" \
    "${image}:arm64-${version}" "${image}:candidate-multiarch-${version}"
done

printf '[cn-multiarch] All 11 staged indexes contain linux/amd64 and linux/arm64; publishing tags.\n'
for name in "${services[@]}"; do
  image="${registry}-${name}"
  docker buildx imagetools create --tag "${image}:latest" \
    "${image}:candidate-multiarch-${source_sha}"
  require_platform "${image}:latest" amd64
  require_platform "${image}:latest" arm64
done
for entry in "${infra[@]}"; do
  name="${entry%%:*}"
  version="${entry#*:}"
  image="${registry}-${name}"
  docker buildx imagetools create --tag "${image}:${version}" \
    "${image}:candidate-multiarch-${version}"
  require_platform "${image}:${version}" amd64
  require_platform "${image}:${version}" arm64
done
printf '[cn-multiarch] Published and verified all 11 dual-architecture tags.\n'

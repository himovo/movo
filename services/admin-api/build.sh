#!/usr/bin/env bash
set -euo pipefail

# 获取脚本所在目录，即 admin/api 目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REGISTRY="${REGISTRY:-registry-vpc.cn-zhangjiakou.aliyuncs.com/guoran}"
IMAGE_NAME="${IMAGE_NAME:-movo-admin}"
IMAGE_TAG="${IMAGE_TAG:-dev-0.0.1}"
LOCAL_IMAGE="movo-admin"
PUSH="${PUSH:-true}"
NO_CACHE="${NO_CACHE:-true}"

IMAGE_REF="${REGISTRY%/}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "Building Admin API Image..."
echo "  Image Tag:   ${IMAGE_REF}"
echo "  Context Dir: ${SCRIPT_DIR}"
echo "  No Cache:    ${NO_CACHE}"
echo "  Push:        ${PUSH}"

cd "${SCRIPT_DIR}"

build_args=()
if [[ "${NO_CACHE}" == "true" ]]; then
  build_args+=(--no-cache)
fi

# 在 admin/api 目录下构建镜像
docker build \
  "${build_args[@]}" \
  -f Dockerfile \
  -t "${LOCAL_IMAGE}:latest" \
  .

# 标记镜像
echo "Tagging image as ${IMAGE_REF}..."
docker tag "${LOCAL_IMAGE}:latest" "${IMAGE_REF}"

# 推送到远程镜像仓库
if [[ "${PUSH}" == "true" ]]; then
  echo "Pushing image to ${IMAGE_REF}..."
  docker push "${IMAGE_REF}"
fi

echo "Successfully built and pushed: ${IMAGE_REF}"

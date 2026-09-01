#!/usr/bin/env bash
set -euo pipefail

# Usage examples:
#   # Default: build CPU image and reuse movo-document-parser-base:bookworm-cpu if present.
#   ./build_document_processing_bigpack.sh
#
#   # Run in the background and write logs to BUILD_LOG.
#   BACKGROUND=true BUILD_LOG=document-build.log ./build_document_processing_bigpack.sh
#
#   # Rebuild and push the CPU base image, then build/push the app image.
#   PYTORCH_ACCELERATOR=cpu REBUILD_SYSTEM_BASE=true PUSH_SYSTEM_BASE=true ./build_document_processing_bigpack.sh
#
#   # Rebuild with a custom PyPI mirror, for example Tsinghua.
#   PYPI_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/ PYPI_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
#     PYTORCH_ACCELERATOR=cpu REBUILD_SYSTEM_BASE=true PUSH_SYSTEM_BASE=true ./build_document_processing_bigpack.sh
#
#   # Build a CUDA 13.0 variant without overwriting the CPU app tag.
#   PYTORCH_ACCELERATOR=cu130 REBUILD_SYSTEM_BASE=true PUSH_SYSTEM_BASE=true IMAGE_TAG=latest-gpu ./build_document_processing_bigpack.sh
#
#   # Supported PYTORCH_ACCELERATOR values:
#   #   cpu     -> installs torch/torchvision from https://download.pytorch.org/whl/cpu
#   #   cu128   -> installs CUDA 12.8 torch/torchvision from https://download.pytorch.org/whl/cu128
#   #   cu130   -> installs CUDA 13.0 torch/torchvision from https://download.pytorch.org/whl/cu130
#   #   default -> does not preinstall PyTorch; lets pip resolve Docling dependencies normally
#   #
#   # Override SYSTEM_BASE_IMAGE only when you intentionally want a custom base tag.
#
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENVIRONMENT="${ENVIRONMENT:-test}"
REGISTRY="${REGISTRY:-registry-vpc.cn-zhangjiakou.aliyuncs.com/guoran}"
IMAGE_NAME="${IMAGE_NAME:-movo-document-processing}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BASE_IMAGE="${BASE_IMAGE:-registry-vpc.cn-zhangjiakou.aliyuncs.com/guoran/python:3.10}"
USE_COMMITTED_SYSTEM_BASE="${USE_COMMITTED_SYSTEM_BASE:-true}"
SYSTEM_BASE_SOURCE_IMAGE="${SYSTEM_BASE_SOURCE_IMAGE:-python:3.10-slim-bookworm}"
PYPI_INDEX_URL="${PYPI_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
PYPI_TRUSTED_HOST="${PYPI_TRUSTED_HOST:-mirrors.aliyun.com}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
DOCLING_ARTIFACTS_PATH="${DOCLING_ARTIFACTS_PATH:-/opt/docling/models}"
PYTORCH_ACCELERATOR="${PYTORCH_ACCELERATOR:-cpu}"
PYTORCH_CPU_INDEX_URL="${PYTORCH_CPU_INDEX_URL:-https://download.pytorch.org/whl/cpu}"
PYTORCH_CUDA_INDEX_URL="${PYTORCH_CUDA_INDEX_URL:-}"
case "${PYTORCH_ACCELERATOR}" in
  cpu)
    DEFAULT_SYSTEM_BASE_TAG="bookworm-cpu"
    ;;
  cu128|cu130)
    DEFAULT_SYSTEM_BASE_TAG="bookworm-${PYTORCH_ACCELERATOR}"
    PYTORCH_CUDA_INDEX_URL="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/${PYTORCH_ACCELERATOR}}"
    ;;
  default)
    DEFAULT_SYSTEM_BASE_TAG="bookworm"
    ;;
  *)
    echo "ERROR: unsupported PYTORCH_ACCELERATOR=${PYTORCH_ACCELERATOR}. Use cpu, cu128, cu130, or default." >&2
    exit 2
    ;;
esac
SYSTEM_BASE_IMAGE="${SYSTEM_BASE_IMAGE:-${REGISTRY%/}/movo-document-parser-base:${DEFAULT_SYSTEM_BASE_TAG}}"
REBUILD_SYSTEM_BASE="${REBUILD_SYSTEM_BASE:-false}"
PUSH_SYSTEM_BASE="${PUSH_SYSTEM_BASE:-false}"
RESUME_SYSTEM_BASE_BUILD="${RESUME_SYSTEM_BASE_BUILD:-true}"
SYSTEM_BASE_PRIVILEGED="${SYSTEM_BASE_PRIVILEGED:-true}"
VERIFY_LIBREOFFICE_PRIVILEGED="${VERIFY_LIBREOFFICE_PRIVILEGED:-true}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
CONTEXT_DIR="${CONTEXT_DIR:-.}"
PLATFORM="${PLATFORM:-}"
NO_CACHE="${NO_CACHE:-true}"
PUSH="${PUSH:-true}"
SAVE_TAR="${SAVE_TAR:-false}"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"
BACKGROUND="${BACKGROUND:-false}"
BUILD_MEMORY="${BUILD_MEMORY:-}"
BUILD_MEMORY_SWAP="${BUILD_MEMORY_SWAP:-}"
INSTALL_SYSTEM_DEPS_AT_BUILD="${INSTALL_SYSTEM_DEPS_AT_BUILD:-true}"
INSTALL_PYTHON_DEPS_AT_BUILD="${INSTALL_PYTHON_DEPS_AT_BUILD:-true}"
VERIFY_DOCLING="${VERIFY_DOCLING:-true}"
BUILD_LOG="${BUILD_LOG:-${OUTPUT_DIR}/document-processing-build-${IMAGE_TAG}-${PYTORCH_ACCELERATOR}.log}"

cd "${ROOT_DIR}"

if [[ "${BACKGROUND}" == "true" ]] && [[ "${BACKGROUND_CHILD:-false}" != "true" ]]; then
  mkdir -p "$(dirname "${BUILD_LOG}")"
  nohup env \
    BACKGROUND=false \
    BACKGROUND_CHILD=true \
    ENVIRONMENT="${ENVIRONMENT}" \
    REGISTRY="${REGISTRY}" \
    IMAGE_NAME="${IMAGE_NAME}" \
    IMAGE_TAG="${IMAGE_TAG}" \
    BASE_IMAGE="${BASE_IMAGE}" \
    USE_COMMITTED_SYSTEM_BASE="${USE_COMMITTED_SYSTEM_BASE}" \
    SYSTEM_BASE_SOURCE_IMAGE="${SYSTEM_BASE_SOURCE_IMAGE}" \
    PYPI_INDEX_URL="${PYPI_INDEX_URL}" \
    PYPI_TRUSTED_HOST="${PYPI_TRUSTED_HOST}" \
    HF_ENDPOINT="${HF_ENDPOINT}" \
    DOCLING_ARTIFACTS_PATH="${DOCLING_ARTIFACTS_PATH}" \
    PYTORCH_ACCELERATOR="${PYTORCH_ACCELERATOR}" \
    PYTORCH_CPU_INDEX_URL="${PYTORCH_CPU_INDEX_URL}" \
    PYTORCH_CUDA_INDEX_URL="${PYTORCH_CUDA_INDEX_URL}" \
    SYSTEM_BASE_IMAGE="${SYSTEM_BASE_IMAGE}" \
    REBUILD_SYSTEM_BASE="${REBUILD_SYSTEM_BASE}" \
    PUSH_SYSTEM_BASE="${PUSH_SYSTEM_BASE}" \
    RESUME_SYSTEM_BASE_BUILD="${RESUME_SYSTEM_BASE_BUILD}" \
    SYSTEM_BASE_PRIVILEGED="${SYSTEM_BASE_PRIVILEGED}" \
    VERIFY_LIBREOFFICE_PRIVILEGED="${VERIFY_LIBREOFFICE_PRIVILEGED}" \
    DOCKERFILE="${DOCKERFILE}" \
    CONTEXT_DIR="${CONTEXT_DIR}" \
    PLATFORM="${PLATFORM}" \
    NO_CACHE="${NO_CACHE}" \
    PUSH="${PUSH}" \
    SAVE_TAR="${SAVE_TAR}" \
    OUTPUT_DIR="${OUTPUT_DIR}" \
    BUILD_MEMORY="${BUILD_MEMORY}" \
    BUILD_MEMORY_SWAP="${BUILD_MEMORY_SWAP}" \
    INSTALL_SYSTEM_DEPS_AT_BUILD="${INSTALL_SYSTEM_DEPS_AT_BUILD}" \
    INSTALL_PYTHON_DEPS_AT_BUILD="${INSTALL_PYTHON_DEPS_AT_BUILD}" \
    VERIFY_DOCLING="${VERIFY_DOCLING}" \
    BUILD_LOG="${BUILD_LOG}" \
    "$0" "$@" >"${BUILD_LOG}" 2>&1 &
  background_pid="$!"
  echo "Started document processing image build in background."
  echo "pid               : ${background_pid}"
  echo "log               : ${ROOT_DIR}/${BUILD_LOG}"
  echo "follow log        : tail -f ${ROOT_DIR}/${BUILD_LOG}"
  exit 0
fi

GIT_COMMIT="$(cd "${ROOT_DIR}/.." && git rev-parse HEAD 2>/dev/null || true)"
GIT_STATUS="$(cd "${ROOT_DIR}/.." && git status --short 2>/dev/null || true)"

IMAGE_REF="${REGISTRY%/}/${IMAGE_NAME}:${IMAGE_TAG}"
LOCAL_TAG="${IMAGE_NAME}:${IMAGE_TAG}"
TAR_FILE="${OUTPUT_DIR}/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found. Please install Docker or run this script on a build node with Docker available." >&2
  exit 127
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not available. Please start Docker or configure access to the Docker daemon." >&2
  exit 1
fi

prepare_committed_system_base() {
  if [[ "${USE_COMMITTED_SYSTEM_BASE}" != "true" ]]; then
    return
  fi

  use_system_base_image() {
    BASE_IMAGE="${SYSTEM_BASE_IMAGE}"
    INSTALL_SYSTEM_DEPS_AT_BUILD="false"
    INSTALL_PYTHON_DEPS_AT_BUILD="false"
  }

  if [[ "${REBUILD_SYSTEM_BASE}" != "true" ]] && docker image inspect "${SYSTEM_BASE_IMAGE}" >/dev/null 2>&1; then
    echo "Using existing local system base image: ${SYSTEM_BASE_IMAGE}"
    use_system_base_image
    return
  fi

  if [[ "${REBUILD_SYSTEM_BASE}" != "true" ]]; then
    echo "Local system base image not found, pulling: ${SYSTEM_BASE_IMAGE}"
    if docker pull "${SYSTEM_BASE_IMAGE}"; then
      echo "Using pulled system base image: ${SYSTEM_BASE_IMAGE}"
      use_system_base_image
      return
    fi
    echo "System base image pull failed; rebuilding locally: ${SYSTEM_BASE_IMAGE}"
  fi

  local container_name="${IMAGE_NAME}-system-base-build"
  local staging_image="${SYSTEM_BASE_IMAGE}-staging"
  local build_source_image="${SYSTEM_BASE_SOURCE_IMAGE}"
  if [[ "${RESUME_SYSTEM_BASE_BUILD}" == "true" ]] && docker image inspect "${staging_image}" >/dev/null 2>&1; then
    build_source_image="${staging_image}"
    echo "Resuming system base build from staging image: ${staging_image}"
  fi
  echo "Preparing movo document parser base image: ${SYSTEM_BASE_IMAGE}"
  echo "Source image: ${build_source_image}"
  docker rm -f "${container_name}" >/dev/null 2>&1 || true

  system_base_run_args=()
  if [[ "${SYSTEM_BASE_PRIVILEGED}" == "true" ]]; then
    system_base_run_args+=(--privileged)
  fi

  if ! docker run \
    "${system_base_run_args[@]}" \
    -e "PIP_INDEX_URL=${PYPI_INDEX_URL}" \
    -e "PIP_TRUSTED_HOST=${PYPI_TRUSTED_HOST}" \
    -e "HF_ENDPOINT=${HF_ENDPOINT}" \
    -e "DOCLING_ARTIFACTS_PATH=${DOCLING_ARTIFACTS_PATH}" \
    -e "PYTORCH_ACCELERATOR=${PYTORCH_ACCELERATOR}" \
    -e "PYTORCH_CPU_INDEX_URL=${PYTORCH_CPU_INDEX_URL}" \
    -e "PYTORCH_CUDA_INDEX_URL=${PYTORCH_CUDA_INDEX_URL}" \
    -v "${ROOT_DIR}/requirements.txt:/tmp/requirements.txt:ro" \
    -v "${ROOT_DIR}/requirements-docling.txt:/tmp/requirements-docling.txt:ro" \
    --name "${container_name}" \
    "${build_source_image}" bash -lc '
set -euo pipefail
if [ -f /etc/apt/sources.list ]; then
  sed -i "s|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g" /etc/apt/sources.list
fi
if [ -f /etc/apt/sources.list.d/debian.sources ]; then
  sed -i "s|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g" /etc/apt/sources.list.d/debian.sources
fi
unset XZ_DEFAULTS XZ_OPT
rm -f /etc/apt/apt.conf.d/docker-clean
apt-get clean
rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*
apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  fontconfig \
  fonts-wqy-zenhei \
  fonts-noto-cjk \
  libgl1 \
  libglib2.0-0 \
  libgomp1 \
  libreoffice-core \
  libreoffice-common \
  libreoffice-writer \
  libreoffice-calc \
  libreoffice-impress
python -m pip install --progress-bar off --upgrade pip setuptools wheel
case "${PYTORCH_ACCELERATOR}" in
  cpu)
    python -m pip install --progress-bar off --index-url "${PYTORCH_CPU_INDEX_URL}" "torch>=2.2.2,<3.0.0" "torchvision>=0,<1"
    ;;
  cu128|cu130)
    python -m pip install --progress-bar off --index-url "${PYTORCH_CUDA_INDEX_URL}" "torch>=2.2.2,<3.0.0" "torchvision>=0,<1"
    ;;
  default)
    echo "Skip PyTorch preinstall (PYTORCH_ACCELERATOR=default)"
    ;;
esac
python -m pip install --progress-bar off -r /tmp/requirements.txt
python -m pip install --progress-bar off --prefer-binary -r /tmp/requirements-docling.txt
python - <<PY
from pathlib import Path
from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
from docling.utils.model_downloader import download_models

output_dir = Path("${DOCLING_ARTIFACTS_PATH}")
print(f"Downloading Docling offline models to {output_dir}")
download_models(
    output_dir=output_dir,
    progress=True,
    with_layout=True,
    with_tableformer=True,
    with_code_formula=False,
    with_picture_classifier=False,
    with_rapidocr=False,
)
print("Downloading Docling RapidOCR onnxruntime models")
RapidOcrModel.download_models(
    backend="onnxruntime",
    local_dir=output_dir / RapidOcrModel._model_repo_folder,
    progress=True,
)
PY
HF_HUB_OFFLINE=1 python - <<PY
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

options = PdfPipelineOptions(artifacts_path="${DOCLING_ARTIFACTS_PATH}")
StandardPdfPipeline(options)
print("docling offline pipeline ok")
PY
python -c "from docling.document_converter import DocumentConverter; print(\"docling ok\")"
python -c "import torch; print(f\"torch {torch.__version__}, cuda_available={torch.cuda.is_available()}, cuda={torch.version.cuda}\")"
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*
libreoffice --version
'; then
    echo "System base build failed; saving reusable staging image: ${staging_image}" >&2
    docker commit "${container_name}" "${staging_image}" >/dev/null
    docker rm -f "${container_name}" >/dev/null 2>&1 || true
    echo "Re-run the same command to resume without reinstalling completed dependencies." >&2
    return 1
  fi

  docker commit "${container_name}" "${SYSTEM_BASE_IMAGE}"
  docker rm -f "${container_name}" >/dev/null
  docker image rm "${staging_image}" >/dev/null 2>&1 || true
  docker run "${system_base_run_args[@]}" --rm "${SYSTEM_BASE_IMAGE}" libreoffice --version

  if [[ "${PUSH_SYSTEM_BASE}" == "true" ]]; then
    docker push "${SYSTEM_BASE_IMAGE}"
  fi

  BASE_IMAGE="${SYSTEM_BASE_IMAGE}"
  INSTALL_SYSTEM_DEPS_AT_BUILD="false"
  INSTALL_PYTHON_DEPS_AT_BUILD="false"
}

prepare_committed_system_base

echo "=== Document processing big package build ==="
echo "environment       : ${ENVIRONMENT}"
echo "image             : ${IMAGE_REF}"
echo "base image        : ${BASE_IMAGE}"
echo "system base mode  : ${USE_COMMITTED_SYSTEM_BASE}"
echo "system base image : ${SYSTEM_BASE_IMAGE}"
echo "pypi index        : ${PYPI_INDEX_URL}"
echo "pypi trusted host : ${PYPI_TRUSTED_HOST}"
echo "hf endpoint       : ${HF_ENDPOINT}"
echo "docling models    : ${DOCLING_ARTIFACTS_PATH}"
echo "pytorch accel     : ${PYTORCH_ACCELERATOR}"
echo "pytorch cpu index : ${PYTORCH_CPU_INDEX_URL}"
echo "pytorch cuda index: ${PYTORCH_CUDA_INDEX_URL:-default}"
echo "system privileged : ${SYSTEM_BASE_PRIVILEGED}"
echo "verify lo priv    : ${VERIFY_LIBREOFFICE_PRIVILEGED}"
echo "dockerfile        : ${DOCKERFILE}"
echo "context           : ${CONTEXT_DIR}"
echo "platform          : ${PLATFORM:-default}"
echo "no-cache          : ${NO_CACHE}"
echo "push              : ${PUSH}"
echo "save-tar          : ${SAVE_TAR}"
echo "system-deps       : ${INSTALL_SYSTEM_DEPS_AT_BUILD}"
echo "python-deps       : ${INSTALL_PYTHON_DEPS_AT_BUILD}"
echo "verify            : ${VERIFY_DOCLING}"
echo "memory            : ${BUILD_MEMORY:-default}"
echo "memory-swap       : ${BUILD_MEMORY_SWAP:-default}"
echo "git commit        : ${GIT_COMMIT:-unknown}"
if [[ -n "${GIT_STATUS}" ]]; then
  echo "git status        : dirty"
  echo "${GIT_STATUS}"
else
  echo "git status        : clean"
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
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  --build-arg "PYPI_INDEX_URL=${PYPI_INDEX_URL}" \
  --build-arg "PYPI_TRUSTED_HOST=${PYPI_TRUSTED_HOST}" \
  --build-arg "INSTALL_SYSTEM_DEPS_AT_BUILD=${INSTALL_SYSTEM_DEPS_AT_BUILD}" \
  --build-arg "INSTALL_PYTHON_DEPS_AT_BUILD=${INSTALL_PYTHON_DEPS_AT_BUILD}" \
  --build-arg "PYTORCH_ACCELERATOR=${PYTORCH_ACCELERATOR}" \
  --build-arg "PYTORCH_CPU_INDEX_URL=${PYTORCH_CPU_INDEX_URL}" \
  --build-arg "PYTORCH_CUDA_INDEX_URL=${PYTORCH_CUDA_INDEX_URL}" \
  -f "${DOCKERFILE}" \
  -t "${LOCAL_TAG}" \
  "${CONTEXT_DIR}"

docker tag "${LOCAL_TAG}" "${IMAGE_REF}"

if [[ "${VERIFY_DOCLING}" == "true" ]]; then
  echo "Verifying built image imports Docling..."
  docker run --rm --entrypoint python "${LOCAL_TAG}" -c "from docling.document_converter import DocumentConverter; print('docling ok')"
  docker run --rm --entrypoint python "${LOCAL_TAG}" -c "import importlib.util, numpy; assert numpy.__version__ == '1.26.4', numpy.__version__; assert importlib.util.find_spec('onnxruntime'); assert importlib.util.find_spec('rapidocr'); print('ocr deps ok')"
  verify_pipeline_run_args=()
  if [[ "${SYSTEM_BASE_PRIVILEGED}" == "true" ]]; then
    verify_pipeline_run_args+=(--privileged)
  fi
  docker run "${verify_pipeline_run_args[@]}" --rm -e HF_HUB_OFFLINE=1 --entrypoint python "${LOCAL_TAG}" -c "from docling.datamodel.pipeline_options import PdfPipelineOptions; from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline; StandardPdfPipeline(PdfPipelineOptions()); print('business image offline pipeline ok')"
  verify_lo_run_args=()
  if [[ "${VERIFY_LIBREOFFICE_PRIVILEGED}" == "true" ]]; then
    verify_lo_run_args+=(--privileged)
  fi
  docker run "${verify_lo_run_args[@]}" --rm "${LOCAL_TAG}" libreoffice --version
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

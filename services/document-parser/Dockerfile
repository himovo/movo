ARG BASE_IMAGE=python:3.10-slim-bookworm
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PROGRESS_BAR=off \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models \
    MOVO_DOC_PROCESSING_LIBREOFFICE_BIN=/usr/bin/libreoffice

WORKDIR /app

ARG INSTALL_SYSTEM_DEPS_AT_BUILD=true
ARG INSTALL_PYTHON_DEPS_AT_BUILD=true
ARG PYTORCH_ACCELERATOR=cpu
ARG PYTORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG PYTORCH_CUDA_INDEX_URL=
ARG INSTALL_DOCLING_MODELS_AT_BUILD=true
ARG MOVO_APT_MIRROR=
ARG MOVO_APT_SECURITY_MIRROR=
ARG MOVO_PYPI_INDEX_URL=
ARG MOVO_HF_ENDPOINT=
COPY scripts /tmp/document-parser-scripts
RUN if [ -n "${MOVO_APT_MIRROR}" ]; then \
        for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
            if [ -f "${source_file}" ]; then \
                sed -i "s|http://deb.debian.org/debian|${MOVO_APT_MIRROR}|g; s|https://deb.debian.org/debian|${MOVO_APT_MIRROR}|g" "${source_file}"; \
                if [ -n "${MOVO_APT_SECURITY_MIRROR}" ]; then \
                    sed -i "s|http://deb.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|https://deb.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|http://security.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|https://security.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g" "${source_file}"; \
                fi; \
            fi; \
        done; \
    fi \
    && if [ -n "${MOVO_PYPI_INDEX_URL}" ]; then \
        python -m pip config set global.index-url "${MOVO_PYPI_INDEX_URL}"; \
    fi
RUN if [ "${INSTALL_SYSTEM_DEPS_AT_BUILD}" = "true" ]; then \
        unset XZ_DEFAULTS XZ_OPT \
        && rm -f /etc/apt/apt.conf.d/docker-clean \
        && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update \
        && apt-get install -y --no-install-recommends \
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
            libreoffice-impress \
        && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Skip apt system dependencies in build stage (INSTALL_SYSTEM_DEPS_AT_BUILD=false)"; \
    fi

COPY requirements.txt /tmp/requirements.txt
COPY requirements-docling.txt /tmp/requirements-docling.txt

RUN if [ "${INSTALL_PYTHON_DEPS_AT_BUILD}" = "true" ]; then \
        python -m pip install --progress-bar off --upgrade pip setuptools wheel \
        && case "${PYTORCH_ACCELERATOR}" in \
            cpu) \
                python -m pip install --progress-bar off --index-url "${PYTORCH_CPU_INDEX_URL}" "torch>=2.2.2,<3.0.0" "torchvision>=0,<1" ;; \
            cu128|cu130) \
                python -m pip install --progress-bar off --index-url "${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/${PYTORCH_ACCELERATOR}}" "torch>=2.2.2,<3.0.0" "torchvision>=0,<1" ;; \
            default) \
                echo "Skip PyTorch preinstall (PYTORCH_ACCELERATOR=default)" ;; \
            *) \
                echo "Unsupported PYTORCH_ACCELERATOR=${PYTORCH_ACCELERATOR}" >&2; exit 2 ;; \
        esac \
        && python -m pip install --progress-bar off -r /tmp/requirements.txt \
        && python -m pip install --progress-bar off --prefer-binary -r /tmp/requirements-docling.txt \
        && python -m pip uninstall --yes pip wheel \
        && find /usr/local/lib/python3.10/ensurepip/_bundled -type f -delete; \
    else \
        echo "Skip Python dependencies in build stage (INSTALL_PYTHON_DEPS_AT_BUILD=false)"; \
    fi \
    && python -c "from docling.document_converter import DocumentConverter; print('docling ok')" \
    && python -c "import torch; print(f'torch {torch.__version__}, cuda_available={torch.cuda.is_available()}, cuda={torch.version.cuda}')"

RUN if [ "${INSTALL_DOCLING_MODELS_AT_BUILD}" = "true" ]; then \
        if [ -n "${MOVO_HF_ENDPOINT}" ]; then export HF_ENDPOINT="${MOVO_HF_ENDPOINT}"; fi; \
        python /tmp/document-parser-scripts/download_docling_models.py; \
    else \
        echo "Skip Docling model download (INSTALL_DOCLING_MODELS_AT_BUILD=false)"; \
    fi \
    && HF_HUB_OFFLINE=1 python /tmp/document-parser-scripts/verify_docling_runtime.py

ENV HF_HUB_OFFLINE=1

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY app /app/app
COPY .env.example /app/.env.example

EXPOSE 8200

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]

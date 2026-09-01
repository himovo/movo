FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PROGRESS_BAR=off \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

ARG INSTALL_SYSTEM_DEPS_AT_BUILD=false
RUN if [ "${INSTALL_SYSTEM_DEPS_AT_BUILD}" = "true" ]; then \
        unset XZ_DEFAULTS XZ_OPT \
        && rm -f /etc/apt/apt.conf.d/docker-clean \
        && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update \
        && apt-get install -y --no-install-recommends \
            ca-certificates \
            curl \
            wget \
            unzip \
            fontconfig \
            fonts-wqy-zenhei \
            fonts-noto-color-emoji \
        && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Skip apt system dependencies in build stage (INSTALL_SYSTEM_DEPS_AT_BUILD=false)"; \
    fi

COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install --progress-bar off --upgrade pip setuptools wheel \
    && python -m pip install --progress-bar off -r /tmp/requirements.txt

ARG INSTALL_PLAYWRIGHT_AT_BUILD=false
ARG PLAYWRIGHT_WITH_DEPS=false
RUN if [ "${INSTALL_PLAYWRIGHT_AT_BUILD}" = "true" ]; then \
        if [ "${PLAYWRIGHT_WITH_DEPS}" = "true" ]; then \
            playwright install --with-deps chromium; \
        else \
            playwright install chromium; \
        fi; \
    else \
        echo "Skip playwright browser install in build stage (INSTALL_PLAYWRIGHT_AT_BUILD=false)"; \
    fi

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY app /app/app
COPY .env.example /app/.env.example

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

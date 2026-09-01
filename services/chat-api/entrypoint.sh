#!/usr/bin/env bash
set -euo pipefail

load_runtime_secrets() {
  local secret_file="${ASKAI_RUNTIME_SECRETS_FILE:-/run/askai-secrets/runtime.env}"
  if [[ -r "${secret_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${secret_file}"
    set +a
  fi
}

prepare_apt_mirror() {
  if [[ -f /etc/apt/sources.list ]]; then
    sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list || true
  fi
  if [[ -f /etc/apt/sources.list.d/debian.sources ]]; then
    sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources || true
  fi
  unset XZ_DEFAULTS XZ_OPT || true
  rm -f /etc/apt/apt.conf.d/docker-clean || true
}

install_system_deps_on_start() {
  if [[ "${AUTO_INSTALL_SYSTEM_DEPS_ON_START:-true}" != "true" ]]; then
    echo "[entrypoint] Skip system deps install (AUTO_INSTALL_SYSTEM_DEPS_ON_START != true)"
    return 0
  fi

  if command -v fc-list >/dev/null 2>&1 && fc-list | grep -qiE "WenQuanYi|Noto Color Emoji"; then
    echo "[entrypoint] Fonts already present"
  fi

  if command -v curl >/dev/null 2>&1 && command -v wget >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1; then
    echo "[entrypoint] Base system tools already present"
  fi

  echo "[entrypoint] Installing system dependencies at container startup..."
  prepare_apt_mirror

  apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update
  apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    unzip \
    fontconfig \
    fonts-wqy-zenhei \
    fonts-noto-color-emoji
  rm -rf /var/lib/apt/lists/*

  echo "[entrypoint] System dependencies installed"
}

install_playwright_on_start() {
  if [[ "${AUTO_INSTALL_PLAYWRIGHT_ON_START:-true}" != "true" ]]; then
    echo "[entrypoint] Skip playwright install (AUTO_INSTALL_PLAYWRIGHT_ON_START != true)"
    return 0
  fi

  echo "[entrypoint] Installing Playwright Chromium at container startup..."
  if [[ "${PLAYWRIGHT_INSTALL_WITH_DEPS_ON_START:-true}" = "true" ]]; then
    playwright install --with-deps chromium
  else
    playwright install chromium
  fi
  echo "[entrypoint] Playwright Chromium installed"
}

main() {
  load_runtime_secrets
  if [[ "${REQUIRE_RUNTIME_PREPARE_SUCCESS:-true}" = "true" ]]; then
    install_system_deps_on_start
    install_playwright_on_start
  else
    install_system_deps_on_start || echo "[entrypoint] WARNING: system deps install failed"
    install_playwright_on_start || echo "[entrypoint] WARNING: playwright install failed"
  fi

  exec "$@"
}

main "$@"

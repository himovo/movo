#!/usr/bin/env bash

MOVO_VOLUME_SUFFIXES=(
  deployment-secrets
  mongo-data
  redis-data
  weaviate-data
  dsh-runtime-data
  askai-storage
  knowledge-storage
  admin-static
)

movo_sha256_create() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum ./*.tar.gz
  else
    shasum -a 256 ./*.tar.gz
  fi
}

movo_sha256_verify() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c SHA256SUMS
  else
    shasum -a 256 -c SHA256SUMS
  fi
}

movo_volume_prefix() {
  local prefix="${MOVO_VOLUME_PREFIX:-$(dotenv_value MOVO_VOLUME_PREFIX)}"
  prefix="${prefix:-movo}"
  if [[ ! "${prefix}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    printf 'Invalid MOVO_VOLUME_PREFIX: %s\n' "${prefix}" >&2
    return 2
  fi
  printf '%s' "${prefix}"
}

movo_write_backup() {
  local target_dir="$1"
  local prefix="$2"
  local suffix volume
  for suffix in "${MOVO_VOLUME_SUFFIXES[@]}"; do
    volume="${prefix}_${suffix}"
    if ! "${DOCKER_BIN}" volume inspect "${volume}" >/dev/null 2>&1; then
      printf 'Required Docker volume does not exist: %s\n' "${volume}" >&2
      return 1
    fi
    "${DOCKER_BIN}" run --rm \
      -v "${volume}:/source:ro" \
      -v "${target_dir}:/backup" \
      alpine:3.21 tar -C /source -czf "/backup/${suffix}.tar.gz" .
  done
  printf '%s\n' "${prefix}" > "${target_dir}/volume-prefix.txt"
  printf '%s\n' "${MOVO_VERSION:-latest}" > "${target_dir}/movo-version.txt"
  git -C "${ROOT_DIR}" rev-parse HEAD > "${target_dir}/git-commit.txt" 2>/dev/null || true
  (
    cd "${target_dir}"
    movo_sha256_create > SHA256SUMS
  )
}

movo_backup() {
  local requested="${1:-}"
  local target_dir prefix timestamp
  prefix="$(movo_volume_prefix)"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target_dir="${requested:-${ROOT_DIR}/backups/movo-backup-${timestamp}}"
  if [[ "${target_dir}" != /* ]]; then
    target_dir="${ROOT_DIR}/${target_dir}"
  fi
  if [[ -e "${target_dir}" ]]; then
    printf 'Backup destination already exists: %s\n' "${target_dir}" >&2
    return 2
  fi
  mkdir -p "${target_dir}"

  movo_msg backup_stopping
  movo_compose stop
  if ! movo_write_backup "${target_dir}" "${prefix}"; then
    movo_msg backup_failed >&2
    movo_compose up -d || true
    return 1
  fi
  movo_compose up -d
  refresh_gateway_resolution
  wait_until_ready
  movo_msg backup_complete "${target_dir}"
}

movo_restore() {
  local source_dir="$1"
  local confirmed="${2:-false}"
  local prefix archived_prefix suffix volume
  if [[ "${source_dir}" != /* ]]; then
    source_dir="${ROOT_DIR}/${source_dir}"
  fi
  if [[ ! -d "${source_dir}" || ! -f "${source_dir}/SHA256SUMS" || ! -f "${source_dir}/volume-prefix.txt" ]]; then
    printf 'Invalid MOVO backup directory: %s\n' "${source_dir}" >&2
    return 2
  fi
  prefix="$(movo_volume_prefix)"
  archived_prefix="$(tr -d '\r\n' < "${source_dir}/volume-prefix.txt")"
  if [[ "${archived_prefix}" != "${prefix}" ]]; then
    printf 'Backup volume prefix %s does not match configured prefix %s.\n' "${archived_prefix}" "${prefix}" >&2
    return 2
  fi
  (
    cd "${source_dir}"
    movo_sha256_verify
  )
  if [[ "${confirmed}" != "true" ]]; then
    movo_msg restore_confirm
    return 2
  fi

  movo_compose down
  for suffix in "${MOVO_VOLUME_SUFFIXES[@]}"; do
    if [[ ! -f "${source_dir}/${suffix}.tar.gz" ]]; then
      printf 'Backup archive is missing: %s.tar.gz\n' "${suffix}" >&2
      return 1
    fi
    volume="${prefix}_${suffix}"
    "${DOCKER_BIN}" volume create "${volume}" >/dev/null
    "${DOCKER_BIN}" run --rm \
      -v "${volume}:/target" \
      -v "${source_dir}:/backup:ro" \
      alpine:3.21 sh -ec \
      "find /target -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf '/backup/${suffix}.tar.gz' -C /target"
  done
  movo_compose up -d
  refresh_gateway_resolution
  wait_until_ready
  movo_msg restore_complete
}

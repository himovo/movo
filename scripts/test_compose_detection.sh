#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/deploy/cli/compose.sh"
source "${ROOT_DIR}/deploy/cli/images.sh"
movo_msg() { :; }
DOCKER_BIN=fake_docker
plugin_version='Docker Compose version v2.33.1'
standalone_version='Docker Compose version v2.33.1'
selected=''
forwarded=()
fake_docker() {
  if [[ "$*" == 'compose version' ]]; then
    [[ -n "${plugin_version}" ]] || return 1
    printf '%s\n' "${plugin_version}"
  else
    selected=plugin
    forwarded=("$@")
  fi
}
docker-compose() {
  if [[ "$*" == version ]]; then
    [[ -n "${standalone_version}" ]] || return 1
    printf '%s\n' "${standalone_version}"
  else
    selected=standalone
    forwarded=("$@")
  fi
}
movo_detect_compose
movo_compose up -d --pull never
[[ "${selected}" == plugin ]]
[[ "${forwarded[*]}" == "compose -f ${ROOT_DIR}/docker-compose.yml up -d --pull never" ]]
plugin_version=''
movo_detect_compose
movo_compose up -d --pull never
[[ "${selected}" == standalone ]]
[[ "${forwarded[*]}" == "-f ${ROOT_DIR}/docker-compose.yml up -d --pull never" ]]
MOVO_COMPOSE_BUILD=true
movo_compose build chat-api
[[ "${forwarded[*]}" == "-f ${ROOT_DIR}/docker-compose.yml -f ${ROOT_DIR}/docker-compose.build.yml build chat-api" ]]
movo_compose_command -p askai down --remove-orphans
[[ "${forwarded[*]}" == '-p askai down --remove-orphans' ]]
plugin_version='Docker version 28.0.1, build test'
movo_detect_compose
[[ "${MOVO_COMPOSE_COMMAND[*]}" == docker-compose ]]
standalone_version='docker-compose version 1.29.2, build test'
if movo_detect_compose; then
  printf 'Expected Compose v1 and Docker Engine version output to be rejected.\n' >&2
  exit 1
fi
plugin_version='Docker Compose version v5.1.4'
movo_detect_compose
[[ "${MOVO_COMPOSE_COMMAND[*]}" == 'fake_docker compose' ]]
plugin_version=''
standalone_version='Docker Compose version v2.33.1'
MOVO_COMPOSE_COMMAND=()
movo_compose_command version >/dev/null
[[ "${MOVO_COMPOSE_COMMAND[*]}" == docker-compose ]]
printf 'Compose command detection and argument forwarding are valid.\n'

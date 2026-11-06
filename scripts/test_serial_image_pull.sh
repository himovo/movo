#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=../deploy/cli/pull.sh
source "${ROOT_DIR}/deploy/cli/pull.sh"

movo_msg() { :; }
dotenv_value() { :; }
sleep() { :; }

calls=()
failures_remaining=0
failure_status=1
movo_compose() {
  calls+=("$*")
  if ((failures_remaining > 0)); then
    failures_remaining=$((failures_remaining - 1))
    return "${failure_status}"
  fi
}

calls=()
failures_remaining=4
MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially always
[[ "${#calls[@]}" -eq 5 ]]
[[ "${calls[4]}" == "--parallel 1 pull --policy always" ]]

calls=()
failures_remaining=1
failure_status=130
if MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially always; then
  printf 'Expected an interrupted pull to stop.\n' >&2
  exit 1
else
  pull_status=$?
fi
[[ "${pull_status}" -eq 130 ]]
[[ "${#calls[@]}" -eq 1 ]]

DOCKER_BIN=fake_docker
local_images=true
pull_failure=false
docker_calls=()
fake_docker() {
  docker_calls+=("$*")
  if [[ "$1 $2" == 'image inspect' ]]; then
    [[ "${local_images}" == true || "$3" == cached:latest ]]
  elif [[ "$1" == pull ]]; then
    [[ "${pull_failure}" == false ]]
  else
    return 1
  fi
}
movo_compose() {
  [[ "$*" == 'config --images' ]] || return 1
  printf '%s\n' cached:latest missing:v1 missing:v1
}
movo_pull_images_serially missing
[[ "${#docker_calls[@]}" -eq 2 ]]
[[ "${docker_calls[0]}" == 'image inspect cached:latest' ]]
[[ "${docker_calls[1]}" == 'image inspect missing:v1' ]]

local_images=false
docker_calls=()
movo_pull_images_serially missing
[[ "${#docker_calls[@]}" -eq 3 ]]
[[ "${docker_calls[2]}" == 'pull missing:v1' ]]

pull_failure=true
if movo_pull_images_serially missing; then
  printf 'Expected unavailable missing image to fail without endless retries.\n' >&2
  exit 1
fi
movo_compose() { return 1; }
docker_calls=()
if movo_pull_images_serially missing; then
  printf 'Expected invalid Compose configuration to fail.\n' >&2
  exit 1
fi
[[ ${#docker_calls[@]} -eq 0 ]]

printf 'Serial image pull behavior is valid.\n'

movo_compose() { printf '%s\n' missing:v1; }
MOVO_OFFLINE_ONLY=1
pull_failure=false
docker_calls=()
if movo_pull_images_serially missing; then
  printf 'Expected an offline missing image to fail.\n' >&2
  exit 1
fi
[[ "${#docker_calls[@]}" -eq 1 ]]
[[ "${docker_calls[0]}" == 'image inspect missing:v1' ]]

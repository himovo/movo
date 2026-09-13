#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=../deploy/cli/pull.sh
source "${ROOT_DIR}/deploy/cli/pull.sh"

movo_msg() { :; }
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

movo_pull_images_serially missing
[[ "${#calls[@]}" -eq 1 ]]
[[ "${calls[0]}" == "--parallel 1 pull --policy missing" ]]

calls=()
failures_remaining=4
MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially always
[[ "${#calls[@]}" -eq 5 ]]
[[ "${calls[4]}" == "--parallel 1 pull --policy always" ]]

calls=()
failures_remaining=1
failure_status=130
if MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially missing; then
  printf 'Expected an interrupted pull to stop.\n' >&2
  exit 1
else
  pull_status=$?
fi
[[ "${pull_status}" -eq 130 ]]
[[ "${#calls[@]}" -eq 1 ]]

printf 'Serial image pull behavior is valid.\n'

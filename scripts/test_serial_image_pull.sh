#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=../deploy/cli/pull.sh
source "${ROOT_DIR}/deploy/cli/pull.sh"

movo_msg() { :; }
sleep() { :; }

calls=()
failures_remaining=0
movo_compose() {
  calls+=("$*")
  if ((failures_remaining > 0)); then
    failures_remaining=$((failures_remaining - 1))
    return 1
  fi
}

movo_pull_images_serially missing
[[ "${#calls[@]}" -eq 1 ]]
[[ "${calls[0]}" == "--parallel 1 pull --policy missing" ]]

calls=()
failures_remaining=2
MOVO_PULL_RETRIES=3 MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially always
[[ "${#calls[@]}" -eq 3 ]]
[[ "${calls[2]}" == "--parallel 1 pull --policy always" ]]

calls=()
failures_remaining=3
if MOVO_PULL_RETRIES=2 MOVO_PULL_RETRY_DELAY_SECONDS=0 movo_pull_images_serially missing; then
  printf 'Expected serial pull to fail after exhausting retries.\n' >&2
  exit 1
fi
[[ "${#calls[@]}" -eq 2 ]]

printf 'Serial image pull behavior is valid.\n'

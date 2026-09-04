#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/release/create_github_release.sh <vX.Y.Z[-prerelease]> [--notes-file PATH]

Creates a GitHub Release for an existing remote tag after the corresponding
Container Release workflow has completed successfully. This script never
creates or pushes a tag, so it does not trigger a container rebuild.
EOF
}

version="${1:-}"
if [[ -z "$version" || "$version" == "-h" || "$version" == "--help" ]]; then
  usage
  [[ -n "$version" ]] && exit 0
  exit 2
fi
shift

notes_file=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --notes-file)
      [[ $# -ge 2 ]] || { echo "--notes-file requires a path" >&2; exit 2; }
      notes_file="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
  echo "Version must look like v1.2.3 or v1.2.3-rc.1: $version" >&2
  exit 2
fi

for command_name in git gh; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

gh auth status >/dev/null
repository="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"

if existing_url="$(gh release view "$version" --repo "$repository" --json url --jq .url 2>/dev/null)"; then
  echo "GitHub Release already exists: $existing_url"
  exit 0
fi

tag_commit="$(git rev-parse "${version}^{commit}" 2>/dev/null || true)"
if [[ -z "$tag_commit" ]]; then
  echo "Local tag does not exist: $version" >&2
  exit 1
fi

remote_tag="$(git ls-remote --tags origin "refs/tags/$version" "refs/tags/$version^{}")"
if [[ -z "$remote_tag" ]]; then
  echo "Tag has not been pushed to origin: $version" >&2
  exit 1
fi

remote_commit="$(printf '%s\n' "$remote_tag" | awk '$2 ~ /\^\{\}$/ {print $1; found=1} END {if (!found) print first} NR == 1 {first=$1}')"
if [[ "$remote_commit" != "$tag_commit" ]]; then
  echo "Local and remote tag commits differ for $version" >&2
  echo "Local:  $tag_commit" >&2
  echo "Remote: $remote_commit" >&2
  exit 1
fi

run_data="$(gh run list \
  --repo "$repository" \
  --workflow container-release.yml \
  --branch "$version" \
  --event push \
  --limit 1 \
  --json status,conclusion,url,headSha \
  --jq '.[0] | [.status, .conclusion, .url, .headSha] | @tsv')"

if [[ -z "$run_data" ]]; then
  echo "No Container Release workflow run found for $version" >&2
  exit 1
fi

IFS=$'\t' read -r run_status run_conclusion run_url run_sha <<< "$run_data"
if [[ "$run_status" != "completed" || "$run_conclusion" != "success" ]]; then
  echo "Container Release has not succeeded for $version: $run_url" >&2
  echo "Status: $run_status; conclusion: ${run_conclusion:-none}" >&2
  exit 1
fi
if [[ "$run_sha" != "$tag_commit" ]]; then
  echo "Container Release commit does not match $version: $run_url" >&2
  exit 1
fi

release_args=(
  release create "$version"
  --repo "$repository"
  --verify-tag
  --title "MOVO Community Edition $version"
)

if [[ -n "$notes_file" ]]; then
  [[ -f "$notes_file" ]] || { echo "Notes file not found: $notes_file" >&2; exit 1; }
  release_args+=(--notes-file "$notes_file")
else
  release_args+=(--generate-notes)
fi

if [[ "$version" == *-* ]]; then
  release_args+=(--prerelease)
else
  release_args+=(--latest)
fi

echo "Container images verified: $run_url"
echo "Creating GitHub Release for $repository at $version"
gh "${release_args[@]}"

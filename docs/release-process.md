# Release process

MOVO Community releases are immutable Git commits, Git tags and matching GHCR
image tags. Do not publish a release while an item in
`docs/open-source-productization/release-checklist.md` remains unresolved.

## One-time GitHub setup

1. Create the public repository and push the reviewed history.
2. Enable branch protection for `main` and require the Runtime, Web, Community
   and DSH guards.
3. Enable Discussions and private vulnerability reporting.
4. Run the `Container Release` workflow manually once. This publishes only
   commit-SHA candidate tags and validates both `linux/amd64` and `linux/arm64`.
5. Set every `movo-*` GHCR package to public visibility so Docker users can pull
   anonymously. Confirm each package is linked to the repository.

## Release candidate

1. Resolve the legal copyright owner, security contact and asset-distribution
   review recorded in the release checklist.
2. Update `CHANGELOG.md` and choose a semantic version such as `v0.1.0-rc.1`.
3. Run all required checks and the manual container workflow on the exact
   candidate commit.
4. On fresh amd64 and arm64 hosts, clone the tag, set `MOVO_VERSION` to that
   tag, run `./movo up`, complete setup, and exercise chat, document parsing,
   knowledge retrieval and presentation generation.
5. Restore a backup into a disposable installation and exercise rollback to
   the previous image tag.
6. Create and push the signed tag only after those checks pass.

The tag workflow publishes seven image families, creates build provenance and
SBOM attestations, and rejects images with known fixable high or critical
vulnerabilities. Prerelease tags never update `latest`.

## Stable release

Publish GitHub release notes from the corresponding `CHANGELOG.md` entry. A
stable `vX.Y.Z` tag also updates `latest`, but production documentation and
support responses must continue recommending an explicit version tag.

After the tag-triggered `Container Release` workflow succeeds, create the
GitHub Release with:

```bash
scripts/release/create_github_release.sh vX.Y.Z
```

The script verifies that the tag exists on `origin`, that its container release
completed successfully for the same commit, and then marks a stable release as
Latest. It never creates or pushes a tag and therefore does not trigger another
container build. Pass `--notes-file PATH` to publish reviewed notes from the
matching changelog entry; otherwise GitHub generates the notes.

If any image build, vulnerability scan or attestation fails, do not create a
GitHub Release. Fix the cause, create a new candidate commit and use a new tag;
never move or overwrite an existing public release tag.

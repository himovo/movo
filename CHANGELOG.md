# Changelog

All notable MOVO Community Edition changes are recorded here. Releases use
semantic version tags and the same tag is applied to every published container
image.

## Unreleased

### Added

- Share conversations with other users in the same organization through a
  revocable, expiring session share link. Recipients log in when needed and
  join from the link, and the session appears under a "Shared with me"
  sidebar section; both members see the full author-labelled history while
  each keeps their own model, tools, and permissions.

### Fixed

- Refresh Skill feedback state when new feedback notifications arrive without
  interrupting the current page with a loading state.
- Copy Skill sharing links in desktop WebViews that expose the Clipboard API
  but deny direct clipboard writes.

## v0.1.14 - 2026-09-15

### Fixed

- Avoid rebuilding unchanged container images when only the release workflow or
  release planner changes; full rebuilds now require an explicit operator request.
- Apply available Debian security updates to runtime images before publishing.
- Build and scan immutable candidate images before promoting a release to its
  version and `latest` tags, and use the last successful container release as
  the incremental-build baseline.

## v0.1.13 - 2026-09-15

### Added

- Complete the Skill distribution lifecycle with publishing, direct sharing,
  update discovery, feedback, and organization-level management.
- Support installing external Skills from ZIP packages and show their source,
  version, update status, and local modifications in the Web workspace.
- Add clearer Windows installation guidance for Docker Desktop, WSL 2, Ubuntu,
  and common WSL environment mistakes.

### Changed

- Use the official GHCR images by default so both `./movo up` and native
  `docker compose up -d` work without an `.env` file.
- Pull container images sequentially and keep retrying interrupted downloads
  until they succeed or the user stops the launcher.
- Improve the English and Chinese README onboarding, quick start, capability
  boundaries, and community feedback entry points.

### Fixed

- Allow users to switch models between turns in the same conversation while
  preserving the selected model when conversation history is reopened.
- Correct packaged Skill editing actions and labels so imported Skills are not
  presented as unpublished authoring drafts.
- Improve Skill list and detail UI state handling, including safe rendering of
  optional feedback data and clearer local-change indicators.

## v0.1.5 - 2026-09-05

### Security

- Upgrade the Community Web runtime base image to the current minimal
  Nginx/Alpine release to remove fixable high-severity OS vulnerabilities.

## v0.1.4 - 2026-09-05

### Added

- Add durable DSH turn recovery and idempotent terminal-state finalization.
- Preserve evidence from manually recorded browser events to improve workflow
  portability and target matching.

### Changed

- Make chat cancellation wait for authoritative backend acknowledgement before
  releasing the active UI state.
- Improve stream startup, interrupted-turn handling and browser recording review.

## v0.1.1 - 2026-09-04

### Added

- Add configurable Python package, PyTorch and Hugging Face mirrors for source builds.
- Support externally provisioned Docling models and preserve reusable document-build caches.
- Add MOVO Desktop service-address and update controls to the Community Web workspace.
- Add selective promotion of validated container candidates.

### Changed

- Improve document-model download reliability and timeout handling.
- Expand the English and Chinese product documentation, including MOVO positioning,
  Desktop capability boundaries and official website links.

### Security

- Upgrade vulnerable DSH Runtime Host dependencies and republish the affected images.

## v0.1.0 - 2026-09-02

- Prepare the independent Community Edition repository.
- Remove Community Edition member limits and cloud billing behavior.
- Add isolated `movo_*` Docker volumes and first-run setup.
- Add resumable presentation generation.
- Add source-build and prebuilt-container deployment modes.

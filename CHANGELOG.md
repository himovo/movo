# Changelog

All notable MOVO Community Edition changes are recorded here. Releases use
semantic version tags and the same tag is applied to every published container
image.

## Unreleased

No changes yet.

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

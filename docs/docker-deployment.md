# Docker deployment

## Install from GitHub Container Registry

Clone the GitHub repository at a release tag and run:

```bash
git clone --branch vX.Y.Z https://github.com/himovo/movo.git
cd movo
./movo up
```

`./movo` derives the image prefix from the GitHub `origin` remote and pulls seven
MOVO images from `ghcr.io/owner/repository-*`. Set `MOVO_VERSION` in `.env` to
the same release tag. Release archives without an origin remote must also set:

```env
MOVO_IMAGE_PREFIX=ghcr.io/owner/repository
MOVO_VERSION=vX.Y.Z
```

Do not use `latest` for a production deployment. Upgrade only after reading the
release notes, taking a backup and confirming the rollback image tag.

## Build from source

For development or before public images are available:

```bash
./movo up --build
```

This loads `docker-compose.build.yml` in addition to the default Compose file.
It downloads and builds Playwright, LibreOffice, Docling and model assets, so it
needs substantially more time and disk space than the prebuilt-image path.

To build without starting services:

```bash
./movo build
```

## Operations

```bash
./movo status
./movo logs chat-api
./movo restart
./movo update
./movo backup /path/on/a/large-disk/movo-backup
./movo down
```

`./movo update` pulls the configured image tag and recreates services. Pin a new
`MOVO_VERSION` before running it. It does not migrate or delete data volumes.

`./movo down -v` permanently deletes all MOVO data and now requires an explicit
interactive confirmation. Automation must pass `./movo down -v --yes`.

`./movo backup` briefly stops the deployment and archives all eight named
volumes, including deployment secrets. Because the archive can be large, put
it on a disk with sufficient free space. Verify restoration only on a
disposable host:

```bash
./movo restore /path/to/movo-backup --yes
```

Restore verifies SHA-256 checksums and requires the configured volume prefix to
match the backup. It replaces all data in the target volumes; it is not a merge.

## Production baseline

- Terminate TLS in an external reverse proxy and expose only the gateway port.
- Keep MongoDB, Redis and Weaviate on the internal Compose network.
- Keep `MOVO_VOLUME_PREFIX` unchanged throughout the installation lifecycle.
- Back up deployment secrets together with MongoDB, generated files, knowledge
  documents, Weaviate and DSH state.
- Restrict Docker daemon access; Docker access is equivalent to root access on
  the host in common installations.
- Monitor free disk, memory, container health and gateway error rates.
- Test backup restoration and release rollback with non-production data before
  every production upgrade.

The default Compose file is a single-host baseline. Operators requiring
high-availability databases, external object storage, centralized secrets or
orchestrated rolling updates should replace the bundled stateful services with
managed equivalents and validate those integrations independently.

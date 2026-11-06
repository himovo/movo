# Deployment on restricted networks

## Compose command selection

The launcher accepts Docker Compose v2 or newer in either installation form:
`docker compose` or `docker-compose`. It prefers the Docker CLI plugin and falls
back to the standalone executable. Compose v1 is not supported. Use
`docker compose version` or `docker-compose version` to inspect Compose;
`docker compose -v` can report the Docker Engine version instead.

## Image availability

`./movo up` checks the exact configured image references locally and downloads
only missing images. It starts with `--pull never` after preparation. A cached
`latest` image is reused without querying a remote registry. Use `./movo update`
when connectivity is available and an explicit remote update is intended.

A Docker Hub DNS or connection error requires working registry access, an
accessible alternative registry, or offline image import. Changing Compose
commands does not fix registry connectivity.

For enterprise packages, preserve `MOVO_IMAGE_PREFIX` and `MOVO_VERSION` from the
supplied package. Do not use `--mirror cn` to work around a dependency download:
that option selects community application images as well.

The four infrastructure images can be overridden independently in the deployment
`.env`, without changing enterprise application images. Replace existing values
rather than adding duplicate entries. For example, when these public mirrors are
accessible and approved for the deployment:

```dotenv
MOVO_ALPINE_IMAGE=registry.cn-beijing.aliyuncs.com/himovo-cn/movo-alpine:3.21
MOVO_MONGO_IMAGE=registry.cn-beijing.aliyuncs.com/himovo-cn/movo-mongo:6.0.20
MOVO_REDIS_IMAGE=registry.cn-beijing.aliyuncs.com/himovo-cn/movo-redis:7.4.2-alpine
MOVO_WEAVIATE_IMAGE=registry.cn-beijing.aliyuncs.com/himovo-cn/movo-weaviate:1.25.7
```

These values may also point to a company registry. Confirm it contains the target
architecture and required image versions. If the delivery pins dependencies by
digest, preserve the supplied references when preparing offline images.

## Offline import

On a connected machine, pull the exact references from the delivered Compose
configuration for the target Docker host architecture, then export them using
`docker save`. Transfer the archive and use `docker load -i images.tar` on the
target host. Include application images, the four infrastructure images and the
sandbox-script image. A local tag must match the configured reference exactly;
a differently named copy is not considered a cache hit.

Run `./movo --lang zh-CN up` after import. Missing-image errors name the reference
that must be imported. Importing the installer alone does not import its images.

## Versioned offline bundles

New enterprise deployment archives include the offline preparation tools. On a
connected Linux Docker host (Windows: use WSL2 with Docker integration), install
Python 3.10 or newer and sign in to the private registry, then run:

```bash
./prepare-offline.sh --arch arm64 --output /path/movo-offline-arm64.tar.gz
```

Choose the target architecture explicitly. The tool never executes target images.
It reads the immutable release defaults, pins published image digests, pulls every
service including sandbox execution images, verifies the platform, and saves
content-addressed local tags. The offline archive includes a service override
file and checksums. Customer `.env`, Docker credentials, data and application
source trees are not copied. Images may contain interpreted runtime code.

Transfer and extract this archive on the offline Linux Docker host:

```bash
sudo ./install-offline.sh --target /opt/movo-enterprise
```

For an existing deployment, `--target` MUST point to its original directory, not
a new extraction directory. The installer preserves existing environment values,
Compose project identity and physical volume names. It imports and verifies all
images before stopping the old services. It cold-backs up every named volume and
configuration under the sibling `movo-offline-backups/` directory before migration.
Use `--backup-dir /absolute/path` to choose another filesystem. Writable bind
mounts (except the Docker socket) require a separate backup plan and are rejected.
Changes to MongoDB, Redis or Weaviate image identities are rejected; migrate
infrastructure separately with a tested data migration plan.

Failed upgrades after backup stop services and retain the backup; they do not
automatically roll back database migrations. Inspect the failure before restoring.
Explicit restoration replaces current volume data with the backup:

```bash
sudo python3 deploy/offline/restore.py --target /opt/movo-enterprise \
  --backup /path/to/backup --alpine-image movo-offline/image:CONTENT_ID \
  --confirm-restore
```

Use the local bootstrap image shown in `offline-compose.json`. Restoration checks
backup hashes and project identity, restores deployment files and all volumes,
and starts the prior images with pulling disabled. Verify health before resuming
traffic. Old images and backups are never automatically pruned.

The installed deployment is offline-only. Normal `movo up`, status, logs and
restart remain available; `movo update` is rejected. Import the next complete
release bundle and rerun its installer against the same target for upgrades.
Python is required for the offline tools, but ordinary `movo` commands remain Bash.

## Skill and plugin environments

The existing offline-package and sandbox-image management pages remain the
transfer interface after MOVO starts. The installer preserves the package volume
and enables its offline-only marker. Export prepared Skill images or dependency
package collections on a connected MOVO deployment of the same architecture and
base-image identity. Install the identical Skill package and import its prepared
image on the target; existing environment detection reuses the image. Environment
images built on different base IDs must be prepared again. Installing a package
cache does not supply dependencies that were never collected, external services,
or model endpoints; provision those inside the customer's network separately.

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

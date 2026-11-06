# Keep this runtime aligned with both web images. The Debian/glibc variant avoids
# the Alpine musl pwritev2 path rejected by older container hosts.
ARG NGINX_RUNTIME_IMAGE=nginx:1.31.6-trixie
FROM ${NGINX_RUNTIME_IMAGE}

ARG MOVO_SECURITY_REFRESH=local
RUN test -n "${MOVO_SECURITY_REFRESH}" \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends curl wget \
    && rm -rf /var/lib/apt/lists/*

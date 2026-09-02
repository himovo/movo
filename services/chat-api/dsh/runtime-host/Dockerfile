FROM node:24-bookworm-slim AS dependencies

ARG MOVO_NPM_REGISTRY=

ENV NODE_ENV=production \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

WORKDIR /app

RUN if [ -n "${MOVO_NPM_REGISTRY}" ]; then npm config set registry "${MOVO_NPM_REGISTRY}"; fi \
    && npm install --global pnpm@10.34.4

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod
RUN node -e "const declared=require('./package.json').dependencies['@deepseek-ai/dsh']; const installed=require('@deepseek-ai/dsh/package.json').version; if (declared !== installed) throw new Error('DSH version mismatch: declared='+declared+' installed='+installed); console.log('DSH Runtime installed version: '+installed)"

FROM node:24-bookworm-slim

ARG MOVO_APT_MIRROR=
ARG MOVO_APT_SECURITY_MIRROR=

ENV NODE_ENV=production

WORKDIR /app

RUN if [ -n "${MOVO_APT_MIRROR}" ]; then \
        for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
            if [ -f "${source_file}" ]; then \
                sed -i "s|http://deb.debian.org/debian|${MOVO_APT_MIRROR}|g; s|https://deb.debian.org/debian|${MOVO_APT_MIRROR}|g" "${source_file}"; \
                if [ -n "${MOVO_APT_SECURITY_MIRROR}" ]; then \
                    sed -i "s|http://deb.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|https://deb.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|http://security.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g; s|https://security.debian.org/debian-security|${MOVO_APT_SECURITY_MIRROR}|g" "${source_file}"; \
                fi; \
            fi; \
        done; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/* \
    && npm uninstall --global npm

COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=dependencies /app/package.json ./package.json

COPY src ./src
COPY config ./config
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /data/dsh-runtime \
    && chown -R node:node /data/dsh-runtime

EXPOSE 8101

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["node", "src/host.mjs", "--host", "0.0.0.0", "--port", "8101", "--storage-root", "/data/dsh-runtime"]

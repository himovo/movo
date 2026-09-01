FROM node:24-bookworm-slim

ENV NODE_ENV=production \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates gosu \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global pnpm@10.14.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod
RUN node -e "const declared=require('./package.json').dependencies['@deepseek-ai/dsh']; const installed=require('@deepseek-ai/dsh/package.json').version; if (declared !== installed) throw new Error('DSH version mismatch: declared='+declared+' installed='+installed); console.log('DSH Runtime installed version: '+installed)"

COPY src ./src
COPY config ./config
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /data/dsh-runtime \
    && chown -R node:node /data/dsh-runtime

EXPOSE 8101

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["node", "src/host.mjs", "--host", "0.0.0.0", "--port", "8101", "--storage-root", "/data/dsh-runtime"]

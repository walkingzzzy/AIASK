# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS node-base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates python3 \
  && rm -rf /var/lib/apt/lists/*

FROM node-base AS node-deps
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY apps/bff/package.json ./apps/bff/package.json
COPY packages/shared-types/package.json ./packages/shared-types/package.json
RUN npm ci

FROM node-deps AS shared-build
COPY . .
RUN npm run build -w packages/shared-types

FROM shared-build AS bff-build
RUN npm run build -w apps/bff

FROM shared-build AS web-build
RUN npm run build -w apps/web

FROM node-base AS node-prod-deps
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY apps/bff/package.json ./apps/bff/package.json
COPY packages/shared-types/package.json ./packages/shared-types/package.json
RUN npm ci --omit=dev

FROM node:20-bookworm-slim AS web
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=node-prod-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=node-prod-deps --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=web-build --chown=node:node /app/packages/shared-types/package.json ./packages/shared-types/package.json
COPY --from=web-build --chown=node:node /app/packages/shared-types/dist ./packages/shared-types/dist
COPY --from=web-build --chown=node:node /app/apps/web/package.json ./apps/web/package.json
COPY --from=web-build --chown=node:node /app/apps/web/next.config.mjs ./apps/web/next.config.mjs
COPY --from=web-build --chown=node:node /app/apps/web/public ./apps/web/public
COPY --from=web-build --chown=node:node /app/apps/web/.next ./apps/web/.next
WORKDIR /app/apps/web
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]

FROM node:20-bookworm-slim AS bff
WORKDIR /app
ENV NODE_ENV=development
COPY --from=node-prod-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=node-prod-deps --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=bff-build --chown=node:node /app/packages/shared-types/package.json ./packages/shared-types/package.json
COPY --from=bff-build --chown=node:node /app/packages/shared-types/dist ./packages/shared-types/dist
COPY --from=bff-build --chown=node:node /app/apps/bff/package.json ./apps/bff/package.json
COPY --from=bff-build --chown=node:node /app/apps/bff/dist ./apps/bff/dist
COPY --from=bff-build --chown=node:node /app/apps/bff/migrations ./apps/bff/migrations
WORKDIR /app/apps/bff
USER node
EXPOSE 3001
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.BFF_PORT||3001)+'/api/health/live').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/main.js"]

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS akshare-python-runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*
COPY packages/strategy-factory/pyproject.toml packages/strategy-factory/README.md ./packages/strategy-factory/
COPY packages/strategy-factory/src ./packages/strategy-factory/src
COPY packages/akshare-mcp/pyproject.toml packages/akshare-mcp/uv.lock packages/akshare-mcp/README.md ./packages/akshare-mcp/
COPY packages/akshare-mcp/start_server.py ./packages/akshare-mcp/start_server.py
COPY packages/akshare-mcp/src ./packages/akshare-mcp/src
WORKDIR /app/packages/akshare-mcp
RUN uv sync --frozen --extra legacy --no-dev

FROM akshare-python-runtime AS akshare-mcp
EXPOSE 3100
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD .venv/bin/python -c "import os, socket; s=socket.create_connection(('127.0.0.1', int(os.getenv('MCP_PORT', '3100'))), 3); s.close()"
CMD [".venv/bin/python", "start_server.py"]

FROM akshare-python-runtime AS strategy-factory-worker
CMD [".venv/bin/python", "-m", "akshare_mcp.workers.strategy_factory_worker"]

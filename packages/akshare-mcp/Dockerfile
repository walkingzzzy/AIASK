FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

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

EXPOSE 3100

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD .venv/bin/python -c "import os, socket; s=socket.create_connection(('127.0.0.1', int(os.getenv('MCP_PORT', '3100'))), 3); s.close()"

CMD [".venv/bin/python", "start_server.py"]

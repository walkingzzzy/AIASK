# AKShare MCP 配置指南

> 本文用于在 Cursor / Augment 等 AI 客户端中接入本仓库里的 `packages/akshare-mcp` 服务。
>
> **校准说明**：本指南优先描述当前仓库中更容易验证的接入方式与约束。默认推荐 **stdio**；HTTP / SSE / streamable-http 仅作为附加模式说明，不应被默认视为“已经在所有环境下验证通过”。

## 1. 配置文件位置

> 校准边界：不同 AI 客户端版本的 MCP 配置路径可能变化。当前仓库内已有明确示例的是 `.kiro/settings/mcp.json`；其余客户端路径请以对应客户端版本文档为准。

- Cursor：常见写法为 `.cursor/mcp.json` 或 `.cursor/settings/mcp.json`
- Kiro / 仓库内现有示例：`.kiro/settings/mcp.json`
- 其他客户端（如 Augment）：请以客户端当前版本文档为准，不要把本文示例路径当成唯一事实

## 2. 适用范围与命名说明
- 适用服务目录：`packages/akshare-mcp`
- Python 分发名：`akshare-mcp`
- Python import 包名：`akshare_mcp`
- MCP 服务名：可以自定义；下文统一用 `akshare-mcp`，避免与历史文档中的 `akshare-stock` 混用

补充说明：
- `packages/akshare-mcp/README.md` 仍保留“安装后通过 `akshare-mcp` CLI / `uvx` 启动”的示例
- 本文优先给出“直接在仓库工作区内启动 `start_server.py`”的方式，因为这条路径对本项目开发和本地排障更容易验证
- `start_server.py` 通过 `akshare_mcp.env_loader.load_mcp_env()` 会依次尝试 `packages/akshare-mcp/.env`、`cwd/packages/akshare-mcp/.env` 与 `cwd/.env`；因此从包目录或仓库根目录启动都可能生效，但前者更少路径歧义
- 若你走已安装 CLI 路径，请确保环境变量、工作目录与 `PYTHONPATH` 仍能正确覆盖到当前仓库依赖

## 3. 推荐配置（stdio）

### 3.1 通用原则
- 优先使用 **stdio**，因为这是当前代码里最直接、最保守、最容易验证的接入方式
- `start_server.py` 已明确要求 stdio 协议日志走 `stderr`，避免污染协议输出
- `cwd` 优先指向 `packages/akshare-mcp`；若必须从仓库根目录启动，也应显式核对 `.env` 与 `PYTHONPATH` 的命中路径
- `PYTHONPATH` 建议指向 `packages/akshare-mcp/src`

### 3.2 Windows — 使用 uv
```json
{
  "mcpServers": {
    "akshare-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "c:\\path\\to\\股票\\packages\\akshare-mcp",
        "python",
        "start_server.py"
      ],
      "cwd": "c:\\path\\to\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\path\\to\\股票\\packages\\akshare-mcp\\src"
      }
    }
  }
}
```

### 3.3 Windows — 使用 Python 直接运行
```json
{
  "mcpServers": {
    "akshare-mcp": {
      "command": "python",
      "args": ["start_server.py"],
      "cwd": "c:\\path\\to\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\path\\to\\股票\\packages\\akshare-mcp\\src"
      }
    }
  }
}
```

### 3.4 macOS — 使用 `.venv` Python（更稳妥）

> 若直接用 `uv run`，首次可能因为构建 `.venv` 与下载依赖而超时。对 MCP 客户端来说，先预装依赖、再用 `.venv/bin/python` 启动通常更稳。

第一步：预装依赖
```bash
cd /Users/<你的用户名>/Desktop/股票/packages/akshare-mcp
uv sync --extra legacy
```

第二步：配置 MCP
```json
{
  "mcpServers": {
    "akshare-mcp": {
      "command": "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/.venv/bin/python",
      "args": ["/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/start_server.py"],
      "cwd": "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp",
      "env": {
        "PYTHONPATH": "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/src"
      }
    }
  }
}
```

注意：
- `args` 建议使用 `start_server.py` 的绝对路径
- `legacy` extras 对当前仓库中的部分历史/兼容数据源导入是有帮助的
- 若本机缺少平台专用依赖、本地数据库或相关 token，服务仍可能启动，但部分能力不可用或降级

### 3.5 macOS — 使用 `uv run`（备用）
```json
{
  "mcpServers": {
    "akshare-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp",
        "python",
        "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/start_server.py"
      ],
      "cwd": "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp",
      "env": {
        "PYTHONPATH": "/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/src"
      }
    }
  }
}
```

若首次超时，请先在终端执行 `uv sync --extra legacy`，再重载 MCP。

## 4. HTTP / SSE / streamable-http 模式说明

当 `MCP_TRANSPORT` 为 `http` / `streamable-http` / `sse` 时，建议至少满足以下安全基线：

1. 仅本地绑定：`MCP_HOST=127.0.0.1`（或 `localhost` / `::1`）
2. 配置来源校验：`MCP_ALLOWED_ORIGINS`
3. 启用鉴权：`MCP_AUTH_MODE`（如 `bearer` / `api-key`）
4. 禁止 token passthrough：`MCP_ALLOW_TOKEN_PASSTHROUGH=false`

**证据边界说明**：
- `packages/akshare-mcp/start_server.py` 已确认安全默认值设置：`MCP_HOST=127.0.0.1`、`MCP_ALLOW_TOKEN_PASSTHROUGH=false`
- `packages/akshare-mcp/src/akshare_mcp/server.py::_enforce_http_security_baseline()` 已确认会对 `http / streamable-http / sse` 执行 host、origin、auth、token passthrough 四项硬校验
- 因此本节既是推荐基线，也是当前服务端代码里已看到的启动约束；但“某个具体 AI 客户端配置已端到端验证通过”仍需按客户端单独回归

应用端性能模式推荐把 `packages/akshare-mcp` 作为常驻 `streamable-http` 服务运行，然后让 BFF 连接该 endpoint，避免每次冷路径都落到 stdio worker 启停或连接池重建：

推荐直接使用 Docker Compose 托管 MCP：

```bash
npm run mcp:up
npm run mcp:logs
```

Compose 服务名为 `akshare-mcp`，容器内监听 `0.0.0.0:3100`，但宿主机只发布
`127.0.0.1:3100`，因此 BFF 仍通过 `http://127.0.0.1:3100/mcp` 访问。容器内绑定
`0.0.0.0` 必须同时设置 `MCP_CONTAINER_BIND_ALL=true` 与 `MCP_ALLOWED_HOSTS`。

```env
MCP_TRANSPORT=streamable-http
AKSHARE_MCP_STARTUP_PROFILE=worker
MCP_HOST=127.0.0.1
MCP_PORT=3100
MCP_CONTAINER_HOST=0.0.0.0
MCP_CONTAINER_BIND_ALL=true
MCP_ALLOWED_HOSTS=127.0.0.1:3100,localhost:3100,akshare-mcp:3100
MCP_AUTH_MODE=bearer
MCP_AUTH_TOKEN=change_me_mcp_token
MCP_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
MCP_ALLOW_TOKEN_PASSTHROUGH=false

MCP_STREAMABLE_HTTP_URL=http://127.0.0.1:3100/mcp
MCP_STREAMABLE_HTTP_HEADERS={"authorization":"Bearer change_me_mcp_token"}
MCP_STREAMABLE_HTTP_ALLOW_SSE_FALLBACK=false
MCP_TRANSPORT_ALLOW_STDIO_FALLBACK=false
MCP_STREAMABLE_HTTP_TIMEOUT_MS=2500
MCP_POOL_ACQUIRE_TIMEOUT_MS=1500
BFF_HEALTH_PROBE_TIMEOUT_MS=1500
MARKET_SCHEDULER_ENABLED=true
MARKET_INDEX_FAILURE_BACKOFF_MS=30000
MARKET_INDEX_FAILURE_MAX_BACKOFF_MS=120000
```

`AKSHARE_MCP_STARTUP_PROFILE=worker` 是应用端实时模式的关键配置：它保留完整工具注册能力，但不会启动 StrategyFactory、DataSyncScheduler、StartupValidator 等自主后台任务，避免常驻 HTTP MCP 与前端交互请求抢 CPU。离线批处理或策略工厂巡检再单独使用 `full` profile。

## 5. HTTP 安全示例
```json
{
  "mcpServers": {
    "akshare-mcp": {
      "command": "python",
      "args": ["start_server.py"],
      "cwd": "c:\\path\\to\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\path\\to\\股票\\packages\\akshare-mcp\\src",
        "MCP_TRANSPORT": "streamable-http",
        "MCP_HOST": "127.0.0.1",
        "MCP_ALLOWED_ORIGINS": "https://chat.openai.com,https://cursor.sh",
        "MCP_AUTH_MODE": "bearer",
        "MCP_ALLOW_TOKEN_PASSTHROUGH": "false"
      }
    }
  }
}
```

## 6. 常见问题

### 6.1 服务无法导入模块
- 检查 `PYTHONPATH` 是否指向 `packages/akshare-mcp/src`
- 检查当前工作目录是否与你配置的 `.env` / `PYTHONPATH` 路径一致；最省事的做法仍是指向 `packages/akshare-mcp`
- 检查是否使用了正确的 Python / `.venv`

### 6.2 HTTP 模式风险较高或行为不符合预期
- 先回退到 stdio 模式，确认服务本体可正常启动
- 再逐项检查 `MCP_HOST`、`MCP_ALLOWED_ORIGINS`、`MCP_AUTH_MODE`、`MCP_ALLOW_TOKEN_PASSTHROUGH`
- 若需要把某个客户端的 HTTP 接入写成“已验证现状”，仍需补一轮该客户端的专门回归

### 6.3 行情数据源降级
- 服务可能优先尝试主数据源，再按实现走降级链
- 降级不等于完全不可用，但返回口径、时效与字段完整性可能变化

### 6.4 macOS 首次启动超时
- 原因通常是 `uv run` 首次建环境与下载依赖
- 优先方案：先执行 `uv sync --extra legacy`
- 再用 `.venv/bin/python` 直接启动

### 6.5 `can't open file '.../start_server.py'`
- 通常是 `args` 使用了相对路径
- 建议把 `start_server.py` 写成绝对路径

### 6.6 `ModuleNotFoundError: No module named 'akshare'`
- 常见原因是未安装 `legacy` extras
- 解决：`uv sync --extra legacy`

### 6.7 平台专用依赖警告
- 历史 Windows 路径在 macOS 上通常不可直接复用
- 无平台专用依赖时，公共能力通常仍可使用，但平台专用能力会降级、跳过或失败

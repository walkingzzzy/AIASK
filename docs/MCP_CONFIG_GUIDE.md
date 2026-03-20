# AKShare MCP 配置指南

> 本文用于在 Cursor / Augment 等 AI 客户端中接入本仓库里的 `packages/akshare-mcp` 服务。
>
> **校准说明**：本指南优先描述当前仓库中更容易验证的接入方式与约束。默认推荐 **stdio**；HTTP / SSE / streamable-http 仅作为附加模式说明，不应被默认视为“已经在所有环境下验证通过”。

## 1. 配置文件位置
- Cursor: `.cursor/mcp.json` 或 `.cursor/settings/mcp.json`
- Augment: `.augment/mcp.json` 或 `.kiro/settings/mcp.json`

## 2. 适用范围与命名说明
- 适用服务目录：`packages/akshare-mcp`
- Python 包名：`akshare-mcp`
- MCP 服务名：可以自定义；下文统一用 `akshare-mcp`，避免与历史文档中的 `akshare-stock` 混用

## 3. 推荐配置（stdio）

### 3.1 通用原则
- 优先使用 **stdio**，因为这是当前代码里最直接、最保守、最容易验证的接入方式
- `start_server.py` 已明确要求 stdio 协议日志走 `stderr`，避免污染协议输出
- `cwd` 建议始终指向 `packages/akshare-mcp`
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
- 本次校对已在 `start_server.py` 中确认安全默认值设置：`MCP_HOST=127.0.0.1`、`MCP_ALLOW_TOKEN_PASSTHROUGH=false`
- 但“HTTP 模式下服务端一定会在启动时强制拒绝所有不满足条件的配置”这一点，本轮未完整追到全部校验实现链路
- 因此本节应理解为**推荐安全基线**，而不是对所有传输模式都已完成逐项验收的声明

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
- 检查当前工作目录是否为 `packages/akshare-mcp`
- 检查是否使用了正确的 Python / `.venv`

### 6.2 HTTP 模式风险较高或行为不符合预期
- 先回退到 stdio 模式，确认服务本体可正常启动
- 再逐项检查 `MCP_HOST`、`MCP_ALLOWED_ORIGINS`、`MCP_AUTH_MODE`、`MCP_ALLOW_TOKEN_PASSTHROUGH`
- 若需要把 HTTP 模式写成正式现状，请先补一轮专门验证

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

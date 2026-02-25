# AKShare MCP 配置指南

本文用于在 Cursor/Augment 中配置 `akshare-stock` MCP 服务，并提供 HTTP 传输的安全基线。

## 1. 配置文件位置
- Cursor: `.cursor/mcp.json` 或 `.cursor/settings/mcp.json`
- Augment: `.augment/mcp.json` 或 `.kiro/settings/mcp.json`

## 2. 推荐配置（stdio）

### 2.1 使用 uv（推荐）
```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
        "python",
        "start_server.py"
      ],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src"
      }
    }
  }
}
```

### 2.2 使用 Python 直接运行
```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "python",
      "args": ["start_server.py"],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src"
      }
    }
  }
}
```

## 3. HTTP 传输安全基线（强制）
当 `MCP_TRANSPORT` 为 `http` / `streamable-http` / `sse` 时：

1. 仅允许本地绑定：`MCP_HOST=127.0.0.1`（或 `localhost` / `::1`）
2. 必须配置来源校验：`MCP_ALLOWED_ORIGINS`
3. 必须启用鉴权：`MCP_AUTH_MODE`（如 `bearer` / `api-key`）
4. 禁止 token passthrough：`MCP_ALLOW_TOKEN_PASSTHROUGH=false`

服务端会在启动时校验上述条件，不满足将拒绝启动。

## 4. HTTP 安全示例
```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "python",
      "args": ["start_server.py"],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src",
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

## 5. 常见问题

### 5.1 服务无法导入模块
- 检查 `PYTHONPATH` 是否指向 `packages/akshare-mcp/src`
- 检查当前工作目录是否为 `packages/akshare-mcp`

### 5.2 HTTP 模式启动被拒绝
- 检查是否按“第 3 节”配置所有安全项
- 重点检查 `MCP_ALLOWED_ORIGINS` 与 `MCP_AUTH_MODE`

### 5.3 行情数据源降级
- 服务会优先尝试 HTTPS 数据源
- 如降级到 HTTP，会在日志中标记为 `*_http_fallback`
- 这不代表无行情机会，只是数据链路降级

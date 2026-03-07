# AKShare MCP 配置指南

本文用于在 Cursor/Augment 中配置 `akshare-stock` MCP 服务，并提供 HTTP 传输的安全基线。

## 1. 配置文件位置
- Cursor: `.cursor/mcp.json` 或 `.cursor/settings/mcp.json`
- Augment: `.augment/mcp.json` 或 `.kiro/settings/mcp.json`

## 2. 推荐配置（stdio）

### 2.1 Windows — 使用 uv（推荐）
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

### 2.2 Windows — 使用 Python 直接运行
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

### 2.3 macOS — 使用 .venv 直接运行（推荐）

> **说明**：Cursor MCP 直接用 `uv run` 启动时，首次会在超时窗口内重建 `.venv` 并下载依赖，容易超时。
> 推荐先在终端预装依赖，再用 `.venv` 里的 Python 直接启动，启动时间可缩短至 1 秒以内。

**第一步：预装依赖（仅首次或依赖变更时执行）**
```bash
cd /Users/<你的用户名>/Desktop/股票/packages/akshare-mcp
uv sync --extra legacy
```
> `--extra legacy` 会安装 akshare、baostock、efinance 等可选依赖，服务端导入时需要。

**第二步：配置 `~/.cursor/mcp.json`**
```json
{
  "mcpServers": {
    "akshare-stock": {
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
> 将 `<你的用户名>` 替换为实际用户名（运行 `whoami` 可获取）。

**注意事项**
- 使用 `.venv/bin/python` 而非系统 Python，避免模块冲突。
- `args` 必须使用 `start_server.py` 的**绝对路径**；若只写文件名，Cursor 可能以 `~` 作为工作目录导致找不到文件。
- `cwd` 仍需配置，确保服务内相对路径（如配置文件读取）正确。

### 2.4 macOS — 使用 uv run（备用，首次启动较慢）
```json
{
  "mcpServers": {
    "akshare-stock": {
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
> 首次启动时 uv 会重建 `.venv` 并下载所有依赖，可能触发 Cursor 的 60 秒超时。
> 若超时，重新加载 MCP 即可（依赖已缓存，第二次启动很快）。

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

### 5.4 macOS — 启动超时（MCP error -32001: Request timed out）
- 原因：`uv run` 首次启动时需重建 `.venv` 并下载依赖（scikit-learn 等体积较大），超过 Cursor 约 60 秒超时限制
- 解决方案一（推荐）：改用 `.venv/bin/python` 直接启动（见第 2.3 节），彻底跳过 uv 启动阶段
- 解决方案二：先在终端执行 `uv sync --extra legacy` 预装依赖后重启 Cursor MCP，第二次启动会命中缓存，速度正常

### 5.5 macOS — `can't open file '/Users/<用户名>/start_server.py'`
- 原因：`args` 只写了相对路径 `"start_server.py"`，Cursor 启动进程时实际工作目录为用户家目录，路径解析错误
- 解决方案：`args` 中必须使用**绝对路径**，例如：
  ```json
  "args": ["/Users/<你的用户名>/Desktop/股票/packages/akshare-mcp/start_server.py"]
  ```

### 5.6 macOS — `ModuleNotFoundError: No module named 'akshare'`
- 原因：akshare 属于可选依赖组 `legacy`，默认 `uv sync` 不会安装
- 解决方案：执行以下命令安装可选依赖：
  ```bash
  cd /Users/<你的用户名>/Desktop/股票/packages/akshare-mcp
  uv sync --extra legacy
  ```

### 5.7 macOS — TDX 插件路径警告（不影响运行）
- 日志出现 `TDX plugin path does not exist: C:\...` 属于正常现象，配置保留了 Windows 路径
- TDX 相关工具会自动降级为 Python 回退实现，不影响其余工具正常使用
- 若需在 macOS 上启用 TDX，需在项目 `.env` 文件中将 `TDX_PLUGIN_PATH` 改为 Mac 上通达信的实际插件路径

# AKShare MCP

`packages/akshare-mcp` 是 AIASK 当前的 Python MCP 服务端，负责把行情、基本面、回测、风险、研究、策略工厂等能力以 MCP runtime surface 暴露给 Web、BFF 和 AI 客户端。

## 当前定位

- 服务入口：`start_server.py`
- 运行时注册：`src/akshare_mcp/server.py`
- 工具注册表：`src/akshare_mcp/tool_registry.py`
- 策略工厂依赖：`packages/strategy-factory`

## 当前本地核对结果

按当前仓库代码在本地校验：

- tools: `155`
- resources: `3`
- prompts: `6`

当前能直接看到的顶层 resources：

- `resource://server/capabilities`
- `resource://server/tool-catalog`
- `resource://governance/system/report`

当前能直接看到的 prompts：

- `factor-mining`
- `stock-analysis`
- `strategy-review`
- `prediction-diagnosis`
- `factor-registry-review`
- `strategy-promotion-review`

## 安装与启动

### 推荐方式

```bash
cd packages/akshare-mcp
uv sync --extra legacy
uv run python start_server.py
```

### 从仓库根目录校验

```bash
PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src \
python packages/akshare-mcp/start_server.py
```

## 最小环境变量

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stockdb
DB_USER=postgres
DB_PASSWORD=your_password

TUSHARE_TOKEN=your_tushare_token
```

补充说明：

- 数据库不是所有工具都强依赖，但很多存储、回测工件、告警、策略工厂与运行历史能力都依赖数据库。
- 未配置外部依赖时，部分能力会降级、返回 fallback 或直接不可用。
- HTTP / SSE / streamable-http 使用前，先看 [../../docs/MCP_CONFIG_GUIDE.md](../../docs/MCP_CONFIG_GUIDE.md)。

## 常用校验

### 运行时工具数量

```bash
PYTHONPATH=src:../strategy-factory/src \
python -c "from akshare_mcp.tool_registry import build_tool_registry; print(len(build_tool_registry()))"
```

### 运行时 surface 明细

```bash
PYTHONPATH=src:../strategy-factory/src \
python -c "import akshare_mcp.server as s; m=s.mcp; print('tools', len(m._tool_manager.list_tools())); print('resources', len(m._resource_manager.list_resources())); print('prompts', len(m._prompt_manager.list_prompts()))"
```

### pytest

```bash
pytest tests -q
```

## 当前文档入口

- 接入与 transport 安全： [../../docs/MCP_CONFIG_GUIDE.md](../../docs/MCP_CONFIG_GUIDE.md)
- 运行时工具矩阵： [../../docs/171工具全量对话式深度测试任务.md](../../docs/171工具全量对话式深度测试任务.md)
- Manager 协议： [MCP_MANAGER_CONTRACT.md](./MCP_MANAGER_CONTRACT.md)
- 回测指标契约： [docs/metrics-contract.md](./docs/metrics-contract.md)
- 项目总导读： [../../docs/README.md](../../docs/README.md)

## 已知边界

- runtime 数量会变，任何静态数字都只能视为当前校验结果。
- 当前仓库已支持 resources / prompts，不应继续沿用“只支持 tools”的旧文案。
- 一些历史测试报告和阶段性材料仍保留在 `tests/` 或 `docs/archive/`，但它们不再代表当前默认事实。

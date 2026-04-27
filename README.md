# AIASK

AIASK 是一个面向 A 股研究与策略场景的 monorepo，当前主线是：

- `apps/web`：Next.js 前端工作台
- `apps/bff`：NestJS BFF / API / WebSocket 编排层
- `packages/akshare-mcp`：Python MCP 服务
- `packages/strategy-factory`：策略工厂主实现
- `packages/shared-types`：前后端共享类型

## 当前代码基线

以下数字按当前仓库代码在本地重新核对：

- Web 页面路由：`48`
- BFF 模块：`42`
- 本地 skills：`21`
- MCP runtime tools：`161`
- MCP resources：`3`
- MCP prompts：`7`

说明：

- 这些数字会随代码变化而变化，文档只保留“当前核对结果”与复核命令。
- 若后续数字变化，应以运行时结果和源码目录为准，而不是继续沿用静态文案。

## 目录结构

```text
apps/
  web/                 Next.js 前端
  bff/                 NestJS BFF
packages/
  akshare-mcp/         Python MCP 服务
  strategy-factory/    策略工厂主包
  shared-types/        共享类型
docs/
  README.md            文档导读
  MCP_CONFIG_GUIDE.md  MCP 接入与启动说明
  DEMO.md              对话式演示样例
  archive/             已归档的时点性材料
策略工厂/
  README.md            策略工厂当前导读
  策略工厂整改详细清单.md
```

## 本地启动

### 1. 前端 / BFF

```bash
npm install
npm run dev:bff
npm run dev:web
```

默认端口：

- Web: `3000`
- BFF: `3001`

### 2. MCP 服务

```bash
npm run mcp:up
```

这会通过 Docker Compose 启动常驻 `akshare-mcp` streamable-http 服务，并发布到
`http://127.0.0.1:3100/mcp`。BFF 默认使用 `MCP_STREAMABLE_HTTP_URL` 连接该端点，
避免每次请求都通过 stdio 冷启动 Python MCP。

本地直接运行仍然可用：

```bash
cd packages/akshare-mcp
uv sync --extra legacy
uv run python start_server.py
```

如果你从仓库根目录直接校验运行时 surface，可用：

```bash
PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src \
python packages/akshare-mcp/start_server.py
```

## 常用验证命令

### 目录基线

```bash
find apps/web/app -name page.tsx | wc -l
find apps/bff/src -name '*.module.ts' | wc -l
find .codex/skills -name 'SKILL.md' | wc -l
```

### MCP runtime surface

```bash
PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src \
python -c "from akshare_mcp.tool_registry import build_tool_registry; print(len(build_tool_registry()))"
```

```bash
PYTHONPATH=packages/akshare-mcp/src:packages/strategy-factory/src \
python -c "import akshare_mcp.server as s; m=s.mcp; print('tools', len(m._tool_manager.list_tools())); print('resources', len(m._resource_manager.list_resources())); print('prompts', len(m._prompt_manager.list_prompts()))"
```

## 当前建议阅读顺序

1. [docs/README.md](./docs/README.md)
2. [docs/MCP_CONFIG_GUIDE.md](./docs/MCP_CONFIG_GUIDE.md)
3. [packages/akshare-mcp/README.md](./packages/akshare-mcp/README.md)
4. [策略工厂/README.md](./策略工厂/README.md)

如果你要直接改业务：

- Web 页面与路由：`apps/web/app`
- BFF 接口与模块：`apps/bff/src`
- MCP tools / services：`packages/akshare-mcp/src/akshare_mcp`
- 策略工厂主实现：`packages/strategy-factory/src/strategy_factory`

## 文档整理说明

这次整理后：

- 根目录 dated 方案、阶段修复记录、专项审计已移入 [docs/archive/README.md](./docs/archive/README.md)。
- 根目录曾回流的策略工厂专题文档已按类别归档到 [docs/archive/strategy-factory/root-2026-04/README.md](./docs/archive/strategy-factory/root-2026-04/README.md)。
- 当前入口文档只保留和现行代码仍强相关的说明。
- 历史材料不再作为默认阅读入口，但仍保留供追溯和审计参考。

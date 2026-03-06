## 项目上下文摘要（虚拟盘方案补齐）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `apps/web/app/market/layout.tsx:1-10`
  - 模式：`layout.tsx` 仅导出 `metadata` 与透传 `children`
  - 可复用：页面级 Metadata 写法
  - 注意：保持文件轻量，不引入额外逻辑

- **实现2**: `apps/web/app/factor/layout.tsx:1-10`
  - 模式：与 `market/layout.tsx` 一致的 App Router 元数据布局
  - 可复用：标题/描述结构
  - 注意：与现有页面保持统一风格

- **实现3**: `apps/bff/src/portfolio/portfolio.controller.ts:1-141`
  - 模式：Controller 中内联 DTO、参数校验、统一 `traceId`
  - 可复用：BFF 控制器风格基线
  - 注意：避免新建多余 DTO 文件

- **实现4**: `packages/akshare-mcp/tests/test_p0_regressions.py:53-154`
  - 模式：用 `_DummyMCP` + `_FakeDB` + 假连接覆盖 manager 回归
  - 可复用：对 `paper_trading_manager` 新规则补回归测试
  - 注意：需要扩展 `_PaperConn` 以支撑 T+1 和价格刷新场景

### 2. 项目约定
- Web App Router 页面元数据使用 `layout.tsx` + `Metadata`
- Next.js 路由保护统一在 `apps/web/middleware.ts`
- MCP manager 使用 `register(mcp)` + `@mcp.tool()` 暴露
- MCP 返回结构使用 `ok({...})` / `fail("...")`

### 3. 可复用组件清单
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:get_batch_quotes_compat`
- `packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py:get_realtime_quote`
- `apps/web/app/paper-trading/page.tsx` 现有页面主体
- `apps/bff/src/paper-trading/paper-trading.service.ts` 现有 BFF 封装

### 4. 测试策略
- Python：优先补 `packages/akshare-mcp/tests/test_p0_regressions.py`
- Web：优先跑 `npm run typecheck -w apps/web`，必要时补 `build`
- BFF：若改动 TypeScript 服务层则跑 `npm run build -w apps/bff`

### 5. 依赖与集成点
- 前端路由：`apps/web/middleware.ts`
- 前端页面：`apps/web/app/paper-trading/page.tsx`
- BFF 接线：`apps/bff/src/paper-trading/*`
- MCP 核心：`packages/akshare-mcp/src/akshare_mcp/tools/managers/paper_trading_manager.py`

### 6. 关键风险点
- T+1 规则会改变既有回归测试预期，需要同步修正测试
- `update_prices` 若直接联网取行情，测试需通过 monkeypatch 隔离
- 前端当前数量校验对卖出也限制整手，与方案不一致，需要一并修正

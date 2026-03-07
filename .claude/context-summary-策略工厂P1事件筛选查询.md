## 项目上下文摘要（策略工厂P1事件筛选查询）
生成时间：2026-03-07

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:list_strategy_status_events`
  - 模式：`save/list/get` 存储层最小扩展
  - 可复用：`_decode_json_field()` 负责 `metadata` 解码
  - 注意：当前仅支持 `strategy_id + limit`，需保持 `created_at DESC`
- **实现2**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/signal_tracking.py:get_signals`
  - 模式：`sql + params + idx` 动态 SQL 拼接
  - 可复用：按条件逐步追加 `AND ... = ${idx}`
  - 注意：`LIMIT` 必须最后追加并进入参数列表
- **实现3**: `apps/bff/src/strategy/strategy.controller.ts:EventsQueryDto`
  - 模式：NestJS controller 内联 DTO + `class-validator`
  - 可复用：`@IsOptional()`、`@Type(() => Number)`、范围限制
  - 注意：日期字符串用 `@Matches(/^\d{4}-\d{2}-\d{2}$/)`
- **实现4**: `apps/web/app/strategy-market/[id]/page.tsx:FactoryReviewPanel`
  - 模式：`useApiQuery + useState + SectionCard/DataTable`
  - 可复用：父组件持有筛选状态，子组件只负责展示和回调
  - 注意：保持轻量，不引入新依赖或复杂状态管理

### 2. 项目约定
- **命名约定**：筛选字段统一使用 `event_type/from_status/to_status/actor_id/start_time/end_time/limit`
- **文件组织**：`tests -> storage -> manager -> BFF -> Web` 顺序增量补齐
- **代码风格**：Python 使用轻量 helper；TS 使用内联 DTO；Web 使用原生表单控件

### 3. 可复用组件清单
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/signal_tracking.py:get_signals`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:_build_incubation_overview`
- `apps/web/app/strategy-market/[id]/page.tsx:FactoryReviewPanel`

### 4. 测试策略
- **测试框架**：`pytest`
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖范围**：事件 `metadata` 回传、`event_type` 输出、状态/触发方/时间窗口筛选、manager action 查询闭环

### 5. 依赖和集成点
- **后端链路**：`strategy.py -> strategy_manager.py -> apps/bff/src/strategy/* -> apps/web/app/strategy-market/[id]/page.tsx`
- **时间协议**：Web 传 `YYYY-MM-DD`；manager 转整日 UTC 边界；storage/fake DB 按 ISO 时间过滤
- **外部文档**：已查询 Context7 `class-validator`，确认 `@IsOptional() + @IsString() + @Matches()` 适合日期 query DTO

### 6. 关键风险点
- fake DB 若继续使用 naive 时间，会与 UTC 边界比较冲突，需统一为 UTC ISO 字符串
- Web 仅做轻量筛选，避免把 metadata 展示做成复杂 JSON 浏览器
- 本地 Node 构建环境此前存在缺依赖历史，本轮优先执行 pytest 与 diagnostics

### 7. 本轮收口结果
- **已落盘链路**：`strategy.py -> strategy_manager.py -> apps/bff/src/strategy/strategy.controller.ts -> apps/web/app/strategy-market/[id]/page.tsx`
- **BFF 收口**：`EventsQueryDto` 已支持 `event_type/from_status/to_status/actor_id/start_time/end_time/limit`，并补齐 `POST /strategy-market/:id/review-report/recheck`
- **Web 收口**：工厂页签已支持事件筛选输入、`metadata` 摘要展示、报告历史展示与多周期 `forward_returns` 表格
- **本地验证**：后端关键子集 `4 passed, 75 deselected`；`apps/web/app/strategy-market/[id]/page.tsx` 与 BFF strategy 文件 `diagnostics` 无问题
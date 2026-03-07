## 项目上下文摘要（工厂运行历史详情展示）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
  - 模式：`get_* / list_* / save_*` 统一放在 `StrategyMixin`
  - 可复用：`get_strategy_quality_report()`、`list_strategy_factory_runs()`
  - 需注意：JSONB 查询结果要统一解码

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 模式：`action + kwargs` 分发
  - 可复用：`review_report`、`events`、`factory_runs`
  - 需注意：详情查询应保持 `ok/fail` 返回格式

- **实现3**: `apps/bff/src/strategy/strategy.controller.ts` + `strategy.service.ts`
  - 模式：BFF 仅做薄封装转发到 manager
  - 可复用：`review-report`、`events`、`factory/runs`
  - 需注意：新路由延续相同命名方式即可

- **实现4**: `apps/web/app/strategy-market/[id]/page.tsx`
  - 模式：使用 `useApiQuery` 拉取详情，在 `SectionCard` 中展示结构化摘要
  - 可复用：`FactoryReviewPanel` 的块状展示方式
  - 需注意：不要把运行详情做成重页面，先在列表页展开即可

- **实现5**: `apps/web/app/strategy-market/page.tsx`
  - 模式：当前已展示最近运行历史摘要
  - 可复用：现有 factory history card 列表位置
  - 需注意：详情展示应增量追加，不影响现有摘要布局

### 2. 项目约定
- **命名约定**: Python 用 `factory_run_detail` action；BFF 路由用 `factory/runs/:runId`
- **文件组织**: 存储层方法放 `strategy.py`；BFF 不承载业务逻辑；Web 只扩展示意
- **代码风格**: 优先增量、小步补丁，不改现有 `run_once()` 数据结构

### 3. 可复用组件清单
- `StrategyMixin._decode_factory_run()`
- `strategy_manager.factory_runs`
- `StrategyController` / `StrategyService` 现有 factory route
- `FactoryReviewPanel` 的分段展示样式
- `useApiQuery` / `useApiMutation`

### 4. 测试策略
- **测试框架**: Python `pytest`
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**:
  - `get_strategy_factory_run(run_id)` 读取
  - `factory_run_detail` action
  - Web 展示类型变更不引入 diagnostics 问题

### 5. 依赖和集成点
- **内部依赖**: `strategy_factory_runs` 已落库；当前只缺按 `run_id` 读取
- **上层接入**: BFF `/strategy-market/factory/runs/:runId`；Web 列表页详情展开
- **配置来源**: 沿用当前 MCP / BFF / Web 现有配置

### 6. 技术选型理由
- 详情查询优先按 `run_id` 单条读取，不新建详情页路由，减少路径扩散
- 继续直接复用 `stages / snapshot_summary` JSONB，不做额外字段拆分
- 前端先做“展开详情”，不做复杂对比视图

### 7. 关键风险点
- `stages` 字段可能过长，页面展示需只做摘要与 JSON 片段
- BFF/Web 构建仍可能受 Node 环境缺失阻塞，需要继续留痕
- 测试以 Python 为主，前端以 diagnostics + diff 检查兜底

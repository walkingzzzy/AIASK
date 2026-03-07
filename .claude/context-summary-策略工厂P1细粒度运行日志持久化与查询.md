## 项目上下文摘要（策略工厂P1细粒度运行日志持久化与查询）
生成时间：2026-03-07

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:372-449`
  - 模式：`save/get/list + _decode_json_field` 的 JSONB 持久化模式
  - 可复用：`_decode_factory_run()`、`save_strategy_factory_run()`
  - 需注意：新增字段必须同步解码、写入和 fake DB

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:1591-1721`
  - 模式：`run_once()` 汇总单次工厂运行结果到 `results`
  - 可复用：`summary / stages / snapshot_summary` 现有结构
  - 需注意：P1-7 应增量扩展，不新建平行日志体系

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:147-170,374-409`
  - 模式：`action + kwargs` 分发，`ok/fail` 返回
  - 可复用：`factory_runs`、`factory_run_detail` 的输入校验与回包风格
  - 需注意：help 文案与 action 列表必须同步更新

- **实现4**: `apps/bff/src/strategy/strategy.controller.ts:70-143`
  - 模式：NestJS controller 内联 DTO + service 薄转发
  - 可复用：`FactoryRunsQueryDto` 与 `GET /factory/runs/:runId`
  - 需注意：可选整数查询参数使用 `@IsOptional() + @Type(() => Number) + @IsInt() + @Min() + @Max()`

- **实现5**: `apps/web/app/strategy-market/page.tsx:63-95,589-665`
  - 模式：`useApiQuery` 拉取详情，`FactoryRunDetailPanel` 做增量展示
  - 可复用：详情展开逻辑与失败阶段保守推断
  - 需注意：新增日志展示时要避免复杂对象直接渲染报错

- **实现6**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:637-845,1170-1380`
  - 模式：`_StrategyDB` fake DB + `StrategyFactoryScheduler` 定向断言
  - 可复用：运行历史持久化、manager action、scheduler 场景测试
  - 需注意：新字段和新 action 必须同时补 fake DB 与断言

### 2. 项目约定
- **命名约定**：工厂运行字段沿用 `run_id/status/started_at/completed_at/elapsed_seconds/summary/stages` 风格；新增字段使用 `run_logs/error_context/failure_stage`
- **文件组织**：继续按 `schema -> storage -> service -> manager -> BFF -> Web -> tests` 单链路收口
- **导入顺序**：保持 Python 标准库在前；TypeScript 保持 NestJS/validator 在前，本地模块在后
- **代码风格**：以最小 helper 扩展既有对象结构，不引入新模块或新页面

### 3. 可复用组件清单
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：JSONB 解码入口
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：单次运行聚合边界
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:factory_runs/factory_run_detail`：工厂查询 action 模式
- `apps/web/app/strategy-market/page.tsx:FactoryRunDetailPanel`：运行详情展示骨架

### 4. 测试策略
- **测试框架**：pytest
- **测试模式**：fake DB 单元测试 + scheduler 行为测试 + BFF/Web diagnostics
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖要求**：正常运行日志持久化、失败阶段与错误上下文、日志筛选查询、manager action、前端静态检查

### 5. 依赖和集成点
- **外部依赖**：无新增依赖
- **内部依赖**：`StrategyFactoryScheduler` 依赖 `DataCollector/StrategySpawner/BacktestFilter/Deduplicator/StrategySubmitter/EliminationChecker`
- **集成方式**：`storage -> manager -> BFF -> Web` 逐层透传
- **配置来源**：沿用既有 DB schema 初始化与 BFF strategy 模块

### 6. 技术选型理由
- **为什么用现有 `strategy_factory_runs` 扩展**：当前已是单次运行聚合边界，新增 `run_logs/error_context/failure_stage` 可最小化改动并复用详情查询
- **优势**：不需要新表、不需要新同步逻辑、BFF/Web 接线短
- **劣势和风险**：`run_once()` 内部会再增加一些辅助逻辑；Web 需要处理嵌套对象展示

### 7. 关键风险点
- **边界条件**：阶段尚未开始就失败时，需要给出合理 `failure_stage`
- **序列化问题**：异常对象、时间对象、复杂 payload 必须转成 JSON 友好结构
- **兼容问题**：历史库中已存在 `strategy_factory_runs` 时必须使用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- **验证风险**：前端仍以 diagnostics 为主，若 Node 依赖缺失需在验证报告中留痕
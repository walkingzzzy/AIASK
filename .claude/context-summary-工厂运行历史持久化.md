## 项目上下文摘要（工厂运行历史持久化）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`
  - 模式：`StrategyFactoryScheduler.run_once()` 串联执行完整工厂流程，并在结束时写入 `self.last_result`
  - 可复用：结构化 `results` 对象、`summary/stages/snapshot_summary`
  - 需注意：当前历史仅保留进程内最近一次，进程重启即丢失

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
  - 模式：策略域 JSONB 对象统一由 `StrategyMixin` 持久化
  - 可复用：`save_daily_snapshot()`、`save_strategy_quality_report()`、`list_strategy_status_events()`
  - 需注意：已有 JSONB upsert/list 模式，适合新增运行历史表

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/schema.py`
  - 模式：策略工厂相关表按顺序增量追加 DDL
  - 可复用：`daily_snapshot_history`、`strategy_quality_reports`、`strategy_status_events`
  - 需注意：新表应继续采用 JSONB 字段 + 时间索引模式

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 模式：`action + kwargs` 分发，统一 `ok/fail`
  - 可复用：`factory_status`、`factory_run_once`、`events`、`review_report`
  - 需注意：新增历史查询 action 时应保持同一返回风格

- **实现5**: `apps/bff/src/strategy/strategy.controller.ts` + `strategy.service.ts`
  - 模式：BFF 仅做薄封装转发到 manager action
  - 可复用：`factory/status`、`factory/run-once` 路由与 service 方法命名
  - 需注意：新端点应沿用同一命名与 envelope 结构

- **实现6**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
  - 模式：`_DummyMCP + _StrategyDB + monkeypatch`
  - 可复用：fake DB 状态、manager action 回归测试、scheduler monkeypatch
  - 需注意：若新增存储方法，需要同步扩展 fake DB

### 2. 项目约定
- **命名约定**: Python 存储方法使用 `save_* / list_* / get_*`；manager action 使用下划线风格
- **文件组织**: DDL 在 `schema.py`；读写方法在 `strategy.py`；业务接线在 `strategy_factory.py`
- **导入顺序**: 先标准库，再第三方，再项目内模块
- **代码风格**: 优先增量补齐，不重构既有调度主链路

### 3. 可复用组件清单
- `StrategyFactoryScheduler.run_once()`：已有结构化运行结果对象
- `StrategyMixin.save_strategy_quality_report()`：可复用 JSONB upsert 写法
- `StrategyMixin.list_strategy_status_events()`：可复用列表查询与 JSON 解码写法
- `apiKeys.strategy()`：前端统一失效 key
- `useApiQuery / useApiMutation`：前端查询与触发入口

### 4. 测试策略
- **测试框架**: Python `pytest`
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**:
  - 运行历史写入成功
  - 历史列表按时间倒序返回
  - manager `factory_runs` action 返回结构正确
  - `factory_run_once` 后历史记录可见
- **辅助验证**: `npm run build -w apps/bff`、`npm run build -w apps/web`

### 5. 依赖和集成点
- **内部依赖**: `strategy_factory.py` 依赖 `get_db()`；`strategy_manager` 调用 scheduler
- **存储依赖**: TimescaleDB/PostgreSQL JSONB
- **上层接入**: BFF `/strategy-market/factory/*`；Web `/strategy-market` 概览页
- **配置来源**: 沿用当前 MCP / BFF / Web 构建配置

### 6. 技术选型理由
- 新增 `strategy_factory_runs` 表比继续只保留 `last_result` 更可审计、更稳定
- 继续采用 JSONB 保存 `summary/stages/snapshot_summary/error`，避免过早拆细字段
- 运行历史优先做“列表查询 + 最新结果回显”，不在本阶段引入复杂分页和二级索引搜索

### 7. 关键风险点
- **数据体积**: `stages` 过大可能导致单行 JSONB 膨胀，需要只保存必要摘要
- **兼容性**: `status()` 仍是同步方法，不适合直接做 DB 访问，应新增独立历史查询入口
- **测试边界**: fake DB 需要同步支持运行历史，不然 manager 测试会缺口
- **前端边界**: 列表页应只展示最近若干次运行摘要，不做复杂运维台

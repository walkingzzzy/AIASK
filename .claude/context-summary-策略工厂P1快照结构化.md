## 项目上下文摘要（策略工厂P1快照结构化）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:51-160`
  - 模式：`DataCollector.collect()` 先采集、再 best-effort 降级、最后统一 `save_daily_snapshot()` 落库。
  - 可复用：现有 `snapshot` 基础字段、`save_daily_snapshot()` 调用点、`run_once()` 的 `snapshot_summary` 使用链路。
  - 需注意：当前只有日志级失败处理，没有结构化 `degraded / failure_reasons / completeness` 契约。

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:417-618`
  - 模式：`Deduplicator.last_report` 采用 `summary + kept + dropped` 的稳定结构化报告模式。
  - 可复用：`summary` 作为机器可读摘要对象的表达方式。
  - 需注意：P1-1 应沿用“轻量结构化对象”思路，不引入新报告体系。

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:328-449`
  - 模式：存储层使用 `save_* / get_* / list_*` 命名，JSONB 字段统一经 `_decode_json_field()` 解码。
  - 可复用：`_decode_factory_run()`、`get_strategy_quality_report()` 的 JSONB 读回模式。
  - 需注意：`daily_snapshot_history` 当前只有写，没有查询方法，需要保持同一风格补齐。

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:374-409`
  - 模式：manager 通过 `action + kwargs` 分发，并用 `ok/fail` 返回结构化结果。
  - 可复用：`factory_runs` / `factory_run_detail` 的查询动作模式。
  - 需注意：新增 snapshot 查询 action 时应保持轻量，不直接扩散到 BFF/Web。

- **实现5**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:744-1079`
  - 模式：测试沿用 `_DummyMCP + _StrategyDB + monkeypatch + AsyncMock`。
  - 可复用：manager action 回归、scheduler 落库回归、`DataCollector` 外部依赖失败兜底测试。
  - 需注意：需要同步扩展 fake DB 的 daily snapshot 读写能力，否则 manager 查询测试无法闭环。

### 2. 项目约定
- **命名约定**：存储层使用 `save_* / get_* / list_*`；manager action 使用蛇形命名；JSON 摘要统一使用 `summary`。
- **文件组织**：继续保持 `services -> storage -> manager -> tests` 分层，本任务先不扩散到 BFF/Web。
- **导入顺序**：沿用 Python 标准库、第三方、项目内模块顺序。
- **代码风格**：优先最小补丁；JSONB 结构保持轻量、可解码、可回归。

### 3. 可复用组件清单
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:DataCollector.collect`：快照采集主入口。
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:StrategyFactoryScheduler.run_once`：消费快照摘要的下游入口。
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_json_field`：JSONB 解码 helper。
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:_decode_factory_run`：结构化查询读回模式。
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`：snapshot 查询 action 接线模板。

### 4. 测试策略
- **测试框架**：`pytest`
- **测试模式**：单元 + manager 集成风格 fake DB 回归
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **本轮覆盖目标**：
  - 正常采集时返回结构化 `summary/completeness/sources`
  - 全部失败时 `degraded=true` 且存在 `failure_reasons`
  - scheduler `run_once()` 能保留增强后的 `snapshot_summary`
  - manager 可以查询 latest/detail/list daily snapshot

### 5. 依赖和集成点
- **外部依赖**：`sentiment_analyzer`、`fund_flow` 三个工具函数、数据库 `save_daily_snapshot()`。
- **内部依赖**：`StrategyFactoryScheduler.run_once()` 消费快照摘要；`strategy_manager` 负责对外查询。
- **集成方式**：`DataCollector` 采集后直接落库，manager 再通过 storage 查询。
- **配置来源**：无新增配置，沿用现有 DB 与 scheduler 结构。

### 6. 技术选型理由
- **为什么用 JSONB 增量扩展**：当前 `daily_snapshot_history` 已存在，继续增列比新建平行表更收敛。
- **为什么先补 manager 查询，不立即补 BFF/Web**：P1-1 的验收重点是“结构化并可查询”，manager 足以形成最小闭环，避免本轮扩散。
- **为什么沿用 summary/completeness/sources**：与 Deduplicator/quality report 的结构化摘要模式一致，易于后续 P1-2/P1-7 复用。

### 7. 关键风险点
- **边界条件**：部分数据源失败但总体仍可运行，需要区分 `partial` 与 `failed`，避免把所有 fallback 都算成致命失败。
- **兼容性风险**：已有 `daily_snapshot_history` 是存量表，需要补 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。
- **查询风险**：测试 fake DB 若不补 `get/list` 方法，会导致 manager action 无法验证。
- **性能风险**：查询只按日期排序/过滤，避免引入重型扫描逻辑。
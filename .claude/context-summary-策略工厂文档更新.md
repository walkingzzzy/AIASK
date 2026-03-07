## 项目上下文摘要（策略工厂文档更新）
生成时间：2026-03-07

### 1. 相似实现/证据来源
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`
  - `StrategyFactoryScheduler.run_once()` 已串联 collect → spawn → autonomy → backtest → dedup → submit → elimination
  - `StrategySubmitter.submit()` 通过质检后会尝试 `ensure_account()` 与 `build_strategy_profile()`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 已暴露 `factory_status`、`factory_run_once`、`factory_runs`、`factory_run_detail`
  - 已暴露 `review_report`、`events`、`incubation_overview`
  - 已暴露 `vector_profiles`、`vector_indexes`、`ai_generate`、`ai_experiments`
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
  - 已持久化 `strategy_quality_reports`、`strategy_status_events`、`strategy_factory_runs`
  - 已持久化 `strategy_incubation_accounts`、`strategy_incubation_metrics`
  - 已持久化 `strategy_vector_profiles`、`vector_index_registry`

### 2. 关键事实
- 向量去重已接入：`Deduplicator.deduplicate()` 对可疑候选调用向量复筛
- 质量报告已落库：不再是运行时临时对象
- 状态事件已落库：不再是“无审计流”
- 工厂运行历史已落库并可查询
- 孵化已超过“仅绑定账户”：已有账户、订单同步、指标记录、决策输出
- AI 生成已接入主链路，但仍是轻量候选增强，不是完整自治工厂

### 3. 文档修订目标
- `README.md`：更新目录首页的“当前代码基线”描述
- `01-系统架构设计文档.md`：修正已实现/缺口/分期建议
- `03-模块功能方案.md`：收紧 AI/孵化/向量/排期口径
- `04-策略生命周期管理流程图.md`：修正时序图说明、晋级口径、建议演进
- `05-向量设计方案.md`：修正“未接入工厂主链路”等过时表述

### 4. 当前不应写成已实现的事项
- `pgvector/HNSW` 持久化 ANN 检索
- 完整 Event Sourcing / CQRS
- 模拟盘 NAV 驱动的全自动晋级/淘汰生产闭环
- 工业级 RL/LLM 自治工厂
- 工厂级总控台、熔断器、完整审计回放系统

### 5. 验证依据
- 测试文件：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- 已本地执行：`pytest -o addopts='' tests/test_strategy_factory_and_marketplace.py -q`
- 结果：`82 passed`


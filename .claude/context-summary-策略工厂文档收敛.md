## 项目上下文摘要（策略工厂文档收敛）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:50-853`
  - 模式：一个文件内按“采集 → 生成 → 回测 → 去重 → 提交 → 淘汰 → 调度”串起完整工厂闭环
  - 可复用：`DataCollector`、`StrategySpawner`、`BacktestFilter`、`Deduplicator`、`StrategySubmitter`、`EliminationChecker`、`StrategyFactoryScheduler`
  - 需注意：`Deduplicator` 当前只做参数相似度；`Scheduler.status()` 与 `run_once()` 已有运行态基础，但尚未通过 BFF 暴露

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py:47-448`
  - 模式：`action` 分发 + `ok/fail` 返回；生命周期与质检逻辑集中在 manager 中
  - 可复用：`LIFECYCLE_TRANSITIONS`、`_run_quality_gate()`、`_lifecycle_scan()`
  - 需注意：当前状态更新直接 `update_strategy_status()`；没有事件流审计；孵化晋级直接读取 `strategy_metrics`

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py:14-264`
  - 模式：围绕策略 CRUD、指标、血缘、淘汰日志、快照做轻量持久化
  - 可复用：`save_strategy_lineage()`、`save_elimination_log()`、`save_daily_snapshot()`
  - 需注意：当前没有 `save_quality_report()`、没有 `strategy_events` 事件表

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py:14-505`
  - 模式：独立向量检索服务，支持 Python 索引主路径，文档注释提到 pgvector，但当前未接入工厂去重
  - 可复用：`find_similar_patterns()`、`build_index()`、`search_index()`、`dtw_distance()`
  - 需注意：`index` 仍是进程内索引；“pgvector/HNSW”更适合作为中期持久化增强，而非现状能力

- **实现5**: `apps/bff/src/strategy/strategy.controller.ts:74-189` + `strategy.service.ts:135-225`
  - 模式：NestJS Controller/Service 分层，端点与 MCP action 一一对应
  - 可复用：现有 16 个策略超市端点扩展方式
  - 需注意：当前并不存在 `factory/status`、`review-report`、`events` 等端点，文档必须明确为“草案”或“建议新增”

### 2. 项目约定
- **文档分层**：研究报告与落地方案必须分层，不能把远期蓝图写成现状能力
- **服务分层**：MCP 核心逻辑在 `packages/akshare-mcp`；BFF 负责 HTTP 暴露；Web 负责展示
- **返回风格**：manager 使用 `ok/fail`，BFF 使用 Controller/Service 转发
- **状态口径**：以 `LIFECYCLE_TRANSITIONS` 为唯一准绳

### 3. 可复用组件清单
- `services/strategy_factory.py`：工厂主流程与调度状态
- `tools/managers/strategy_manager.py`：生命周期与质量门禁
- `services/validation.py`：WF / PKF / Bootstrap 验证能力
- `services/vector_search.py`：相似形态检索基础设施
- `services/paper_trading.py`：模拟交易引擎
- `services/signal_tracker.py`：前向收益与命中率跟踪
- `storage/timescaledb/strategy.py`：策略存储、血缘、淘汰、快照

### 4. 外部资料结论（联网）
- **pgvector 官方文档**：HNSW 适合 ANN 检索，但需要建索引、参数调优（`m`、`ef_construction`、`ef_search`），且过滤条件会影响召回；因此更适合作为中期持久化向量去重方案
- **NestJS 官方文档**：Controller/Service 分层与 `@Get/@Post/@Param/@Body` 路由模式完全符合当前 BFF 结构，说明若未来新增端点，应沿用现有风格扩展
- **Martin Fowler Event Sourcing**：事件溯源能提供审计、回放、快照重建，但会增加外部系统交互与重放复杂度；因此当前更适合先做“轻量审计日志”，而不是直接宣称完整 Event Sourcing/CQRS 已具备
- **JSON Schema 官方资料**：`type/properties/required` 适合定义对象契约，但当前仓库尚未看到运行时强校验接线，故应在文档中表述为“推荐契约格式”而非“已执行校验” 

### 5. 测试策略
- **测试框架**：`packages/akshare-mcp/tests/` 下使用 pytest
- **参考文件**：`packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **验证重点**：已有策略工厂、淘汰、生命周期、strategy_manager action 测试可以作为“现状能力”依据；本轮是文档改写，因此以文档一致性自检为主，不新增代码测试

### 6. 依赖与集成点
- **MCP 核心**：`strategy_factory.py`、`strategy_manager.py`
- **存储层**：`strategy.py`
- **HTTP 暴露**：`apps/bff/src/strategy/*`
- **展示层**：`apps/web/components/strategy-card.tsx`
- **运行编排**：`StrategyFactoryScheduler` 19:00、`SignalTracker` 18:30

### 7. 技术选型理由
- 文档收敛优先基于“现有代码可证明能力”，避免继续扩大研究报告范围
- 对外部技术方案只保留与现有仓库有自然接缝的部分：pgvector/HNSW、NestJS 端点扩展、审计事件流
- 对高复杂度方案（完整 Event Sourcing、真实模拟撮合、RL/LLM 生成）统一下放到中长期规划

### 8. 关键风险点
- 文档若继续混写“现状 / 草案 / 远期”，会误导排期与对外承诺
- 事件溯源、pgvector 持久化、模拟盘绑定都涉及跨模块改动，不应被表述成当前已有能力
- 研究报告正文保留价值较高，但必须加定位说明，避免被误读为实施说明
## 项目上下文摘要（完整实现策略工厂）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py`
  - 模式：工厂主链路调度器串联 `collect → spawn → filter → deduplicate → submit → eliminate`
  - 可复用：`_build_strategy_panels()`、`_run_validation_report()`、`_run_risk_report()`
  - 需注意：原始 `Deduplicator` 只做参数去重，`run_once()` 只输出轻量统计

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
  - 模式：`action + kwargs` 分发，返回 `ok/fail`
  - 可复用：`_run_quality_gate()`、`_lifecycle_scan()`、`get_signal_stats()`
  - 需注意：原始 action 缺少 `factory_status / factory_run_once / review_report / events`

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py`
  - 模式：策略域持久化集中在 `StrategyMixin`
  - 可复用：`save_strategy()`、`save_strategy_metrics()`、`save_strategy_lineage()`、`save_elimination_log()`
  - 需注意：原始存储层缺少质量报告与状态事件表/方法

- **实现4**: `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py`
  - 模式：进程内向量索引 + fallback 检索
  - 可复用：`VectorSearchEngine.find_similar_patterns()`、`last_backend_used`
  - 需注意：当前真实能力是 K 线/收益率/技术特征向量，不是 pgvector

### 2. 项目约定
- **命名约定**: Python 侧工具/manager 继续使用动作名或 `get_*`；BFF 使用 `controller -> service`
- **文件组织**: 工厂逻辑在 `services/strategy_factory.py`；持久化在 `storage/timescaledb/strategy.py`
- **导入顺序**: 先标准库，再三方库，再项目内模块
- **代码风格**: 增量补丁优先，不做跨模块重构

### 3. 可复用组件清单
- `services/strategy_factory.py:_build_strategy_panels()`：构造策略行为序列
- `services/vector_search.py:VectorSearchEngine`：候选行为向量复筛
- `tools/managers/strategy_manager.py:_run_quality_gate()`：统一质量门禁口径
- `storage/timescaledb/strategy.py:update_strategy_status()`：策略状态更新入口

### 4. 测试策略
- **测试框架**: Python `pytest`；BFF/Web 以构建与类型检查为主
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖重点**:
  - 去重结构化结果与向量复筛
  - 质量报告落库
  - 生命周期事件查询与孵化概览
  - BFF/Web 构建不回归

### 5. 依赖和集成点
- **内部依赖**: `strategy_factory.py` 依赖 `strategy_manager._run_quality_gate()`
- **存储依赖**: `schema.py` 负责 TimescaleDB DDL；`strategy.py` 负责读写方法
- **上层接入**: BFF `apps/bff/src/strategy/*`；Web `/strategy-market` 与 `/strategy-market/[id]`
- **配置来源**: MCP 数据库连接与 Next/Nest 现有构建配置

### 6. 技术选型理由
- 第一阶段优先新增 `strategy_quality_reports` 和 `strategy_status_events`，避免把运行时对象继续塞进固定指标表
- 向量判重优先复用 `vector_search.py` 的进程内索引能力，避免越级引入 `pgvector/HNSW`
- 孵化判断复用 `signal_forward_returns`，只做最小观察窗口，不引入完整模拟盘闭环

### 7. 关键风险点
- **接口兼容**: 旧测试 fake DB 不支持新参数，需要兼容式状态更新调用
- **边界条件**: 向量复筛可能拿不到足够行为序列，需回退到参数去重
- **性能**: 行为序列构建可能重复读 K 线，需要缓存
- **验证**: BFF/Web 缺少现成单测，只能以构建和类型检查兜底

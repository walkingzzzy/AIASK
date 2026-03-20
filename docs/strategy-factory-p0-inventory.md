# Strategy Factory P0 清单

## 1. 目标

这份清单用于支撑独立包迁移的 P0 阶段，目的只有三件事：

- 固化最小回归集，防止迁移过程出现静默回归。
- 明确 `StrategyFactoryRepository` 需要覆盖的实际 DB 能力。
- 明确兼容层必须保留的 patch-point，避免“能 import 但不能 patch”的伪兼容。

## 2. 最小回归集

固定执行顺序见脚本：

- `scripts/strategy-factory-p0-regression.sh`

包含测试：

- `packages/akshare-mcp/tests/test_strategy_factory_module_compat.py`
- `packages/akshare-mcp/tests/test_strategy_factory_package_migration_contract.py`
- `packages/akshare-mcp/tests/test_strategy_factory_gate_report.py`
- `packages/akshare-mcp/tests/test_backtest_filter_concurrency.py`
- `packages/akshare-mcp/tests/test_concurrency_optimization.py`
- `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`

说明：

- `test_strategy_factory_package_migration_contract.py` 会先校验旧路径公共契约。
- 当新包 `strategy_factory` 或 `strategy_factory.api.facade` 尚未接入时，新旧路径对照断言会自动 `skip`，不会影响当前基线。

## 3. 兼容导出契约

迁移期间旧路径必须持续暴露以下核心符号：

- `StrategyFactoryScheduler`
- `StrategySpawner`
- `BacktestFilter`
- `Deduplicator`
- `StrategySubmitter`
- `EliminationChecker`
- `get_strategy_factory_scheduler`

旧包根路径还必须保留以下 patch surface：

- `asyncio`
- `get_strategy_factory_package`
- `_call_optional_async`
- `_build_strategy_panels`
- `_run_validation_report`
- `_run_risk_report`

额外必须保留的模块级 patch-point：

- `akshare_mcp.services.strategy_factory.factory_scheduler.get_strategy_factory_package`
- `akshare_mcp.services.strategy_factory.factory_scheduler._call_optional_async`

## 4. Repository 能力盘点

以下按调用阶段整理，便于后续抽 `StrategyFactoryRepository` 时按场景拆接口，而不是把所有方法塞进一个超大协议。

### 4.1 快照采集与市场上下文

- `get_klines`
  - 用于恐贪、事件研究、回测前置数据。
- `get_limit_up_stats`
  - 用于恐贪宽度指标。
- `get_factor_ic_history`
  - 用于 `collect.py` 与 `factor_research.py` 的因子历史。
- `count_strategies_by_type`
  - 用于快照中的已上市/孵化策略数量。
- `save_daily_snapshot`
  - 用于保存每日工厂快照。
- `get_recent_north_fund_summary`
  - 可选增强能力，用于北向资金摘要。
- `get_factory_market_internal_snapshot`
  - 可选增强能力，用于市场内部指标回退。
- `list_factory_event_clusters`
- `list_factory_event_signals`
- `list_factory_theme_definitions`
  - 以上三项为事件驱动快照的可选读取能力。

### 4.2 事件引擎与主题持久化

- `list_stock_universe`
- `save_factory_theme_definition`
- `save_factory_event_cluster`
- `save_factory_event_signal`
- `save_factory_market_internal_snapshot`
- `save_factory_company_theme_exposure`

说明：

- 这些能力当前通过 `getattr` / `_call_optional_async` 接入，属于可选增强能力。
- 迁移时不建议直接并入“最小可用 Repository”，更适合拆为事件研究侧 gateway。

### 4.3 候选去重与淘汰

- `list_strategies`
  - 用于 `deduplicator.py`、`elimination.py` 扫描已存在策略。
- `get_strategy_metrics`
  - 用于淘汰阶段读取回测/验证/风险指标。
- `get_strategy_quality_report`
  - 可选增强能力，优先读取提交时保存的质量报告。
- `get_signal_stats`
  - 可选增强能力，用于信号命中率淘汰规则。
- `save_elimination_log`
  - 可选写入能力，用于淘汰留痕。

### 4.4 提交、状态流转与实验留痕

- `save_strategy`
- `update_strategy_status`
- `save_strategy_lineage`
- `save_strategy_metrics`
- `save_strategy_quality_report`
  - 以上构成提交阶段最核心的实体、状态、指标与报告写入能力。
- `get_strategy`
  - 用于 dedup 命中后刷新已有策略。
- `get_strategy_generation_experiment`
- `save_strategy_generation_experiment`
  - 用于工厂生成实验记录去重与落盘。

### 4.5 调度器运行记录

- `save_factory_task_evidence`
  - 可选增强能力，用于事件任务证据留痕。
- `save_strategy_factory_run`
  - 可选增强能力，用于保存整次工厂运行结果。

## 5. patch-point 盘点

当前测试中，以下旧路径会被直接 patch 或 monkeypatch，迁移时必须优先保留：

### 5.1 包根路径

- `akshare_mcp.services.strategy_factory.DataCollector`
- `akshare_mcp.services.strategy_factory.MarketOpportunityScanner`
- `akshare_mcp.services.strategy_factory.StrategySpawner`
- `akshare_mcp.services.strategy_factory.BacktestFilter`
- `akshare_mcp.services.strategy_factory.Deduplicator`
- `akshare_mcp.services.strategy_factory.StrategySubmitter`
- `akshare_mcp.services.strategy_factory.EliminationChecker`
- `akshare_mcp.services.strategy_factory.run_gated_filter`
- `akshare_mcp.services.strategy_factory.FactorResearchBuilder.build`
- `akshare_mcp.services.strategy_factory._build_strategy_panels`
- `akshare_mcp.services.strategy_factory._run_validation_report`
- `akshare_mcp.services.strategy_factory._run_risk_report`
- `akshare_mcp.services.strategy_factory.asyncio.to_thread`

### 5.2 模块路径

- `akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen`
- `akshare_mcp.services.strategy_factory.factory_scheduler.get_strategy_factory_package`
- `akshare_mcp.services.strategy_factory.factory_scheduler._call_optional_async`
- `akshare_mcp.services.strategy_factory.backtest_filter.REPRESENTATIVE_STOCKS`
- `akshare_mcp.services.strategy_factory.backtest_filter.BACKTEST_CODE_CONCURRENCY`

### 5.3 兼容层结论

- 旧路径兼容不能只做 `from new_pkg import symbol` 级别的 re-export。
- 对包含 patch surface 的模块，必须优先保留 shim 层。
- 尤其要保住包根路径上的 `asyncio` 绑定，否则现有并发测试会直接失效。

## 6. P0 完成标准

满足以下条件即可视为 P0 完成：

- 最小回归集可独立执行。
- 兼容契约测试已落库。
- `StrategyFactoryRepository` 所需 DB 能力已有盘点文档。
- 关键 patch-point 已有盘点文档。
- 后续 Phase 1 可以直接基于这份清单抽 `contracts.py` 与 compat shim。

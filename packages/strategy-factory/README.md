# strategy-factory

当前策略工厂主实现包。

如果你要理解“现行入口”而不是历史方案，请优先看：

1. [`../../策略工厂/README.md`](../../策略工厂/README.md)
2. [`../../策略工厂/策略工厂整改详细清单.md`](../../策略工厂/策略工厂整改详细清单.md)
3. [`../../docs/plans/策略工厂策略对象协议.md`](../../docs/plans/策略工厂策略对象协议.md)

## 当前定位

- 这里承载策略工厂的当前主实现，不再只是迁移中的占位包。
- `akshare_mcp.services.strategy_factory` 仍保留兼容层，但新增业务逻辑应优先落在本包。
- MCP 侧的主要消费入口仍是 `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`。

## 当前目录结构

- `api/`
  对外 facade、contracts、DTO。
- `application/`
  工厂主链编排、质量门禁、提交、去重、回测过滤、调度与运行时服务。
- `domain/`
  候选、研究任务、命名、目标池、常量等领域对象。
- `infrastructure/`
  MCP 适配器与持久化边界。
- `compat/`
  迁移兼容层。

## 推荐使用方式

优先通过稳定 facade 使用本包，而不是直接跨层导入内部文件：

```python
from strategy_factory import (
    StrategyFactoryScheduler,
    get_strategy_factory_scheduler,
    run_submission_quality_gate,
    get_factory_constants,
)
```

当前 facade 主要从 `strategy_factory.__init__` 和 `strategy_factory.api.facade` 暴露以下能力：

- `StrategyFactoryScheduler`
- `BacktestFilter`
- `Deduplicator`
- `StrategySubmitter`
- `EliminationChecker`
- `MarketOpportunityScanner`
- `FactorResearchBuilder`
- `run_submission_quality_gate`
- `get_strategy_factory_scheduler`
- `get_factory_constants`

## 当前代码主线

按当前实现，策略工厂主链大致分为：

1. `collect` / 市场快照与输入准备
2. `opportunity` / `event_engine` / `factor_research`
3. `spawner` / 候选生成
4. `backtest_filter`
5. `deduplicator`
6. `submitter` / `submission_gate` / `quality_gates`
7. `factory_scheduler` / `cycle_runner` / `elimination`

补充说明：

- 当前运行态、review、孵化、工厂历史等读接口，仍主要通过 `strategy_manager` 暴露给 MCP / BFF / Web。
- 当前策略对象与统一决策协议不在这里单独闭环定义，需同时参考 `docs/plans/` 中的协议文档。

## 与兼容层的关系

- 旧路径 `akshare_mcp.services.strategy_factory.*` 仍服务于历史 import、patch surface 和部分测试。
- 新增逻辑不要优先堆到兼容层；应先在本包实现，再按需要向兼容层桥接。
- 如果要判断“哪些代码已经迁入主包”，以本包 `application/`、`domain/`、`api/` 的实际实现为准。

## 测试与排障

- 本包测试位于 `packages/strategy-factory/tests/`
- 吞吐和专项脚本可参考 `scripts/strategy-factory-throughput-benchmark.py`
- 运行时入口与现行文档导读在根目录 `策略工厂/` 和 `docs/README.md`

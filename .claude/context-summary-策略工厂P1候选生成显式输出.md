## 项目上下文摘要（策略工厂P1候选生成显式输出）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:301-500`
  - 模式：`StrategySpawner` 以 `_from_* + _fill_gaps + _make()` 生成候选
  - 可复用：保留 `spawn_reason` 文本说明，在 `_make()` 处统一扩展结构化字段
  - 需注意：不能改变现有启发式生成逻辑和参数分布

- **实现2**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:556-618`
  - 模式：`Deduplicator.last_report` 使用 `summary + kept + dropped` 暴露结构化报告
  - 可复用：为 `StrategySpawner` 增加 `last_report / get_last_report()`
  - 需注意：运行历史更适合存汇总，不宜无界膨胀

- **实现3**: `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py:1236-1238`
  - 模式：scheduler 已将 `spawn` 阶段写入 `results["stages"]`
  - 可复用：在 `stages.spawn` 中补充结构化 summary
  - 需注意：保持与现有 `collect/backtest/deduplicate/submit` 风格一致

- **实现4**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py:207-284`
  - 模式：`TestStrategySpawner` 已覆盖 `_from_* / _fill_gaps / spawn()`
  - 可复用：直接补充结构化字段与配额补位断言
  - 需注意：测试应覆盖阈值命中与 quota fill 两类原因

### 2. 项目约定
- **命名约定**: 候选对象保留 `spawn_reason`，新增字段以 `trigger_*` / `generation_*` / `quota_*` 为主
- **文件组织**: 逻辑继续放在 `strategy_factory.py` 内，不新增平行服务模块
- **代码风格**: 采用轻量 dict 契约，不引入 dataclass/新依赖

### 3. 可复用组件清单
- `StrategySpawner._make()`：统一候选输出入口
- `Deduplicator.get_last_report()`：结构化报告模式参考
- `StrategyFactoryScheduler.run_once()`：阶段汇总落运行历史入口
- `TestStrategySpawner`：候选生成测试入口

### 4. 测试策略
- **测试框架**: pytest
- **参考文件**: `packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py`
- **覆盖要求**:
  - 正常阈值触发场景
  - 分类配额补位场景
  - scheduler `stages.spawn` 汇总可见

### 5. 依赖和集成点
- **内部依赖**: `StrategySubmitter`、`StrategyFactoryScheduler` 会继续消费候选对象
- **集成方式**: 候选先经 `spawn -> backtest -> deduplicate -> submit`，运行历史通过 `save_strategy_factory_run()` 落库

### 6. 技术选型理由
- **方案**: 在 `_make()` 统一补结构化字段，并为 `StrategySpawner` 增加轻量 `last_report`
- **优势**: 改动集中、复用性强、对下游兼容好
- **风险**: 若汇总字段设计过重会放大运行历史体积，因此只保留 summary

### 7. 关键风险点
- **边界条件**: 同一候选可能同时受多个信号影响，但当前实现是“单条规则生成单个候选”，应保持该粒度
- **兼容性**: 不能破坏现有 `spawn_reason`、`StrategySubmitter`、去重逻辑与既有测试
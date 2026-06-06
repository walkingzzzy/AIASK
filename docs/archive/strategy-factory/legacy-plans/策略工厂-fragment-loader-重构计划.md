# 策略工厂 · fragment loader 重构计划（治理立项 PR-S/#29）

> 日期：2026-05-17（立项）
> 状态：未实施 — 仅作为治理基线与重构路线图

---

## 1. 现状

策略工厂的多个核心类通过自定义的 `fragment loader`（`strategy_factory._fragment_loader.exec_block`）拼装：

```python
_exec_block(
    globals(),
    'spawner_parts',
    'class StrategySpawner:\n',
    ['matching.py', 'selection.py', 'factories.py', 'serialization.py', 'part_5.py'],
    future_annotations=True,
)
```

涉及的类（截至 2026-05-17）：

| 类 | 主入口 | parts 目录 | parts 数 | 总行数估计 |
|---|---|---|---|---|
| `StrategySpawner` | `domain/spawner.py` | `domain/spawner_parts/` | 5 | ~2000 |
| `BacktestFilter` | `application/backtest_filter.py` | `application/backtest_filter_parts/` | 5 | ~2500 |
| `Deduplicator` | `application/deduplicator.py` | `application/deduplicator_parts/` | 4 | ~1800 |
| `StrategySubmitter` | `application/submitter.py` | `application/_submitter_actions/runner_parts/` | 6 | ~3000 |
| `FactoryCycleRunner` | `application/cycle_runner.py` | `application/cycle_runner_parts/` | 1 | ~1010 |
| `StrategyFactoryScheduler` | `application/factory_scheduler.py` | `application/_factory_scheduler_loop_parts/` 等 | 3+ | ~2500 |
| 因子调度器 | `services/factor_scheduler.py` | `services/factor_scheduler_parts/` | 3 | ~1500 |
| Quality Gate | `application/quality_gates.py` | `application/quality_gates_parts/` | 5 | ~2000 |
| Submission Gate | `application/submission_gate/runner.py` | `application/submission_gate/runner_parts/` | 5 | ~2500 |

合计 **9 个类，~18,800 行**通过 fragment loader 拼装。

---

## 2. 影响

### 2.1 直接代价

- **`import` 后类才存在**：单元测试不能直接 `from xxx_parts.policy import _foo`，必须先触发主入口 `import strategy_factory.application.deduplicator`，然后 part 的函数才注入到 class。
- **grep / IDE 跳转跨文件**：审计文档每篇都要列 5 个 parts 文件路径就是症状（见模块审计 `02 / 04 / 05 / 06 / 07 / 08`）。
- **静态类型检查丢失**：Python 类型工具（mypy / pyright）大多看不见 `exec_block` 注入的函数，IDE 报"undefined attribute"成为常态。
- **错误堆栈失真**：栈追踪显示 `/runner.py::runner_parts` 而非真实文件路径（参考 PR-S3 第一次 smoke 报错时的 `_save_metric_with_retry` 行号）。

### 2.2 间接代价

- 每次新增/重构一个 part 都要小心 method 名字冲突（同一 class 拼出来）。
- code review 阅读路径长。
- 新人上手成本高。

---

## 3. 为什么当初这么做（推测）

- 单文件 1000+ 行难以维护，自然想拆。
- 但拆成"独立 module"后，class 跨 module 难以共享 `self` —— `exec_block` 是绕过这一限制的取巧。
- 历史上可能避免循环 import。

---

## 4. 推荐重构路径

按风险与收益排序，建议分三步走：

### 步骤 1（低风险）：把 parts 改成 Mixin

```python
# 重构前
_exec_block(globals(), 'spawner_parts', 'class StrategySpawner:\n', ['matching.py', 'selection.py', ...])

# 重构后
from .spawner_parts.matching import _SpawnerMatchingMixin
from .spawner_parts.selection import _SpawnerSelectionMixin
# ...
class StrategySpawner(_SpawnerMatchingMixin, _SpawnerSelectionMixin, ...):
    pass
```

收益：grep / 类型检查 / 错误堆栈全部正常，IDE 跳转可用。
风险：每个 part 顶层需要从游离方法改成 class 内方法，但 `self` 引用方式不变。

### 步骤 2（中风险）：把高内聚的小 part 合回主文件

像 `cycle_runner_parts/normalizers.py` 只有一份 1010 行的单文件 part，与主类 1:1，合回 `cycle_runner.py` 完全合理。

### 步骤 3（中风险）：拆分大类

`StrategySpawner` / `StrategySubmitter` 真正的问题不是文件长，而是单类职责过多。重构方向：

- Spawner → `SignalBatchBuilder` + `VariantExpander` + `QuotaFiller` + `TargetAligner` 4 个协作类
- Submitter → `SubmissionPolicy` + `SubmissionExecutor` + `LifecycleCoordinator` 3 个协作类（lifecycle_coordinator 已存在，剩下两个可继续拆）

---

## 5. 不做什么

- 不要保留"fragment loader 占位"，直接迁移到 Mixin 后删除 `exec_block` 调用与 `_fragment_loader` 模块本身。
- 不要混合方案（部分 fragment + 部分 Mixin），会让代码 review 更混乱。
- 不要在重构同时改业务逻辑 —— 一次只动一件事。

---

## 6. 验收

- [ ] `grep "exec_block" packages/strategy-factory` 返回 0 行
- [ ] 删除 `strategy_factory/_fragment_loader.py`
- [ ] `mypy packages/strategy-factory` 通过率不下降
- [ ] 现有 `tests/` 全绿
- [ ] 审计文档 02/04/05/06/07/08 不再需要"5 个 parts 文件路径"列表

---

## 7. 工作量估计

| 步骤 | 单类工作量 | 9 个类合计 |
|---|---|---|
| Mixin 改造 | 0.5-1 天 | 5-10 天 |
| 合回主文件（仅小 part） | 0.5 天 | 2 天 |
| 大类拆分（Spawner / Submitter） | 2-3 天 | 4-6 天 |

**总计约 2-3 人周**，但可以增量做，每个类独立 PR。

---

## 8. 立即可做的预备工作

- 在每篇模块审计文档顶部加 "parts 索引表"（已部分完成）。
- 给所有 parts 文件加文件级 docstring：`"""Internal fragment of <ClassName>. Do not import directly."""`
- 写一个 `scripts/fragment_loader_audit.py`，扫描 `exec_block` 调用并输出每个类的方法清单，作为 Mixin 改造的输入。

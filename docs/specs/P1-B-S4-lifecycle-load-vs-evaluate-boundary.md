# P1-B S4：Lifecycle 装载 vs 判定边界

> 日期：2026-07-11  
> 状态：边界约定生效（判定已上移；装载仍在宿主）

## 判定（Strategy Factory ownership）

| 能力 | 模块 |
| --- | --- |
| execution hard gate | `strategy_factory.contracts.hard_gate` |
| promotion_ready 布尔组合 | `strategy_factory.contracts.promotion_ready` |
| evidence gap schema | `strategy_factory.contracts.evidence_gaps` |
| DSR 晋升门 | `strategy_factory.infrastructure.promotion.dsr_gate` |
| 晋级 review/score | `strategy_factory.infrastructure.promotion.review_outcome` |
| 撮合时段/涨跌停 | `strategy_factory.infrastructure.matching.rules` |
| incubation phase 表 | `strategy_factory.runtime.incubation_phases` |

**规则**：上述模块 **禁止** import `akshare_mcp`；只接受 dict / 序列 / 可注入 fn。

## 装载（akshare-mcp host ownership）

| 能力 | 模块 |
| --- | --- |
| overview DB 组装 | `strategy_lifecycle_shared/overview.py` |
| 前向序列 fetch | `incubation_factory/promotion_gate.fetch_forward_return_series` |
| promotion apply / 写库 | `promotion_pipeline.review`（async I/O） |
| matching 扫描/lease/成交写库 | `matching_engine.MatchingEngine` |
| runner phase 实现体 | `incubation_factory/runner.py` |
| formal 诊断聚合 | `factory_diagnostics.FactoryDiagnosticsService` |

**规则**：装载层调用 SF 纯函数，不复制 hard gate / score 权重；新增状态机优先 SF。

## 验收

```powershell
# SF 无 MCP 可跑
pytest packages/strategy-factory/tests/test_hard_gate_thresholds_snapshot.py `
  packages/strategy-factory/tests/test_promotion_evaluation_kernel.py -q

# Host identity
pytest packages/akshare-mcp/tests/test_hard_gate_contract_ownership.py `
  packages/akshare-mcp/tests/test_promotion_kernel_ownership.py -q
```

## 下一步（S5 加严）

- runner 逐步用 `get_phase_timeout(name)` 替换散落 timeout 字面量
- overview 大函数按「装载块 / 判定块」注释分区（不强制一次拆文件）

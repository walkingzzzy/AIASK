# HEAD 校正版落实审计与整改计划

- 审计时间：2026-04-13
- 基线提交：`305838a`
- 本轮范围：`packages/strategy-factory`、`packages/akshare-mcp`、`packages/shared-types`
- 结论口径：以当前 `HEAD` 源码、迁移、运行链路与测试为准；仅有测试桩但无生产链路才判定为“未闭环”。

## 一、校正版差异审计表

| 项目 | 原判定 | HEAD 事实 | 修正判定 | 证据路径 |
| --- | --- | --- | --- | --- |
| `strategy_trade_position_fills` | 完全缺失 | 已有 phase_5 schema、CRUD、运行时写入、round-trip backfill 与审计汇总 | 已实现，待核验生产迁移/回填覆盖率 | `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_5.py` `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation.py` `packages/akshare-mcp/src/akshare_mcp/services/incubation.py` `packages/akshare-mcp/tests/test_execution_audit_phase5.py` |
| `strategy_signal_evidence` | 调用方依赖、部分达标 | 孵化链路 `sync_signals_to_orders()` 已真实落表，且有原生表与 list/save 接口 | 已实现，剩余问题是覆盖面是否超出 incubation 路径 | `packages/strategy-factory/src/strategy_factory/application/semantic_contract.py` `packages/akshare-mcp/src/akshare_mcp/services/incubation.py` `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation.py` |
| `strategy_candidate_evidence` | 仅 legacy 兼容 | 原生表与 native backfill 已存在，submitter 之前是 legacy/native 双写 | 已实现但主写路径未统一；本轮改为 native 优先、legacy mirror | `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_5.py` `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_6.py` `packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py` |
| `signal_quality_registry` | 未接入 scheduler summary 输出 | 已进入 `factory_status`、capabilities 与 shared-types 合同 | 已实现，剩余问题在外部消费者展示而非仓内合同 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_lifecycle.py` `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_crud.py` `packages/shared-types/src/strategy.ts` |
| `STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED` 默认策略 | 未明确 | 常量默认仍为关闭，属兼容优先策略 | 非缺失；需运行时决策与文档化 | `packages/strategy-factory/src/strategy_factory/domain/constants.py` |

## 二、本轮已落地整改

### 1. 执行审计核验入口

- 新增 DB 级核验方法 `get_execution_audit_verification()`，统一核查：
  - 必要表是否存在
  - `paper_orders/paper_trades` 的 `signal_id/position_id` 补列是否存在
  - phase_5/6 migration key 是否已登记
  - 订单/成交 linkage 覆盖率
  - round-trip 持仓状态与可审计样本汇总
- 新增 `strategy_manager(action="execution_audit_verification")`，可直接输出迁移后状态核验与回填结果审计视图。
- 配套补了 in-memory test runtime 与 manager 集成测试。

证据：

- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_mgr_lifecycle.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`
- `packages/akshare-mcp/tests/_strategy_factory_test_support_runtime.py`
- `packages/akshare-mcp/tests/test_execution_audit_phase5.py`
- `packages/akshare-mcp/tests/test_strategy_manager_marketplace.py`

### 2. Candidate Evidence 主写路径统一

- `StrategySubmitter` 现在改为：
  - 先写 `save_strategy_candidate_evidence()`
  - 再按兼容需要 mirror 到 `save_factory_task_evidence()`
- 这保持了旧消费者兼容，但把主持久化路径切到原生表优先。

证据：

- `packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py`
- `packages/strategy-factory/tests/test_submitter_compat_bridge.py`

### 3. Submission Gate 软化总收益硬阻断

- `total_return_min` 不再单独触发硬拒绝。
- 当 `total_return` 低于阈值但 `target_layer_oos_return` 等核心门仍通过时，只记录 warning。
- 同时修正 `total_return` 的读取优先级，优先消费独立 `total_return`，缺失时再回退到 `target_layer_oos_return`。

证据：

- `packages/strategy-factory/src/strategy_factory/application/submission_gate.py`
- `packages/strategy-factory/tests/test_submission_gate_contract.py`

### 4. Incubation Budgeter 重标

- 降低 `total_return` 的基础权重。
- 将 `paper_skill_lcb`、`paper_recent_skill_lcb`、`paper_stability_gap`、`paper_coverage_ratio`、`execution_conversion_efficiency` 真正纳入优先级评分。
- feedback 可用时优先使用 `skill_priority_adjustment / skill_budget_multiplier`，并叠加 `skill_control_mode` 惩罚。

证据：

- `packages/strategy-factory/src/strategy_factory/application/incubation_budgeter.py`
- `packages/strategy-factory/tests/test_incubation_budgeter.py`

## 三、整改路线图

### P0

- 明确 `STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED` 的运行策略。
  - 若继续默认关闭：补 rollout 文档，说明开启条件与回归面。
  - 若改为默认开启：补常量切换与更完整回归测试。
- 在真实库执行 `execution_audit_verification`，确认：
  - phase_5/6 migration key 已登记
  - `paper_orders/paper_trades` 的 `signal_id/position_id` 已补列
  - 生产库历史数据的 backfill 覆盖率达到预期

### P1

- 决定 `strategy_candidate_evidence` 是否长期保留 dual write。
  - 当前状态：native 优先 + legacy mirror
  - 后续可选：切到 native-only，再把旧接口降为 fallback
- 用真实库验证 `closed/open/incomplete` 三类持仓的 round-trip 聚合稳定性。
  - 重点看 `refresh_strategy_trade_position()` 与回填脚本在脏历史数据上的行为

### P2

- 继续梳理 promotion/budget 之外仍残留的 ROI 高权重位置，决定是否同样切到 signal-quality 主导。
- Web/BFF 展示升级作为外部依赖任务跟进；本仓仅保留 DTO/shared-types/feature-flag 合同收口。

## 四、风险提示

### 1. 运行时开关

- `confidence_diagnostics` 仍是默认关闭策略；不应把“字段没返回”误判为“代码未实现”。

### 2. 迁移状态

- 本轮代码已具备核验入口，但如果没有现网数据库访问，仍只能确认“迁移与回填代码已存在”，不能替代“生产已执行”的事实核验。

### 3. 外部 UI 消费

- `signal_quality_registry`、质量开关与新审计状态已在仓内合同层暴露。
- 若页面/BFF 不显示，属于仓外或跨模块消费问题，不应回写为 Python 层“未实现”。

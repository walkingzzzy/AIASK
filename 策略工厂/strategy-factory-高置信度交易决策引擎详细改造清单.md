# Strategy Factory 高置信度交易决策引擎详细改造清单

更新日期：2026-04-13
适用范围：`packages/akshare-mcp`、`packages/strategy-factory`、`apps/bff`、`apps/web`
定位：基于当前 HEAD 重新核对后的详细改造清单，重点解决“结构合同已部分落地，但编译、回测、孵化、执行审计尚未完全统一”的问题。

---

## 0. 当前 HEAD 的重新判断

这次改造不是从零设计，而是对已有 Phase 1 / Phase 2 能力做统一、收口和补齐。

### 已经存在的能力

- 评审层已经有 `evidence_alignment_audit`、`confidence_contract`、`hard_fail_reasons`、`unsupported_rule_count`、`proxy_only_event_claim_count` 的硬门与评分逻辑。见：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_reviewer.py:246`
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_reviewer.py:364`
- 生命周期层已经用 `skill_lcb / recent_skill_lcb / effective_n / coverage_ratio / stability_gap` 作为主质量指标。见：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py:346`
- 执行审计 gate 已经存在，且已接入 `trade_expectancy`、`pnl_conversion_efficiency`、`execution_conversion_efficiency`。见：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py:246`
- `strategy_candidate_evidence`、`strategy_signal_evidence`、`strategy_trade_positions` 已经存在于 schema 与 backfill 中，不应再按“新建表”口径处理。见：
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_6.py:7`
  - `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_6.py:35`
- `runtime_playbook` 已经有默认生成逻辑，并包含 `exit_policy` / `adverse_move_policy` / `reentry_policy` / `position_policy`。见：
  - `packages/akshare-mcp/src/akshare_mcp/services/strategy_spec.py:537`

### 当前最关键的缺口

1. 同一 `loss_bands.action == "reduce"` 在回测链与孵化链语义不一致：
   - 回测 DSL：`reduce` 被并入 `forced_exit=True`，等同平仓。
   - 孵化 runtime：`reduce` 是半仓减仓。
   - 见：
     - `packages/akshare-mcp/src/akshare_mcp/services/backtest/dsl_strategy.py:160`
     - `packages/akshare-mcp/src/akshare_mcp/services/incubation.py:906`
2. 评审层语义合同强于编译/运行层，存在“review 看起来合规，lowering/runtime 发生语义漂移”的风险。
3. `resolve_incubation_pipeline_stage()` 已较合理，但 `_readiness_score()` 仍混入较多历史兼容型综合分逻辑，容易与硬门混淆。见：
   - `packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py:25`
4. execution audit 指标已存在，但从 `signal -> order -> fills -> round-trip position -> execution metrics` 的主写路径还不够统一。
5. `trade_plan -> runtime_playbook -> DSL` 的映射关系仍不够显式，可解释性不足。

---

## 1. 改造总原则

- 先修正**研究/回测/孵化执行语义不一致**，再做结构收口。
- 不重复发明已存在的能力；优先把已有 reviewer / lifecycle / schema 能力打通。
- 所有改造按“**硬门优先，评分次之，展示最后**”推进。
- 不把 `observed_days` 当主门；它只能作为观察辅助字段。
- 不把 `ECE/Brier` 提前升级成硬门；继续维持诊断优先。

---

## 2. P0 清单：修复回测 DSL 与孵化执行的语义分裂

### 2.1 目标

让 `runtime_playbook.adverse_move_policy.loss_bands[].action` 在以下链路里保持一致：

- DSL 回测
- runtime signal
- incubation order generation
- round-trip position 聚合

### 2.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/backtest/dsl_strategy.py`

**现状问题**
- `reduce` 目前和 `exit` / `freeze_reentry` 一起进入 `forced_exit=True` 分支。
- 这会导致回测对“减仓”语义的表达失真。

**改造项**
- [ ] 把 `reduce` 从 `forced_exit` 语义中拆出来。
- [ ] 在策略内部状态中引入 `position_units` 或 `position_fraction`。
- [ ] 支持 `1.0 -> 0.5 -> 0.0` 这种最小减仓路径。
- [ ] `freeze_reentry` 保持退出 + cooldown 逻辑不变。
- [ ] `exit` 保持全平逻辑。

**验收标准**
- [ ] 同一组 `loss_bands` 在回测与孵化下，对 `reduce` 的行为一致。
- [ ] `reduce` 不再无条件生成 `-1` 全平信号。

#### B. `packages/akshare-mcp/src/akshare_mcp/services/backtest/strategy_base.py`

**改造项**
- [ ] 保留 `generate_signals()` 兼容接口。
- [ ] 新增可选细粒度接口，例如：
  - `generate_signal_events()` 或
  - `generate_position_actions()`
- [ ] 默认实现由旧 `generate_signals()` 退化生成简单事件，保证兼容老策略。

**验收标准**
- [ ] 不破坏现有 built-in strategies 的调用。
- [ ] DSL 策略可走事件流，其他策略仍可走旧信号流。

#### C. `packages/akshare-mcp/src/akshare_mcp/services/backtest/engine.py`

**改造项**
- [ ] 引擎优先消费事件流；无事件流时 fallback 到 `generate_signals()`。
- [ ] position state 支持部分减仓。
- [ ] 统计回测结果时保留部分减仓的真实 cashflow 和持仓路径。

**验收标准**
- [ ] 回测交易明细中能看到 partial exit。
- [ ] `gross_qty / avg entry / avg exit / realized pnl` 与部分减仓路径一致。

#### D. 相关测试
- [ ] 为 DSL 策略新增 `loss_bands.reduce` 回测测试。
- [ ] 为孵化 runtime 增加同配置下的行为对照测试。
- [ ] 新增“回测行为 = 孵化行为”的契约测试。

---

## 3. P1 清单：把 reviewer 的 semantic contract 下沉到编译与运行链

### 3.1 目标

把当前 reviewer 已使用的合同从“评审层 metadata”升级成“编译产物 + 运行产物”。

### 3.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/strategy_reviewer.py`

**现状**
- 已经存在 semantic consistency gate，不应重做。

**改造项**
- [ ] 明确 reviewer 只消费编译层稳定产物，不再承担“推断缺失字段”的兜底职责。
- [ ] 将以下字段列为“编译必产物”：
  - `evidence_alignment_audit`
  - `dsl_support_audit`
  - `confidence_contract`
  - `hard_fail_reasons`
- [ ] 对缺失产物的路径给出明确 reject reason，而不是只降分。

**验收标准**
- [ ] 任意 accepted candidate 都具备完整 semantic contract 产物。

#### B. `packages/akshare-mcp/src/akshare_mcp/services/strategy_dsl.py`

**改造项**
- [ ] 在 lowering/compile 过程中显式产出：
  - `claim_to_trade_plan_map`
  - `trade_plan_to_dsl_map`
  - `unsupported_rule_count`
  - `hard_fail_reasons`
  - `evidence_alignment_score`
  - `semantic_integrity_score`
- [ ] 让 `unsupported_rule_count > 0` 与 `hard_fail_reasons` 来自真实编译检查，而不是外层猜测。
- [ ] 对 `trade_plan` 中无法表达的规则直接记录编译失败原因。

**验收标准**
- [ ] reviewer 不再需要从零推测 DSL 是否支持某条 claim。
- [ ] 编译日志能解释“为何 reject / 为何 revise”。

#### C. `packages/akshare-mcp/src/akshare_mcp/services/strategy_spec.py`

**改造项**
- [ ] 明确 `trade_plan`、`runtime_playbook`、`risk_rules`、`holding_horizon` 的来源优先级。
- [ ] 在默认 playbook 生成时保留 `source_claim_ids` / `source_trade_step_ids` 元信息。
- [ ] 对 family 默认值和 research task 显式标注“推导生成”而非“用户原始声明”。

**验收标准**
- [ ] 任意自动生成的 stop/time_stop/reentry 规则都能解释来源。

#### D. strategy-factory 提交链（`packages/strategy-factory`）

**改造项**
- [ ] 提交前统一输出 semantic contract。
- [ ] 保证 candidate evidence 与 claim 映射在 submitter 主路径原生写入。
- [ ] 降低 legacy/dual-write 的分叉判断。

**验收标准**
- [ ] submit 后可直接从 native 表追溯 candidate lineage。

---

## 4. P1 清单：收缩 readiness_score，避免与 stage hard gate 竞争

### 4.1 目标

让 `resolve_incubation_pipeline_stage()` 负责“状态”；让 `_readiness_score()` 只负责“排序/优先级”。

### 4.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py`

**现状问题**
- `_readiness_score()` 仍混入：
  - `observed_days`
  - `trade_days`
  - `promote_streak`
  - `nav`
  - `sharpe_ratio`
  - `forward_sharpe_5d`
  - `max_drawdown`
- 容易让上层误把 score 当成主门。

**改造项**
- [ ] 将 `_readiness_score()` 拆成两层：
  - `hard_gate_result`（直接来自 lifecycle shared）
  - `priority_score`（同 stage 内排序）
- [ ] 降低或移除 `observed_days` 对 score 的直接正向加成。
- [ ] 将 `promote_streak` / `trade_days` 改为辅助排序字段，而非主分值来源。
- [ ] UI / API 输出时明确字段命名，避免误读。

**验收标准**
- [ ] 两个 strategy 在同一 hard stage 下，score 只能表达优先级，不能推翻 stage。
- [ ] `observed_days` 更多但 `recent_skill_lcb` 崩塌的策略不能获得更高实际状态判断。

#### B. `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`

**改造项**
- [ ] 继续保持 `resolve_incubation_pipeline_stage()` 作为唯一状态主门。
- [ ] 如有必要，把阈值常量集中化，便于 BFF/Web 展示和测试共享。

---

## 5. P1 清单：统一 evidence / signal / position 主写路径

### 5.1 目标

把已有表结构真正变成统一主路径，而不是“有 schema，但写入分散”。

### 5.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/incubation.py`

**现状**
- 已存在 runtime playbook 驱动卖出逻辑。
- 已存在 `position seed` 写入。

**改造项**
- [ ] 统一 `signal_id`、`position_id`、`candidate_artifact_id`、`applied_claim_id` 的生成与传递。
- [ ] 在生成 buy/sell signal 时同步写 `strategy_signal_evidence`。
- [ ] 对 runtime playbook 触发的 stop/reduce/freeze 等动作，写出明确 `reason -> claim/trade_step` 映射。
- [ ] `position seed` 与最终 round-trip position 聚合使用同一主键约定。

**验收标准**
- [ ] 从任一 closed position 都能追到 signal 与 evidence。
- [ ] 从任一 signal 都能追到 candidate artifact / claim。

#### B. `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/*strategy_incubation*`

**改造项**
- [ ] 收口 `save_strategy_candidate_evidence` / `save_strategy_signal_evidence` / `save_strategy_trade_positions` 的调用路径。
- [ ] 统一 native 写入入口，减少 legacy mirror 分叉。
- [ ] 完善索引命中最常见查询：
  - strategy + status
  - signal + claim
  - candidate artifact + experiment

**验收标准**
- [ ] 无需跨多套入口兜底才能写全 evidence lineage。

---

## 6. P2 清单：把 execution audit 从“指标存在”升级为“产出稳定可信”

### 6.1 目标

execution audit 不是重新设计指标，而是确保这些指标有稳定、统一、审计级的来源。

### 6.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`

**现状**
- `evaluate_execution_audit_gate()` 已有硬门逻辑。

**改造项**
- [ ] 明确 `audit_summary` 字段的上游来源约定。
- [ ] 区分：
  - `missing`
  - `bootstrap_pending`
  - `insufficient_samples`
  - `failed_metrics`
  对应的 remediation action。
- [ ] 在 `build_incubation_overview()` 中输出更细的 execution diagnostics，供 BFF/Web 使用。

**验收标准**
- [ ] `prediction_weak` 与 `execution_conversion_weak` 在 overview 中可以稳定区分。

#### B. `packages/akshare-mcp/src/akshare_mcp/services/matching_engine.py`
#### C. `packages/akshare-mcp/src/akshare_mcp/services/paper_trading.py`

**改造项**
- [ ] 确认 fill 粒度与 round-trip position 聚合规则一致。
- [ ] partial fill / partial reduce / multi-exit 能正确进入 position 聚合。
- [ ] 对 A 股整手、T+1、费用等约束，保证 execution metrics 的口径一致。

**验收标准**
- [ ] 多次卖出完成一个 round-trip 的情况下，`trade_expectancy` 与 `net_pnl` 计算正确。

#### D. `packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py`

**改造项**
- [ ] 将 execution audit diagnostics 纳入 snapshot summary。
- [ ] 当 `execution_audit_gate_status == failed_metrics` 时，明确优先级高于 readiness_score。

---

## 7. P2 清单：完善 `trade_plan -> runtime_playbook -> dsl` 的可解释映射

### 7.1 目标

让运行时的 stop/take-profit/reentry/reduce 不再只是默认推导，而是可解释地映射回 trade plan / claim。

### 7.2 必改文件

#### A. `packages/akshare-mcp/src/akshare_mcp/services/strategy_spec.py`

**改造项**
- [ ] 在 `_default_runtime_playbook()` 产物中附带：
  - `source_trade_step_ids`
  - `source_claim_ids`
  - `derived_from_defaults`
- [ ] 对 family 推导出的参数打标签，例如：
  - `family_default`
  - `task_default`
  - `claim_aligned`
- [ ] 把 `loss_bands`、`time_stop_days`、`trailing_stop_pct` 的来源暴露给 reviewer / runtime。

**验收标准**
- [ ] Web/BFF 能显示“当前止损规则来自哪里”。

#### B. `packages/akshare-mcp/src/akshare_mcp/services/strategy_reviewer.py`

**改造项**
- [ ] 对“trade plan 中写了，但 runtime_playbook 无来源映射”的情况给出 revise 或 reject。

#### C. BFF / Web

**涉及文件（按当前改动面优先检查）**
- `apps/bff/src/strategy/strategy.service.ts`
- `apps/web/app/strategy-market/[id]/page.tsx`
- `apps/web/app/strategy-market/components/FactoryDashboard.tsx`
- `apps/web/app/strategy-market/components/FactoryReviewPanel.tsx`
- `apps/web/app/strategy-market/components/StrategyDetailOverviewTab.tsx`
- `apps/web/app/strategy-market/hooks/use-strategy-detail-page.ts`
- `apps/web/app/strategy-market/lib/factory-review-view-model.ts`

**改造项**
- [ ] 增加 semantic contract 与 execution audit 的展示字段。
- [ ] 区分：
  - `hard gate`
  - `priority score`
  - `diagnostic only`
- [ ] 可视化输出 claim / trade step / DSL rule / runtime playbook 的映射关系。

**验收标准**
- [ ] 用户在详情页可分清“为什么通过 / 为什么拒绝 / 为什么降级 / 为什么执行差”。

---

## 8. 测试清单

### 8.1 单元测试
- [ ] `dsl_strategy.py`：`reduce` 不再等同全平。
- [ ] `strategy_lifecycle_shared.py`：
  - [ ] `skill_lcb = hit_rate_lcb - null_hit_rate` fallback 正确。
  - [ ] `evaluate_execution_audit_gate()` 在四种状态下输出正确。
- [ ] `strategy_reviewer.py`：
  - [ ] `hard_fail_reasons` 直接 reject。
  - [ ] `proxy_only_event_claim_count > 0` 直接 reject。
  - [ ] `confidence_contract_missing` 只能 revise / reject，不能 accept。

### 8.2 集成测试
- [ ] submit -> review -> compile -> runtime 一条链上，semantic contract 字段保持完整。
- [ ] incubation runtime 卖出时，`signal -> order -> position -> evidence` 能完整回查。
- [ ] partial reduce 的 round-trip position 能正确聚合 execution metrics。

### 8.3 回归测试
- [ ] `apps/bff/test/assistant/strategy-and-search-guardrail.test.ts`
- [ ] `apps/bff/test/assistant/workflow-surface-regressions.test.ts`
- [ ] `apps/web/e2e/helpers/strategy-market-mocks.ts`
- [ ] 新增 strategy market 页面展示断言，确保新字段不会破坏现有 UI。

---

## 9. 分阶段实施顺序

### Phase A：先修执行语义一致性
- [ ] 修复 `reduce` 在 backtest 与 incubation 的不一致。
- [ ] 补事件流接口和 engine 兼容消费逻辑。

### Phase B：再下沉 semantic contract
- [ ] 把 reviewer 使用的合同变成 compile/runtime 稳定产物。
- [ ] 收口 candidate/signal/position/evidence 主写路径。

### Phase C：再收缩 readiness score 语义
- [ ] stage hard gate 与 priority score 明确拆分。

### Phase D：最后补 BFF / Web 展示
- [ ] 把 hard gate / diagnostics / execution audit / semantic lineage 可视化。

---

## 10. 验收总表

### 必须满足
- [ ] `reduce` 在回测与孵化链路语义一致。
- [ ] 任一 accepted candidate 都能提供完整 semantic contract。
- [ ] lifecycle stage 由 shared hard gate 决定，readiness score 不得越权。
- [ ] 任一 closed position 都可回查到 signal、claim、evidence。
- [ ] `prediction_weak` 与 `execution_conversion_weak` 在 API/UI 层可区分。

### 不应再出现
- [ ] reviewer 通过，但 compile/runtime 发生严重语义漂移。
- [ ] 回测显示可部分减仓，runtime 却全平；或反之。
- [ ] 用 `observed_days` 掩盖 `recent_skill_lcb` 崩塌。
- [ ] execution audit gate 已失败，但展示层仍给出“高 readiness”误导。

---

## 11. 建议的首批落地文件（第一批直接动手）

建议先从以下文件开工，收益最大、链路最关键：

1. `packages/akshare-mcp/src/akshare_mcp/services/backtest/dsl_strategy.py`
2. `packages/akshare-mcp/src/akshare_mcp/services/backtest/strategy_base.py`
3. `packages/akshare-mcp/src/akshare_mcp/services/backtest/engine.py`
4. `packages/akshare-mcp/src/akshare_mcp/services/strategy_dsl.py`
5. `packages/akshare-mcp/src/akshare_mcp/services/strategy_spec.py`
6. `packages/akshare-mcp/src/akshare_mcp/services/incubation.py`
7. `packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py`
8. `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`
9. `apps/bff/src/strategy/strategy.service.ts`
10. `apps/web/app/strategy-market/lib/factory-review-view-model.ts`

---

## 12. 备注

本清单刻意避免把已经存在的 schema / gate / reviewer 能力再次当作“待设计模块”。后续实现时，应优先遵循“收口已有能力、修复链路不一致、补齐执行语义”的原则，而不是继续扩散新概念。

# Strategy Factory 高置信度交易决策引擎可执行重构路线图

更新日期：2026-04-12  
适用范围：`packages/strategy-factory`、`packages/akshare-mcp`、`packages/shared-types`、`apps/bff`、`apps/web`

---

## 1. 目的

本文不是对原始方案的复述，而是基于当前仓库真实代码、协议、存储和前端承载后的实施版路线图。

目标只有一个：

- 在不打断现有策略工厂运行、评审、孵化、展示链路的前提下，把系统从“候选完整性优先”升级成“预测质量优先、执行转化可解释、历史防伪持续保留”的高置信度交易决策引擎。

本文默认：

- 原文件 `strategy-factory-高置信度交易决策引擎重构方案.md` 继续保留，作为愿景版方案。
- 本文是实施版，优先级高于愿景版中的抽象结构命名。

---

## 2. 当前代码基线结论

### 2.1 已经存在、可以直接复用的能力

- 孵化主门的底层指标已经存在：
  - `hit_rate` / `hit_rate_lcb` / `null_hit_rate` / `skill_lcb`
  - `recent_skill_lcb`
  - `effective_n`
  - `stability_gap`
  - `forward_ic`
  - `forward_sharpe`
- 当前 `strategy_lifecycle_shared.py` 已经实现：
  - `derive_signal_quality()`
  - `prediction_quality_label`
  - `execution_quality_label`
  - `diagnosis`
  - `build_incubation_overview()`
  - `resolve_incubation_pipeline_stage()`
- 当前 `incubation_pipeline.py` 已经使用 `skill_lcb / recent_skill_lcb / effective_n / stability_gap / open_risk_count` 决定 `warmup / observe / candidate / graduation_ready / failed`。
- 当前 `probability_calibration.py`、`uncertainty_contract.py` 已经能输出：
  - `brier_score`
  - `ece`
  - `prediction_interval`
  - `quality_band`
- 当前 `signal_quality_registry.py` 已实现，但尚未进入策略工厂主链。
- 当前 `evidence_chain.py` 已实现，但它是通用决策证据链，不是策略工厂候选协议的一部分。
- 当前 `paper_orders / paper_trades / paper_nav` 已能支撑执行 proxy 指标。

### 2.2 当前真实短板

- `strategy_reviewer.py` 主要做结构、执行假设、容量、任务对齐审查，不做“证据 -> hypothesis -> trade_plan -> DSL”的严格一致性审计。
- `strategy_dsl.py::tune_strategy_dsl()` 当前的排序目标仍以活动度为主，不以预测边际为主。
- `hypothesis_lowering_compiler.py` 当前要求 `trade_plan / risk_rules / execution_assumptions / portfolio_spec` 等完整，但还没有 `claim/evidence` 映射审计。
- 执行质量当前仍明确是 proxy 模型，不是审计级模型。
- Web/BFF/共享类型当前强依赖：
  - `validation_grade`
  - `strict_incubation_ready`
  - `live_candidate_ready`
  - 以及围绕这些字段的工厂统计面板

### 2.3 本路线图的总判断

- `Phase 1` 可做，但必须是“协议增量扩展”，不能一次性替换旧协议。
- `Phase 2` 可行性最高，属于“已有底座上的收口和升级”。
- `Phase 3` 是最大工程量，必须接受 schema 扩展和执行语义补齐。
- `Phase 4` 必须在兼容旧字段的前提下做展示升级，不能直接切断现有前端统计口径。

---

## 3. 实施原则

### 3.1 不做的事

- 不一次性移除 `validation_grade / strict_incubation_ready / live_candidate_ready`。
- 不在 `confidence_contract` 未稳定、样本不足前把 `ECE/Brier` 变成硬门。
- 不在 Phase 1/2 引入必须依赖新库表才能运行的硬依赖。
- 不把现有 `evidence_chain.py` 直接当成候选协议；只复用其“证据项结构”和“审计思路”。

### 3.2 兼容策略

- 新对象全部采用“新增字段、旧字段保留”的方式接入。
- 候选对象、提交对象、质量报告、孵化概览、工厂汇总都做双轨输出：
  - 新轨：证据链与高置信度质量字段
  - 旧轨：现有展示和统计字段
- 任何 Phase 1/2 的改造都不得要求 Web/BFF 同步上线后系统才能运行。

### 3.3 命名与承载约定

Phase 1 起新增以下四个对象，全部作为可选扩展字段：

- `evidence_chain`
- `prediction_contract`
- `confidence_contract`
- `evidence_alignment_audit`

承载位置统一为：

- 生成阶段：candidate 顶层 payload
- 提交落库后：`params` 中保留副本
- 质量报告中：`quality_gate` 和 `summary` 中放精简版审计摘要

不新建独立 dataclass 的阶段：

- Phase 1 可以先以 dict 协议落地
- Phase 2 以后再考虑升级为 dataclass / pydantic model

---

## 4. 目标架构

### 4.1 候选阶段

候选生成顺序固定为：

1. `evidence_chain`
2. `prediction_contract`
3. `trade_plan`
4. `dsl`

硬规则：

- 没有 `evidence_chain` 时，候选可以继续走旧链路，但必须打 `legacy_semantic_contract=true`
- 一旦提供 `prediction_contract`，则：
  - claim 无证据引用直接 reject
  - trade_plan 节点无 claim 引用直接 reject
  - DSL 节点无 trade_plan 映射直接 reject
  - 存在明确矛盾直接 reject

### 4.2 孵化阶段

保留现有状态名：

- `warmup`
- `observe`
- `candidate`
- `graduation_ready`
- `failed`
- `promoted`

主门优先级固定为：

1. 预测质量
2. 执行转化
3. 风险与历史防伪

### 4.3 展示与统计阶段

旧字段继续输出：

- `validation_grade`
- `raw_validation_grade`
- `effective_validation_grade`
- `strict_incubation_ready`
- `live_candidate_ready`

新字段增量输出：

- `prediction_quality_label`
- `execution_quality_label`
- `quality_diagnosis`
- `signal_quality`
- `execution_quality`
- `confidence_contract_status`
- `evidence_alignment_audit`

---

## 5. Phase 1：证据链合同与一致性审计

### 5.1 本阶段目标

- 让候选对象具备可审计证据链
- 让 `hypothesis -> trade_plan -> DSL` 可校验
- 不修改现有孵化状态机硬门
- 不引入新数据库表

### 5.2 必改模块

- `packages/akshare-mcp/src/akshare_mcp/services/_strategy_llm_provider_prompt.py`
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_hypothesis_generator.py`
- `packages/strategy-factory/src/strategy_factory/application/hypothesis_lowering_compiler.py`
- `packages/strategy-factory/src/strategy_factory/application/candidate_contract.py`
- `packages/strategy-factory/src/strategy_factory/application/quality_gates.py`
- `packages/strategy-factory/src/strategy_factory/application/_submitter_actions.py`

### 5.3 具体实现决策

#### A. Prompt 输出要求

LLM 生成链新增四段输出，顺序固定：

- `evidence_chain`
- `prediction_contract`
- `trade_plan`
- `dsl`

其中：

- `evidence_chain` 中每条 evidence 至少包含：
  - `evidence_id`
  - `source_type`
  - `target_symbols`
  - `direction`
  - `horizon_days`
  - `freshness_ts`
  - `raw_confidence`
  - `proxy_only`
- `prediction_contract` 中每条 claim 至少包含：
  - `claim_id`
  - `thesis_statement`
  - `evidence_ids`
  - `expected_move`
  - `expected_horizon`
  - `failure_condition`
- `trade_plan` 中每个节点至少包含：
  - `claim_ids`
  - `evidence_ids`

#### B. Compiler 审计行为

`hypothesis_lowering_compiler.py` 新增：

- `claim_extraction`
- `evidence_ref_resolution`
- `trade_plan_mapping_check`
- `dsl_mapping_check`
- `contradiction_check`

输出新增：

- `evidence_alignment_audit`
- `semantic_integrity_score`
- `proxy_dependency_score`
- `contradiction_count`
- `unsupported_rule_count`
- `legacy_semantic_contract`

硬失败条件：

- `prediction_contract` 存在但 claim 无 `evidence_ids`
- `trade_plan` 节点无 `claim_ids`
- DSL entry/exit 无法映射回 `trade_plan`
- `contradiction_count > 0`

解释性分数：

- `semantic_integrity_score`
- `proxy_dependency_score`
- `evidence_alignment_score`

这些分数本阶段只做排序与诊断，不做单独硬拒绝。

#### C. 持久化策略

Phase 1 不新建 `strategy_candidate_evidence` 表。

复用现有：

- `save_factory_task_evidence()`

落库方式：

- 将 candidate 中的 `evidence_chain.evidences[]` 展平成多条 `strategy_factory_task_evidence`
- `task_key` 使用现有任务主键
- `evidence_payload` 保存完整 evidence dict
- `event_id / theme_code / symbol` 继续走现有兼容字段

#### D. 提交落库策略

提交时把以下字段写入已存在的 `params`：

- `evidence_chain`
- `prediction_contract`
- `confidence_contract`
- `evidence_alignment_audit`

质量报告中增加精简摘要：

- `evidence_alignment_status`
- `contradiction_count`
- `proxy_dependency_score`
- `legacy_semantic_contract`

### 5.4 本阶段验收

- 提供 `prediction_contract` 的 candidate，若 claim 无证据，提交前直接失败
- 有 `trade_plan` 但无 claim 映射的 candidate，提交前直接失败
- DSL 节点无上游映射的 candidate，提交前直接失败
- 不提供新对象的旧 candidate 仍可运行，但质量报告中必须标记为 legacy

---

## 6. Phase 2：孵化主门升级与质量收口

### 6.1 本阶段目标

- 以现有 `signal_quality` 为中心，统一孵化主门口径
- 保留旧展示字段，新增高置信度质量字段
- 让执行 proxy 正式成为辅助判断
- `ECE/Brier` 仅做诊断，不做硬门

### 6.2 必改模块

- `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`
- `packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py`
- `packages/strategy-factory/src/strategy_factory/application/_budget_feedback.py`
- `packages/strategy-factory/src/strategy_factory/api/dto.py`
- `packages/shared-types/src/strategy.ts`
- `apps/bff/src/strategy/strategy.service.ts`
- `apps/web/app/strategy-market/components/FactoryReviewPanel.tsx`
- `apps/web/app/strategy-market/lib/factory-review-view-model.ts`

### 6.3 具体实现决策

#### A. `build_incubation_overview()` 升级

继续以现有 `derive_signal_quality()` 为底层标准化入口，不重复造轮子。

本阶段新增输出：

- `prediction_quality_label`
- `execution_quality_label`
- `quality_diagnosis`
- `signal_quality`
- `execution_quality`
- `confidence_contract_status`
- `confidence_diagnostics`

其中：

- `confidence_contract_status = missing / insufficient / diagnostic_ready / comparable_ready`
- 判断规则：
  - 缺少 `confidence_contract`：`missing`
  - `support_samples < 50`：`insufficient`
  - `50 <= support_samples < 100`：`diagnostic_ready`
  - `support_samples >= 100` 且合同版本稳定：`comparable_ready`

#### B. 孵化状态机阈值

沿用现有状态名，按如下阈值落地：

- `warmup`
  - `primary_effective_n < 20` 或 `coverage_ratio < 0.25`
- `failed`
  - `recent_primary_skill_lcb < -0.03`
  - 或 `stability_gap > 0.10`
  - 或 `open_risk_count >= 3`
- `graduation_ready`
  - `primary_effective_n >= 60`
  - `secondary_effective_n >= 30`
  - `primary_skill_lcb > 0`
  - `secondary_skill_lcb > 0`
  - `recent_primary_skill_lcb > 0`
  - `coverage_ratio >= 0.75`
  - `stability_gap <= 0.05`
  - `open_risk_count == 0`
- `observe`
  - `primary_skill_lcb <= 0`
  - 或 `coverage_ratio < 0.5`
  - 或 `stability_gap > 0.08`
  - 或 `open_risk_count > 1`
- 其余为 `candidate`

#### C. 执行质量使用方式

本阶段明确承认执行层仍是 proxy。

因此：

- `execution_quality_label = weak` 时可以阻止晋级
- `execution_quality_label = insufficient_evidence` 不能单独判失败
- `nav_conversion_proxy` 只作辅助判断
- 不输出“审计级 execution_conversion_efficiency 已完成”的结论

#### D. 旧字段兼容策略

继续输出并维护：

- `validation_grade`
- `raw_validation_grade`
- `effective_validation_grade`
- `strict_incubation_ready`
- `strict_incubation_blocked`
- `incubation_candidate_ready`
- `live_candidate_ready`

映射规则：

- 旧字段作为产品兼容投影，不再视为唯一真实主门
- 新的 `prediction_quality_label / execution_quality_label / quality_diagnosis` 才是内部主判断

#### E. `signal_quality_registry` 接入方式

本阶段不把 registry 接成单策略硬门，只接成工厂级观测层。

接入位置固定为：

1. 研究侧输出因子质量时，调用 `register_factor()`
2. 情绪/新闻验证产出时，调用 `register_sentiment()`
3. 概率/校准输出产出时，调用 `register_probability()`
4. `factory_scheduler` 或工厂状态汇总中输出 `default_registry.snapshot()`

本阶段不要求把 registry 内容写入策略详情页的单策略硬门，只要求进入工厂 dashboard 或 factory status 的诊断块。

### 6.4 本阶段验收

- 同一策略可同时看到：
  - 旧的 `validation_grade`
  - 新的 `prediction_quality_label / execution_quality_label / quality_diagnosis`
- `prediction_weak` 和 `execution_conversion_weak` 必须可区分
- `ECE/Brier` 在样本不足时只能显示诊断状态，不能直接阻止晋级
- Web/BFF 旧面板不报错

---

## 7. Phase 3：执行质量审计化

### 7.1 本阶段目标

- 从 `paper_orders / paper_trades / paper_nav` proxy 升级到 round-trip 审计
- 让执行质量成为真正硬门
- 让“预测不行”和“执行没转化出来”可被稳定区分

### 7.2 本阶段必须接受的工程现实

只新增聚合表不够，必须同时补齐关联键。

当前问题：

- `signal_tracking` 有 `signal_id`
- `paper_orders / paper_trades` 目前没有稳定的 `signal_id / position_id` 主关联
- 仅靠 `strategy_id + signal_date + source_order_id` 不足以稳定还原 round-trip 语义

### 7.3 schema 设计决策

新增一个新 phase 文件，不修改旧 phase 的语义边界：

- 新建 `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/_schema_market_phase_5.py`
- 在 `schema_market.py` 中显式调用 `init_market_tables_phase_5(conn)`

新增表：

#### A. `strategy_candidate_evidence`

- `candidate_artifact_id`
- `experiment_id`
- `strategy_id`
- `evidence_id`
- `source_type`
- `event_type`
- `target_symbols`
- `direction`
- `horizon_days`
- `raw_confidence`
- `calibrated_confidence`
- `freshness_ts`
- `proxy_only`
- `support_metric`
- `payload`

#### B. `strategy_signal_evidence`

- `signal_id`
- `strategy_id`
- `candidate_artifact_id`
- `experiment_id`
- `evidence_id`
- `applied_claim_id`
- `source_type`
- `direction`
- `horizon_days`
- `signal_ts`
- `payload`

#### C. `strategy_trade_positions`

- `position_id`
- `strategy_id`
- `signal_id`
- `account_id`
- `entry_ts`
- `exit_ts`
- `entry_avg_price`
- `exit_avg_price`
- `gross_qty`
- `gross_return`
- `net_return`
- `gross_pnl`
- `net_pnl`
- `hold_days`
- `exit_reason`
- `mfe`
- `mae`
- `status`

#### D. `strategy_trade_position_fills`

- `position_id`
- `order_id`
- `fill_id`
- `fill_ts`
- `side`
- `qty`
- `price`
- `fee`
- `signal_id`
- `strategy_id`

### 7.4 现有表补列决策

对现有表增量补列：

- `paper_orders`
  - `signal_id`
  - `position_id`
- `paper_trades`
  - `signal_id`
  - `position_id`

用途：

- 下单时把信号和逻辑仓位绑定到订单
- 成交后把订单级成交写回到逻辑仓位

### 7.5 代码改造范围

- `packages/akshare-mcp/src/akshare_mcp/services/incubation.py`
- `packages/akshare-mcp/src/akshare_mcp/services/matching_engine.py`
- `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy_incubation.py`
- `packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`
- `packages/strategy-factory/src/strategy_factory/api/contracts.py`
- `packages/strategy-factory/src/strategy_factory/infrastructure/mcp_adapters.py`

### 7.6 指标启用顺序

先算再上硬门，顺序固定：

1. `realized_win_rate`
2. `avg_win_loss_ratio`
3. `trade_expectancy`
4. `pnl_conversion_efficiency`
5. `execution_conversion_efficiency`

只有满足以下条件后，才允许进入 `candidate / graduation_ready / failed` 的硬门：

- `realized_trade_count >= 20`
- `trade_expectancy > 0`
- `pnl_conversion_efficiency > 0`
- `execution_conversion_efficiency >= 0.20`

### 7.7 本阶段验收

- 每笔 paper trade 都能映射到 `position_id`
- 每个 `position_id` 都能回溯到 `signal_id`
- `strategy_trade_positions` 能稳定输出 round-trip 统计
- `execution_quality.audit_grade = true`

---

## 8. Phase 4：反馈控制与展示升级

### 8.1 本阶段目标

- 把高置信度质量结构接入工厂预算反馈、调度汇总和前端展示
- 但继续兼容旧统计口径

### 8.2 改造决策

#### A. budget feedback 升级为双轴

保留现有 `paper_skill_lcb` 轴，再新增执行轴：

- `paper_skill_lcb`
- `execution_conversion_efficiency`

动作规则：

- 高 skill、低执行转化：
  - 保留 family
  - 降预算
  - 标记执行优化队列
- 低 skill、高收益：
  - 小预算观察
  - 禁止扩张
- 高 skill、高转化：
  - 允许增配
- 低 skill、低转化：
  - 冷却或冻结

#### B. 前端展示

在不删除旧卡片的前提下新增：

- 预测质量卡片
- 执行质量卡片
- 证据链一致性卡片
- 置信度合同诊断卡片

旧卡片保留：

- 验证评级
- 5日命中率
- 孵化信号数
- 现有 strict/live ready 相关指标

#### C. 工厂汇总

工厂层新增聚合：

- `prediction_quality_distribution`
- `execution_quality_distribution`
- `evidence_alignment_distribution`
- `confidence_contract_ready_rate`

不删除现有：

- `validation_grade_distribution`
- `strict_incubation_ready_rate`
- `live_candidate_ready_rate`

---

## 9. 测试与验收清单

### 9.1 Phase 1

- candidate 缺 `trade_plan` 仍按旧逻辑失败
- candidate 有 `prediction_contract` 但 claim 无证据时失败
- candidate 有 `trade_plan` 但 DSL 无映射时失败
- 旧 candidate 不提供新字段时仍能跑通

### 9.2 Phase 2

- `build_incubation_overview()` 同时输出新旧字段
- `resolve_incubation_pipeline_stage()` 在边界值上行为稳定
- `quality_diagnosis` 能区分预测弱和执行弱
- Web/BFF DTO 不因新增字段报错

### 9.3 Phase 3

- 下单到成交全链路保留 `signal_id / position_id`
- 能从 position 还原 round-trip PnL
- 新表建表与旧库升级可重复执行
- 审计级执行指标在样本不足时不进入硬门

### 9.4 Phase 4

- budget feedback 能消费新双轴指标
- 工厂 dashboard 能显示新质量分布
- 旧 dashboard 字段仍存在

---

## 10. 实施顺序

必须按以下顺序推进：

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4

禁止跳过：

- 不允许先做 Phase 3 再回头补 Phase 1 协议
- 不允许先删除旧字段再做前端迁移
- 不允许在未补 `signal_id / position_id` 之前宣称执行质量已审计化

---

## 11. 最终结论

这个重构方向成立，但实施方式必须从“大一统替换”改成“分阶段兼容升级”。

真正可执行的版本应遵循以下判断：

- Phase 1：加合同，不拆旧链
- Phase 2：收口孵化主门，旧展示照常
- Phase 3：补执行语义和 schema，才谈审计级执行
- Phase 4：再把预算反馈和展示切到新质量结构

只有这样，策略工厂才能在当前代码基线上稳定演进为高置信度交易决策引擎。

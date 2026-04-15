# Strategy Factory 高置信度交易决策引擎重构方案

更新日期：2026-04-12
适用范围：`packages/strategy-factory`、`packages/akshare-mcp`、`docs/archive/strategy-factory`

---

## 1. 目标与口径

本方案的目标不是把策略工厂继续优化成“更会产出候选”的系统，而是把它升级为“高置信度交易决策引擎”。

这里的“命中率”统一拆成三层：

1. `预测命中率`
   指策略信号方向与未来收益方向是否一致，即 `signal -> forward return` 的方向预测质量。
2. `执行转化率`
   指已经成立的预测优势，能否通过订单、成交、持仓、退出规则转成真实可实现收益。
3. `历史防伪质量`
   指这套策略是不是只在历史样本里“看起来显著”，但本质上是被回测筛选、参数搜索或数据挖掘挑出来的幸运规则。

本次重构的核心定义如下：

- “100% 预测一致性”不等于承诺未来市场 100% 命中。
- 它的工程定义是：`证据 -> hypothesis -> trade_plan -> DSL -> signal` 必须 100% 可追溯、无逻辑跳跃、无自相矛盾。
- 真正的未来可靠性，则由孵化期的 `signal_skill_lcb + execution conversion` 持续验证。

---

## 2. 现状深度审计

### 2.1 当前真实链路

当前工厂并不是单文件闭环，而是“生成、评审、提交、孵化、晋级”分布式承载：

- 生成主链：`strategy_autonomy.py`
- 结构评审：`strategy_reviewer.py`
- DSL 编译与调优：`strategy_dsl.py`
- 命中率证据链：`signal_tracking.py`
- 孵化质量门：`strategy_lifecycle_shared.py`、`incubation_pipeline.py`
- 情绪/新闻代理验证：`sentiment.py`

当前真实顺序是：

1. 生成候选
2. 委员会评审
3. 记录实验
4. 提交工厂
5. 进入孵化
6. 由 `SignalTracker -> forward returns -> incubation overview` 持续验证

这意味着一个非常关键的事实：

- submit 前只能判断“像不像一个合理策略”
- submit 后才能逐步判断“未来是否真的预测有效”

### 2.2 当前已经具备的资产

当前项目不是“没有命中率能力”，而是“命中率没有成为全链路主门禁”。

已经存在的关键资产有：

- `signal_tracking.py` 已支持：
  - `hit_rate`
  - `hit_rate_lcb`
  - `null_hit_rate`
  - `skill_lcb`
  - `recent_skill_lcb`
  - `effective_n`
  - `stability_gap`
  - `forward_ic`
  - `forward_sharpe`
- `strategy_lifecycle_shared.py` 已支持：
  - `prediction_quality_label`
  - `execution_quality_label`
  - `quality_diagnosis`
  - `promotion_ready`
  - `deprecation_risk`
- `probability_calibration.py` 已支持：
  - `brier_score`
  - `ece`
  - `prediction_interval`
  - `calibration_quality_report`
- `signal_quality_registry.py` 已支持统一登记：
  - 概率质量
  - 情绪信号质量
  - 因子 OOS 质量

也就是说，仓库里已经有足够多的“质量原件”，缺的是统一质量合同。

### 2.3 当前瓶颈

#### 瓶颈 A：生成门主要审结构，不审未来预测力

`strategy_reviewer.py` 当前的 `committee review` 主要看：

- planner
- risk
- feasibility
- execution
- capacity
- task alignment
- novelty

它更擅长拦截“格式差、语义不全、目标池不对齐”的候选，但并不真正验证：

- hypothesis 是否被证据支持
- trade plan 是否忠实表达 hypothesis
- DSL 是否忠实表达 trade plan
- 这套表达在 OOS 上是否仍有方向优势

因此，当前第一道门回答的是：

> 这像不像一个合格策略

而不是：

> 这是不是一个未来更可能预测正确的策略

#### 瓶颈 B：DSL 调优目标仍偏“活跃度”，不是“预测力”

`strategy_dsl.py` 当前的 `tune_strategy_dsl()` 会在多组 DSL 变体中选“更容易触发、更均衡触发、重叠更少”的变体。

这能改善“规则过稀疏”的问题，但也带来偏差：

- 它优化的是可触发性
- 不是预测边际
- 更不是样本外 skill

因此会出现一种典型失真：

- 某个 DSL 触发更频繁，回测看起来更平滑
- 但它可能只是放松了条件，把原本有信息含量的信号稀释掉

#### 瓶颈 C：hypothesis 很完整，但仍偏“文本契约”

`strategy_hypothesis_generator.py` 已经强制要求：

- `alpha_hypothesis`
- `failure_mode`
- `holding_rationale`
- `alpha_half_life`
- `cost_sensitivity_grid`
- `position_model`
- `capacity_assumption`
- `market_regime_assumption`

这是很好的基础，但目前更多是“是否写出来了”，还不是“是否被结构化证据支持了”。

也就是说，系统现在能检查：

- 有没有故事

还不能稳定检查：

- 故事是否由证据推出
- trade plan 是否严格遵守故事
- DSL 是否严格遵守 trade plan

#### 瓶颈 D：情绪与新闻验证还存在代理偏差

`sentiment.py` 当前做了两个重要动作：

- 价量动量历史验证
- 新闻情绪 OOS proxy 验证

但新闻验证现在仍主要依赖价格路径代理：

- 没有稳定持久化“带时间戳的新闻标签 -> 目标股票 -> 后续收益”
- 会把价格路径本身重新当作新闻代理

这会带来自引用偏差：

- 价格涨了，被归类成 bullish bucket
- 然后再证明 bullish bucket 后面更容易涨

这种结构无法支撑“高置信事件驱动策略”的严格门禁。

#### 瓶颈 E：执行层仍是 proxy，而不是审计级交易语义

`strategy_lifecycle_shared.py` 已经把执行质量单独抽成一层，这非常正确。

但当前执行层仍是近似代理：

- `signal_to_fill_ratio`
- `filled_order_ratio`
- `paper_nav_return`
- `nav_conversion_proxy`

它还不能稳定回答：

- 单笔 round-trip 胜率
- 单笔平均盈亏比
- 真实 trade expectancy
- 预测优势转成净利润的效率

因此当前系统会出现：

- 预测是对的，但执行没转出来
- 执行赚到钱了，但其实是少量大运气交易
- 系统只能大概看出来，不足以审计

### 2.4 为什么会出现“回测显著但实战无效”

当前至少存在五类结构性原因：

1. `语义漂移`
   hypothesis 说的是事件、资金、情绪、板块扩散，但 lower 到 DSL 后只剩价格阈值。
2. `代理偏差`
   新闻或情绪证据没有真实事件标签，最后退化成价格自引用。
3. `搜索偏差`
   DSL tuning 与回测筛选更容易选中“会触发、会拟合”的规则。
4. `验证偏差`
   submit 前的回测仍主要承担“防伪门”，还没形成严格的预测力门。
5. `执行缺口`
   就算方向预测为正，也可能被成交失败、仓位不当、退出错误和成本摩擦吃掉。

结论是：

> 当前系统最欠缺的不是统计命中率能力，而是“证据到预测、预测到执行”的统一质量合同。

---

## 3. 多维特征对齐方案

### 3.1 新的核心对象：Evidence Chain

建议在生成阶段显式引入 `evidence_chain`，作为 hypothesis 的上游强约束。

每条证据最少包含：

- `evidence_id`
- `source_type`
- `event_type`
- `target_symbols`
- `direction`
- `horizon_days`
- `freshness_ts`
- `support_metric`
- `contradiction_metric`
- `raw_confidence`
- `proxy_only`

其中 `source_type` 至少支持：

- `kline_pattern`
- `news_event`
- `sentiment_regime`
- `fund_flow`
- `cross_section_context`
- `market_regime`

### 3.2 证据如何与 hypothesis 对齐

新增 `prediction_contract`，每个 hypothesis claim 都必须显式引用证据：

- `claim_id`
- `thesis_statement`
- `evidence_ids`
- `expected_move`
- `expected_horizon`
- `failure_condition`
- `expected_execution_path`

要求：

- 没有 `evidence_ids` 的 claim 不允许进入 trade plan
- 同一 claim 若被多个证据支持，则要记录权重和冲突处理
- 若不同证据方向相反，必须输出 `conflict_resolution_rule`

### 3.3 证据如何与 Trade Plan 对齐

`trade_plan` 不再只是文字说明，而要成为结构化中间层。

建议 `trade_plan` 至少拆成：

- `entry_logic`
- `exit_logic`
- `holding_logic`
- `risk_logic`
- `position_logic`

每个节点都必须引用：

- `claim_ids`
- `evidence_ids`

这样可以保证：

- entry 不是凭空生成
- exit 不是和 hypothesis 无关的默认止盈止损
- holding horizon 真正来自 alpha half-life 与市场结构

### 3.4 证据如何与 DSL 对齐

DSL 编译器输出时新增：

- `evidence_alignment_audit`
- `claim_to_trade_plan_map`
- `trade_plan_to_dsl_map`
- `contradiction_count`
- `unsupported_rule_count`
- `evidence_alignment_score`

其中 `evidence_alignment_score` 只用于表达“映射完整性与证据健康度”的综合分，不直接替代确定性校验。

建议把它拆成可解释子项：

- `claim_coverage_ratio`
- `trade_plan_coverage_ratio`
- `evidence_freshness_score`
- `proxy_dependency_penalty`
- `contradiction_penalty`

门禁规则：

- 任一 DSL entry/exit 节点无法映射回 `claim_id`
  - reject
- 任一 `trade_plan` 规则无上游 `evidence_id`
  - reject
- `contradiction_count > 0`
  - reject

分阶段使用规则：

- Phase 1/2：
  - `evidence_alignment_score` 只作为排序、风险标记和人工复核信号
  - 不作为单独的硬拒绝条件
- Phase 3 以后：
  - 只有在评分公式稳定、分布完成校准后，才允许把 `evidence_alignment_score` 升级为硬门
  - 升级前必须先完成 band 标定，例如：
    - `>= 0.90`：strong_alignment
    - `0.75 ~ 0.90`：acceptable_alignment
    - `< 0.75`：review_required

也就是说：

- `缺映射 / 真矛盾 / 不支持的规则` 是硬失败
- `alignment score` 先是解释性分数，后续才考虑转成硬门

### 3.5 K 线、新闻、情绪、资金流的统一整合方式

#### K 线走势

K 线不再只是 DSL 的原料，而是证据链的一部分：

- 趋势持续
- 波动压缩后扩张
- 假突破过滤
- 结构性回踩

其输出应直接进入：

- `kline_pattern evidence`
- `expected_move`
- `expected_horizon`

#### 新闻舆情

新闻需要从“文本背景”升级成“事件标签证据”：

- 新闻时间戳
- 事件类型
- 目标公司/板块
- 极性
- 置信度
- 事件后 CAR 或 forward return

默认不再允许仅凭“摘要里有利好”就直接进入高置信候选。

#### 情绪价值

情绪应拆成两层：

1. `market sentiment regime`
   用于判断当前适不适合趋势、修复、事件跟随类策略。
2. `target sentiment evidence`
   用于支持个股或主题层面的 direction claim。

若只有市场情绪、没有标的级情绪证据，则只能作为辅助证据，不能单独驱动 entry。

#### 资金流向

资金流需要从“说明性文本”升级成“方向性执行证据”：

- 北向净流入/净流出
- 融资余额变化
- 板块主力资金偏移
- 主题资金扩散持续性

trade plan 中若写了：

- “资金流确认后入场”

则 DSL 必须真的包含对应的结构化条件或上游 gating，而不能只在文案里提一句。

---

## 4. 高质量门禁定义

### 4.1 总体原则

新的门禁顺序必须固定为：

1. `预测门`
   先证明信号真的在未来样本里更容易预测对。
2. `执行门`
   再证明这个预测优势能转成真实收益。
3. `历史防伪门`
   用于抑制数据挖掘和回测过拟合。

换句话说：

- `signal_skill_lcb` 是第一性指标
- `Execution Conversion Efficiency` 是第二性指标
- `Sharpe / MDD / DSR / PBO` 是防伪与解释层

### 4.2 预测门核心指标

保留并提升现有指标：

- `raw_hit_rate`
- `hit_rate_lcb`
- `null_hit_rate`
- `signal_skill_lcb`
- `recent_signal_skill_lcb`
- `effective_n`
- `coverage_ratio`
- `stability_gap`
- `forward_ic`
- `forward_sharpe`

统一解释：

- `hit_rate` 是裸方向正确率
- `hit_rate_lcb` 是保守下界
- `null_hit_rate` 是在方向偏置下的基线命中率
- `signal_skill_lcb = hit_rate_lcb - null_hit_rate`

因此：

- `signal_skill_lcb > 0`
  表示在保守口径下，策略相对基线仍有方向优势
- `signal_skill_lcb <= 0`
  表示方向优势不再显著

### 4.3 执行门核心指标

建议正式引入：

- `execution_conversion_efficiency`
- `realized_win_rate`
- `avg_win_loss_ratio`
- `trade_expectancy`
- `pnl_conversion_efficiency`

定义建议：

- `execution_conversion_efficiency`
  = 真实净收益 / 可归因预测边际
- `trade_expectancy`
  = `win_rate * avg_win - loss_rate * avg_loss`
- `pnl_conversion_efficiency`
  = 实现净 PnL / 信号理论 PnL

当前仓库已有近似代理：

- `signal_to_fill_ratio`
- `filled_order_ratio`
- `nav_conversion_proxy`

这些应在 V1.5 之前继续保留，但只作为临时 proxy，不再充当审计级事实。

### 4.4 概率校准指标与概率合同

策略工厂应显式接入现有校准模块，但前提是先定义统一的概率合同。

新增 `confidence_contract`，最少包含：

- `confidence_contract_version`
- `claim_confidence`
- `entry_confidence`
- `strategy_confidence`
- `confidence_generation_method`
- `support_samples`
- `calibration_method`
- `calibration_band`
- `prediction_interval`

默认语义约束：

- `claim_confidence`
  表示单个 hypothesis claim 在指定 horizon 上成立的经验概率估计
- `entry_confidence`
  表示 trade plan 当前 entry 在给定市场状态下触发后兑现的经验概率
- `strategy_confidence`
  表示候选策略在 primary horizon 上的统一方向性成功概率估计

只有满足以下前提时，跨 family 的 `ECE/Brier` 才允许作为可比较指标：

- `confidence_contract_version` 已稳定
- 概率生成方法固定，不在不同 family 间漂移
- `support_samples` 达到最小样本门槛
- 校准方法与标签定义一致

建议最小样本门槛：

- `support_samples < 50`
  - 不输出硬性的 `ECE/Brier` 结论，只保留 `unknown/insufficient`
- `50 <= support_samples < 100`
  - 输出诊断，但不允许进入状态机硬门
- `support_samples >= 100`
  - 才允许把 `ECE/Brier` 纳入跨策略比较与后续硬门讨论

因此本方案默认：

- Phase 1/2 中，`brier_score / ece / prediction_interval` 先作为诊断与解释字段
- 在概率合同未稳定前，`ece` 不能单独决定 `observe/candidate/graduation_ready/failed`
- 只有在 `confidence_contract` 落地且样本门槛达标后，才考虑把 `ece` 升级为强门禁

原因：

- 方向预测正确率只能告诉我们“经常对不对”
- 校准质量才能告诉我们“说自己 70% 把握时，是不是真有 70%”
- 但如果没有统一概率语义，`ECE` 反而会制造伪精度和跨 family 不可比问题

### 4.5 推荐门禁阈值

#### Phase 2：预测主门 + 执行 proxy 辅助门

Phase 2 的目标是先把“未来方向预测是否成立”变成硬门。

这一阶段：

- `skill_lcb / recent_skill_lcb / effective_n / coverage_ratio / stability_gap` 是硬门
- `execution_quality_label` 仅作为辅助门
- `ece` 仅作为诊断字段，不进入硬门
- 不要求 `execution_conversion_efficiency`，因为审计级执行数据模型尚未完成

#### `observe`

- `primary_effective_n >= 20`
- `signal_skill_lcb > 0`
- `coverage_ratio >= 0.50`
- `stability_gap <= 0.08`
- 若 `confidence_contract` 已存在且 `support_samples >= 50`
  - 记录 `ece` 作为诊断，但不作为 blocker

#### `candidate`

- `primary_effective_n >= 40`
- `secondary_effective_n >= 20`
- `primary_skill_lcb >= 0.01`
- `recent_primary_skill_lcb > 0`
- `coverage_ratio >= 0.60`
- `stability_gap <= 0.06`
- 若已有足够 proxy 执行证据
  - `execution_quality_label != weak`
  - 或至少不连续多个窗口落入 `execution_conversion_weak`

#### `graduation_ready`

- `primary_effective_n >= 60`
- `secondary_effective_n >= 30`
- `primary_skill_lcb >= 0.03`
- `secondary_skill_lcb > 0`
- `recent_primary_skill_lcb >= 0.01`
- `coverage_ratio >= 0.75`
- `stability_gap <= 0.05`
- `open_risk_count = 0`
- 若已有充分 proxy 执行证据
  - `execution_quality_label != weak`
  - `filled_order_ratio` 与 `nav_conversion_proxy` 至少不显示明显失真
- 若概率合同已稳定且 `support_samples >= 100`
  - `ece` 可作为附加晋级条件讨论，但默认不在 Phase 2 强制启用

#### `failed`

- `recent_primary_skill_lcb < -0.03`
- 或 `stability_gap > 0.10`
- 或 `open_risk_count >= 3`
- 或在已有充分 proxy 执行证据的前提下，连续多个窗口落入 `execution_conversion_weak`

#### Phase 3：审计级执行门上线后的最终阈值

当 `strategy_trade_positions` 与 fill/order 映射落地后，再把以下审计级门禁启用到 `candidate/graduation_ready/failed`：

- `execution_conversion_efficiency`
- `realized_win_rate`
- `avg_win_loss_ratio`
- `trade_expectancy`
- `pnl_conversion_efficiency`

推荐启用条件：

- `realized_trade_count >= 20`
- `execution_conversion_efficiency >= 0.20`
- `trade_expectancy > 0`
- `pnl_conversion_efficiency > 0`

只有到这个阶段，执行门才升级为真正的硬门。

---

## 5. 孵化状态机改造

### 5.1 submit 前与 submit 后职责重新划分

submit 前新增强调三类判断，但这些判断是叠加在当前结构性护栏之上的，不是替代现有 gate。

submit 前必须继续保留现有安全门：

- task alignment
- feasibility
- execution assumption completeness
- capacity semantics
- precompile contract checks
- validation profile / quality gate / anti-overfitting checks

在此基础上，submit 前新增重点做三件事：

1. 判断 evidence 是否完整
2. 判断 hypothesis 与 DSL 是否一致
3. 判断历史层是否存在明显防伪失败

submit 前不做的事：

- 不宣称已通过未来命中率验证
- 不用一次回测结果替代真实孵化命中率

submit 后孵化阶段再回答：

- 未来方向预测是否仍成立
- 这种预测优势是否能转成订单与收益

### 5.2 新状态机

- `warmup`
  样本太少，只能收集证据
- `observe`
  样本够，但 skill 还不稳定或仅略为正
- `candidate`
  预测优势已确立，但执行或确认样本还不足以晋级
- `graduation_ready`
  预测、执行、风控三者共同满足晋级门
- `failed`
  近期 skill 崩塌、稳定性断裂或运行风险失控
- `promoted`
  已完成 review 并升级到 listed

---

## 6. 技术改造建议

### 6.1 Prompt Engineering

生成 prompt 必须从“让模型输出完整结构”升级为“让模型输出可审计证据链”。

新增约束：

- 先输出 `evidence_chain`
- 再输出 `prediction_contract`
- 再输出 `trade_plan`
- 最后输出 `dsl`

并明确要求：

- 不允许先写 DSL 再补故事
- 不允许 claim 无证据
- 不允许 trade step 无 claim
- 不允许 DSL rule 无 trade step

### 6.2 Hypothesis Lowering

`hypothesis_lowering_compiler.py` 需要新增：

- `claim extraction`
- `evidence ref resolution`
- `alignment audit`
- `unsupported_claim reject`
- `contradiction reject`

同时给每个 candidate 打出：

- `evidence_alignment_score`
- `semantic_integrity_score`
- `proxy_dependency_score`

### 6.3 DSL 编译与调优

`strategy_dsl.py` 的 tuning 目标从：

- “最近一年至少若干次触发”

调整为：

- “先满足活动度下限”
- “再最大化历史代理 skill + 校准质量”
- “再最小化证据语义漂移”

这样可以防止模型仅为了可触发性而稀释真实预测边际。

### 6.4 孵化指标持久化

建议新增“候选证据层 + 信号落地层 + 交易聚合层”三层模型，而不是只在信号或单笔进出订单层持久化。

#### 表 1：`strategy_candidate_evidence`

字段建议：

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

用途：

- 保存 submit 前候选使用了哪些证据
- 支持对 rejected candidate 做可追溯审计
- 让 experiment 级别就能解释“为什么通过/为什么拒绝”

#### 表 2：`strategy_signal_evidence`

字段建议：

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

用途：

- 把真实运行期 signal 和候选期 evidence lineage 连起来
- 允许同一 evidence 先服务于 candidate，再映射到 realized signal

#### 表 3：`strategy_trade_positions`

字段建议：

- `strategy_id`
- `signal_id`
- `position_id`
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

用途：

- 表示“一个逻辑仓位/一笔完整交易”的聚合结果
- 不假设只有单一 entry order 和单一 exit order

#### 表 4：`strategy_trade_position_fills`

字段建议：

- `position_id`
- `order_id`
- `fill_id`
- `fill_ts`
- `side`
- `qty`
- `price`
- `fee`

用途：

- 支持加仓、减仓、分批止盈止损
- 避免单个 `entry_order_id / exit_order_id` 模型在真实执行路径下失真

这样才能从 proxy 走向审计级执行质量。

### 6.5 预算反馈与控制平面

当前 `paper_skill_lcb` 已经开始进入反馈路径，这是正确方向，应继续保留。

但后续要从“单一预测信号驱动”升级为“双轴驱动”：

- 轴 1：`paper_skill_lcb`
- 轴 2：`execution_conversion_efficiency`

预算控制策略建议：

- 高 `paper_skill_lcb` 低转化
  - 保留 family
  - 降低预算
  - 进入执行优化队列
- 低 `paper_skill_lcb` 高收益
  - 小预算观察
  - 禁止继续大规模扩张
- 高 `paper_skill_lcb` 高转化
  - 优先晋级与增配
- 低 `paper_skill_lcb` 低转化
  - 冷却或冻结

---

## 7. 行业调研结论与落地启示

### 7.1 事件驱动策略的评价重点

事件驱动类研究通常不会只看简单 hit rate，而会同时看：

- 方向准确率
- 超额收益
- 单笔交易收益
- 事件窗口 CAR
- 解释性与事件类型分层表现

参考：

- [Trade the Event: Corporate Events Detection for News-Based Event-Driven Trading](https://arxiv.org/abs/2105.12825)
- [Janus-Q: End-to-End Event-Driven Trading via Hierarchical-Gated Reward Modeling](https://arxiv.org/abs/2602.19919)

对本项目的启示：

- 事件驱动策略必须显式落到 `event_type`
- 需要按事件类别做 OOS 质量统计
- 不能只让新闻作为模糊背景信息

### 7.2 文本信号必须为收益预测专门建模

文本研究的关键经验不是“情绪词典有效”，而是：

- 文本标签必须围绕收益预测目标构建
- 通用 sentiment 并不自动等于 return-predictive sentiment

参考：

- [Predicting Returns With Text Data](https://www.nber.org/papers/w26186)
- [When Sentiment Is News](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3706522)

对本项目的启示：

- `sentiment.py` 不能长期停留在 price proxy
- 必须建设“新闻事件 -> 标的 -> 时间 -> 后验收益”的真实标签链

### 7.3 历史防伪必须上升到 PBO / DSR / CPCV 视角

行业里已经非常清楚：

- 单次 OOS 远远不够
- 多次参数搜索、规则搜索、候选筛选后，回测显著往往会被高估

参考：

- [The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [Deflating the Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2465675)
- [Backtest Overfitting in the Machine Learning Era](https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110)

对本项目的启示：

- `Sharpe` 不能直接代表可靠性
- 工厂需要把 `DSR/PBO/CPCV` 继续保留在 submit 前防伪层
- paper 孵化负责回答未来预测是否还成立

### 7.4 高摩擦交易下必须看校准，而不是只看命中率

在交易摩擦、仓位约束、容量约束存在时，过度自信的预测会导致极差决策。

参考：

- [Utility-Weighted Forecasting and Calibration for Risk-Adjusted Decisions under Trading Frictions](https://arxiv.org/abs/2601.07852)

对本项目的启示：

- `brier_score / ECE / prediction_interval` 应进入策略工厂
- 概率校准质量必须作为高置信候选的门禁之一

---

## 8. 分阶段实施路线

### Phase 1：证据链与对齐审计

目标：

- 把 hypothesis 变成证据驱动对象
- 把 trade plan 和 DSL 纳入同一审计链
- 明确 `confidence_contract` 的 schema，但暂不把 `ece` 设为硬门

交付：

- `evidence_chain`
- `prediction_contract`
- `evidence_alignment_audit`
- `confidence_contract`
- prompt 改造
- lowering compiler 改造

### Phase 2：孵化主门升级

目标：

- 让 `skill_lcb + recent_skill_lcb + effective_n + stability_gap` 成为孵化硬门
- 让 proxy execution label 进入辅助判断
- 让 `ece` 保持诊断字段，等待概率合同稳定后再考虑升级

交付：

- `build_incubation_overview()` 改造
- `incubation_pipeline.py` 阈值重写
- `signal_quality_registry` 接入策略工厂

### Phase 3：执行质量审计化

目标：

- 从 proxy execution 走向 round-trip 审计
- 把审计级执行指标真正接入状态机
- 在概率合同样本门槛达标后，再讨论把 `ece` 升级为硬门

交付：

- `strategy_trade_positions`
- `strategy_trade_position_fills`
- `realized_win_rate`
- `trade_expectancy`
- `execution_conversion_efficiency`

### Phase 4：反馈控制与展示升级

目标：

- 让 family、generator_mode、target_pool 都能看到真实预测与执行质量

交付：

- budget feedback 双轴驱动
- scheduler summary 聚合
- strategy manager/incubation panel 展示新质量结构

---

## 9. 验收标准

### 9.1 生成侧

- 任何 claim 无证据引用，候选直接 reject
- 任何 trade_plan 规则无 claim 映射，候选直接 reject
- 任何 DSL 规则无 trade_plan 映射，候选直接 reject
- `proxy_only=true` 的新闻/情绪证据不能单独支撑高置信事件策略

### 9.2 孵化侧

- 单边上涨市场中，`skill_lcb` 应显著低于裸 `hit_rate`
- `recent_skill_lcb` 退化时，状态机会从 `candidate/graduation_ready` 回落
- `prediction_weak` 与 `execution_conversion_weak` 必须可区分

### 9.3 执行侧

- round-trip 表能稳定产出：
  - `realized_win_rate`
  - `avg_win_loss_ratio`
  - `trade_expectancy`
  - `pnl_conversion_efficiency`

### 9.4 控制面

- 低 `paper_skill_lcb` 的 family 会进入冷却
- 高 `paper_skill_lcb` 但低转化的 family 会被保留但减配
- 高收益但低 skill 的 family 不再继续占据大预算

---

## 10. 结论

本次改造的关键不在于“发明命中率”，而在于完成四件事：

1. 统一质量口径
   把核心质量指标从“候选完整性”提升为“预测质量 + 执行转化 + 历史防伪”。
2. 建立证据链
   让 `evidence -> hypothesis -> trade_plan -> DSL` 成为可审计链条。
3. 提升孵化主门
   让 `signal_skill_lcb` 及其稳定性成为真实主门，而不是附属说明指标。
4. 补齐执行审计
   让系统能区分“预测不行”和“执行没转出来”。

最终目标是：

> 让策略工厂先学会持续预测对，再学会稳定赚到钱，最后才扩大规模。

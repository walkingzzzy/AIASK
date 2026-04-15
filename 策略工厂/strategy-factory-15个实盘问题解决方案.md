# 策略工厂 15 个实盘问题解决方案

审计日期：2026-04-14  
审计基线：当前 `HEAD`  
覆盖范围：`packages/strategy-factory`、`packages/akshare-mcp`、根目录文档 `strategy-factory-高置信度交易决策引擎重构方案.md`

---

## 1. 审计目标

本文不是泛泛讨论“策略思想对不对”，而是回答一个更具体的问题：

为什么策略工厂在中芯国际（688981）这类高波动单股上，仍会生成看似完整、实际上难以落地的趋势策略；以及这些问题在当前代码里是如何产生的，该如何按“高置信度交易决策引擎”方向完成整改。

本文重点围绕以下链路展开：

- 生成：`packages/akshare-mcp/src/akshare_mcp/services/strategy_autonomy.py`
- 生成组件：`packages/akshare-mcp/src/akshare_mcp/services/strategy_autonomy_components.py`
- 模板与提示词：`packages/akshare-mcp/src/akshare_mcp/services/strategy_generators.py`、`packages/akshare-mcp/src/akshare_mcp/services/strategy_stages.py`
- 编译与语义合同：`packages/strategy-factory/src/strategy_factory/application/hypothesis_lowering_compiler.py`、`packages/strategy-factory/src/strategy_factory/application/semantic_contract.py`
- DSL 与执行合同：`packages/akshare-mcp/src/akshare_mcp/services/strategy_dsl.py`、`packages/akshare-mcp/src/akshare_mcp/services/strategy_spec.py`
- 信号与孵化：`packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/signal_tracking.py`、`packages/akshare-mcp/src/akshare_mcp/services/incubation_pipeline.py`、`packages/akshare-mcp/src/akshare_mcp/services/strategy_lifecycle_shared.py`
- 评审与质量面板：`packages/akshare-mcp/src/akshare_mcp/services/strategy_reviewer.py`、`packages/strategy-factory/src/strategy_factory/application/panels.py`
- 回测与执行：`packages/akshare-mcp/src/akshare_mcp/services/backtest/dsl_strategy.py`、`packages/akshare-mcp/src/akshare_mcp/services/backtest/engine.py`、`packages/akshare-mcp/src/akshare_mcp/services/backtest/_engine_support.py`

说明：用户提到的 `packages/strategy-factory/src/strategy_factory/application/research/strategy_autonomy.py` 在当前仓库中不存在。当前真实生成入口位于 `packages/akshare-mcp/src/akshare_mcp/services/strategy_autonomy.py`。

---

## 2. 总体结论

当前策略工厂已经完成了“高置信度重构方案”的一大半基础设施，但尚未完成最后一跳：从“结构化生成系统”进化为“标的级真实执行系统”。

已经具备的能力：

- 语义合同审计已上线，`evidence_chain / prediction_contract / trade_plan / dsl` 已能在编译层做 hard fail。
- 单标的趋势家族已经具备 `compiled_dsl` 路径，`strategy_dsl.py` 已支持 `adx / turnover_rate / upper_shadow_ratio / rolling_count / slope`。
- `signal_tracking.py` 已完整实现 `effective_n / hit_rate_lcb / skill_lcb / recent_skill_lcb / stability_gap`。
- `strategy_lifecycle_shared.py` 已把 `skill_lcb + recent_skill_lcb + effective_n + stability_gap` 提升为孵化硬门。
- `runtime_playbook`、`execution_semantic_mode`、`strategy_signal_event_snapshots_latest`、`execution_audit_gate_status` 等运行时合同与留痕能力已存在。

仍然没有彻底解决的问题：

- 生成层依然是“模板优先”，不是“证据链优先”。
- 很多真实策略仍处在 `builtin_legacy` 或 `missing_executable_contract`，没有稳定进入 `compiled_dsl + measured instrument_profile + native runtime_playbook` 路径。
- `runtime_playbook` 虽然支持波动率自适应，但真实 `instrument_profile` 经常仍是启发式默认值，而不是逐股实测。
- 回测与 runtime 仍主要是日线 bar 级近似执行，成本和成交路径仍偏 proxy。
- reviewer 还没有把 `execution_conversion_efficiency` 前移成第一类提交审计维度。

核心结论：

> 现在的系统已经“开始以命中率为核心”，但还不是“真正以命中率和执行转化双核心驱动”的高置信度交易决策引擎。

---

## 3. 架构级根因

### 3.1 生成语义与执行语义仍未完全统一

当前存在三层语义：

- 生成叙事：`trade_plan / market_regime_assumption / family_specialization`
- 编译合同：`prediction_contract / claim_to_trade_plan_map / trade_plan_to_dsl_map`
- 运行执行：`compiled_dsl` 或 `builtin_legacy`

问题不在于系统完全没有“执行合同”，而在于大量真实候选仍会退回：

- `compiled_dsl`
- `builtin_legacy`
- `missing_executable_contract`

一旦回退到 `builtin_legacy`，复杂的过滤、风控、再入场、波动率适配都会退化成内置家族策略的简化逻辑。

### 3.2 上游仍是模板驱动，不是证据链驱动

`strategy_generators.py` 仍直接内置家族模板，例如：

- `ma_cross` 默认 `short_period / long_period`
- `momentum` 默认 `lookback / threshold`
- `quality_factor / value_factor` 默认量化分位参数

`strategy_stages.py` 的主提示词虽然要求输出可执行 DSL，但仍是“先给 DSL 候选”的思路，而不是方案 6.1 要求的“先 evidence_chain，再 prediction_contract，再 trade_plan，最后 dsl”。

结果就是：  
系统会优先想“给芯片股配个趋势策略”，而不是先问“这只高波动个股的可交易 alpha 证据链到底是什么”。

### 3.3 `instrument_profile` 存在，但很多时候不是真实逐股测量

`strategy_spec.py` 里已经有：

- `_default_instrument_profile()`
- `_trend_runtime_warmup_policy()`
- `_build_single_name_trend_dsl()`
- `_default_runtime_playbook()`

这是正确方向，但 `_default_instrument_profile()` 仍大量依赖：

- 板块桶
- 市值区间
- 启发式默认值

这意味着系统能“猜到科创板高波动”，但不一定真正知道中芯国际最近 60 日的真实 ATR、跳空分布、趋势效率。

### 3.4 命中率硬门已经存在，但执行转化硬门还没前置到 reviewer

`signal_tracking.py` 已经非常接近方案目标，`strategy_lifecycle_shared.py` 也已经把 `effective_n / skill_lcb / recent_skill_lcb / stability_gap` 做成主门。

但 reviewer 侧仍更偏向：

- 合同字段是否齐全
- DSL 是否编译
- slippage / tradability 假设是否存在

而不是：

- 这个策略是否真的能把 signal 转成 fills
- fills 是否真的能转成正向 round-trip expectancy

### 3.5 回测和 runtime 仍是 bar 级近似

虽然 backtest engine 已支持：

- partial reduce
- action source
- implementation shortfall proxy

但执行仍以：

- next bar close 近似成交
- 额外 bps 模拟 arrival / tradability / capacity

为主。这不等于真实地解决了：

- 高开追价
- 跳空穿透止损
- 盘中假跌破
- 高波动股慢止损

---

## 4. 15 个问题逐项审计与整改方案

下面按 15 个问题顺序展开。每项都给出：

- 代码根因
- 为什么当前实现仍不足
- 工程化整改建议

### 4.1 问题 1：MA5 > MA20 是滞后确认，而不是前瞻性证据

#### 代码根因

- `strategy_generators.py` 仍内置 `ma_cross` 家族模板。
- `strategy_stages.py` 的 prompt 仍以 DSL 候选为先，不是 evidence-chain-first。
- `strategy_spec.py` 的趋势 DSL 仍以 `cross_above` 为核心触发器，只是在其上叠加过滤器。

#### 为什么当前实现仍不足

编译器能拒绝“语义不闭环”，但不会拒绝“虽然可执行、但本质上仍是滞后追涨”的策略。  
也就是说，系统已经能保证策略不是胡说八道，但还不能保证它对高波动单股有真实前瞻边际。

#### 整改建议

- 按重构方案 6.1，把生成顺序改成：
  - `evidence_chain`
  - `prediction_contract`
  - `trade_plan`
  - `dsl`
- 为趋势类 claim 增加强约束：
  - 必须解释为什么这个触发条件在该标的上不是纯滞后确认
  - 必须给出 `failure_condition`
  - 必须给出 `expected_execution_path`
- 在 `hypothesis_lowering_compiler.py` 新增 `lagging_entry_without_lead_evidence` 审计项。

### 4.2 问题 2：过滤条件彼此独立，缺少时序协同

#### 代码根因

- 当前 `trade_plan_to_dsl_map` 主要验证映射是否存在。
- semantic contract 主要验证 claim、trade step、dsl section 是否一一对应。
- 但没有检查“这些过滤条件在时间窗口上是否互相打架”。

#### 为什么当前实现仍不足

系统能证明“有量能确认、有长上影过滤、有 anti-chop”，却不能证明“它们组合后仍然有可触发性”。

#### 整改建议

- 在编译阶段增加 `temporal_coherence_audit`：
  - setup 条件有效期
  - trigger 条件确认窗口
  - must_not_occur 条件是否覆盖 trigger 期
- 为 DSL 扩展三类窗口语义：
  - `setup_valid_for_days`
  - `confirm_within_days`
  - `must_not_occur_during_window`

### 4.3 问题 3：固定 1.2x 成交量阈值对中芯国际没有意义

#### 代码根因

- 当前 `strategy_spec.py` 已支持基于 `atr14_pct / gap_p95` 派生 volume/turnover floor。
- 但大量真实候选仍依赖默认 profile，甚至仍使用老模板语义。

#### 为什么当前实现仍不足

“支持个股自适应”不等于“真实策略已经逐股自适应”。  
如果 profile 只是板块桶启发式，那么 688981 和另一只科创板股票的 volume filter 很可能仍差不多。

#### 整改建议

- 新增实测型 `instrument_profile` 字段：
  - `volume_ratio_p80`
  - `volume_ratio_p90`
  - `turnover_rate_p80`
  - `turnover_rate_p90`
  - `volume_zscore_60d`
  - `turnover_zscore_60d`
- 趋势策略的量能确认不再默认固定倍数，改为：
  - percentile mode
  - z-score mode
  - regime-scaled mode

### 4.4 问题 4：“明显震荡”没有量化定义

#### 代码根因

- 生成侧和面板侧仍保留 `avoid_regime` 这类叙事字段。
- `panels.py` 虽然已经要求 `execution_semantic_ready` 才给这些字段加分，但“有叙事但没量化”的内容还可以作为说明性字段存在。

#### 为什么当前实现仍不足

这类语义如果不强制落到 DSL，就会在报告里显得合理，在实盘里完全不可执行。

#### 整改建议

- 新增 `regime_filter_contract`，至少包含：
  - `adx_floor`
  - `trend_efficiency_floor`
  - `cross_count_ceiling`
  - `range_compression_threshold`
  - `volatility_regime_bucket`
- 对“震荡、趋势扩张、量价失配”等模糊词，若没有数值化映射，则：
  - 不给执行加分
  - 不允许进入 `formal_incubation`
  - 不允许进入 `live_ready_review`

### 4.5 问题 5：固定百分比止损与 47% 年化波动错配

#### 代码根因

- `strategy_spec.py` 里的 trend playbook 已支持 ATR-aware 默认值。
- 但很多真实候选没有 measured `instrument_profile`，只能退回默认值或旧 `risk_rules.stop_loss_pct`。

#### 为什么当前实现仍不足

这会导致“看起来用了 ATR”，实际仍在用启发式 stop band。  
对于高波动科创板个股，这和真正按历史 ATR 校准不是一回事。

#### 整改建议

- 建立逐股真实 `instrument_profile` 计算任务，至少写入：
  - `annual_volatility_realized_252d`
  - `atr14_pct_realized`
  - `gap_p95_realized`
  - `intraday_range_p90`
  - `trend_efficiency_60d_realized`
- 对单标的趋势策略，没有 measured profile 就不允许高于 `observe_incubation`。
- 把 stop 公式改成：
  - `initial_stop_loss_pct = f(real_atr14_pct, gap_p95, board_bucket)`
  - `trailing_stop_pct = f(real_atr14_pct)`
  - `shock_exit_pct = f(gap_p95, intraday_range_p90)`

### 4.6 问题 6：多档止损形成慢止损

#### 代码根因

- `dsl_strategy.py` 的 `loss_bands` 逐档触发。
- `engine.py` 的执行是 next-bar 路径。

#### 为什么当前实现仍不足

系统已经能表达 `reduce / exit / freeze_reentry`，但对高波动单股仍更像“慢慢处理亏损”，不是“优先切断失控风险”。

#### 整改建议

- 增加 `shock_exit_policy`：
  - `single_bar_loss_multiple_of_atr`
  - `overnight_gap_stop_pct`
  - `gap_through_stop_behavior`
- 增加 `stop_execution_mode`：
  - `normal_band`
  - `shock_exit`
  - `gap_through_stop`
- 当触发 `shock_exit` 时，允许跳过中间 reduce band，直接 full exit。

### 4.7 问题 7：跌破入场日低点的语义不明确

#### 代码根因

- 当前 DSL 已支持 `open/high/low/close`。
- 但运行时并没有统一“盘中跌破”和“收盘确认跌破”的标准动作语义。

#### 为什么当前实现仍不足

同一句自然语言，在 backtest 可能被理解成 low breach，在 runtime 可能又按 close break 执行，审计会失真。

#### 整改建议

- 运行时持仓新增锚点：
  - `entry_anchor_low`
  - `entry_anchor_close`
  - `entry_anchor_break_mode`
- DSL 新增或规范化：
  - `intraday_break`
  - `close_confirmed_break`
  - `break_and_fail_reclaim`

### 4.8 问题 8：连续下跌时仍依赖均线死叉退出

#### 代码根因

- `strategy_spec.py` 的趋势 exit 虽然加入了 `slope / close<sma / cross_below`，但本质仍以趋势结构衰减为主。
- 缺少独立于均线的“价格损伤型失败出口”。

#### 为什么当前实现仍不足

在快速下跌里，均线仍然太慢。  
这会让趋势策略把 alpha 退出和风险退出混成一个出口。

#### 整改建议

- 将退出拆成三层并行：
  - `signal_failure_exit`
  - `adverse_move_exit`
  - `relative_weakness_exit`
- 引入：
  - `relative_strength_vs_sector`
  - `relative_strength_break_window`
  - `trend_decay_threshold`

### 4.9 问题 9：孵化需要太多信号，单股趋势策略根本凑不齐

#### 代码根因

- 好消息是，`signal_tracking.py` 已完成 `effective_n / skill_lcb / stability_gap`。
- `strategy_lifecycle_shared.py` 已用这些指标做硬门。
- 坏消息是，很多真实旧策略仍带着旧的 `warmup_target_signals=20` 或旧 playbook。

#### 为什么当前实现仍不足

状态机已经换了，但历史策略合同没有全部回填。  
所以实际运行体验仍像“在数信号”，而不是“在积累有效样本”。

#### 整改建议

- 对所有已提交的单标的趋势策略执行重编译回填：
  - `instrument_profile`
  - `runtime_playbook`
  - `execution_semantic_mode`
  - `dsl_compiled`
- 统一把 warmup 主逻辑切到：
  - `effective_n`
  - `coverage_ratio`
  - `recent_skill_lcb`
- 原始 `signal_count` 只保留为观测指标。

### 4.10 问题 10：冷却期过长，错过完整反弹

#### 代码根因

- 当前 `cooldown_days` 主要从 `risk_rules / holding_horizon / playbook defaults` 派生。
- 没有按退出原因分型。

#### 为什么当前实现仍不足

`stop_loss`、`shock_exit`、`time_stop` 不应共用一个冷却期。  
否则会在某些标的上过度错失反弹。

#### 整改建议

- 增加：
  - `cooldown_by_exit_reason`
  - `reclaim_trigger`
  - `retry_budget_after_cooldown`
- 对趋势策略，`reentry_policy` 不再只认“再次金叉”，而支持：
  - reclaim long MA
  - recover relative strength
  - recover volume confirmation

### 4.11 问题 11：命中率低时直接冻结新单，容易锁死账户

#### 代码根因

- `resolve_incubation_action_plan()` 已经比旧版好多了，能区分 `signal_vacuum / prediction_skill_negative / stability_break / execution_conversion_weak`。
- 但 `recent_primary_skill_lcb < 0` 仍可能较早进入冻结路径。

#### 为什么当前实现仍不足

当前动作矩阵更适合“样本已够，质量开始恶化”的情况；  
但对低样本 early-stage 策略仍可能过于激进。

#### 整改建议

- 冻结条件增加样本门：
  - `recent_primary_skill_lcb < 0`
  - 且 `recent_effective_n >= threshold`
- 新增三级节流：
  - `budget_cut_to_25`
  - `paper_shadow_only`
  - `full_freeze`

### 4.12 问题 12：把 max_drawdown 改成 warning 是错误方向

#### 代码根因

- `incubation_pipeline.py` 的 `_readiness_score` 只对 MDD 做弱惩罚。
- `strategy_lifecycle_shared.py` 的 `hard_gate_result` 目前主要由 signal gate 和 execution gate 驱动。
- MDD 仍更多落在 `deprecation_risk`，不是独立 hard gate。

#### 为什么当前实现仍不足

这会产生一种危险错觉：  
“只要 prediction quality 还强，大回撤可以继续 observe。”

#### 整改建议

- 增加 `risk_hard_gate_status`，与 `hard_gate_result` 并列或合并：
  - `warn_threshold`
  - `mandatory_review_threshold`
  - `kill_switch_threshold`
- 当以下任一组合出现时，必须强制 review：
  - MDD 超线
  - `recent_skill_lcb < 0`
  - `stability_gap > threshold`

### 4.13 问题 13：参数之间没有协同验证

#### 代码根因

- reviewer 现在已经会审计 compile-stable 字段、semantic alignment、runtime playbook provenance。
- 但缺少“参数组合级”一致性检查。

#### 为什么当前实现仍不足

一个策略可以：

- 语义上完全闭环
- DSL 可编译
- runtime_playbook 也存在

但参数组合仍可能根本不适合该标的。

#### 整改建议

- 新增 `parameter_coherence_audit`，至少检查：
  - `stop_loss_pct vs atr14_pct`
  - `cooldown_days vs expected_trade_interval`
  - `warmup_target_signals vs expected_annual_signal_count`
  - `volume_filter_threshold vs observed_signal_density`
  - `holding_horizon vs rebalance_interval`
  - `expected_trade_density vs execution_cost`

### 4.14 问题 14：没有定义策略失效边界

#### 代码根因

- 方案里 `prediction_contract` 已要求 `failure_condition`。
- 当前 reviewer 会检查这些合同字段是否存在。
- 但系统还没有把它提升为统一的 `thesis_invalidation_contract`。

#### 为什么当前实现仍不足

所以系统擅长“修参数”，不擅长明确宣布“这条 thesis 已经失效，应停止继续观察”。

#### 整改建议

- 为每条策略统一生成：
  - `thesis_invalidation_contract`
  - `revise_conditions`
  - `terminate_conditions`
  - `keep_observe_conditions`
- 对趋势策略，至少包含：
  - `signal_vacuum_timeout`
  - `recent_skill_negative_streak`
  - `stability_break`
  - `relative_strength_failure`
  - `drawdown_kill_switch`

### 4.15 问题 15：执行成本仍被弱化为 proxy

#### 代码根因

- `engine.py` 已支持 implementation shortfall proxy。
- `_engine_support.py` 会估算 arrival / tradability / capacity penalty。
- 但整体执行路径仍是 bar-level 近似。

#### 为什么当前实现仍不足

这意味着系统已经能估“成本大概多高”，但还不能准确回答：

- 次日高开追价损失了多少
- gap-through-stop 造成了多少额外亏损
- 频繁 reduce/exit 把 edge 吃掉了多少

#### 整改建议

- 回测执行模型升级到至少 `OHLC-aware`：
  - entry 默认 `next_open`
  - stop 支持 `gap_through_stop`
  - trailing stop 支持 `high/low path`
- execution 审计新增：
  - `expected_round_trip_cost_pct`
  - `gap_cost_risk`
  - `execution_cost_to_expected_edge_ratio`

---

## 5. 架构收口建议

### 5.1 用 `hard_gate_result` 重新确立硬门禁地位

当前系统容易出现一种误解：

- 命中率指标是主门
- 风险与回撤是“辅助提醒”

这不够。建议在 `strategy_lifecycle_shared.py` 中统一输出三类 gate：

- `signal_hard_gate_result`
- `execution_hard_gate_result`
- `risk_hard_gate_result`

并让最终 `hard_gate_result` 汇总三者，避免“prediction quality 掩盖真实亏损”。

### 5.2 reviewer 前移执行转化率审计

`execution_conversion_efficiency` 当前主要在 lifecycle/execution audit 中使用。  
建议在 `strategy_reviewer.py` 增加一维正式评审：

- `signal_to_order_conversion`
- `filled_order_ratio`
- `trade_expectancy`
- `execution_conversion_efficiency`

这样可以在 submit 前就识别“理论上能赚钱，但根本执行不出来”的候选。

### 5.3 统一 backtest 与 incubation 的动作语义

必须确保以下动作在 backtest/runtime/incubation/audit 中语义一致：

- `enter`
- `reduce`
- `exit`
- `freeze_reentry`
- `time_stop`
- `shock_exit`

同时所有动作都要能回查来源：

- `dsl_entry`
- `dsl_exit`
- `runtime_playbook_stop`
- `runtime_playbook_reduce`
- `builtin_legacy_signal`

### 5.4 对 legacy 候选做强制回填

对所有已 submitted 的单标的趋势策略执行“重编译回填”：

- `params.dsl`
- `runtime_playbook`
- `instrument_profile`
- `execution_semantic_mode`
- `dsl_compiled`
- `claim_to_trade_plan_map`
- `trade_plan_to_dsl_map`

不能确定性生成的，保留在 `observe_incubation`，并显式标记：

- `execution_semantic_gap=true`
- `revision_required=true`

---

## 6. 推荐实施顺序

### P0：先堵生成与执行脱节

1. prompt 改成 evidence-chain-first
2. 单标的趋势策略默认 DSL-first，禁止静默退回 builtin
3. 未测量 `instrument_profile` 的趋势策略，不得高于 `observe_incubation`

### P1：再补标的适配

1. 建立真实 `instrument_profile` 计算与回填任务
2. 趋势入场改成 `setup -> trigger -> execution`
3. 止损改成 ATR/gap-aware
4. 增加 `parameter_coherence_audit`

### P2：再补孵化与失效边界

1. warmup 以 `effective_n` 为主，不再以 raw signal count 为主
2. 冻结改成分层节流
3. drawdown 升级为正式 risk hard gate
4. 建立 `thesis_invalidation_contract`

### P3：最后补真实执行审计

1. execution reviewer 前移
2. OHLC-aware 执行路径
3. round-trip execution cost attribution

---

## 7. 验收标准

整改完成后，至少应满足以下条件：

- 单标的趋势新策略默认进入 `compiled_dsl`，不再大面积 `builtin_legacy`
- `instrument_profile` 以真实市场数据计算为主，启发式默认仅作兜底
- `trade_plan / prediction_contract / dsl / runtime_playbook` 能一跳回查
- `warmup` 主门以 `effective_n / skill_lcb / stability_gap / coverage_ratio` 为核心
- `max_drawdown` 不再只是 warning，而是正式 risk hard gate 的一部分
- `execution_conversion_efficiency` 进入 reviewer 或 submit gate，而不是只留在后置诊断
- backtest 与 runtime 对 `reduce / exit / freeze_reentry / stop` 的动作来源和语义保持一致

---

## 8. 最终判断

当前策略工厂的问题，不是“完全没做命中率化”，而是“命中率主门已经做了，执行真实性和标的适配性还没完全跟上”。

中芯国际这 15 个问题之所以会集中暴露，根本原因不是某个 `ma_cross` 参数错了，而是以下四件事还没有同时完成：

- 生成必须 evidence-chain-first
- 单标的趋势必须 DSL-first
- `instrument_profile` 必须 measured-first
- reviewer 和 hard gate 必须把风险与执行转化前移

如果这四件事不同时完成，系统就仍会反复生成“看起来像高置信度、实际上仍偏模板化”的策略。

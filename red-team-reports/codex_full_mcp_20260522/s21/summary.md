# S21 · AI 工作流 / 高确定性诊断 / 因子候选 / 数据质量 / 治理工件

- **判定**: ✅ 通过 (33/31 工具,Pass=14 / Degraded=11 / Fail-graceful=8 / Fail=0)
- **耗时**: 17:10:33 → 17:11:32 (约 59 秒)
- **覆盖**: governance_check / data_quality_workflow / get_tool_contract / prediction_diagnosis / get_available_categories / available_tools / experiment_tracker(log_run+list_runs) / analyze_stock_product_workflow / analyze_stock_workflow / factor_candidate_workflow / strategy_review_workflow / get_ipo_info / fuse_decision_payload / get_unified_decision_summary(000651) / search_stocks / list_factors / get_factor_library / get_stock_capital / build_stock_context / get_signal_hit_rate / get_unified_decision_details / build_quant_context / list_industry_templates / run_decision_gate / build_event_context / validate_factor_oos / find_similar_patterns / data_validation / factor_robustness_check / log_recommendation_audit / get_conditional_returns / ai_workflow_artifact

## 🔥 7 条 high finding

### 1. prediction_diagnosis_workflow sklearn + mapie 双重降级(S21-F01)

```
method: platt
sklearn_calibrated_classifier_cv → builtin_lightweight  (ValueError)
mapie_conformal_prediction → builtin_conformal_proxy    (ValueError)
sample_size: 5 (太小)
ECE: 0.397  quality_band: poor
output: 仍输出 platt_a/platt_b 校准建议
```

**外部 sklearn + mapie 库双跪 → 内置降级**;5 样本 + ECE 0.397(poor)却照常输出。

### 2. prediction_diagnosis quality=poor 仍输出建议(S21-F02)

```
ECE=0.397  Brier=0.21  log_loss=0.65
sample_size: 5  effective_n: <30 (推荐阈值)
quality_band: poor
但 platt 校准 a/b 仍输出
coverage_target=0.9 但 PI 宽 ±0.42
```

**系统在 quality=poor 时不阻断输出** — AI 决策可能被低质量校准误导。

### 3. governance online_offline:inconsistent 第 3 次复现(S21-F03)

```
strategy_review_workflow.factory_status:
  backtest_assumption.slippage_bps: 0
  execution_assumption.slippage_bps: 5     ← 不一致
  → online_offline:inconsistent (high severity)
  
recent_runs(5): 全 proceed readiness=0.7-0.84 但 submitted=0/0/0/0/0
quality_baseline.submitted_strategy_cohort:
  factory_strategy_count: 143
  zero_signal_rate: 100%       ← S19-F12 复现
  raw_validation_d_rate: 99.3%
  promotion_ready_rate: 0.0
```

**累计 3 次 governance inconsistent + 143 strategies 100% zero_signal**(同 S19-F12)。

### 4. factor_candidate_workflow partial_failed(S21-F04)

```
7 step pipeline:
  llm_factor_mining: ✅ (3 candidates, fallback_reason=workflow_fast_mode_prefer_local_fallback)
  validate_factor_candidate: ❌ (artifact not found: factor_llm_xxx, persist_artifact=false)
  factor_candidate_registry: ✅ (1 excluded, multiple_testing_risk_high)
  factor_candidate_registry.list: ✅ (count=0)
  factor_candidate_registry.get: ❌ (artifact not found, 矛盾上一步)
  factor_research_memory.stats: ✅ (1 record, review status)
  scheduler_status: ✅ (running=false universe=165)

fallback chain: openai_compatible(gpt-5.5) → local_rule_v1
generation_mode: local_rule_fallback
provider_enabled: true (但被 fast_mode 强制本地)
```

**7 步流水线中 2 步失败**(validate + get) — 主因 dry_run/persist_artifact=false 导致工件不持久化但下游仍尝试拉取;且 list 返回 0 vs registry summary 1 矛盾。

### 5. strategy_review_workflow 3/5 partial_failed(S21-F05)

```
strategy_id: codex_full_mcp_20260522_s21_review (不存在)
5 step:
  resource.strategy_review: ❌ (strategy not found)
  strategy_manager.closure_review: ❌ (STRATEGY_MANAGER_NOT_FOUND)
  strategy_manager.review_report: ✅ (reports=[])
  strategy_manager.factory_status: ✅ (last_run=success readiness=0.7)
  strategy_manager.runtime_alerts: ✅ (count=0)

但即使在 strategy_id 不存在的情况下,factory_status 仍返回完整 last_persisted_run + 143 strategies + capability_health 全绿(虽然 zero_signal=100%)
```

**strategy_id 不存在 → 2 步 NOT_FOUND 但 workflow 仍返回 success**;运行时 alerts=0 但 quality_baseline 显示 zero_signal_rate=100%。

### 6. validate_factor_oos n=3 全 0 但 DSR Sharpe=2.28(S21-F06)

```
factor: momentum
codes: [600519, 000858, 002304]  (3 < 10 推荐阈值)
panel_periods: 90  forward_period: 10
walk_forward.n_folds: 0  oos_ic_mean: 0.0  stability_ratio: 0.0
purged_kfold.n_folds: 0  oos_ic_mean: 0.0
bootstrap_ci: ic_mean=0 ci_lower=0 ci_upper=0 sample_size=0

但 multiple_testing.deflated_sharpe:
  observed_sharpe: 2.28        ← 高 Sharpe!
  z_score: 11.73
  dsr: 1.0
  psr: 1.0
  
rating.grade: D  total_score: 0.0  recommendation: "Weak"
```

**矛盾输出**:Sharpe 2.28 / DSR 1.0 显示极强,但 grade=D total_score=0(因 OOS IC=0);不一致。

### 7. factor_robustness_check 极端 IC 倒挂(S21-F07)

```
factor: momentum
windows=[10, 20, 60]:
  10d IC=-0.999 rank_ic=-1.0 p=0.000  significant=true   ← 完全负相关
  20d IC=+0.812 rank_ic=+0.5 p=0.667  significant=false
  60d IC=+0.046 rank_ic=+0.5 p=0.667  significant=false
stability: 0.0

param_sensitivity (10/20/40/60): 同样翻转
subsample_consistency: 0.0 (insufficient codes for split)
robustness_score: 0.0  grade: weak
```

**短窗 IC=-0.999 vs 中窗 IC=+0.81 vs 长窗 IC=+0.05** — 因子在不同时间尺度方向完全相反;n=3 样本量本身就有问题但仍输出。

## 🟡 4 条 medium finding

### S21-F08:factor_decay + model_drift 5 维全 unknown

```
governance_check.factor_decay:
  status: unknown
  reason: insufficient_history (0 evaluation_count)

model_drift:
  brier: unknown
  ece: unknown  
  rank_ic: unknown
  stability: unknown
  total: unknown
```

### S21-F09:experiment_tracker 状态卡死

```
backend_requested: mlflow → builtin_fallback (mlflow_not_installed)
run-8d6bc23eab81 status: "running"
started_at: 09:10:33  completed_at: null
```

### S21-F10:signal_hit_rate 9 样本 reliable=false 但全输出

```
sample_count: 9  reliability_warning: "样本量不足（9 < 10）"
5d hit=0.75 (4 sample)   reliable=false
10d hit=1.00 (3 sample)  reliable=false
20d hit=1.00 (3 sample)  reliable=false
```

### S21-F11:find_similar_patterns 短长期倒挂

```
top5 (window=15d):
  5d  avg=-0.0052 hit=0.4
  10d avg=-0.0129 hit=0.4   ← 短期负
  20d avg=+0.0002 hit=0.8   ← 长期正(倒挂)
```

## ✅ 4 positive

### S21-F12:data_validation GE backend 累计 14 场景 70/70 stable

```
validation_id: val-b4f48e7cdd29  
backend: great_expectations_runtime
3/3 expectations passed
quality_score: 1.0
suite_name: runtime_suite_e4c28f7140ba
```

### S21-F13:get_tool_contract analyze_stock_workflow 完整契约

```
input_schema: 完整(code/include_decision/include_financials/include_kline/investment_style/kline_limit)
output_schema: 多 step 嵌套
side_effect: read_only / idempotent=true / confirmation_policy=none
freshness: data_timestamp_field 标注
examples: 2 个 (basic + with_decision)
```

### S21-F14:analyze_stock_product_workflow deep_analysis 8 step 全过 + 工件回查

```
8 stages × 8 success:
  target_resolution → data_assembly → evidence_normalization →
  integrity_gate (recoverable, gap=0) → agent_review (pass) →
  synthesis (8 sections) → final_check (passed) → report_render (HTML+manifest)

artifact_ids: 7 子工件
ai_workflow_artifact("codex_full_mcp_20260522_s21_product"):
  返回 完整 payload 含 standalone_html + manifest + 20 evidence
```

### S21-F15:available_tools(161) + categories(33) 锚点

```
available_tools.count: 161 ✓ (基线匹配)
get_available_categories.count: 33 ✓ (基线匹配)
trace_id: available_tools:list:1779613833xxx
```

## 🔬 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s21_product` | analyze_stock_product_workflow run | 8 step deep_analysis 完成 |
| `codex_full_mcp_20260522_s21_review` | strategy_review_workflow id | 不存在但 factory_status 仍返回 |
| `factor_llm_1779613838_c0b4e1f6` | factor_candidate artifact | persist=false 不可回查 |
| `val-b4f48e7cdd29` | data_validation GE | 3/3 passed |
| `run-8d6bc23eab81` | experiment_tracker run | 卡在 running |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **21/22**
- 累计 Fail: **0**
- 累计推荐 bug: **244 条**(S02-S20 累计 229 + S21 新增 15,其中 high 累计 **111 条**)

## 关键观察:S21 验证了"AI 工作流 + 自动化诊断层完整性参差"

**核心问题**:

1. **prediction_diagnosis 双重降级**(F01/F02):sklearn + mapie 全跪 → builtin;quality=poor 仍输出建议
2. **governance online_offline 第 3 次复现**(F03):S19/S21 重复出现 backtest slippage 0 vs execution 5bps
3. **factor_candidate_workflow 7 步 partial_failed**(F04):persist_artifact=false 但下游强制拉取 → 矛盾 NOT_FOUND
4. **strategy_review NOT_FOUND 仍返回 success**(F05):factory_status zero_signal_rate=100% 全跪
5. **validate_factor_oos Sharpe vs Grade 矛盾**(F06):Sharpe=2.28 / DSR=1.0 / Grade=D / Score=0
6. **factor_robustness IC 极端倒挂**(F07):10d=-0.999 vs 20d=+0.81 vs 60d=+0.05

**positive 证据**:
- data_validation GE backend 累计 14 场景 70/70 stable(F12)
- get_tool_contract input_schema + examples 完整(F13)
- analyze_stock_product_workflow 8 step deep_analysis 全 pass + HTML 报告(F14)
- available_tools 161 + categories 33 锚点持续验证(F15)

**累计 21/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计 bug 244(其中 high 111),22 场景红队复测剩 1 场景(S22 收尾)。

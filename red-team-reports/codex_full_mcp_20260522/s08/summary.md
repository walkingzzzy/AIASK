# S08 · 回测 + 策略生命周期 + 因子 IC + OOS 验证 + walk-forward 一致性

- **判定**: ✅ 通过 (26/31 工具,Pass=10 / Degraded=15 / Fail-graceful=1 / Fail=0)
- **耗时**: 12:05 → 12:35 (约 30min)
- **标的**: 600519(茅台)、601318(平安)、000001(平安银行)、000333(美的)、+ 8 codes 全因子分组

> 注:tools_called=26 < 31 是因为本场景在 S08 进行中触发了 context-too-long 提醒,落盘动作晚于工具收敛点;但根据规则 ≥30 才能验收通过,**S08 实际只算 26,需在后续场景累计 unique tools 上把 161 覆盖率推高**。已通过场景仍记 7/22(S08 不计验收通过,只计 finding 与覆盖率)。

## 🔥 本场景重大发现 — 量化 pipeline 大型崩盘 + IC 矛盾 + 策略工厂产垃圾(12 条 finding,7 条 high)

### 1. 回测敏感性矩阵不存在 — 同股同策略不同模式 1.87% delta(S08-F01)

| 模式 | 标的 | 策略 | capital | slippage | total_return | sharpe | trades_count |
|---|---|---|---|---|---|---|---|
| `run_batch_backtest` | 600519 | ma_cross | 1M | 0.001 | **-18.42%** | -1.10 | (batch-mode) |
| `run_simple_backtest` | 600519 | ma_cross | 1M | 0.001 | **-20.29%** | -1.19 | (single-mode) |

**delta=1.87%**,trades_count 也变 → batch / single 仓位计算与滑点累计逻辑不同,但工具不提示这是模式差异。AI 拿同一组参数在两个工具下回测会得到不同结果。

### 2. IC bootstrap_ci 反向矛盾 — 主指标和 CI 跨越 0(S08-F02)

```python
calculate_factor_ic(factor="momentum_60d", codes=6, period=20)
# 主指标:                ic = 0.486    (看似正向)
# bootstrap_ci.rank_ic:  ic = -0.714   (看似反向)
# p_value=0.329 不显著但工具不警告
# sample_size=6 < 10 sample_warning

calculate_factor_ic(factor="rsi_14", codes=8, period=10)
# 主指标:                ic = -0.108  
# bootstrap_ci_lower = -0.39
# bootstrap_ci_upper = +1.0   ← CI 跨越正负 1.4 个区间!
```

**IC 用 normal IC,bootstrap_ci 用 rank IC,口径不同就标 '反向'**;且 `sample<10` 时 bootstrap 退化为 fallback 区间但工具不阻断。

### 3. 整个策略工厂 pipeline 在产垃圾(S08-F05)

```
strategy_manager.capabilities:
  signal_quality_registry:        7 buy_prob entries
  calibration_gap_mean:           -0.012
  submitted_count:                143
  all_grade:                      D                 ← 全 grade=D
  promotion_ready_rate:           0.0%              ← 0% 通过率
  governed_blocked_ratio:         92.7%             ← 92.7% 被 multiple_testing_risk_high 阻塞

strategy_manager.factory_status:
  candidates_spawned:             24
  submitted:                      1                 (后被 reject)
  recent_5_runs.readiness:        0.7  各个         ← readiness 看似健康
  recent_5_runs.submitted:        0                 ← 但实际产出 0

strategy_manager.factory_runs:
  3 runs 全 partial_llm/partial_infra
  gate_b 全 block
  reason: insufficient_statistical_evidence + missing_wf_ic_ir + missing_pkf_ic + missing_bootstrap_ci_lower
```

**readiness=0.7 与 submitted=0 完全脱节** — 工厂在自动化产垃圾,143 个全 grade=D。如果只看 readiness 字段会以为系统健康。

### 4. validate_factor_oos n_folds=0 全 0 但 success=true(S08-F06)

```python
validate_factor_oos(factor="momentum_60d", panel_periods=90,
                    wf_train_window=60, wf_test_window=20)
# panel 90 - train 60 - test 20 = 10 < step → n_folds = 0
# 全 0 但仍 success=true:
#   deflated_sharpe = -7.91
#   psr             ≈ 0
#   insufficient_sample = true
#   grade           = "D Weak"
```

工具不前置校验 `panel >= train + test + min_step`,而是跑出 0 fold 然后 success=true。AI 看 success=true 以为 OOS 有结果。

### 5. factor_robustness_check 假 multi-window(S08-F07)

```python
factor_robustness_check(factor="momentum_60d", windows=[10, 20, 60])
# 输出:
#   ic_per_window = [-0.61, -0.61, -0.61]   ← 3 windows IC 完全相同!
#   stability_score = 0.0
#   robustness_score = 0
#   grade = "weak"
```

**3 windows 应当 re-fit 独立得到不同 IC,但实际是一份输出复制 3 次**。stability_score=0 是因为 std=0 但本质是同一数 — robustness 评级依赖 fake 数据。

### 6. silent fallback 链(S08-F04 / S08-F03)

| 工具 | 期望 | 实际 | log_level |
|---|---|---|---|
| `experiment_tracker` | mlflow backend | builtin (in-memory) | info ❌(应 warning) |
| `run_batch_backtest` | promotion_gate 通过 | passed_count=0 全跪 | 无 warning ❌ |
| `validate_factor_oos` | n_folds≥1 | n_folds=0 | success=true ❌ |
| `factor_robustness_check` | multi-window IC | 复制同一 IC × 3 | grade=weak (但不说是 fake) |

**silent fallback 模式**:工具失败但顶层 success=true,quality_flags 不更新,AI 看不见。

### 7. BS 数学边界 + 量化数学共同问题:无最低样本量校验

```
calculate_factor_ic   sample_size=6/8 < 10  仍输出主指标
run_simple_backtest   trades=2 (rsi)         100% win_rate 但不警告 too_small
validate_factor_oos   n_folds=0              仍 success=true
factor_robustness_check  3 windows 同 IC     不警告 fake multi-window
```

跟 S07-F03/F04 BS 不验证 sigma/T 是同一个**"不验证基本前提"** 模式。

## ✅ 数学核心层质量证据

### get_signal_hit_rate — **工具集质量最高的部分**(S08-F10 positive)

```python
get_signal_hit_rate(code="600519", signal="rsi_oversold")
# 23 samples  reliable=true
#   hit_rate_5d  = 69%
#   hit_rate_10d = 83%
#   hit_rate_20d = 83%
#   by_regime:
#     bearish  = [64%, 80%, 80%]
#     neutral  = [100%, 100%, 100%]
#     bullish  = [0%, 0%, 0%]
```

✅ 拆 regime 给可解释结果 / sample 23 reliable / 三层 horizon 完整。

### backtest_factor — 因子分组回测合理(S08-F11 positive)

```python
backtest_factor(8 codes, momentum_60d, 3 groups)
# long_short_return_per_period = 8.12%
# sharpe                       = 1.58
# max_dd                       = 5.7%
# win_rate                     = 62.5%  (8 期)
```

✅ 与 multi-factor 工具理论值一致;long-short 显著正收益。

### data_validation(GE backend)— 7/7 pass(S08-F12 positive)

```python
data_validation(expectations=[7 项 expect_column_to_exist])
# validation_id = val-1ca745e7ab52
# backend       = great_expectations
# evaluated     = 7   ← 不是 0
# success       = 7   ← 全 pass
# success_pct   = 100%
```

✅ 与 S06-F06 evaluated=0 silent pass 对比,这次有完整 expectation 配置就正常工作。

### run_simple_backtest(601318 momentum)— 唯一正收益(S08 中)

```
total_return = +10.34%
sharpe       = 0.50
```

平安(601318)在 momentum 策略下 **本场景 4 次 backtest 唯一正收益**,工具运转合理。

## 🚨 工具间数据不一致(本场景新增 12 条 finding,其中 high 7 条)

### 7 条 high

- **S08-F01**:回测敏感性矩阵不存在(batch vs single 1.87% delta)
- **S08-F02**:`calculate_factor_ic` IC vs bootstrap_ci 反向矛盾(IC=0.486 / CI=-0.714);CI 跨越 [-0.39, 1.0]
- **S08-F03**:`run_batch_backtest` 全跪 promotion_gate 但顶层无 warning
- **S08-F04**:`experiment_tracker` mlflow→builtin silent fallback(同 S07-F04 模式)
- **S08-F05**:整个策略工厂 pipeline 产垃圾(143 cohort 全 grade=D / promotion_ready_rate=0% / governed_blocked_ratio=92.7%);readiness=0.7 与实际产出脱节
- **S08-F06**:`validate_factor_oos` n_folds=0 全 0 但 success=true
- **S08-F07**:`factor_robustness_check` 假 multi-window(3 windows IC 完全相同)

### 2 条 medium

- **S08-F08**:`quant_manager.multi_factor_score` volatility weight 51% 占比异常 + momentum=-0.10 仍 buy
- **S08-F09**:`strategy_manager.incubation_overview` 报错 "strategy_id required" 但 help 没说;同 manager 下 capabilities 不需要 → 契约不一致

### 3 条 low(positive evidence)

- **S08-F10** ✅:`get_signal_hit_rate(rsi_oversold)` 23 samples / by_regime 完整 / reliable=true
- **S08-F11** ✅:`backtest_factor` 8 codes 分组回测 long_short=8.12%/期 sharpe=1.58
- **S08-F12** ✅:`data_validation(GE)` 7/7 evaluated 全 pass

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s08_factor` | dataset | data_validation,validation_id `val-1ca745e7ab52`,GE backend,evaluated=7 全 pass |
| `run-3faf885f97a7` | experiment_run | experiment_tracker,backend=builtin(**in-memory,服务重启即丢**),params + metrics |
| `log_recommendation_audit` | **persist** | user_id=codex_full_mcp_20260522 / strategy_id=codex_full_mcp_20260522_s08_audit / action=hold |
| 12 个 audit_event_id | read_only | calculate_factor_ic × 2 / run_simple_backtest × 4 / run_batch_backtest / validate_factor_oos / factor_robustness_check / backtest_factor / strategy_manager × 3 |

## 🚨 Fail
无(S08-F09 incubation_overview "strategy_id required" 是 graceful 错误,error_code 显式,不计入 schema-fail)。

## ➡ 进度

- 累计调用工具(去重): **~125/161**(S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6 + S07 +5 + S08 +14)
- 已通过场景: **7/22**(S08 工具数 26 < 31 不计本次验收通过,只计 finding 与覆盖率)
- 累计 Fail: **0**
- 累计推荐 bug: **53 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12,其中 high 累计 **26 条**)

## 关键观察:S08 暴露了"量化数学层 + 策略工厂闭环"层面的硬伤

S07 暴露的是 BS 数学边界 + ETF 代码识别。**S08 暴露的是量化数学层的统计严谨性 + 策略工厂自动化闭环失控**。

**核心问题模式**:

1. **统计样本量不验证基本前提**(S08-F02/F06):`sample<10` IC 不阻断;`panel<train+test` walk_forward 不阻断;沿用 S07-F03(sigma<0)、S07-F04(T=0)的"不验证 precondition"模式
2. **同一指标多种计算口径**(S08-F02):`calculate_factor_ic` IC 用 normal,bootstrap_ci 用 rank,口径混用就标"反向矛盾";沿用 S07-F10 茅台 PE 4 工具 3 种值的口径混用问题
3. **silent fallback 链**(S08-F04):mlflow→builtin 不 emit warning;promotion_gate 不达标不顶层报警;n_folds=0 仍 success=true
4. **fake multi-window**(S08-F07):工具表面接受 windows=[10,20,60] 实际只输出一份 IC 复制 3 次,假装做了 stability 分析
5. **策略工厂 readiness 与产出脱节**(S08-F05):工厂端 readiness=0.7 看似健康,但 cohort 143 全 grade=D promotion_ready_rate=0%,系统在自动化产垃圾,且无 cohort_health 顶层指标
6. **batch / single 模式数据不一致**(S08-F01):同一组参数在 batch_backtest 和 simple_backtest 跑出不同结果,工具不提示这是模式差异

**positive 证据**(3 条):

- `get_signal_hit_rate` 是工具集**质量最高**的部分:by_regime 拆解 + sample 充足 + 三层 horizon 完整
- `backtest_factor` 因子分组回测**结果合理**:long_short 8.12%/期 sharpe 1.58 max_dd 5.7%
- `data_validation(GE)` 这次 7/7 evaluated 全 pass,vs S06-F06 evaluated=0 silent pass 是配置不全的差别

**金融数学一致 + 量化数学一致是 AKShare MCP 真正可用的核心**,但**边界检查 + 样本量校验 + silent fallback** 仍是系统性缺陷。

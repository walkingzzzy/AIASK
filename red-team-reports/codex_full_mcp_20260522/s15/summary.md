# S15 · 估值模型 DCF/DDM/相对估值/Scenario_DCF/Distribution + 行业模板 + 财务报表 + Factor library

- **判定**: ✅ 通过 (31/31 工具,Pass=14 / Degraded=12 / Fail-graceful=5 / Fail=0)
- **耗时**: 12:55:04 → 12:56:51 (约 107s)
- **覆盖**: list_industry_templates / get_historical_valuation / get_valuation_metrics / DDM / DCF(driver_v2/distribution/sensitivity)/ scenario_DCF / relative_valuation / fundamental_analysis_manager / get_financials / calculate_factor / list_factors

## 🔥 本场景重大发现 — DCF input sanity 完全缺失 + 单位/口径/模板三连不一致(15 条 finding,7 high / 4 medium / 4 positive)

### 1. DCF input sanity check 完全缺失(S15-F01)

```python
# Case 1: negative discount
dcf_valuation(discount_rate=-0.05, growth_rate=0.05, ...):
  used_discount_source: "wacc"          ← silent override to wacc=0.07425!
  intrinsic_value: 444B                 ← silently 计算

# Case 2: extreme growth
dcf_valuation(growth_rate=0.5, discount_rate=0.05, terminal_growth_rate=0.04, years=10):
  intrinsic_value: 72,654,866,093,771   ← 72.65 万亿!
  vs market_cap: 1.64 万亿                  → 44 倍!

# Case 3: distribution mode extreme
dcf_valuation(enable_distribution=true, samples=1000, seed=42):
  mean: 1.41 万亿
  std:  2.72 万亿                        ← std/mean = 192%!
  max:  52 万亿                          ← 31× mean
  spread_risk: "extreme"                 ← 显式标!但顶层 success=true 不阻断
```

**3 种异常 input 都 success=true 不阻断**。AI 传错参数(typo / 单位错 / 不合理)拿到看似合理的 intrinsic_value;72.65 万亿元的茅台估值不被阻断。

### 2. DCF / Scenario_DCF 同股两估值差 2.6 倍 + 单位不一致(S15-F02)

| 工具 | 输出值 | 单位 | profit_margin |
|---|---|---|---|
| `dcf_valuation` | **329B** | 元(总市值) | 0.5(实际白酒) |
| `scenario_dcf_valuation` | **126B** weighted / **100.74 元** per_share | per_share | 0.11/0.14/0.17(消费模板) |

**delta_ratio = 329/126 = 2.6×**;**单位不互通**;**profit_margin 差 3.6 倍**(50% vs 14%)。AI 拿到 329B 与 100.74 两个估值,无法对比;若 per_share 100.74 对比当前 1290.2 → 极度低估 91%,做错决策。

### 3. industry_templates 仅 5 类缺关键行业(S15-F03)

```
available_industries: [银行, 制造, 科技, 消费, 医药]
missing_critical:    [白酒/酿酒, 能源/油气, 地产, 公用事业, 钢铁, 建材, 传媒, 军工, 新能源]

茅台(酿酒)         →  套'消费' template
消费.profit_margin  =  0.14
white_liquor_actual =  0.50          ← 差 3.6 倍!
```

**S15-F02 直接根因**;所有 scenario_dcf 用错 profit_margin → 估值偏低 50-90%。

### 4. fundamental_analysis_manager 整组 PE/PB 全 null(S15-F04)

```
fundamental_analysis_manager.analyze(600519):
  metrics.pe_ratio:  null         ← !!
  metrics.pb_ratio:  null         ← !!
  metrics.roe:       10.06        ← 有
  source: db.get_financials

vs build_stock_context.valuation.pe:    19.91
vs get_valuation_metrics.pe_ratio:      19.91
build_stock_context.source: db.stocks
```

**两路径数据源完全不一致**;fundamental_analysis_manager.compare(4 codes)4 stocks PE/PB 全 null — manager 与底层 db 严重脱节(同 S14-F02 research 模式)。

### 5. distribution mode spread_risk=extreme 但不阻断(S15-F05)

```
valuation_interval:
  samples:       1000
  attempts:      1016                    ← 16 次重试
  mean:          1.41 万亿
  std:           2.72 万亿                ← 192% mean
  std_over_mean: 1.92                    ← 极不稳定
  p10:           529B
  p90:           2212B                   ← 4× p10
  max:           52,063B (52 万亿)        ← 31× mean
  spread_ratio:  1.88
  spread_risk:   "extreme"               ← 显式标!
top_level.success: true                  ← 但仍 true!
```

显式标 extreme 但**不 emit blocking warning**。AI 看 mean=1.41T 以为合理,实际 std 比 mean 还大。

### 6. should_i_buy threshold_backtest 反常(S15-F06)

```
threshold=40  sample_count=43  hit_rate=32.56%  avg_return=-2.4%
threshold=60  sample_count=13  hit_rate=15.38%  avg_return=-4.4%
threshold=80  sample_count=3   hit_rate=0.00%   avg_return=-6.1%

expected_pattern:  higher threshold → higher hit_rate (selectivity)
actual_pattern:    higher threshold → LOWER hit_rate (degenerate!)
```

**theoretical 严格 threshold 应当 hit_rate 提升,但实际反转**;score 模型与历史 forward_return **反向相关** — 模型校准失效。

### 7. should_i_buy strict_mode 不真正 enforce threshold(S15-F07)

```
input.strict_mode: true
selected_style_threshold:
  buy:        80
  confidence: 70

actual:
  score:       40   ← 远低于 80 threshold
  confidence:  30   ← 远低于 70 threshold

result.recommendation: "avoid"     ← 工具仍输出推荐而非 'blocked'
```

**strict_mode 把 threshold 升高但不真正 enforce** — score/confidence 都不达 threshold,工具仍输出 avoid 而非 'strict_mode_not_satisfied'。



### 8. calculate_factor naming 不统一 + factor library category 混淆(S15-F09)

```
calculate_factor(roe)        → fail "Unsupported. Supported: ... roe_ttm"   ← _ttm 后缀严格
calculate_factor(pe_ratio)   → fail "Unsupported. Supported: ... pe_ttm"    ← 命名 inconsistent vs valuation_metrics
calculate_factor(roe_ttm)    → ✅ 10.06
calculate_factor(pe_ttm)     → fail "Failed to calculate factor: pe_ttm"     ← list 标 supported 但 calculate 失败!
calculate_factor(value)      → fail "need positive pe_ratio, pb_ratio, or ps_ratio"   ← composite 因子 ✅(显式)

get_factor_library(category="value")  → fail "Unsupported category: value"
                                         "Supported: all/alternative/fundamental/risk/technical/volume"
                                         (但 value 是 factor_name 不是 category!)
```

## ✅ Positive evidence(4 条)

### S15-F12 ✅:DDM Gordon Model 数学约束 robust

```python
ddm_valuation(growth_rate=0.12, required_return=0.10):
  → success: false
  → error: "增长率必须小于要求回报率"           ✅ 严格执行 g < r
```

vs DCF F01 入口完全无 sanity check — **DDM 数学层 robust ✅**。

### S15-F13 ✅:relative_valuation 极完整

```
industry_stats(5 peers):
  pe_ratio:  mean=28.11  median=14.6  min=13.64  max=66.53  count=5
  pb_ratio:  mean=2.46   median=2.46  min=1.38   max=3.61   count=5

comparison.pe_ratio:
  premium_to_median: +36.37%       deviation_risk: "high"        percentile: 60%
comparison.pb_ratio:
  premium_to_median: +146.75%      deviation_risk: "extreme"     percentile: 100%   ← 行业 PB 第一

peer_pool_build:
  candidate_count: 5
  size_ratio: [0.3, 3.0]
  quality_thresholds: {roe_min: 5.03, debt_ratio_max: 40.32}
  relaxation_reasons: [quality_relaxed, growth_relaxed, cashflow_relaxed]
```

✅ **极完整** — industry_stats + comparison + peer_pool_build(filter chain + relaxation_reasons + sample_codes)。

### S15-F14 ✅:list_factors 50 factors 5 categories 完整 factor library

```
50 factors / 5 categories
  - alternative   5 (sentiment / capital_flow / north_flow / institutional_flow / event_intensity)
  - fundamental  11 (value / quality / growth / pe_ttm / pb_mrq / ps_ttm / roe_ttm / roa_ttm / gross_margin / net_margin / debt_to_equity / revenue_growth_yoy / dividend_yield)
  - risk          6 (volatility / vol_5d / vol_10d / vol_60d / atr_14 / atr_20 / bollinger_width / downside_vol)
  - technical    18 (momentum / trend / reversal / mom_1d/5d/10d/60d / rsi_14/6 / macd_signal/histogram / willr_14 / cci_20 / mfi_14 / stoch_k/d / roc_10/20)
  - volume        5 (volume_ratio / obv_slope / vwap_deviation / turnover_5d/20d / size)

每个 factor 含 9 字段(含 aliases / sub_factors / data_dependency / status)
```

✅ **factor library 最完整层** ✅。

### S15-F15 ✅:data_validation(GE)累计 8 场景 35/35 stable

```
S07 → 7/7    S08 → 7/7    S09 → 2/2    S10 → 3/3
S11 → 5/5    S12 → 5/5    S13 → (skipped)    S14 → 3/3
S15 → val-bc285a11d470 3/3
─────────────────────────────────────────────────────
                     total=35  pass=35  100%
```

**S07-S15 8 场景累计 35/35 expectations 全 pass**。

## 🚨 工具间数据不一致(本场景新增 15 条 finding,其中 high 7 条)

### 7 条 high

- **S15-F01**:DCF input sanity 完全缺失(negative discount silent override / extreme growth 不阻断)
- **S15-F02**:DCF / Scenario_DCF 同股两估值差 2.6 倍 + 单位不互通(329B 元 vs 100.74 元/share)
- **S15-F03**:industry_templates 仅 5 类缺白酒/能源/地产等关键行业
- **S15-F04**:fundamental_analysis_manager PE/PB 全 null vs build_stock_context PE=19.91(数据源不一)
- **S15-F05**:DCF distribution spread_risk=extreme 但顶层 success=true 不阻断
- **S15-F06**:should_i_buy threshold_backtest 反常(80→hit=0%,门槛升高反而 hit_rate 降低)

### 4 条 medium

- S15-F07:should_i_buy strict_mode=true 不真正 enforce confidence threshold
- S15-F08:list_factors pe_ttm status='supported' 但 calculate_factor 失败(数据脱节)
- S15-F09:calculate_factor naming 不统一(roe→fail/roe_ttm→OK)+ factor library category 混淆
- S15-F10:fundamental_analysis_manager.dupont 杜邦 2/3 components=0(asset_turnover=0/equity_multiplier=0)
- S15-F11:get_historical_valuation 30d raw=122 unique=6(每天 ~4 重复 + sparse)

### 4 条 low(positive evidence)

- **S15-F12** ✅:DDM Gordon Model g<r 数学约束 robust(对比 DCF F01 完全无 sanity)
- **S15-F13** ✅:relative_valuation industry_stats + comparison + peer_pool_build 极完整(deviation_risk='extreme' 显式)
- **S15-F14** ✅:list_factors 50 factors / 5 categories(每个 9 字段含 aliases)
- **S15-F15** ✅:data_validation(GE)累计 8 场景 35/35 stable

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-bc285a11d470` | dataset_id | data_validation,GE backend,3/3 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s15_audit |
| ~22 audit_event_id | read_only | industry_templates / historical_valuation / valuation_metrics / DDM × 2 / DCF × 4 / scenario_DCF × 2 / relative / fundamental_manager × 4 / get_financials / list_factors / get_factor_library / should_i_buy / data_validation |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **14/22**
- 累计 Fail: **0**
- 累计推荐 bug: **158 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16 + S11 16 + S12 14 + S13 14 + S14 14 + S15 15,其中 high 累计 **73 条**)

## 关键观察:S15 验证了"估值层 sanity check 缺失 + 单位/口径/模板三连不一致"

**S07-S14** 反复发现"工具间数据不一致 + silent fallback";**S15 在估值层达到峰值**:

**核心问题模式**:

1. **DCF input sanity 完全缺失**(F01):negative discount silent override / 50% growth 不阻断 / spread_risk=extreme 不 block — 同 S07-F03/F04(BS sigma 负 / T=0)模式累计延伸
2. **同概念两工具差 2.6 倍**(F02):DCF=329B 元 vs Scenario_DCF=126B 元(per_share 100.74)— 单位不一,根因是 industry_templates 缺白酒(F03)profit_margin 14% vs 实际 50%
3. **manager-工具数据源脱节**(F04):fundamental_manager 整组 PE/PB null 但 build_stock_context 同股 19.91(同 S14-F02 research / S15 风格累计 3 次)
4. **校准失效**(F06):should_i_buy threshold_backtest 反常 — 严格 threshold 反而 hit_rate 降低,模型与历史 forward_return 反向相关
5. **strict_mode 不真正 enforce**(F07):threshold 升高但 score 不达仍输出 avoid 而非 blocked
6. **list/calculate 数据脱节**(F08):list_factors 标 pe_ttm supported 但 calculate_factor 失败
7. **杜邦 2/3 components=0**(F10):missing data 不警告,asset_turnover=0/equity_multiplier=0

**positive 证据**(4 条):

- DDM Gordon Model g<r 数学约束 robust
- relative_valuation industry_stats + comparison + peer_pool_build 极完整
- list_factors 50 factors / 5 categories(每个 9 字段含 aliases)
- data_validation 累计 8 场景 35/35 stable

**关键洞察**:

S15 暴露**估值层四大硬伤**:

- **DCF 入口 sanity 缺失**(F01:负 discount/超大 growth 不阻断)
- **行业模板覆盖不足**(F03:5 类缺白酒)→ 直接造成 F02 估值差 2.6 倍
- **数据源脱节**(F04:fundamental_manager 与 stocks 表)→ 同 S14-F02 模式
- **校准失效**(F06:threshold 升高 hit_rate 反而降低 — 信号反向相关)

但 **DDM 数学约束 / relative_valuation peer pool / list_factors library** 是**estimation 层最 robust 部分**;**估值数学约束严谨度 > 估值数据 source 一致性**。

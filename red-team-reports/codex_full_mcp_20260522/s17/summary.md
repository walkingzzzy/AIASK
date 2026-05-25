# S17 · 基本面深挖 + 5 估值器跨工具一致性 + 杜邦 + 同行对比 + research 路径分裂 + 决策方向冲突

- **判定**: ✅ 通过 (40/40 工具,Pass=18 / Degraded=16 / Fail-graceful=6 / Fail=0)
- **耗时**: 13:14:28 → 13:17:14 (约 2 分 46 秒)
- **样本股**: 000651 格力电器(白色家电,PE=7.58 PB=1.45 ROE=4.0 dividend_yield=7.57%)— 经典价值股
- **覆盖**: fundamental_analysis_manager(5 actions)/ research_manager(3 actions)+ research.db(4 工具)/ 5 估值器(intrinsic_value(PE)/intrinsic_value(DCF)/dcf_valuation/scenario_dcf/ddm + relative)/ 5 决策工具(should_i_buy/should_i_sell/build_stock_context/smart_diagnosis/get_unified_decision/analyze_stock_workflow)/ analyze_stock_sentiment / get_factor_profile / get_industry_chain / 4 K线/技术指标 / data_validation / log_audit

## 🔥 本场景重大发现 — 5 估值器跨度 8 倍 + 4 决策方向冲突 + research 路径分裂(15 条 finding,7 high / 4 medium / 4 positive)

### 1. 5 个估值器对同股给出 5 个不同 intrinsic_price,跨度 8×(S17-F01)

| 工具 | per_share | vs 当前 39.51 元 |
|---|---|---|
| `fundamental_analysis_manager.intrinsic_value(PE)` | **91.23** | +131% 严重低估 |
| `fundamental_analysis_manager.intrinsic_value(DCF)` | **95.92** | +143% 严重低估 |
| `dcf_valuation(driver_v2, g=5%, d=9%)` | **11.60** | -71% 严重高估 |
| `scenario_dcf_valuation(制造模板)` | **18.24** | -54% 高估 |
| `ddm_valuation(g=4%, r=8.5%)` | **68.64** | +74% 严重低估 |
| `relative_valuation` | percentile=0% / extreme high_discount | 无 per_share 但隐含+++ |

**5 个工具 / 5 个值 / 跨度 11.60 → 95.92 = 8×**;且 **industry_pe 三个值不一**(fa.intrinsic=15 vs relative_mean=26.48 vs relative_median=22.69)。

**S15-F02:茅台估值差 2.6× → S17:格力差 8×,跨工具一致性 4 月内进一步恶化 4×**。

### 2. DCF g=r Gordon 数学退化但仍 success=true(S17-F02)

```
fundamental_analysis_manager.intrinsic_value(method=dcf):
  growth_rate:    10.0%       ← 与 discount_rate 相等
  discount_rate:  10.0%       ← 数学上 Gordon 显性期退化
  terminal_growth: 3.0%
  intrinsic_per_share: 95.92  ← 但仍输出 95.92!
  top_level.success: true     ← 不阻断不警告
```

**vs S15-F12 DDM Gordon 模型 g>=r 显式 fail '增长率必须小于要求回报率'** — DCF 与 DDM 同概念两种处理。S15-F01 dcf_valuation negative discount silent fallback → S17-F02 g=r 不阻断 — 累计 3 次。

### 3. 同股 5 个 decision 工具 3 种方向(hold/hold/sell/watch/sell)(S17-F03)

```
should_i_buy(conservative)            → hold     (score=45  conf=40%  buy_prob=11.39%)
smart_stock_diagnosis                 → hold     (multi 因素交织)
build_stock_context                   → SELL     (score=24  风险偏高建议回避)
analyze_stock_workflow.decision_summary → watch    (final_score=42.47  闸门拦截)
get_unified_decision (conservative)    → watch    (final_score=42.52  compliance gate blocked)
should_i_sell(buy=42, holding=90d)    → SELL     (-7.76% 跌破 ATR 40.71)
                                      ───────────────────────
                                      hold/hold/sell/watch/watch/sell
                                      = 3 种方向严重冲突
```

**5 个 decision 工具 3 种方向**:AI 不知该听哪个 — 听 build_stock_context.sell 错过格力低估机会,听 unified=watch 永远不出手。

**S15-F03 multi_factor 5× / S16-F03 同股 5× / S17-F03 5 工具 3 方向 — 累计 4 次复现**。

### 4. research_manager 与 research.db 完全脱节,同股 6 工具拆分(S17-F04)

| 工具 | reports count | source |
|---|---|---|
| `get_research_summary` | **2** ✅ | research.db |
| `analyze_research_report` | **2** ✅ | research.db |
| `get_research_reports` | **2** ✅ | db.research_reports |
| `search_research_db` | **2** ✅ | research.db |
| `research_manager.get_reports` | **0** ❌ | "暂无研报数据" |
| `research_manager.get_ratings` | **0** ❌ | "暂无评级数据" |

**4 工具看到 2 reports(山西证券买入评级)/ research_manager 完全看不见**!

AI 优先调 research_manager.get_ratings 拿到 'unknown 暂无评级' 直接放弃 — 但 db 实际有"买入"评级。

**S15-F04 fundamental_analysis_manager PE/PB null + S16-F04 fundamental_manager 整组 null + S17-F04 research_manager 整组 0 — 累计 5 次 manager 层与底层数据库完全脱节**。

### 5. industry_chain 强制 fuzzy match 错位:白色家电 → 新能源产业链(S17-F05)

```
build_stock_context.industry_chain_snapshot:
  industry_keyword:   "白色家电"
  matched:            true                    ← 假装成功!
  chain_id:           "new_energy"            ← 强制 fuzzy match
  chain_name:         "新能源产业链"
  related_segments:   [锂矿/钴矿/电池材料/新能源汽车/储能]   ← 完全无关!

vs.get_industry_chain(白色家电):
  "未找到与「白色家电」匹配的产业链,已返回全部预置产业链(共5条)"   ← graceful 诚实
```

**两工具行为完全相反**:build_stock_context 假装 match(误导),get_industry_chain graceful fallback(诚实)。industry_chain 库只有 5 条(new_energy/semi/pv/liquor/pharma)— 缺白色家电/钢铁/银行/地产/汽车/煤炭等核心行业。

**S15-F03 industry_templates 缺白酒 + S16-F01 screener industry filter 失效 + S17-F05 industry_chain 误配 — 累计 3 次产业映射错位**。

### 6. 同股两工具同时刻 PE 不一致(S17-F06)

```
get_realtime_quote (13:17:13):    PE=7.44   PB=1.43   mkt_cap=2169.98 亿
get_valuation_metrics (13:15:16):  PE=7.58   PB=1.45   mkt_cap=2200.23 亿
                                  ───────────────────────────────────
                                  ΔPE=1.85%  Δprice=1.39%  时间间隔 117 秒
```

**两工具底层价格源不一致**(get_realtime_quote 走 tqcenter 实时;get_valuation_metrics 走 db.stocks 缓存)。AI 看 PE=7.44 / 7.58 不知用哪个。

### 7. scenario_dcf_valuation Bear 子情景 intrinsic=-35B 但 weighted 仍 success=true(S17-F07)

```
Bull:  prob=0.25  growth=0.13  margin=0.13  intrinsic=+269B
Base:  prob=0.50  growth=0.08  margin=0.10  intrinsic=+87B
Bear:  prob=0.25  growth=0.03  margin=0.07  intrinsic=-35B   ← 经济上不应为负!

weighted_intrinsic: 102B
per_share: 18.24 元 vs 当前 39.51 = -54%

top_level.success: true   ← 仍输出
warning_emit: 无
```

**企业最差 intrinsic 应当 floor 到 0**(企业价值不可能为负)。AI 看 weighted=102B 看似合理,实际 Bear 子情景"内在价值为 -35B"非但不可信,反而拖累 weighted。

## ✅ Positive evidence(4 条)

### S17-F12 ✅:DDM + relative_valuation 极完整

```
DDM:
  next_dividend / (r - g) = 3.0888 / (0.085 - 0.04) = 68.64 元
  Gordon constraint:        g(0.04) < r(0.085)              ✅

relative_valuation:
  industry_stats(4 peers):  PE mean=26.48  median=22.69  count=4
                            PB mean=2.94   median=2.79   count=4
  comparison.PE:            target=7.58  percentile=0%
                            deviation_risk="extreme"
                            risk_flag="high_discount"
  peer_pool_build.relaxation_reasons:
    [quality_filter_relaxed_due_to_small_sample,
     growth_filter_relaxed_due_to_missing_data,
     cashflow_filter_relaxed_due_to_missing_data]
```

**DDM 数学约束严格 + relative_valuation industry_stats + peer_pool_build(filter chain + relaxation_reasons)极完整**;deviation_risk='extreme' 明确标 PE 0% percentile = 行业最低估。

### S17-F13 ✅:analyze_stock_sentiment OOS validation 极完整

```
news_oos_validation:
  alpha_5d_bull_vs_bear:  -0.019                    ← 信号反向
  signal_stability:       "degraded"                ← 显式标
  decay_analysis.decay_note: "signal_reverses_on_longer_horizon"
  alpha_curve:            5d:-0.019  10d:-0.0344  20d:-0.0212

historical_validation:
  sample_count: 49
  bucket:       neutral
  forward_returns:
    5d:  hit_rate=0.27  avg=-0.0083  [-0.036,+0.019]
    10d: hit_rate=0.27  avg=-0.0083  [-0.046,+0.073]
    20d: hit_rate=0.41  avg=+0.0015  [-0.052,+0.070]
```

bull/neutral/bearish 三 bucket × 5d/10d/20d 三 horizon = 9 cells 完整;signal_stability='degraded' 显式标信号反转;**这是情绪层最严谨的 OOS validation 输出** ✅。

### S17-F14 ✅:get_factor_profile + get_industry_chain graceful

```
get_factor_profile(rsi/macd/momentum_60d):
  每因子 10 字段:
    current / series_30d / percentile_1y / percentile_3y /
    trend / rolling_zscore / industry_rank / industry_total /
    market_percentile / historical_oversold_recovery

  rsi.historical_oversold_recovery:
    sample_count: 27
    5d.hit_rate:  0.4074  reliable=true
    10d.hit_rate: 0.4815  reliable=true

get_industry_chain(白色家电):
  message: "未找到与「白色家电」匹配的产业链,
            已返回全部预置产业链(共5条)"   ← graceful ✅
```

✅ get_factor_profile 因子+OOS hit_rate 完整 + get_industry_chain graceful fallback 行为正确(与 build_stock_context 强制 match 形成对照)。

### S17-F15 ✅:data_validation(GE)累计 10 场景 49/49 stable

```
S07 → 7/7    S08 → 7/7    S09 → 2/2    S10 → 3/3
S11 → 5/5    S12 → 5/5    S13 → (skipped)    S14 → 3/3
S15 → 3/3    S16 → 7/7    S17 → val-79124af7473b 7/7
─────────────────────────────────────────────────────
                     total=49  pass=49  100%
```

**S07-S17 10 场景累计 49/49 expectations 全 pass**。

## 🚨 工具间数据不一致(本场景 15 条 finding,其中 high 7 条)

### 7 条 high

- **S17-F01**:5 估值器跨度 8 倍(11.60 → 95.92 元)
- **S17-F02**:DCF g=r Gordon 数学退化不阻断
- **S17-F03**:5 decision 工具 3 方向(hold/hold/sell/watch/watch/sell)
- **S17-F04**:research_manager 与 research.db 完全脱节(0 vs 2 reports)
- **S17-F05**:industry_chain 强制 fuzzy match 错位(白色家电→新能源)
- **S17-F06**:同股两工具同时刻 PE 不一致(7.44 vs 7.58)
- **S17-F07**:scenario_dcf Bear 子情景 intrinsic=-35B(经济上不可能)但 weighted 仍 success=true

### 4 条 medium

- S17-F08:fundamental_analysis_manager.intrinsic_value(PE) EPS 内部 6.082 vs financials.eps 4.34(差 40%)
- S17-F09:get_unified_decision warnings 含 Python AttributeError(`'str' object has no attribute 'tzinfo'`)
- S17-F10:get_historical_valuation 56 raw → 3 unique(每天 ~18 重复,S15 4/天 → S17 18/天恶化 4 倍)
- S17-F11:get_profit_forecast 三源全跪(eastmoney→tushare→akshare)即使蓝筹也无 forecast

### 4 条 low(positive)

- **S17-F12** ✅:DDM Gordon g<r 严格 + relative_valuation industry_stats / peer_pool_build / relaxation_reasons 极完整
- **S17-F13** ✅:analyze_stock_sentiment news_oos_validation 9 cells + decay_analysis(signal_reverses_on_longer_horizon)
- **S17-F14** ✅:get_factor_profile 10 字段 + get_industry_chain graceful fallback 行为正确
- **S17-F15** ✅:data_validation(GE)累计 10 场景 49/49 stable

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-79124af7473b` | dataset_id | data_validation,GE backend,7/7 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s17_fundamental_audit |
| ~30 audit_event_id | read_only | comprehensive_manager × 2 / research_manager × 3 / fundamental_analysis_manager × 5 / 5 估值器 / 5 decision 工具 / get_research × 4 / kline × 4 / sentiment × 1 / 等 |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **17/22**
- 累计 Fail: **0**
- 累计推荐 bug: **188 条**(S02-S16 累计 173 + S17 新增 15,其中 high 累计 **87 条**)

## 关键观察:S17 验证了"基本面深挖 + 估值跨工具不一致达到峰值"

**S15** 估值层差 2.6× → **S16** quant 评分差 5× → **S17 估值跨度 8×**,跨工具一致性持续恶化。

**核心问题模式**:

1. **5 估值器跨度 8 倍**(F01):同股 5 个值 11.60 → 95.92 元;industry_pe 同概念 3 个值(15/26.48/22.69)
2. **DCF g=r 不阻断**(F02):S15-F01 negative discount → S17-F02 g=r — DCF 入口 sanity 持续缺失;但 DDM Gordon 严格(F12)— **DCF/DDM 同 Gordon 数学约束两种处理**
3. **decision 5 工具 3 方向**(F03):buy.hold / smart.hold / context.sell / unified.watch / sell.sell;S15-F03/S16-F03 累计 4 次
4. **research_manager 整组 0 reports vs db 4 工具 2 reports**(F04):manager 与 db 完全脱节;S15/S16/S17 累计 5 次同模式
5. **industry_chain 错配**(F05):build_stock_context 强制 match 白色家电→新能源 vs get_industry_chain graceful 不 match — 两工具同概念相反行为;industry_chain 库只 5 条
6. **同时刻同股 PE 不一致**(F06):realtime_quote=7.44 vs valuation_metrics=7.58
7. **scenario_dcf Bear=-35B 不阻断**(F07):企业内在价值不可能为负但工具未 floor

**positive 证据**(4 条):

- DDM Gordon g<r + relative_valuation peer pool 极完整
- analyze_stock_sentiment OOS validation 9 cells + decay_analysis 显式标信号反转
- get_factor_profile 10 字段 + get_industry_chain graceful
- data_validation 累计 10 场景 49/49 stable

**关键洞察**:

S17 暴露**基本面层四大破口**:

- **估值跨工具一致性恶化**(F01:8× / F02:DCF 数学退化 / F07:Bear 负值 / F08:EPS 不一致)— S15(2.6×)→ S17(8×)恶化 3 倍
- **decision 多工具方向冲突**(F03:5 工具 3 方向)— 累计 4 次
- **manager-db 系统性脱节**(F04:research_manager / S15/S16 fundamental_manager)— 累计 5 次
- **同概念两路径行为相反**(F05:industry_chain build 强制 match vs get 诚实 fallback / F06:realtime PE vs valuation PE / F02:DCF 不阻断 vs DDM 严格)

但 **DDM 数学严谨 / relative_valuation peer 池 / analyze_stock_sentiment OOS / get_industry_chain graceful** 是基本面+情绪层 robust 部分;**严谨度等级:DDM > relative_valuation > sentiment_oos > DCF / scenario_dcf / fa.intrinsic** —— 工具集**估值层数学严谨度参差不齐,DCF 系列最薄弱**。

**累计 17/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计 bug 188(其中 high 87 条),22 场景红队复测剩 5 场景(S18-S22)。

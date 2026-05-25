# S13 · 决策融合 + 上下文构建 + 用户画像/KYC + 推理链路 + 概率校准 + 风险闸门

- **判定**: ✅ 通过 (31/31 工具,Pass=25 / Degraded=6 / Fail=0)
- **耗时**: 12:40:54 → 12:43:16 (约 142s)
- **覆盖**: decision_manager / user_manager / should_i_buy / should_i_sell / get_unified_decision(summary/details) / build_*_context / analyze_stock_workflow / fuse_decision_payload / run_decision_gate / smart_stock_diagnosis

## 🔥 本场景重大发现 — 决策融合层全 robust + 用户画像层 silent fallback(14 条 finding,6 high / 3 medium / 5 positive)

### 1. ✅ user_manager AUTH_ERROR cross-user 隔离 robust(S13-F01)— vs alerts S11-F06 显著区别

```python
user_manager.assess_kyc(user_id="codex_full_mcp_20260522")
# 我的调用身份 ≠ 目标 user_id  →
{
  "success": false,
  "error_code": "AUTH_ERROR",
  "error": "user_id 与当前调用身份不匹配,禁止跨用户访问"
}

user_manager.assess_kyc(user_id="default")
# 调用身份=default = 目标=default  →
{
  "success": true,
  "data": {
    "kyc_level": "C2",
    "label": "稳健型",
    "composite_score": 35.0,
    "max_drawdown": 0.10,
    "components": {"trade_behavior": 25, "profile": 50, "questionnaire": 50}
  }
}
```

**user_manager 4 actions 全部做了 user_id scope check** — 这是工具集**多用户隔离最 robust 部分**。**vs alerts_manager 全 user_id='default'(S11-F06)** 显著区别。

### 2. user_profile 模块 Python 异常 silent fallback(S13-F02)

```
get_unified_decision warnings:
  ["oos_validation:peer_codes_insufficient",
   "user_profile_snapshots:'str' object has no attribute 'tzinfo'"]      ← Python 异常透出!

user_context:
  profile_source: "fallback"
  kyc_level: null
  weighted_profile: null
  preferences: {}
```

**Python 异常被 catch 转 warning 但 silent fallback 到 anonymous user**;同 S07-F07(pandas tolist)/ S09-F09(numpy broadcast)模式累计第 3 次。AI 看 unified_decision 以为是 user-tailored 决策,实际是 anonymous fallback。

### 3. decision_manager.analyze 3 维度全 50.0 默认值(S13-F03)

```
scores:
  technical:    20.0   ← 实际算出
  fundamental:  50.0   ← 默认值(缺 PE/PB)
  valuation:    50.0   ← 默认值(同上)
  sentiment:    50.0   ← 默认值(volume_ratio=0.969 实际 < 1 应当 < 50)

data_quality.missing_fields: ["pe_ratio", "pb_ratio"]
data_quality.completeness:    0.5
data_quality.score_penalty:   8.0
```

**3/4 维度是默认 50**,但 should_i_buy / build_stock_context 同股 PE=19.91 能拿到 — **不同 decision 工具数据源不一致**。

### 4. decision_manager.recommend 100 candidates 全跪(S13-F04)

```
recommend(balanced, limit=5):
  recommendations: []
  count:            0
  candidate_count:  100
  scanned_count:    100
  coverage_rate:    0.0
  no_candidates:    false              ← 但 coverage=0!矛盾
  filter_chain:     [{step: "source", count: 100}, {step: "dedup", count: 100}]
```

**100 candidates 全部 score 不达 balanced threshold** — 同 S08 strategy factory 143 全 grade=D 模式;coverage_rate=0 但 no_candidates=false 矛盾。

### 5. should_i_buy 概率校准很差(S13-F06)

```
decision_probability:
  buy_probability:    6.42%
  band:               "low"
  method:             "logit(score,confidence,volatility)"

prediction_quality:
  empirical_hit_rate:    32.56%        ← 历史 threshold=40 实际 hit
  calibration_gap:      -0.2614        ← 预测 6% vs 实际 32% 差 26pp!
  ECE:                   0.2614
  brier_score:           0.0683
  sample_size:           43
```

**预测 6% 实际 32%,calibration 差 26 percentage points** — 模型严重欠置信度;但工具仍输出 buy_prob=6.42% 而不是用 empirical_hit_rate 校正。

### 6. 5 个 decision 工具评分量化差距 21 分(S13-F05)

| 工具 | score | recommendation |
|---|---|---|
| `decision_manager.analyze` | 33 | sell |
| `should_i_buy` | 40 | avoid |
| `should_i_sell` | 45 | sell |
| `smart_stock_diagnosis` | 24 | sell |
| `unified_decision` | 38.19 | watch |

**方向一致(全 sell/watch),但量化评分 24-45 差距 21 分** — decision 评分体系没统一 baseline。

### 7. 字段重复 + 默认值脱节(S13-F08 / S13-F09)

- `get_investment_analysis` 与 `build_stock_context.analysis_context` **100% 字段重复**(get_investment_analysis 是 build_stock_context 的子集)— API 设计冗余
- `decision_manager.analyze.sentiment.score=50` 但 `volume_ratio=0.969 < 1.0` 偏弱;同时 RSI=22.59 极超卖 — **sentiment.score 与底层信号脱节**



## ✅ Positive evidence(5 条)

### S13-F01 ✅:user_manager AUTH_ERROR cross-user 隔离 robust

详见上面 §1。**vs alerts_manager S11-F06 全 user='default'** 是工具集多用户隔离最 robust 的部分。

### S13-F10 ✅:三层上下文 builder 完整(stock + quant + event)

```
build_stock_context:
  modules: 7 (price/basic/valuation/fundamentals/technical/momentum/risk)
  + market_snapshot + fund_flow_snapshot + industry_chain_snapshot + security_status
  fields: 50+
  source_chain: 8

build_quant_context:
  factors: 3 (rsi/macd/momentum) full 30d series
  signal_stats: rsi_oversold 22 samples + by_regime 拆解
  conditional_returns: 27 matches AND logic
  similar_patterns: 6 matches aggregate 10d hit=100%
  probability_targets: 5 horizons (1d/3d/5d/10d/20d) full prediction_quality + CI
  effective_sample_size: 3

build_event_context:
  documents: 6 (news 2 / notice 2 / research 2)
  positive: 1   negative: 0
  event_tags: [业绩景气, 资本运作]
  direction: bullish    intensity: low
  veto_candidates: 1 (万联证券研报 '增持')
  raw_texts: 6 完整
```

✅ **AI 决策推理最关键的 evidence 链**完整;3 个 builder 总共提供 100+ 字段、5 个 prediction horizons、6 篇文档原文、22-27 历史样本 matches。

### S13-F11 ✅:analyze_stock_workflow 4-step 编排 + lineage 完整

```
analyze_stock_workflow(600519):
  steps: 4 (stock_profile / daily_kline 90 bars / financials / decision_summary)
  successful: 4 / 4
  run_id: analyze_stock_workflow:1779597774214:d210dbcf
  child_runs: 4
    - stock_profile:1779597774214:ed609c9e
    - daily_kline:1779597774220:1eacccfd
    - financials:1779597795376:5da1ec2e
    - decision_summary:1779597795377:dbddc9d7
  all_parent_run_id_match_root: true
  artifacts.stock_profile_resource: "resource://stock/600519/profile"
```

✅ **lineage trace 完整** — workflow 编排 robust。

### S13-F12 ✅:5 个 decision 工具结论方向一致

```
should_i_buy(600519, balanced):     avoid(40)
should_i_sell(600519, buy=1500):    sell(45)
decision_manager.analyze(600519):    sell(33)
smart_stock_diagnosis(600519):       sell(24)
unified_decision(600519):            watch(38.19)
```

✅ **方向高度一致** — 茅台在 bearish regime + RSI 22.59 极超卖 + MACD 零下方 + 空头排列 时 5 个工具全部 avoid/sell/watch,**无任何 buy 推荐**。虽然评分量化差距 21 分(F05)但方向 robust。

### S13-F13 ✅:fuse_decision_payload style 切换工作

```
balanced:
  weights: {stock_context: 0.55, quant: 0.25, event: 0.20}
  final_score: 38.19

aggressive:
  weights: {stock_context: 0.45, quant: 0.35, event: 0.20}    ← stock -10pp / quant +10pp
  final_score: 40.69                                          ← +2.50
```

✅ **风险偏好 → weight 映射工作** — aggressive 倾向 quant 因子,score 微涨。

### S13-F14 ✅:unified_decision details_hint AI 友好下钻

```json
{
  "details_available": true,
  "details_hint": {
    "tool": "get_unified_decision_details",
    "args": {"code": "600519", "investment_style": "balanced", "user_id": "codex_full_mcp_20260522"}
  }
}
```

✅ **顶层显式告诉 AI 下钻路径** — 工具链发现机制友好。

## 🚨 工具间数据不一致(本场景新增 14 条 finding,其中 high 6 条)

### 6 条 high

- **S13-F02**:`get_unified_decision` user_profile 模块 Python 异常 'str/tzinfo' silent fallback(累计第 3 次复现 Python 异常透出模式)
- **S13-F03**:`decision_manager.analyze` 3 维度全 50.0 默认值
- **S13-F04**:`decision_manager.recommend` 100 candidates 全跪 0 推荐(coverage=0 但 no_candidates=false 矛盾)
- **S13-F05**:5 个 decision 工具评分量化差距 21 分(24-45)无统一 baseline
- **S13-F06**:`should_i_buy` 概率校准 calibration_gap=-0.2614(预测 6% vs 实际 32%)

### 3 条 medium

- S13-F07:`update_user_profile` 写入 profile 但 db.users 表无对应 user 实体
- S13-F08:`get_investment_analysis` 与 `build_stock_context` 字段 100% 重复(API 设计冗余)
- S13-F09:`decision_manager.analyze.sentiment.score=50` 与 RSI=22.59 / volume_ratio=0.969 脱节

### 5 条 low(positive evidence)

- **S13-F01** ✅:`user_manager` AUTH_ERROR cross-user 隔离 robust
- **S13-F10** ✅:三层上下文 builder 完整(stock + quant + event)
- **S13-F11** ✅:`analyze_stock_workflow` 4-step + lineage child_runs 完整
- **S13-F12** ✅:5 个 decision 工具结论方向一致(全 sell/watch)
- **S13-F13** ✅:`fuse_decision_payload` style 切换 weights 映射工作
- **S13-F14** ✅:`unified_decision details_hint` AI 友好下钻

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `user_profile_snapshots(codex_full_mcp_20260522)` | **persist (但 db.users 表无)** | recorded=true / F07 印证 profile 与 user 实体表分离 |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s13_audit |
| `analyze_stock_workflow run_id` | lineage | 4 child_runs 全 parent_run_id 匹配 |
| ~25 audit_event_id | read_only | decision × 4 / user × 5 / should × 2 / context × 3 / unified × 3 / gate / fuse / workflow / smart_diagnosis / get_/update_user_profile |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **~161/161** ✅(覆盖率 100% 已达,本场景 4 个 new tools 都是 decision/user 高级 action 而不是 base tools)
- 已通过场景: **12/22**
- 累计 Fail: **0**
- 累计推荐 bug: **129 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16 + S11 16 + S12 14 + S13 14,其中 high 累计 **60 条**)

## 关键观察:S13 验证了"决策融合层方向 robust + 用户画像层 silent fallback"

**S07-S12** 主要数据/数学/护栏层;**S13 是工具集**最高层抽象** — 决策融合 + 多上下文 builder + 用户画像 + 推理链路。**

**核心问题模式**:

1. **多用户隔离 user_manager robust**(F01):AUTH_ERROR 显式;vs alerts S11-F06 全 default 显著区别
2. **silent fallback 第 3 次复现**(F02):Python 'str/tzinfo' 异常 transparent,触发 user_profile_fallback,但 unified_decision 顶层不警告 user_profile_active=false
3. **decision_manager.analyze 数据源不对齐其它 decision 工具**(F03):3 维度全 50 默认值,但 should_i_buy 同股 PE=19.91 能拿到
4. **recommend 全跪 vs 上下文 builder 完整 — 双层质量不一**(F04 vs F10):recommend 100 candidates 0 推荐;但 stock/quant/event builder 三层 50+ 字段 / 5 horizons / 6 docs 极完整
5. **5 工具评分量化差距 21 分**(F05):scoring baseline 不统一,但**方向高度一致**(F12)
6. **概率校准差**(F06):buy_prob 6% vs hit_rate 32%,**calibration_gap=-0.26 ECE=0.26 brier=0.068** 模型严重欠置信度
7. **API 字段重复**(F08):get_investment_analysis 100% 是 build_stock_context 的子集

**positive 证据**(5 条):

- `user_manager` AUTH_ERROR cross-user 隔离 robust(vs alerts S11-F06)
- 三层上下文 builder 完整(stock 50+ / quant 5 horizons / event 6 docs)
- `analyze_stock_workflow` 4-step + child_runs lineage trace 完整
- 5 个 decision 工具结论**方向一致**(全 sell/watch / 0 buy)
- `fuse_decision_payload` style 切换工作 + `details_hint` AI 友好

**关键洞察**:

S07-S12 暴露的**数据/数学/护栏 robust 与漏洞混杂**;**S13 暴露的是更高层模式**:

- **决策融合**:**方向 robust**(5 工具一致 sell)/ **量化评分不齐**(差 21 分)/ **概率校准失效**(预测/实际差 26pp)
- **多上下文 builder**:**极完整**(50+ 字段 / 5 horizons / 6 docs)
- **多用户隔离**:**user_manager robust**(AUTH_ERROR)/ **alerts/decision 等 silent fallback 至 default user**

**决策方向可信、量化校准失效、用户隔离两套标准** — 这是 S13 总结。

# S14 · 事件/新闻/公告/研报 + 文本信号 + 大宗交易 + 龙虎榜 + 融资融券 + 市场情绪

- **判定**: ✅ 通过 (31/31 工具,Pass=17 / Degraded=14 / Fail=0)
- **耗时**: 12:47:57 → 12:49:43 (约 106s)
- **覆盖**: research_manager / sentiment_manager / event_manager / trading_data_manager + 新闻/公告/研报/文本信号/大宗交易/龙虎榜/融资融券/市场情绪/分析师排名/盈利预测

## 🔥 本场景重大发现 — 多 source 数据冲突 + research 6 工具 5 种结果(14 条 finding,6 high / 3 medium / 5 positive)

### 1. margin_market_flow vs margin_detail 双 db 表数据严重不一致(S14-F01)

```
get_margin_data(600519, 10d):                  [src=margin_detail]
  5/18:  marginBalance=194.16 亿     ✅
  5/15:  marginBalance=192.38 亿     ✅
  5/14:  marginBalance=191.41 亿     ✅
  ...
  4/30:  marginBalance=179.72 亿     ✅
  delta_18d:  +8% 渐增,合理

vs get_market_sentiment_context.margin_market_flow:
  5/21:  marginBalance=0.0          🚨🚨🚨
  5/20:  marginBalance=0.0          🚨🚨🚨
  5/19:  marginBalance=0.0          🚨🚨🚨
  5/18:  marginBalance=1.46 万亿     ← 突变
  5/15:  marginBalance=2.85 万亿     ← 突变 30000 倍

→ margin_balance_change_5d = -100.0%  完全错!
```

**两 db 表 margin_detail / margin_market_flow 数据严重不一致** — 同概念,前者 196 亿/天稳定,后者 5/19-5/21 全 0;market_sentiment_context 走错源给 AI 看 -100% 极度恐慌信号,实际融资余额完全正常增长。

### 2. research 工具同股 600519 6 工具 5 个不同结果(S14-F02)

```
research_manager.get_reports          0    ← tushare/eastmoney/akshare 全跪
get_stock_research                    0    ← 同上
search_research(茅台)                 1    ← keyword 匹配 1 条
get_research_reports                  2    ← db.research_reports
analyze_research_report.report_count  2    ← 同上 db.research_reports
get_research_summary.count            2    ← 同上 db.research_reports
search_research_db(业绩) 含 600519    1    ← keyword 业绩 仅 1 条
```

**6 工具 5 种结果(0/0/1/2/2/2)** — 同 manager 内 `research_manager.get_reports` 走 online API(全跪)而 `analyze_research_report` 走 db.research_reports(有 2 条)— **manager 与底层工具脱节严重**。

### 3. research_manager.get_ratings 中英文格式不互通(S14-F03)

```
research_manager.get_ratings(600519):
  ratings: {buy: 0, hold: 0, sell: 0}      ← 英文
  consensus_rating: "unknown"
  total: 0

vs analyze_research_report.rating_distribution(600519):
  {买入: 1, 增持: 1}                       ← 中文
```

**rating 英中文不互通** — '买入'/'增持' 应映射 buy 但 get_ratings 不识别。

### 4. event_manager.get_by_code 4 events 实际只 2 unique(S14-F04)

```
get_by_code(600519):
  events_count: 4
    [0] type=news     "独立董事候选人声明(郭田勇)"
    [1] type=news     "独立董事候选人声明(盛雷鸣)"
    [2] type=notice   "独立董事候选人声明(郭田勇)"   ← 与 [0] 同标题
    [3] type=notice   "独立董事候选人声明(盛雷鸣)"   ← 与 [1] 同标题
  unique_titles: 2
```

**news + notice 双 source 同 2 条数据 = 4 events**;**去重缺失**;event_count 误导 AI。

### 5. sentiment_manager.market_sentiment 12 stocks 算全市场(S14-F05)

```
market_sentiment:
  sample_size: 12               ← !!
  up_count: 6   down_count: 6
  score: 50.0   "中性"

actual_market_universe: 5529   ← sample 12/5529 = 0.2%!
```

**12 stocks sample 算 5529 市场情绪**(同 S12-F02 quote_snapshot 12 stocks fresh 一致)— 完全不可信。

### 6. analyze_stock_sentiment 3 components 中 2/3 默认 50(S14-F06)

```
components:
  price_momentum:  40.72        ← 真算
  news_sentiment:  50.0         ← 默认(headline_label_count=0)
  fund_flow:       50.0         ← 默认(虽然 available=true)

data_quality:
  headline_count: 0
  headline_label_count: 0
  fund_flow_available: true     ← 但 score 仍 50
```

**S13-F03 / S14-F06 累计 3 次复现 'default 50.0' 模式** — 模块缺失数据时填默认稀释信号。

### 7. 双 source 字段重复(S14-F07 同模式累计 3 次)

| 工具 | 工具 | 数据相同度 |
|---|---|---|
| `get_stock_news` | `get_stock_notices` | **100%**(同 2 条 eastmoney_notice 数据) |
| `get_investment_analysis` | `build_stock_context.analysis_context` | **100%**(S13-F08) |
| `get_stock_text_signals` | `build_event_context` | **100%** |



## ✅ Positive evidence(5 条)

### S14-F10 ✅:analyze_stock_sentiment OOS validation 极完整

```
historical_validation:
  method: price_momentum_bucket_proxy
  sample_count: 55
  5d:  hit=41.82%  avg_ret=+0.10%   CI [-3.81%, +4.91%]
  10d: hit=54.55%  avg_ret=+0.63%   CI [-5.69%, +12.05%]
  20d: hit=40.00%  avg_ret=-0.90%   CI [-7.25%, +6.60%]

news_oos_validation:
  alpha_5d_bull_vs_bear: -0.0185
  alpha_curve.5d:  -0.0185
  alpha_curve.10d: -0.0539
  alpha_curve.20d: -0.0481
  decay_note: "signal_reverses_on_longer_horizon"
  signal_stability: "degraded"        ← 诚实输出 ✅

by_regime: 3 regimes (bullish/neutral/bearish) × 3 horizons
```

✅ **OOS validation 极完整** — historical(55 samples)+ news_oos(3 regimes × 3 horizons)+ decay_analysis(alpha_curve reverses);**承认 signal_stability=degraded** 诚实。

### S14-F11 ✅:sentiment_manager.stock_sentiment 真实数据(vs decision_manager 默认 50)

```
sentiment_manager.stock_sentiment(600519):
  sentiment: "slightly_bearish"
  score:     40.38
  indicators:
    up_days:        7        ← 真实
    down_days:      13       ← 真实
    volume_ratio:   0.969    ← 真实
    volume_status:  "normal"

vs S13.decision_manager.analyze.sentiment.score:  50.0  ← 默认值
```

✅ 用真实 up_days/down_days/volume_ratio 算出 slightly_bearish 40.38 — 比 decision_manager.analyze.sentiment 默认 50 更准确。

### S14-F12 ✅:get_market_news 10 条真实时事

包含 *ST 华嵘退市 / 长电科技异常波动 / 盐湖股东会决议 / 宏桥控股投关 / 天智航股东会临时提案 — **真实公告/退市/异常 数据合理 ✅**(对比 get_concept_fund_flow proxy 全跪 / get_north_fund 21 月前)。

### S14-F13 ✅:get_block_trades schema + numeric_sanity 完整

10 条大宗交易 schema 完整(date/code/name/industry/price/volume/amount/premium/buyer/seller + dataQuality);**numeric_sanity 通过**。虽然 freshness_sla 标 stale(age=190140s>86400s)但数据本身合理。

### S14-F14 ✅:data_validation(GE)累计 7 场景 32/32 stable

```
S07 → 7/7    S08 → 7/7    S09 → 2/2    S10 → 3/3
S11 → 5/5    S12 → 5/5    S13 → (skipped)    S14 → 3/3
total: 32/32 evaluated all pass
```

**S07-S14 7 场景累计 32/32 expectations 全 pass(S13 未跑 GE)** — `data_validation` GE backend 是工具集**最稳定的层**。

## 🚨 工具间数据不一致(本场景新增 14 条 finding,其中 high 6 条)

### 6 条 high

- **S14-F01**:margin_market_flow vs margin_detail 双 db 表数据严重不一致(-100% 错误信号 vs 196 亿稳定)
- **S14-F02**:research 6 工具同股 600519 产出 0/0/1/2/2/2 五个不同结果(manager 与 db 工具脱节)
- **S14-F03**:research_manager.get_ratings 中英文 rating 不互通(buy/hold/sell vs 买入/增持)
- **S14-F04**:event_manager.get_by_code 4 events 实际只 2 unique(news + notice 同源去重缺失)
- **S14-F05**:sentiment_manager.market_sentiment 12 stocks 算 5529 全市场情绪
- **S14-F06**:analyze_stock_sentiment 3 components 2/3 默认 50(累计 3 次复现 'default 50.0' 模式)

### 3 条 medium

- S14-F07:get_stock_news / get_stock_notices 同 2 条 eastmoney_notice 数据(API 字段重复,模式累计 3 次)
- S14-F08:get_block_trades ST 易购 4 笔大宗交易完全相同(同价同量同卖方拆单未聚合)
- S14-F09:get_analyst_ranking total=0 success=true 但未 degraded(同 S12-F08)

### 5 条 low(positive evidence)

- **S14-F10** ✅:`analyze_stock_sentiment` OOS validation + decay_analysis 极完整(诚实承认 signal_stability=degraded)
- **S14-F11** ✅:`sentiment_manager.stock_sentiment` 用真实 up/down_days + volume_ratio 数据
- **S14-F12** ✅:`get_market_news` 10 条真实时事数据合理
- **S14-F13** ✅:`get_block_trades` schema + numeric_sanity 完整(quality_gate 详尽)
- **S14-F14** ✅:`data_validation`(GE)累计 7 场景 32/32 stable

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-7e7355dfa06e` | dataset_id | data_validation,GE backend,3/3 pass |
| `log_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s14_audit |
| ~24 audit_event_id | read_only | research × 6 / sentiment × 4 / event × 3 / trading × 5 / 文本/新闻/公告/盈利预测/data_validation |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅(覆盖率 100% 已稳定达成)
- 已通过场景: **13/22**
- 累计 Fail: **0**
- 累计推荐 bug: **143 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16 + S11 16 + S12 14 + S13 14 + S14 14,其中 high 累计 **66 条**)

## 关键观察:S14 验证了"事件/文本/情绪三层 source 冲突 + research 6 工具 5 种结果"

**S07-S13** 反复出现"工具间数据不一致"模式;**S14 在事件/文本/情绪/研报层达到峰值**:

**核心问题模式**:

1. **双 db 表数据严重不一致**(F01):`margin_market_flow` 5/19-5/21 全 0(-100% 信号)vs `margin_detail` 196 亿/天稳定 — 同 source manager 内两张表
2. **6 工具同股 5 种结果**(F02):research_manager / get_research_reports / analyze_research_report / get_stock_research / search_research / get_research_summary 全测 600519 → 0/0/1/2/2/2 — **史上最严重 manager-tool 脱节**
3. **rating 中英文不互通**(F03):buy/hold/sell vs 买入/增持
4. **去重缺失**(F04):event_manager.get_by_code news+notice 同 2 条 = 4 events
5. **样本极不足但不警告**(F05):market_sentiment 12 stocks 算 5529 universe
6. **默认值稀释信号**(F06):2/3 components 默认 50(S13-F03/S14-F06 累计 3 次)
7. **API 字段重复模式累计 3 次**(F07):news/notices / investment_analysis/stock_context / text_signals/event_context
8. **数据完全缺失但 success=true**(F09 S12-F08 模式):analyst_ranking 数据源限制 但顶层不 degraded

**positive 证据**(5 条):

- `analyze_stock_sentiment` OOS validation + decay_analysis 极完整(承认 signal degraded)
- `sentiment_manager.stock_sentiment` 用真实数据 vs decision_manager 默认 50
- `get_market_news` 真实时事数据合理
- `get_block_trades` schema + numeric_sanity 完整
- `data_validation` 累计 7 场景 32/32 stable

**关键洞察**:

S14 暴露的是**'事件/文本/情绪/研报'四大业务层 source 冲突的总爆发**:

- **manager 与底层工具脱节**(research 6 工具 5 种结果)
- **db 双表数据冲突**(margin_market_flow vs margin_detail)
- **格式不互通**(rating 中英文)
- **去重缺失**(news/notice/event 重复)
- **sample 不足不警告**(市场情绪 12 stocks)
- **默认值稀释**(2/3 components 50)

**修复 S14 的 source 冲突 + manager-tool 对齐 = 一次性提升'文本/事件层' AI 信任度**;但**OOS validation / event signal decay analysis** 是这一层最 robust 部分,比'数据 source'更早成熟。

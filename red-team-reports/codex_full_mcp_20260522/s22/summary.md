# S22 · 收尾 / 跨场景回归 / 161 工具覆盖矩阵验证

- **判定**: ✅ 通过 (32/31 工具,Pass=18 / Degraded=9 / Fail-graceful=5 / Fail=0)
- **耗时**: 17:13:20 → 17:14:11 (约 51 秒)
- **覆盖**: available_tools / get_stock_info / get_index_quote / get_market_news / get_financials / get_realtime_quote / should_i_sell / get_north_fund / smart_stock_diagnosis / get_available_categories / should_i_buy / get_kline / get_sector_fund_flow / get_limit_up_statistics / compliance_manager / get_valuation_metrics / optimize_portfolio / get_macro_indicator / get_user_profile / quant_manager / alerts_manager / watchlist_manager / calculate_factor / paper_trading_manager / calculate_fear_greed_index / calculate_technical_indicators / get_stock_text_signals / screener_manager / industry_chain_manager / get_trading_dates / get_market_sentiment_context / strategy_manager

## 🔥 6 条 high finding

### 1. get_index_quote 上证指数 3 源全跪(S22-F01)

```
code: 000001  name: ???? (GBK 乱码 S20-F02 复现)
price: null  open/high/low/preClose/volume/amount: 全 null
attempted_sources: [eastmoney_index, sina_index]
source_chain: [eastmoney_index, sina_index, tushare_index_daily]
fallback_used: true
fallback_reason:
  - "eastmoney_index_single returned empty"
  - "eastmoney_index失败: 未获取到指数行情"
  - "tushare_index_daily失败: 您的token不对，请确认。"
```

**3 数据源(eastmoney/sina/tushare)全跪 + 名称 GBK 乱码**;`tushare_index_daily` token 错误暴露认证配置问题。

### 2. compliance_manager.check_order 周日仍 blocked(S22-F02)

```
code: 600519  direction: buy  quantity: 100  price: 1290.2 (订单金额 129020 元)
passed: false  blocked: true
checks:
  position_limit: ✓  trading_hours: ✗ (周日)
  suspended: ✓  st_stock: ✓  lot_size: ✓  order_amount: ✓
  limit_up_down: ✓  realtime_quote: ✓  realtime_order_book: ✓
violations: ["实时盘口卖量为 0，当前疑似无法买入"]
warnings: ["当前时间不在交易时段内（仅提示，部分券商支持预委托）"]
realtime.top_ask_volume: 0  top_bid_volume: 0  top5_ask_volume: 0
```

**正确合规阻断 ✓**(周日盘口 0 卖量),但 `trading_hours: false` 仅给警告而非硬阻断 — 真实场景某些券商支持预委托。

### 3. market_sentiment_context 数据漂移叠加(S22-F03)

```
fear_greed_index: 47 (neutral) ✓
index_context.sh000001:
  close: 10.68              ← 上证指数 ❌(应 4112.9 差 385×, S20-F04 复现)
  change_5d_pct: -2.82
  change_20d_pct: -3.61

northbound_flow_{1d,3d,5d}: null
northbound_context.source: "none"  stale: true
margin_balance_latest: 0.0  margin_buy_latest: 99.33
margin_balance_change_5d: -100%

margin_context.recent_rows[0..2]: 5/19,5/20,5/21 全 0
margin_context.recent_rows[3..4]: 5/15,5/18 1462亿/2847亿
breadth: limit_up=0 limit_down=0 advance=14 decline=23
```

**S20-F04 上证 close=10.68 第二次复现** + margin 5/19-21 全 0 vs 5/15-18 1462亿(数据写入断点)+ breadth 涨14 跌23 但 limit_up=0 limit_down=0(涨跌停统计为 0)。

### 4. get_macro_indicator(cpi) provider 不可用(S22-F04)

```
indicator: cpi  records: []
degraded: true  fallback_reason: "provider unavailable: akshare.macro_china_cpi"
source_chain: [macro.get_indicator, akshare.macro_china_cpi]
quality_gate.multi_source_reconciliation:
  passed: false (warning)
  primary_expected: "tushare_pro.macro"
  actual_primary: "macro.get_indicator"
  mismatch: true
provider_status: tushare_pro.macro / akshare.macro / curl.mofcom 全 configured=available
```

**provider 配置可用但路由不命中** — fallback chain 设计 4 个 provider 但只走 1 个就放弃。

### 5. calculate_technical_indicators MA warmup 期填 0(S22-F05)

```
indicators: [MA, RSI, MACD]  limit: 100
ma[0:19]: 全 0  ma[19]: 1407.158 ...
ma 数组前 19 个 warmup 期错误填 0(应为 null);
macd.warmup_periods: 33 (macd 数组前 33 个为 null ✓ 正确)

不一致: ma 用 0 填充 / macd 用 null 填充 → AI 拿 ma[0]=0 可能误判极低价格
RSI = 22.59 oversold=true buy 信号 ✓
```

**MA 与 MACD warmup 期填充策略不一致**:MA 用 0,MACD 用 null;AI 易误读 MA 早期 0 为价格。

### 6. get_north_fund 4 源全跪 — 累计 4 次复现(S22-F06)

```
items: []
sources_status:
  - "north_fund_flow: stale"
  - "tushare: empty/bad_date/missing_values"
  - "hkex: empty/bad_date/missing_values"
  - "eastmoney_direct: empty/bad_date/missing_values"

quality_gate.fallback_degraded_flag: false (warning)
provider_status: 4 provider 全 configured=available
但实际全 empty/stale → 全跪
```

**北向资金 4 源全跪累计第 4 次复现**(S18-F03 / S20-F05 / S21 / S22)— 应升级到全局 P0 bug。

## 🟡 5 条 medium finding

- **S22-F07**:get_realtime_quote db_snapshot 8min stale 但 stale=false 矛盾标记
- **S22-F08**:get_stock_info totalShares 等 2 字段缺失 + asof=2001-08-27(列示日 24 年)freshness 错误
- **S22-F09**:get_limit_up_statistics 5/22 全 0;3 源 fallback 全瘫(tushare/akshare 都跪)
- **S22-F10**:get_sector_fund_flow db.market_blocks degraded;mainNetInflow 实为 changePercent 复用代理
- **S22-F11**:get_user_profile codex_full_mcp_20260522 weighted_profile ✅(snapshot=1 greed_fear=-0.2)— S19-F02 修复后稳定

## ✅ 4 positive

### S22-F12:锚点 + 全维度稳定

```
available_tools.count: 161 ✓ (基线匹配)
categories.count: 33 ✓
smart_stock_diagnosis(600519): 8 evidence + 4 highlights + 4 risks
watchlist: 2 groups (default + s16_high_quality 含 600519/601318)
```

### S22-F13:should_i_buy 完整证据链

```
recommendation: avoid (40 score / 30 confidence)
buy_probability: 6.42% (band: low)
prediction_quality:
  ECE: 0.26  Brier: 0.068  sample_size: 43 hit_rate: 32.6%
  calibration_gap: -0.26 (overconfident)
  selected_threshold: 40 backtest sample=43
prediction_interval (10d 80% CI): [-6.43%, +1.39%] hit_rate=32.6%
offline_baseline: hit_rate 32.6% benchmark_delta -12.4pp
signal_breakdown: 7 evidence (5 valuation/3 technical/1 fundamental)
```

### S22-F14:industry_chain(白酒)完整三段

```
upstream:   粮食种植/包装材料/酒瓶生产   stocks: 600873/002571/600779
midstream: 白酒生产/品牌运营/渠道建设   stocks: 600519/000858/000568
downstream: 经销商/零售终端/电商平台    stocks: 600519/000858/603369
source: preset
```

### S22-F15:paper_trading + strategy_manager 完整支持矩阵

```
paper_trading.accounts: 524dfc8f 默认账户 100K 100%现金
  status: active  account_type: manual  incubation_stage: warmup
  promotion_candidate: 0  archived_reason: null
  
strategy_manager.actions: 65 actions
  生命周期: create/publish/archive/lifecycle_scan/closure_review
  运行时:   runtime_alerts/runtime_control/runtime_cycle_run/risk_events
  治理:     promotion_reviews/execution_audit_verification
  研究:     ai_generate/ai_optimize_personal_strategy/ai_experiments
  向量:     vector_profiles/vector_indexes/vector_reconcile/vector_health
  孵化:     incubation_accounts/incubation_metrics/incubation_sync_run
```

## 🔬 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `available_tools:list:1779614000034` | trace_id | 161 锚点 ✓ |
| `should_i_buy:600519:1779614002839` | evidence_trace_id | 决策证据 chain saved=true |
| `paper_account 524dfc8f` | paper trading | 100K 默认账户 |
| `watchlist default + s16_high_quality` | 2 groups | 共 3 stocks |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **161/161** ✅
- 已通过场景: **22/22** ✅(全部 ≥31 工具)
- 累计 Fail: **0**
- 累计推荐 bug: **259 条**(S02-S21 累计 244 + S22 新增 15,其中 high 累计 **117 条**)

## 关键观察:S22 收尾验证了"长尾数据源 + 工具基础层稳定性参差"

**核心问题**(累计跨场景):

1. **指数 sh000001 close=10.68(应 4112.9)**(F03):S20-F04 第二次复现 — 数据写入逻辑错误使用某 stock close 而非指数
2. **北向资金 4 源全跪**(F06):S18/S20/S21/S22 累计 **4 次复现** → P0 bug
3. **GBK 乱码 ????**(F01):S20-F02 复现,深证成指/创业板指/上证指数 name 中文编码全错
4. **上证指数 3 源全跪**(F01):eastmoney+sina+tushare 都不可用;tushare token 错误
5. **macro 4 source 配置但只走 1 路 fallback**(F04):路由策略浪费 2 个 provider
6. **MA warmup 用 0 填充 vs MACD null**(F05):AI 易误读

**positive 证据**:
- 锚点 161 + 33 持续验证(F12)
- should_i_buy 完整 ECE/Brier/CI/historical 校准证据(F13)
- industry_chain 白酒三段 9 stocks 完整(F14)
- strategy_manager 65 actions 全维度 + paper_trading 100K stable(F15)

**累计 22/22 场景全部 ≥31 工具,工具(去重)161/161 ✅**,Fail=0,累计推荐 bug **259 条**(其中 high 117),22 场景红队复测 **验收通过 ✅**。

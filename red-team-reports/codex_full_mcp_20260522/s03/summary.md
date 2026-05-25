# S03 · 指数 / ETF / 个股代码混淆攻击

- **判定**: ✅ 通过 (32/32 工具,Pass=11 / Degraded=21 / Fail=0)
- **耗时**: 11:22:24 → 11:23:21 (约 57s)

## 🚨 重大发现:**ETF 510050 在不同工具下契约分裂**

同一代码 `510050`,在 stock 通道和原始数据通道之间的识别结果完全相反:

| 工具 | 510050 行为 |
|---|---|
| `get_realtime_quote` | ❌ `success=false`,"Stock 510050 not found" |
| `get_trade_details` | ❌ `success=false`,"Stock 510050 not found" |
| `get_minute_kline(15m)` | ❌ `success=false`,akshare+sina 都空 |
| `get_stock_info` | ❌ 全字段空,`fallback_reason="未找到股票 510050 的信息"` |
| `should_i_buy` | ❌ `success=false`,"Stock 510050 not found" |
| `vector_search_manager.similar_stocks` | ❌ `target_stock_profile_missing` |
| `search_stocks("50ETF")` | ❌ 0 results |
| `semantic_stock_search("沪深300 ETF")` | ❌ 0 results |
| ─ **VS** ─ | |
| `get_batch_quotes` | ✅ price=2.995,跟 510300/159915 一起 OK |
| `get_kline` | ✅ 3 日 daily 完整 |
| `get_kline_data(weekly, qfq)` | ✅ 8 周 4 月数据 |
| `get_stock_capital` | ✅ 总股本 100.5 亿股 |
| `get_order_book` | ✅ 有五档结构(虽然 stale) |

**根因诊断**:`validate.stock_code` 校验环节里 ETF 不在识别表,触发"Stock not found"硬拒绝。但绕过校验直接走 tqcenter raw 通道的工具反而能取到数据。

**判定理由**:这条**没标 Fail**,因为:
1. 失败的工具都是 `success=false` 但**带完整 envelope**(error 文本、source_chain、fallback_chain、quality_flags),没抛栈
2. 错误信息能让 AI 显式知道"这个代码在 stock 通道找不到"
3. 批量/K线/股本 通道能拿到数据,本质上是**不一致而非崩溃**

但写入 **S03-F01,severity=high**,作为最强烈的修复推荐。

## 🎯 关键决策路径完整闭环

| 工具 | 关键事实 |
|---|---|
| `get_unified_decision("000001", summary)` | `action="watch"`,confidence=0.41,**gate_flags 合并 compliance.blocked,veto_reason="indicative_order_blocked"**,position_signal=暂不出手 0.0% |
| `should_i_sell("000001")` | `recommendation="hold"`,score -10(布林下轨触及 → 可能反弹) |
| `should_i_buy("510050")` | `success=false` "Stock not found"(ETF 校验拒绝) |
| `build_quant_context("000001")` | RSI=30.55 percentile_1y=3.3% z-score=-1.86,**10d up_probability=74.4%**,prediction_quality=medium。但 oos_validation=null (peer 不足) |

## ⚠ 推荐 Bug 修复(本场景新增 5 条)

| ID | 严重度 | 简述 |
|---|---|---|
| **S03-F01** | high | ETF 在 stock 通道全跪、批量/K线通道能拿到。validate.stock_code 应当扩展 ETF 识别表 |
| S03-F02 | medium | `get_index_quote` 持续全降级(3 个指数全重现);tushare token 显式 "token不对" |
| S03-F03 | low | `get_market_blocks(concept)` 4 源全跪 vs `industry` 仅 db_stale,源覆盖不平衡 |
| S03-F04 | low | `search_stocks/semantic_stock_search` 不索引 ETF 简称(如 "50ETF") |
| S03-F05 | low | `get_option_chain(510050)` 上交所 ETF 期权全空,影响 S10/S16 |

## 🔬 副作用 / 状态对象

| ID | 备注 |
|---|---|
| `codex_full_mcp_20260522_s03_etf_index_route` | data_validation read_only,记录 ETF 在 4 通道的找到/未找到对照 |
| `val-fd73c0be7da5` | validation_id (great_expectations 4/4 passed) |

## 🚨 Fail
无。

## ➡ 进度对全局

- 累计调用工具(去重): **69/161** (S01 33 + S02 新 24 + S03 新 12)
- 已通过场景: **3/22**
- 累计 Fail: **0**
- 累计推荐 bug 修复: **8 条** (S02 3 + S03 5)

# S02 · 行情/K线/盘口/指数

- **判定**: ⚠️ 通过 (Pass=2 / Degraded=2 / **Fail-graceful=1**)

## 实测结果

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_kline(600519)` | ✅ Pass | 10 条日 K,close 1281.55(2026-05-26),source tqcenter,turnover 缺失但 envelope 完整 |
| `calculate_technical_indicators` | ✅ Pass | RSI=21.25 (oversold), MACD warmup_periods=33,MA20 完整,与 get_factor_profile RSI=22.59 一致(微小窗口口径差) |
| `get_realtime_quote(600519)` | ⚠️ Degraded | price=1281.55 / pe=19.47 / **name="" 缺失**(P1 仍存在),source=tqcenter |
| `get_order_book(600519)` | ⚠️ Degraded | `depth_degraded=true` + `db_snapshot_has_quote_without_level2_depth` 显式标识(envelope 完美),bids/asks 各 1 档 0 vol(周末) |
| `get_index_quote("000001")` | ❌ **Fail-graceful** | **§4.5.1 GBK 乱码 ???? 复现!** name="????",price=null,3 源全跪(eastmoney empty/sina 失败/tushare token 错) |

## 🔴 v1 → v2 高优 finding 状态对比

| v1 高优 | v2 复测 |
|---|---|
| §4.5.1 上证指数 GBK 乱码 (S20-F02 / S22-F01) | 🔴 **依旧复现** — name="????" 间歇性出现(本次 eastmoney_index_single empty + sina/tushare 全跪) |
| §4.5.9 get_realtime_quote name 字段缺失 | ⚠️ 仍存在 (name="") |
| §4.5.5 get_order_book 深度缺失但有标识 | ✅ 完美修复 (depth_degraded=true 显式) |
| K 线 RSI 与 factor_profile RSI 不一致(§4.2.5,差 8 倍) | ✅ 完美修复 (21.25 vs 22.59 微差) |

## 🚨 Fail-graceful 详情

`get_index_quote("000001")` envelope OK 但数据全 null + name 乱码:
```
fallback_reason: [
  "eastmoney_index_single returned empty",
  "eastmoney_index失败: 未获取到指数行情",
  "tushare_index_daily失败: 您的token不对，请确认。"
]
```
- 这是 **v1 §4.5.1 跨场景 2 次重复 high finding 的复现**
- 但相比之前,name="????" 不再被代码当成有效数据,fallback chain 4 源全跪后正确返 null + degraded=true(envelope 完整)
- 真正问题:eastmoney_index_single 偶发返空 + sina/tushare 缺 token,**实际数据获取链 0/3 通**

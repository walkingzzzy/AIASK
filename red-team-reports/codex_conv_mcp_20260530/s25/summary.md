# N25 · 可转债与新股

**工具**: get_cb_info / get_ipo_info / get_stock_capital / get_trading_dates / sync_trading_calendar
**调用**: 30 次 · **结论**: pass

## 覆盖
- get_trading_dates：count(3/5/10) + 日期区间(2026 H1=95 日) + provider_contract
- sync_trading_calendar(2026)
- get_ipo_info：type 0/1/2/5、include_future
- get_cb_info：深市活跃债(128136/127045)、SH/退市债(123039/113050/113537/128095)、空码、带后缀、股票码
- get_stock_capital：8 标的 + 历史日期列表 + 非法码

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N25-1 | medium | get_ipo_info 可转债申购(370881)被误标 `type='stock'` |
| F-N25-4 | medium | get_cb_info 对 SH/已退市可转债不可用(tdx_only_mode)，仅深市活跃债(127/128xxx)可查 |
| F-N25-6 | medium | get_stock_capital 非法代码(BADX)返回 ltgb=0/zgb=0 + success=true，零股本静默返回 |
| F-N25-2 | low | get_ipo_info 申购标的 code/name 字段为空(仅 SGCode 有值) |
| F-N25-5 | low | get_cb_info 正股 HSCode 缺前导零(2475 应为 002475) |
| F-N25-3 | low | get_trading_dates 顶层 degraded(tushare_pro→tqcenter 降级，数据本身正确) |

## 正向能力
- **★ get_cb_info(深市活跃债)数据极完整**：转股价/转股日/到期日/剩余规模/回售价/强赎价/信用评级/转股价值/转股溢价率。
- get_stock_capital 流通股/总股本准确：茅台全流通(ltgb=zgb)，H 股公司 ltgb<zgb 正确；支持历史日期列表。
- get_trading_dates 完整 provider_contract(TradingCalendar 标准模型 + freshness 契约)。
- sync_trading_calendar 含人性化 note；2026 H1 95 交易日准确(含节假日休市)。
- 边界处理：空 cb 码→PARAM_ERROR；非法 ipo_type→友好提示；带后缀代码正确归一化。

## standing caveat
周末非交易时段；cb_info 后端 tqcenter 对部分债(SH 11xxxx/已退市)不可用(tdx_only_mode)；数据源主用 tqcenter(tushare_pro 降级)。

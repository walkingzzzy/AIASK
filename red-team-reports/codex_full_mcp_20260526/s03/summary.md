# S03 · 新闻/公告/研报/事件

- **判定**: ⚠️ 通过 (Pass=2 / Degraded=3 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_market_news` | ✅ Pass | 10 条最新公告(2026-05-26),都来自 eastmoney_notice |
| `get_stock_news("600519")` | ✅ Pass | 2 条茅台独董候选人公告(2026-05-22) |
| `get_stock_research("600519")` | ⚠️ Degraded | 3 源全跪空,fallback_reason 显式,envelope 完整 |
| `get_analyst_ranking()` | ⚠️ Degraded | analysts=[], degraded=true, fallback_reason="tushare_report_rc_no_data_for_recent_5_years"(§5.20 完美修复) |
| `event_manager.upcoming_events(7d)` | ⚠️ Degraded | events=[], 周末非交易日预期 |

## v1 → v2 Delta
- ✅ §5.20 analyst_ranking degraded envelope 完美
- ✅ get_stock_news 数据正常,与 event_manager.get_by_code 同源

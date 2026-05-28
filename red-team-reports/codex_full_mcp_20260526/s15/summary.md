# S15 · 数据同步/缓存/calendar

- **判定**: ✅ 通过 (Pass=4 / Degraded=1 / Fail=0)
- **关键修复验证**: 🎯 **§B6 critical_table_stale_alerts 完美修复**

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_cache_stats()` | ✅ Pass | file_count=9 / total_size=0.0158MB / memory_maxsize=512 / 8 个 ttl_config(realtime_quote=5s/kline_intraday=60s/kline_daily=3600s/...) |
| `data_sync_manager(status)` | ✅ Pass | **§B6 修复完美确认** — critical_table_stale_alerts 返回 5 个 alerts:`north_fund_flow severity=high days_stale=648`(政策性 RFC-001),`north_fund_holding warning 56d`,`margin_market_flow/margin_detail warning 4d`,`dragon_tiger high reason=no_data`,critical_alerts_summary={total:5, high:2, warning:3}。market_aux 完整(quote=14877/2264 north_flow rows/35800 margin_detail/125 market_documents),quote_snapshot.coverage_ratio=99.84% |
| `get_trading_dates(count=10)` | ⚠️ Degraded | tushare_pro 不可用 → fallback tqcenter 10 个交易日(20260513~20260526),provider_contract.v1 完整 + 显式 fallback_used=true,quality_flags=[fallback, degraded] |
| `data_warmup(status)` | ✅ Pass | sync_metrics:pending=0/success=2/fail=0/retry=0/lag=0.0/dead_letter=0,cache_stats 嵌套完整 |
| `check_db_freshness([600519, 000001, 000651])` | ✅ Pass | fresh=3/3 stale=0,各 staleness=0d/0d/4d(600519+000001 当日, 000651 周五数据) |

## v1 → v2 Delta
- ✅ **§B6 完美修复确认** — `data_sync_manager.status` 新增 `critical_table_stale_alerts` 字段,5 项 alerts(2 high / 3 warning)。**v1 无此字段**,这是 8 个 B1-B8 修复中最关键的运行时可观测性增强
- ✅ get_trading_dates provider_contract.v1 完整 + standard_model=TradingCalendar
- ✅ check_db_freshness 显式 fresh/stale/missing 三态(无新鲜度警告则空数组)
- ⚠️ tushare_pro 不可用属于政策性(token 限流),tqcenter fallback chain 正常

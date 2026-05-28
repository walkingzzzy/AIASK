# S09 · 情绪/事件/选股

- **判定**: ✅ 通过 (Pass=4 / Degraded=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `event_manager(upcoming_events, 7d)` | ✅ Pass | events=[] count=0 envelope 完整(db.events 表当前无未来 7 日事件,正常空集) |
| `analyze_stock_sentiment(600519)` | ✅ Pass | sentiment=neutral score=37.6,3 分量(price_momentum=19/news=50默认/fund_flow=50),news 缺数据但用 default_neutral_50 显式标记,**含 news_oos_validation bucket_stats 完整 alpha_5d=-0.0165 信号反转 decay 分析** |
| `get_market_sentiment_context(north=5d, margin=10d)` | ⚠️ Degraded | fear_greed=45 / margin_balance=2.87 万亿(2026-05-22 fresh) / 5 个 hot_sectors db.market_blocks 完整。**§2.5 复现:`index_close_out_of_range:close=10.68 expected [1000, 10000]` warning + `index_close_recovered_via_index_quote=4115.5` 自动 recovery**(v1 S20-F04/S22-F03 同 bug,v2 quality_flags 完整捕获,non-blocking) |
| `screener_manager(help)` | ✅ Pass | 8 个 supported_actions(screen/list/save_strategy/run_strategy/technical_screen/list_conditions/combined_screen/help) |
| `calculate_fear_greed_index()` | ✅ Pass | index=45 level=neutral,4 分量(momentum=43 / volatility=55 / volume=43 / breadth=38)完整 |

## v1 → v2 Delta
- ⚠️ **§2.5 上证 close=10.68 vs 真实 4115.5(差 385×) v1→v2 仍复现**(2 次:S20-F04 / S22-F03 → v2 S09)。但 v2 已加 numeric_sanity_failed_index_close warning + index_close_recovered_via_index_quote 自动 recovery,该 bug 已从 silent corruption 升级为 quality_flags 显式
- ⚠️ northbound_flow_*=null 全空(政策性 RFC-001)
- ✅ analyze_stock_sentiment 增加 news_oos_validation 三 bucket(bullish/neutral/bearish) × 三 horizon(5d/10d/20d)的回测 alpha 矩阵,signal_stability=degraded 显式
- ✅ db.market_blocks fallback 提供 5 个 hot_sectors 完整数据

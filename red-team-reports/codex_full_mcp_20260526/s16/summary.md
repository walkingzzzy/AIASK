# S16 · 自选股/告警

- **判定**: ✅ 通过 (Pass=3 / Degraded=0 / Fail-graceful=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `create_indicator_alert(price < 1200)` | 🟡 Fail-graceful | error="condition 无效: &lt;. 支持: >, <, >=, <=, ==" 显式(HTML escape 错误检测正确,工具返回 graceful error 而非崩溃) |
| `check_all_alerts()` | ✅ Pass | 6 个 alerts(2 indicator + 4 combo),triggered=3(rsi<25 / 茅台超卖+破位 / codex_full_mcp_20260522_s12_combo),current_value=1281.55 / RSI=3.24 完整,sub_results 显式逐条件状态 |
| `watchlist_manager(create_group, codex_s16_test)` | ✅ Pass | group_id=group_c7ad7c2f,默认 color=#6366f1,created=true |
| `create_combo_alert(rsi>70 AND macd<0)` | ✅ Pass | combo_id=combo_codex_s16_combo,triggered=false(条件不满足),logic=AND,2 conditions 完整 |

## v1 → v2 Delta
- ✅ check_all_alerts 6 个 alerts 完整持久化(包含 v1 的 codex_full_mcp_20260521_combo 和 codex_full_mcp_20260522_s12_combo,跨 run 数据持久化稳定)
- ✅ create_indicator_alert HTML escape 错误检测显式(护栏正确,但建议前端工具调用时不要 escape 操作符)
- ✅ create_combo_alert sub_results 数组按 condition 顺序返回 bool,combo logic AND/OR 评估正确

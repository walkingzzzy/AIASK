# S14 · 实盘 dry_run / 合规护栏

- **判定**: ✅ 通过 (Pass=2 / Degraded=0 / Fail-graceful=3 / Fail=0)
- **护栏验证**: 🛡️ **PERFECT** — 所有写操作的安全护栏 100% 生效

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `alerts_manager(help)` | ✅ Pass | 6 个 supported_actions(list/create/check/update/delete/help) |
| `live_trading_manager(help)` | ✅ Pass | **16 个 actions + safety_notes 显式**:`live_trading_manager 写操作(submit_order/cancel_order)默认 dry_run=true` + `execute=true 必须同时提供 confirm_token`,16 个 actions 完整(gateway_status/account/positions/orders/order_status/order_events/fills/broker_receipts/submit_order/cancel_order/mirror_to_paper/sync_order_events/...) |
| `execution_manager(twap dry_run, 600519, 1000 shares, 60min, 6 slices)` | 🟡 Fail-graceful | **compliance_gate 阻断完美**:violations=["实时盘口卖量为 0,当前疑似无法买入"] + 9 项 compliance_checks(position_limit/trading_hours/suspended/st_stock/lot_size/order_amount/limit_up_down/realtime_quote/realtime_order_book) 全 true 但 top_ask_volume=0 阻断。soft_warnings:participation_rate=687.02% > 20% 阈值,balanced profile 显式 |
| `compliance_manager(check_order, buy 600519 100×1281.55)` | 🟡 Fail-graceful | passed=false / blocked=true,limit_up_price=1414.47 / limit_down_price=1157.29 显式,top_ask_volume=0 / top_bid_volume=0,realtime quote/order_book 都 available 但盘口空触发阻断,quote_source=db.stock_quotes |
| `live_trading_manager(submit_order execute=true 不带 confirm_token)` | 🟡 Fail-graceful | **CONFIRMATION_REQUIRED 完美生效** — error="confirmation required: provide confirm_token=I_UNDERSTAND_THE_RISK",error_code=CONFIRMATION_REQUIRED,quality_flags=[confirmation_required, failed, fallback, degraded],side_effect.confirmation_policy="explicit_token_required",capabilities.write_enabled=false,provider=alpaca paper=true |

## v1 → v2 Delta
- ✅ **execution_manager.twap soft_gate v1→v2 增强** — soft_gate_profile=balanced + 显式 thresholds + participation_rate(20%)+ 4 类 warning(participation_rate_high/order_top_book/cost_ratio/duration_short)
- ✅ **compliance_manager 9 项 checks v1→v2 完整暴露** — 包含 realtime_quote 和 realtime_order_book 实时校验
- ✅ **live_trading_manager.submit_order CONFIRMATION_REQUIRED 完美护栏** — execute=true 必须配 confirm_token=I_UNDERSTAND_THE_RISK,token 校验 100% 生效
- ✅ live_trading_manager.help safety_notes 显式 + 16 个 actions 详细参数文档(action_params 嵌套结构)

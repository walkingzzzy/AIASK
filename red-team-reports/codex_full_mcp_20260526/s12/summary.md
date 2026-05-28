# S12 · 模拟交易

- **判定**: ✅ 通过 (Pass=4 / Degraded=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `paper_trading_manager(create_account, 100w)` | ✅ Pass | account_id=be265174,user_id=codex_full_mcp_20260526,initial_capital=1000000 |
| `paper_trading_manager(place_order buy 600519 100shares market)` | ⚠️ Degraded | order_id=ab086261 status=filled,price=1281.55 amount=128155 commission=38.45,**engine_warnings 显式两条**:`market_orders_bypass_matching=true: matching_engine.running=false, 市价单直接成交未经撮合,limit 订单将卡 pending` + `nav_engine.running=false: 账户 NAV 不会自动更新`(envelope 透明度高) |
| `paper_trading_manager(list_accounts)` | ✅ Pass | 返回 1 个账户(默认账户 524dfc8f from 2026-05-24)。**注意:**新建的 be265174 不在 list_accounts 因 user_id 过滤(本工具只列 user_id="default"),与 v1 §S12 行为一致 |
| `paper_trading_manager(summary be265174)` | ✅ Pass | total_value=999961.55,return_pct=-0(成交价瞬时无 P&L),current_capital=871806.55,reconciliation drift_detected=false 完整持仓快照 |
| `paper_trading_manager(orders/positions be265174)` | ✅ Pass | orders=1 笔(ab086261 buy 1281.55×100),positions=1 笔(market_value=128155 cost=1281.55 sellable=0 当日 T+1) |

## v1 → v2 Delta
- ✅ engine_warnings 完整暴露(matching_engine + nav_engine 双 daemon 状态),v1 仅返回 success=true 隐式
- ✅ reconciliation drift_detected=false 详尽 cash/positions 前后对比,持仓无漂移
- ✅ T+1 sellable=0 正确生效(A 股市场规则)
- ⚠️ list_accounts user_id 过滤行为与 v1 一致(per-user 隔离设计意图)

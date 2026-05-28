# S08 · 组合/风险

- **判定**: ✅ 通过 (Pass=5 / Degraded=0 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `portfolio_manager(create, S08_pf, 100w)` | ✅ Pass | portfolio_id=4 写入 db.portfolios,trace_id 完整,side_effect=stateful 正确标识 |
| `analyze_portfolio_risk(4 stocks, 120d)` | ✅ Pass | VaR(95%)=9804 元 / CVaR=12648 元 / 年化波动率 9.52%,coverage 4/4 used,degraded=false |
| `stress_test_portfolio(4 scenarios)` | ✅ Pass | market_crash -20% / sector_rotation -2% / interest_rate_hike -5% / black_swan -30%,signed_return_percent 均显式 |
| `generate_trade_plan(600519, balanced)` | ✅ Pass | direction=avoid / confidence=0.79 / regime=bear_calm,8 个 key_levels(支撑 1274.22 / 阻力 1395.37 强度 4),含 hit_rate_detail+by_regime+similar_patterns 完整证据链。**§4.5.1 平静期 GBK 乱码不复现**(name="" 而非 "????") |
| `optimize_portfolio(risk_parity, 4 stocks)` | ✅ Pass | weights={600519:0.199, 000001:0.255, 000651:0.277, 600036:0.269},风险平价收敛 |

## v1 → v2 Delta
- ✅ generate_trade_plan 完整决策链(market_regime + signal_summary + scenarios + key_levels + position_management),无 high finding
- ✅ optimize_portfolio risk_parity 4 资产收敛(v1 偶现 max_iter 警告,v2 平稳)
- ✅ analyze_portfolio_risk dropped_holdings=0 完美覆盖
- ⚠️ generate_trade_plan.name="" — **§4.5.9 仍存在**(realtime_quote name 字段空,但被 generate_trade_plan 透传,non-blocking)

# S11 · 决策融合

- **判定**: ✅ 通过 (Pass=3 / Degraded=2 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_unified_decision(600519, balanced)` | ⚠️ Degraded | action=watch / final_score=35.19 / confidence=0.366,**veto_reason="indicative_order_blocked"** + compliance gate blocking=true,4 个 data_provenance,quality_flags=[fallback, partial, degraded](anonymous_user 缺 user_id),建议 fallback。8 个 reasons + 8 个 risks,raw_ai_action=watch |
| `should_i_sell(600519, buy=1500, hold=120d)` | ✅ Pass | recommendation=sell / score=55,profit_pct=-14.56% / target_sell=1458.86 已跌破,3 reasons + 1 risk(RSI 超卖反弹可能),decision_mode=hybrid_score_plus_context |
| `should_i_buy(600519, balanced)` | ✅ Pass | recommendation=avoid / score=20 / confidence=30 / **buy_probability=1.27% band=low**,完整 prediction_quality(ECE=0.0707/Brier=0.005/sample=12)+ probability_calibration 三 threshold 回测(40/60/80),threshold_inversion warning 显式,prediction_interval [-6.43%, +1.21%] coverage_proxy=0.8 |
| `decision_consensus(600519)` | ✅ Pass | **§3.3 完美修复确认** — 3 工具自动调度,directions={watch:1, sell:2},agreement_ratio=0.6667 ≥ threshold 0.6,**actionable_recommendation="sell"**,tools_agree=[should_i_sell, build_stock_context],tools_split=[should_i_buy],rationale="2/3 tools agree on 'sell' (ratio 0.67 >= threshold 0.6)" |
| `build_stock_context(600519)` | ⚠️ Degraded | recommendation=sell / score=24,8 个 evidence(valuation/technical/fundamental/momentum/risk),market_snapshot+fund_flow_snapshot 完整,industry_chain_snapshot.matched=false partial(酿酒 keyword 未匹配产业链 db),quality_flags=[fallback, partial, degraded] 显式 |

## v1 → v2 Delta
- ✅ **§3.3 decision_consensus 完美修复**(v1 不存在此 meta-tool,v2 全新,跨工具方向一致性自动判定 sell agreement=0.67)
- ✅ should_i_buy 增加 prediction_quality(ECE/Brier/calibration_bucket)+ threshold_backtest 三档 + threshold_inversion warning(v1 仅基础 score)
- ⚠️ get_unified_decision compliance veto 正确生效(blocking=true 阻断 indicative_order)
- ⚠️ build_stock_context industry_chain_snapshot.matched=false(酿酒 keyword 在 db.chains 缺失,与 v1 §S20 同因)

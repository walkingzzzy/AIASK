# S13 · 策略工厂/factory

- **判定**: ⚠️ 通过 (Pass=2 / Degraded=2 / Fail-graceful=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `governance_check_workflow(factor, ic_history=[0.05,0.04,0.03,0.02,0.01])` | ⚠️ Degraded | **online_offline:inconsistent 显式复现**(backtest slippage=0bps vs execution=5bps + market_impact 0bps vs 3bps),snapshot_id=12,decay_status=stable / IC_mean=0.03 / half_life=1.8 periods,crowding_band=low,strategy_health=healthy,quality_flags=[degraded] **§S19/§S21 v1 累计 3 次 finding v2 仍复现** |
| `strategy_manager(lifecycle_scan)` | ✅ Pass | scanned=0 / transitions=[] / blocked=[] / reviews=[] envelope 正常(无策略需要 lifecycle 转换) |
| `strategy_manager(factory_status)` | ⚠️ Degraded | **§S19-F12 / §S21 quality_baseline finding 完美复现** — submitted=143 全 D 级 / zero_signal_rate=100% / strict_incubation_ready_rate=0% / promotion_ready_rate=0% / quality_pass_rate=99.3% 但 raw_b_or_above=0%。最近 5 个 factory_run governed_blocked_ratio=0.927 高度阻塞,4 次连续 warning `governed_candidate_pool_blocked_ratio_high + factor_research_history_stale_governed_pool_active`。signal_quality_registry 暴露 buy_probability calibration_gap=-0.0167 / sentiment news_alpha_5d=-0.0165 / capability_health 14 个 capability 全 healthy |
| `strategy_manager(incubation_overview)` | 🟡 Fail-graceful | error_code=`STRATEGY_MANAGER_INVALID_PARAMS` + detail.required_any_of=[strategy_id, id] 显式,degraded=true,success=false 正确路径(参数校验生效) |

## v1 → v2 Delta
- ⚠️ **§S19/§S21 governance online_offline:inconsistent v1→v2 仍复现**(backtest 0bps vs execution 5bps slippage gap),non-blocking,quality_flags=[degraded] 完整暴露
- ⚠️ **§S19-F12 / §S21 factory submitted=143 全 D zero_signal=100% v1→v2 政策性持续**(governed_pool stale + provisional_pool_only,需独立 PR 修复 ic_history_rows_below_min / multiple_testing_risk_high 阻塞)
- ✅ governance_check_workflow envelope:5 维度(factor_decay/crowding/model_drift/strategy_health/online_offline_consistency)+ 显式 hard_gate=false 信号
- ✅ strategy_manager.incubation_overview 缺参时 STRATEGY_MANAGER_INVALID_PARAMS 显式 error_code(护栏正确)
- ✅ factory_status capability_health 14 个 capability 全 healthy=true(v1 同表现)

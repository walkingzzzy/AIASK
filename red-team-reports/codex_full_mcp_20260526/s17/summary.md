# S17 · 估值器/DCF/DDM

- **判定**: ✅ 通过 (Pass=5 / Degraded=0 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `scenario_dcf_valuation(600519, 消费, 5y)` | ✅ Pass | base_revenue=539.09 亿,3 情景:Bull(p=25%, growth=15%, IV=2001亿) / Base(p=50%, growth=10%, IV=1206亿) / Bear(p=25%, growth=5%, IV=634亿),**weighted_intrinsic=1261.57 亿** |
| `ddm_valuation(600519, div=25, g=5%, r=8%)` | ✅ Pass | Gordon 模型 IV=875/股(next_div=26.25 / 25/(0.08-0.05)),source=db.financials |
| `relative_valuation(600519, [pe, pb])` | ✅ Pass | 8 个酒类 peers,industry pe_mean=18.60 / pb_mean=2.55,**target PE=19.91 percentile=75 / PB=6.07 percentile=100 extreme deviation_risk** + 完整 peer_pool_build(36 候选→8 final, 4 个 filter 状态)+ invalid_peer_metrics(10 negative PE) |
| `get_historical_valuation(600519, 30d)` | ✅ Pass | 8 个去重数据点(raw=128 dedup=8 missing=0),pe range 19.47~20.05,pb range 5.92~6.12,completeness_ratio=1.0 |
| `dcf_valuation(600519, growth=8%, 5y)` | ✅ Pass | **driver_v2 完整投影** — 5 年 projection 完整(revenue/ebit/nopat/depreciation/capex/delta_nwc/fcf/pv_fcf),wacc=7.43% / pv_sum=905.94 亿 / pv_terminal=9428.46 亿 / **intrinsic_value=1.03 万亿**,profit_basis.strategy=latest_positive_net_profit fallback safe path |

## v1 → v2 Delta
- ✅ scenario_dcf_valuation 行业模板(消费)概率加权三情景完整(v1 同表现)
- ✅ relative_valuation peer_pool_build 4 状态过滤诊断(size/quality/growth/cashflow)+ relaxation_reasons 完整(growth_filter_relaxed_due_to_missing_data)
- ✅ get_historical_valuation 完整 data_quality(raw/dedup/missing/invalid)+ stats 5 项分位数
- ✅ dcf_valuation driver_v2 5 年 projection 显式 + wacc_breakdown(cost_of_equity/cost_of_debt/weights/tax)+ profit_basis fallback 完整审计

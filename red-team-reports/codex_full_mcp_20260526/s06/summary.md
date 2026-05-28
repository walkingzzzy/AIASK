# S06 · 因子/量化

- **判定**: ✅ 通过 (Pass=4 / Degraded=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_factor_profile(600519, RSI/MACD/momentum)` | ✅ Pass | RSI=21.25 / industry_rank=34/37 / industry_total=37 完整(**§B4 修复确认**), industry_avg=27.86, percentile_1y=8.5%, trend=down, rolling_zscore=-1.12 |
| `calculate_factor(600519, momentum)` | ✅ Pass | momentum_20d=-0.121, source=db.kline_aggregated, 样本量=20, financial_required=false |
| `find_similar_patterns(600519, 20d)` | ✅ Pass | 5 个相似形态,聚合 hit_rate(5d)=60%,std=0.087,window=2024-09-12~2024-10-11 +0.04 / 2025-03-15 -0.02 等,quality_gate=passed |
| `get_signal_hit_rate(600519, rsi_oversold)` | ✅ Pass | 30 个历史样本,hit_rate(5d)=0.68 / hit_rate(10d)=1.0 / hit_rate(20d)=1.0,平均超额收益 +2.4% / +5.1% / +9.7% |
| `get_conditional_returns(600519, rsi<30 & vol_ratio>2)` | ⚠️ Degraded | 仅 8 个样本(samples<10 panel insufficient warning),forward_5d_avg=+1.8%,quality_flags=[low_sample_size] |

## v1 → v2 Delta
- ✅ **§B4 修复确认** — `get_factor_profile.industry_total` 不再为空(industry_total=37)
- ✅ get_signal_hit_rate / find_similar_patterns 全 envelope 完整
- ⚠️ get_conditional_returns 在 panel<10 时正确暴露 quality_flags(non-blocking)

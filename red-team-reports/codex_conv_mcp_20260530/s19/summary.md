# N19 · 组合风险与压力测试

**工具**: analyze_portfolio_risk / stress_test_portfolio / risk_manager(calculate_var/stress_test/risk_exposure)
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- `analyze_portfolio_risk`: codes+weights / holdings / 含非法代码 / 多 lookback(10/60/252) / 空
- `risk_manager`: calculate_var(parametric/historical/monte_carlo × confidence 0.5/0.95/0.99/0.999) / risk_exposure / stress_test(单场景/4场景/未知场景) / 空组合
- `stress_test_portfolio`: 4 场景 / 子集场景 / 含非法代码 / 单股

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N19-2 | **high** | `risk_manager(stress_test)` 未知场景名(`bogus_scenario_zzz`)**静默回退为 market_crash**，无报错，AI 误以为测了自定义场景 |
| F-N19-1 | medium | `stress_test_portfolio` 与 `risk_manager(stress_test)` 同名场景损失口径不一致(market_crash 20% vs 21%，black_swan 30% vs 32.3%) |
| F-N19-4 | medium | `sector_rotation` 场景未正确识别个股行业——300750(宁德/科技)仅按"其他"-2%而非科技-10% |
| F-N19-5 | medium | `risk_exposure` 的 `avg_daily_amount` 量纲不一致(000858=2.87e9 vs 600519=2.07e6)，导致流动性评估失真 |
| F-N19-3 | low | confidence=0.999 描述显示"100% confidence"(四舍五入误导) |
| F-N19-6 | low | `liquidity_coverage_pct` 出现 5 万% 量级异常值(与 F-N19-5 同源) |

## 正向能力（含重要对照）
- **★ analyze_portfolio_risk 对无数据代码处理正确**：`dropped_holdings`+`coverage(requested/used/dropped)`+剩余股重新归一化。这与 N18 的 optimize_portfolio(F-N18-1 把有效股丢弃、保留垃圾代码)形成鲜明对照，**证明 F-N18-1 是 optimize_portfolio 特有的列对齐 bug**，非全局问题。
- VaR 三方法产出差异化合理值，confidence 单调性正确。
- `risk_exposure` 极丰富：HHI / effective_positions / style_exposure(PE/PB/ROE/valuation_tilt/size_bucket) / liquidity_risk / 20 日 daily_monitor。
- 权重自动归一化；holdings 与 codes+weights 结果一致。
- 空组合/空 holdings 优雅处理(empty_portfolio / invalid_params + quick_start)。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的，VaR/波动率为日频小样本估计；压力测试为情景假设而非历史模拟。

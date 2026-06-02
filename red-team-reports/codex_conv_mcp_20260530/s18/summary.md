# N18 · 组合优化

**工具**: optimize_portfolio
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- 6 方法：equal_weight / risk_parity / mean_variance / black_litterman / risk_budget / max_sharpe
- 参数：max_weight(0.1/0.35/0.5)、risk_aversion(0.01/1/10)、risk_free_rate(-0.05/0.03/0.1)、lookback_days(30/252/500)、views(absolute/relative)、market_weights、risk_budgets
- 边界：单股、2股、8股、非法代码、方法名错误、预算长度不匹配

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N18-1 | **high** | 含无数据代码时**静默丢弃有效股、保留垃圾代码**：`[600519,BADX,000651]`→`{600519:0.5, BADX:0.5}`，真实股 000651 被丢、无数据 BADX 获 0.5 权重（权重-列错位，数据完整性 bug） |
| F-N18-2 | **high** | `black_litterman` relative 视图产生病态杠杆解 `{600519:92.93, 000001:-92.43}`，185x 杠杆/152% 波动，无 long-only/杠杆/max_weight 约束与告警 |
| F-N18-7 | medium | `risk_budgets` 长度与股票数不匹配 → 裸 numpy 广播错误，无入口校验 |
| F-N18-3 | medium | `max_weight=0.1`(4 股不可行) 静默回退等权 0.25，仍声称 constraints_applied=0.1 |
| F-N18-4 | low | `mean_variance` 的 risk_aversion(0.01/1/10) 对权重几乎无影响 |
| F-N18-5 | low | `risk_parity` lookback=30 退化为精确等权，无低样本告警 |
| F-N18-6 | low | 负 `risk_free_rate` 使负收益组合 sharpe 虚高为正(+8.45) |

## 正向能力
- 6 种方法全部真实可用（非回退占位），输出紧凑（权重 + 组合指标）。
- 权重和 ≈ 1.0（1e-13 精度），求解器收敛良好。
- risk_budget 的 risk_contributions 与目标预算高度吻合。
- max_sharpe 可行 max_weight 约束严格遵守。
- BL 无视图时后验=市场先验（数学正确）。
- 非法 method 优雅拒绝并列出 Supported 方法。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的，协方差估计样本小，权重/收益指标仅供工具行为审计。

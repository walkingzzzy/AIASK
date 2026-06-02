# N20 · Barra 多因子风险分解

**工具**: analyze_portfolio_risk_barra
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- 1/2/3/4/8 股组合，多标的（8 只标准池逐一单股）
- lookback_days：20/60/120/250/252/500
- 边界：空、全无效代码、含非法代码、零权重、负权重(long-short)、未归一化权重

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N20-1 | **high** | Barra 5 因子中 **size/value/quality 恒为 0.0**（30+ 次调用全部），仅 momentum/volatility 有效——3/5 因子未实现，风格归因是占位 |
| F-N20-3 | **high** | Barra **不归一化权重**：[2,2] 的 exposure 是 [0.5,0.5] 的 4 倍，与 analyze_portfolio_risk(自动归一化)冲突，未归一化夸大风险 |
| F-N20-2 | medium | volatility 因子在 lookback≤60 时静默置 0（需 ≥~120 日），无低样本告警 |
| F-N20-4 | medium | 含无数据代码时缺 `dropped_holdings` 透明字段（仅 meta 计数差可推断），不如 analyze_portfolio_risk |
| F-N20-5 | low | 接受负权重(long-short)无 long-only 约束 |

## 正向能力
- 输出结构完整：total_risk / factor_risk / specific_risk + factor_contribution/specific_contribution(和恒=1.0) + portfolio_exposure + factor_names。
- momentum/volatility 两因子产出差异化合理值（000858 momentum 高、300750 volatility 高）。
- 计算确定性良好（同输入逐位一致）。
- 零权重 holding 正确忽略；全无效标的优雅处理。
- lookback=500 被静默截断到可用 ~250 日（结果与 252 一致）。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的，Barra 因子协方差为小样本估计；单只标的"组合"的因子分解仅供工具行为审计。

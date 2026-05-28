# S04 · 财务/估值

- **判定**: ✅ 通过 (Pass=3 / Degraded=0 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_financials("600519")` | ✅ Pass | reportDate=2026-03-31, revenue=539亿, ROE=10.06%, EPS=87.02, source=sqlite, **quality_gate=passed**(全 6 checks 通过) |
| `dcf_valuation("600519")` | ✅ Pass | intrinsic_value=4019亿, WACC=7.425%, 5 年预测 + 27 sensitivity 矩阵, profit_basis=latest_positive_net_profit |
| `valuation_consensus("600519")` | ✅ Pass | **§3.2 P1 完美修复 — relative_pe=2744.23 计算成功**(行业 PE 31.54 × EPS 87.02),DCF/DDM 失败但 envelope 完整,consensus_recommendation 中位数+medium 置信度 |

## v1 → v2 Delta
- ✅ §3.2 valuation_consensus relative_pe `OperationalError: no such column: code` 完美修复
- ✅ dcf_valuation 27 项 sensitivity matrix 输出完整

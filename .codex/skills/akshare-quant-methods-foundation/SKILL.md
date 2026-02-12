---
name: akshare-quant-methods-foundation
description: 量化方法基础能力：时间序列、相关性、协方差与风险度量的落地流程。
---

# 目标
提供量化基础方法的可执行流程，支撑后续策略研究与风险控制。

# 使用流程
- 数据准备：用 `get_kline_data` 获取收益率序列。
- 风险度量：用 `analyze_portfolio_risk` 输出波动率、回撤、夏普等。
- 相关性/协方差：用 `optimize_portfolio` 的输入矩阵输出相关性提示（如无矩阵则提示限制）。
- 结果解读：强调样本区间与市场环境的影响。

# 失败与兜底
- 历史数据不足：缩短区间或减少标的数量。
- 工具分流：`analyze_portfolio_risk` 失败时改用 `risk_manager(action=calculate_var)` 与 `stress_test_portfolio` 输出最小风险指标集。

# 参考
- 组合优化与风险工具：`optimize_portfolio`、`analyze_portfolio_risk`。

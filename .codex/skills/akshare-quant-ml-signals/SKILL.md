---
name: akshare-quant-ml-signals
description: 机器学习信号研究的流程与边界，强调可解释性与回测验证。
---

# 目标
在量化场景中合理使用机器学习信号，并确保可验证与可解释。

# 使用流程
- 特征准备：用 `calculate_technical_indicators` 与 `calculate_factor` 生成特征。
- 信号评估：用 `calculate_factor_ic` 验证相关性与稳定性。
- 策略回测：用 `run_simple_backtest` 或 `run_batch_backtest` 验证效果。
- 风险复核：用 `analyze_portfolio_risk` 与 `stress_test_portfolio` 检查风险暴露。
- 结果报告：输出样本期、样本外与敏感性说明。

# 失败与兜底
- 特征不稳定：提示减少特征或延长样本期。
- 过拟合风险高：提示进行样本外验证并降低复杂度。

# 参考
- 技术指标与因子工具：`calculate_technical_indicators`、`calculate_factor`。

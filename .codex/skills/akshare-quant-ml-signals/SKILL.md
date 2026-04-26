---
name: akshare-quant-ml-signals
description: 机器学习信号研究的流程与边界，强调可解释性与回测验证。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["model_governance", "research_disclosure"]
role_tags: ["quant", "research"]
last_runtime_verified_at: "2026-04-19"
---

# 目标
在量化场景中合理使用机器学习信号，并确保可验证与可解释。

# 使用流程
- 特征准备：用 `calculate_technical_indicators` 与 `calculate_factor` 生成特征。
- 信号评估：用 `calculate_factor_ic` 验证相关性与稳定性。
- 概率诊断：概率输出的校准、区间与不确定性诊断统一使用 `prediction_diagnosis_workflow`。
- 策略回测：用 `run_simple_backtest` 或 `run_batch_backtest` 验证效果。
- 风险复核：用 `analyze_portfolio_risk` 与 `stress_test_portfolio` 检查风险暴露。
- 结果报告：输出样本期、样本外与敏感性说明。

# 失败与兜底
- 特征不稳定：提示减少特征或延长样本期。
- 过拟合风险高：提示进行样本外验证并降低复杂度。
- 工具分流：`calculate_factor_ic` 失败时改用 `backtest_factor` 评估信号分层收益；`run_batch_backtest` 失败时降级到 `run_simple_backtest`。

# 参考
- 技术指标与因子工具：`calculate_technical_indicators`、`calculate_factor`。

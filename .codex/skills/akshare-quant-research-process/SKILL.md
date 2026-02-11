---
name: akshare-quant-research-process
description: 量化研究流程编排：数据→信号→组合→回测→执行与复盘。
---

# 目标
用统一流程组织量化研究与验证，输出可复用结果。

# 使用流程
- 数据准备：用 `get_kline_data` 拉取数据；必要时用 `data_warmup` 预热。
- 信号与因子：用 `get_factor_library` 确认可用因子，再用 `calculate_factor` 与 `calculate_factor_ic` 验证。
- 组合构建：用 `optimize_portfolio` 生成权重，或使用等权方案。
- 回测验证：用 `run_simple_backtest` 或 `run_batch_backtest` 验证策略表现。
- 风险检查：用 `analyze_portfolio_risk`、`stress_test_portfolio` 输出风控指标。
- 结果存档：用 `backtest_manager` 保存结果以便对比。

# 失败与兜底
- 因子不可用：先返回因子列表并提示替代因子。
- 回测失败：缩短区间或减少标的数量。

# 参考
- 因子与回测工具：`calculate_factor`、`run_simple_backtest`、`run_batch_backtest`。

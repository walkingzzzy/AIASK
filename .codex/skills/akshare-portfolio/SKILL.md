---
name: akshare-portfolio
description: 回测、组合优化、风险分析、压力测试以及组合/回测结果管理等场景使用。
---

# 目标
在组合与回测场景中输出可复用结果，并在需要持久化/查询历史时使用管理器工具。

# 使用流程
- 回测
  - 单股回测：`run_simple_backtest`
  - 批量回测：`run_batch_backtest`
- 组合
  - 组合优化：`optimize_portfolio`
  - 风险分析：`analyze_portfolio_risk`
  - 压力测试：`stress_test_portfolio`
- 历史/持久化（需要保存或查询时）
  - 组合管理：`portfolio_manager`
  - 回测管理：`backtest_manager`
  - 风险管理：`risk_manager`
  - 绩效查询：`performance_manager`

# 失败与兜底
- 股票列表过少：提示扩充样本或降低分组数量。
- 回测日期缺失：使用工具默认日期或提示用户补充。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。

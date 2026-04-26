---
name: akshare-portfolio
description: 回测、组合优化、风险分析、压力测试以及组合/回测结果管理等场景使用。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["portfolio_suitability", "backtest_lineage"]
role_tags: ["buy_side_pm", "quant", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 用于定义回测、组合优化、风险分析、压力测试与结果管理的推荐流程，不代表文中列出的回测链路、风险模型、持久化能力与历史结果管理在当前环境都已完成统一口径验证。
>
> 实际可用能力应以当次运行时工具注册结果、回测参数披露、风险模型返回、数据窗口与执行结果为准；若缺少成本参数、基准、风控证据或持久化结果，应明确标注为“分析结果/待确认”，而不是默认视为可直接执行或可直接比较。


# 目标
在组合与回测场景中输出可复用结果，并在需要持久化/查询历史时使用管理器工具。

# 使用流程
- 回测
  - 单股回测：`run_simple_backtest`
  - 批量回测：`run_batch_backtest`
- 组合
  - 组合优化：`optimize_portfolio`
  - 风险分析：`analyze_portfolio_risk`；需要 Barra 风格分解时用 `analyze_portfolio_risk_barra`
  - 压力测试：`stress_test_portfolio`
- 历史/持久化（需要保存或查询时）
  - 组合管理：`portfolio_manager`
  - 回测管理：`backtest_manager`
  - 风险管理：`risk_manager`
  - 绩效查询：`performance_manager`

# 失败与兜底
- 股票列表过少：提示扩充样本或降低分组数量。
- 回测日期缺失：使用工具默认日期或提示用户补充。
- 工具分流：`run_batch_backtest` 失败时降级为 `run_simple_backtest` 分标的执行；`optimize_portfolio` 失败时先用等权并通过 `risk_manager` 做风险复核。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。

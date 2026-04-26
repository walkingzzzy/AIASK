---
name: akshare-asset-allocation
description: 资产配置、分散与再平衡流程设计与落地，结合风险承受能力与时间跨度给出可执行流程。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["portfolio_suitability", "research_disclosure"]
role_tags: ["buy_side_pm", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 用于定义资产配置与再平衡的推荐流程，不代表文中涉及的画像采集、优化求解、风险评估、组合持久化与提醒链路在当前环境都已自动打通。
>
> 实际可用能力应以当次运行时工具注册结果、风险模型返回、约束参数完整性与执行链路状态为准；若缺少画像、风控、合规或持久化证据，应明确标注为“配置建议/待确认”，而不是默认视为可直接执行。


# 目标
将“风险承受能力 + 投资期限 + 约束条件”转化为可执行的资产配置、分散与再平衡流程。

# 使用流程
- 画像采集：询问风险承受能力、投资期限、收益目标、可用资金、流动性与最大回撤约束。
- 标的范围：确认资产范围（默认 A 股/ETF），必要时用 `search_stocks` 定位标的。
- 数据准备：对候选标的用 `get_kline_data` 拉取历史数据。
- 权重配置：用 `optimize_portfolio` 生成权重；用 `analyze_portfolio_risk` 与 `stress_test_portfolio` 验证风险。
- 组合落地：如需持久化，用 `portfolio_manager` 创建组合，并通过 `portfolio_manager(action=add_holding)` 记录初始仓位。
- 再平衡规则：明确频率、触发阈值、现金比例与约束；必要时用 `alerts_manager` 设置提醒。
- 复盘与调整：按周期获取持仓与收益，评估偏离并提示再平衡（不直接给买卖指令）。

# 失败与兜底
- 风险画像缺失：先输出风险问卷与时间跨度要求。
- 标的过少：提示增加候选或降低约束。
- 数据不全：提示缩短时间或更换流动性更好的标的。
- 工具分流：`search_stocks` 失败时改用 `semantic_stock_search`；`optimize_portfolio` 失败时先给等权方案，再用 `analyze_portfolio_risk` 与 `stress_test_portfolio` 做风险复核。

# 参考
- 使用与持久化相关的管理器：`portfolio_manager`、`alerts_manager`。

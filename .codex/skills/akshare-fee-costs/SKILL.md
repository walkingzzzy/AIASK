---
name: akshare-fee-costs
description: 费用与成本识别、长期影响评估与敏感性分析。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["cost_disclosure", "research_disclosure"]
role_tags: ["buy_side_pm", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 用于定义费用与交易成本分析的推荐流程，不代表文中涉及的费率参数、滑点假设、回测执行路径与结果口径在当前环境都已默认统一。
>
> 实际分析结论应以本次任务显式披露的手续费、印花税、过户费、滑点、调仓频率和回测参数为准；若缺少成本参数或执行证据，应明确标注不确定性，而不是默认视为真实交易成本。


# 目标
让投资者明确费用类型与长期影响，并用工具量化不同费率的回测差异。

# 使用流程
- 费用采集：询问券商佣金、印花税、过户费、滑点假设与交易频率。
- 基线回测：用 `run_simple_backtest`（或 `run_batch_backtest`）设置真实费率与滑点参数。
- 敏感性分析：在不同费率/滑点下重复回测，形成对比表。
- 结果解读：强调费用对长期复利的侵蚀，并给出降低成本的方向（不含具体投资建议）。
- 可选存档：如需记录，用 `backtest_manager` 保存结果。

# 失败与兜底
- 无法提供费率：提供默认费率区间并标注不确定性。
- 数据不足：缩短回测区间或减少标的数量。
- 工具分流：`run_batch_backtest` 失败时降级为 `run_simple_backtest` 分标的测试；`backtest_manager` 不可用时输出本次参数与结果对照表作为临时留痕。

# 参考
- 回测参数中的成本模型：`order_cost`、`slippage_rate` 等。

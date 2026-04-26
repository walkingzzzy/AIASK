---
name: akshare-macro-options-alerts
description: 宏观指标、期权链、预警与情绪的组合编排流程。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["market_data_lineage", "risk_disclosure"]
role_tags: ["research", "trader", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 用于定义宏观、期权、情绪与预警的组合查询路径；当前代码层存在对应原子工具，但 BFF/Web 仍以 `/macro`、`/data`、`/options`、`/alerts`、`/sentiment` 分域入口为主，尚无统一的“宏观-期权-预警联动”单页工作台。
>
> 因此，只要出现跨域编排、组合告警或多源摘要，就应明确说明这是“编排结果”，而不是前后端现成的单接口闭环能力。

# 目标
将宏观、期权、情绪与预警能力形成可复用的查询与监控流程。

# 使用流程
- 宏观指标：用 `get_macro_indicator` 获取 cpi/ppi/pmi/m2 等时间序列。
- 情绪指标：用 `analyze_stock_sentiment` 或 `calculate_fear_greed_index`。
- 期权链：用 `get_option_chain` 获取 ETF 期权链与流动性概览。
- 预警设置：用 `create_indicator_alert` 或 `create_combo_alert` 创建提醒条件。
- 结果输出：汇总为“宏观-情绪-期权-预警”四段结构化结果。

# 失败与兜底
- 宏观指标不可用：提示更换指标或缩短时间范围。
- 期权标的不支持：提示仅支持 50ETF/300ETF。
- 工具分流：`get_option_chain` 失败时改用 `options_manager(action=list)`；预警创建失败时改用 `alerts_manager(action=create)` 并返回可复核参数。

# 参考
- 预警如需持久化管理，可使用 `alerts_manager`。

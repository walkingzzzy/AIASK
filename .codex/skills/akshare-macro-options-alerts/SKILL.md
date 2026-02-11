---
name: akshare-macro-options-alerts
description: 宏观指标、期权链、预警与情绪的组合编排流程。
---

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

# 参考
- 预警如需持久化管理，可使用 `alerts_manager`。

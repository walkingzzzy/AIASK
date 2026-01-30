---
name: akshare-fundamental
description: 基本面、财务指标、估值模型、情绪指数，以及智能诊断/自然语言选股解析等需求时使用；适用于“财报/估值/综合诊断/情绪”场景。
---

# 目标
提供结构化的基本面与估值结果，并在需要时给出简明解释。

# 使用流程
- 基本信息与财务：用 `get_stock_info` 与 `get_financials`。
- 估值：
  - 指标：`get_valuation_metrics` / `get_historical_valuation`。
  - 模型：`dcf_valuation` / `ddm_valuation`。
  - 对比估值：`relative_valuation`。
- 情绪：个股用 `analyze_stock_sentiment`，全市场用 `calculate_fear_greed_index`。
- 语义能力：
  - 自然语言选股解析：`parse_selection_query`。
  - 智能诊断：`smart_stock_diagnosis`。
  - 日报：`generate_daily_report`。

# 失败与兜底
- 财务/估值数据为空：提示数据源可能缺失，建议改用 `get_stock_info` 基础字段。
- DDM 增长率 >= 要求回报率：要求用户调整参数。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。
- 读取 `references/aliases.md` 了解兼容参数名与别名。

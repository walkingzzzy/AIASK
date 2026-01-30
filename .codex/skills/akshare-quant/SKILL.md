---
name: akshare-quant
description: 技术指标计算、K线形态识别、因子计算与IC/分组回测、相似K线/相似股票检索等量化分析场景使用。
---

# 目标
在量化分析中优先调用最贴近需求的指标/因子/向量工具，输出可复用的结构化结果。

# 使用流程
- 技术指标：用 `calculate_technical_indicators`。
- K线形态：用 `check_candlestick_patterns`；若需可用形态列表用 `get_available_patterns`。
- 因子：用 `get_factor_library` 获取支持因子，随后用 `calculate_factor`、`calculate_factor_ic` 或 `backtest_factor`。
- 相似形态/股票：
  - 相似K线：`search_by_kline`。
  - 相似股票：`search_similar_stocks`。
  - 语义选股：`semantic_stock_search`。

# 失败与兜底
- 数据不足：提示用户减少周期或选择更高流动性股票。
- 因子不支持：先返回可用因子列表。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。

---
name: akshare-quant
description: 技术指标计算、K线形态识别、因子计算与IC/分组回测、相似K线/相似股票检索等量化分析场景使用。
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

> 校准说明：本 skill 主要提供量化分析工具的推荐调用路径与分流顺序，不代表文中涉及的所有指标、因子、相似检索与管理器路径在当前环境都已完成同口径验证。
>
> 实际分析能力、参数支持范围和结果一致性应以当次运行时注册结果、数据可得性、回测/指标契约及实时返回为准；若与当前工具行为不一致，应以后者为准。


# 目标
在量化分析中优先调用最贴近需求的指标/因子/向量工具，输出可复用的结构化结果。

# 使用流程
- 技术指标：用 `calculate_technical_indicators`。
- K线形态：用 `check_candlestick_patterns`；若需可用形态列表用 `get_available_patterns`。
- 因子：用 `get_factor_library` / `list_factors` 获取支持因子，随后用 `calculate_factor`、`calculate_factor_ic`、`backtest_factor`、`get_factor_profile`、`get_conditional_returns` 或 `get_signal_hit_rate`。
- 相似形态/股票：
  - 相似K线：`search_by_kline`。
  - 历史形态匹配：`find_similar_patterns`。
  - 相似股票：`search_similar_stocks`。
  - 语义选股：`semantic_stock_search`。

# 失败与兜底
- 数据不足：提示用户减少周期或选择更高流动性股票。
- 因子不支持：先返回可用因子列表。
- 工具分流：`calculate_technical_indicators` 失败时改用 `technical_analysis_manager(action=calculate)`；相似检索失败时按 `search_by_kline -> vector_search_manager(action=similar_stocks)` 分流。

# 参考
- 读取 `references/tools.md` 了解参数与返回要点。

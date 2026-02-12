---
name: akshare-tdx-formula-research
description: TDX 公式计算、条件选股与专家信号研究流程；适用于“公式验证-选股-信号确认”场景。
---

# 目标
将 TDX 公式能力组织成可复用研究流程，支持“指标计算 -> 条件选股 -> 信号确认 -> 结果复核”。

# 使用流程
- 数据准备：先用 `tdx_get_formula_data` 获取目标周期 K 线，确认样本长度满足公式需求。
- 指标计算：
  - 通用入口：`tdx_calculate_indicator`
  - 快捷入口：`tdx_calculate_macd`、`tdx_calculate_kdj`、`tdx_calculate_rsi`、`tdx_calculate_boll`
- 条件选股：用 `tdx_screen_stocks` 批量筛选候选标的。
- 信号确认：对候选标的用 `tdx_get_expert_signals` 做买卖信号复核。
- 深度公式：需要自定义输入时用 `tdx_custom_formula_calc`，并记录参数以便复现。

# 失败与兜底
- 公式 API 不可用：降级到快捷指标工具（如 `tdx_calculate_macd`）。
- 样本不足：提升 `count` 或切换更长周期。
- 选股条件不支持：先返回可用条件并建议拆解为多步筛选。
- 工具分流：TDX 公式链路整体失败时，改用 `calculate_technical_indicators` + `technical_analysis_manager(action=check_patterns)` 完成基础研究。

# 参考
- 公式与选股主工具：`tdx_calculate_indicator`、`tdx_screen_stocks`、`tdx_get_expert_signals`。

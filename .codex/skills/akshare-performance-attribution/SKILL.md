---
name: akshare-performance-attribution
description: 绩效衡量与归因流程，包含收益拆解与风险来源说明。
---

> 校准说明：本 skill 用于定义绩效衡量与归因的推荐流程，不代表文中涉及的绩效指标、基准评分、风险拆解与归因维度在当前环境都已具备统一口径和完整数据支撑。
>
> 实际归因结论应以当次组合数据、基准选择、风险模型返回、指标定义与运行时工具结果为准；若缺少基准、行业暴露、因子暴露或历史窗口证据，应显式说明限制，而不是默认输出完整归因结论。


# 目标
将组合收益与风险拆解成可解释结果，便于复盘。

# 使用流程
- 绩效获取：用 `performance_manager` 或 `portfolio_manager` 获取组合收益与持仓信息。
- 基准评测：用 `benchmark_manager(action=run_daily|get_report)` 输出接口级与结果级评分，形成统一评分口径。
- 基准对比：若提供基准，用 `get_index_quote` 或指数K线获取基准表现。
- 风险拆解：结合 `analyze_portfolio_risk` 输出波动、回撤、相关性等。
- 归因输出：按行业/因子/个股暴露进行结构化说明（若无行业数据则说明限制）。

# 失败与兜底
- 无基准数据：提示用户提供基准或仅输出绝对绩效。
- 行业数据缺失：降级为个股与因子层归因。
- 工具分流：`performance_manager` 失败时改用 `benchmark_manager` 或 `portfolio_manager` + `analyze_portfolio_risk` 组合输出；`get_index_quote` 失败时改用指数历史K线近似基准收益。

# 参考
- 风险分析工具：`analyze_portfolio_risk`。
- 基准评测工具：`benchmark_manager`。

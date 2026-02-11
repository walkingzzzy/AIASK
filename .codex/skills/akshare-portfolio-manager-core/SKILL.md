---
name: akshare-portfolio-manager-core
description: 顶级基金经理核心流程：目标与约束、组合构建、执行、风险与绩效闭环。
---

# 目标
把投资目标、约束条件与组合构建/风险管理/绩效衡量串成可执行闭环。

# 使用流程
- 目标与约束：明确收益目标、风险承受能力、期限、流动性与最大回撤。
- 资产范围：确认可投标的范围（默认A股/ETF），必要时用 `search_stocks` 定位标的。
- 组合构建：用 `optimize_portfolio` 生成权重方案。
- 风险评估：用 `analyze_portfolio_risk` 与 `stress_test_portfolio` 评估组合风险。
- 持仓管理：如需落地与持久化，使用 `portfolio_manager` 创建组合与 `add_holding` 记录持仓。
- 绩效复盘：用 `performance_manager` 或 `portfolio_manager` 查询收益并输出复盘摘要。

# 失败与兜底
- 目标不清晰：先输出目标问卷与示例区间。
- 标的不足：提示扩充标的或降低约束。
- 数据不可用：提示更换标的或缩短时间范围。

# 参考
- 管理器工具：`portfolio_manager`、`performance_manager`。

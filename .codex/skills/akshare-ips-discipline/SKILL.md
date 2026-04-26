---
name: akshare-ips-discipline
description: 投资政策声明（IPS）与行为纪律制定流程。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["portfolio_suitability", "risk_disclosure"]
role_tags: ["buy_side_pm", "compliance", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 校准说明：本 skill 用于定义投资政策声明（IPS）与行为纪律的模板化流程，不代表文中列出的目标、约束、再平衡规则与执行纪律在当前系统中都已自动落地、持续校验或强制执行。
>
> 实际约束是否生效，应以用户确认结果、当次组合配置、运行时工具能力与后续执行/监控链路为准；若尚未完成系统同步、持仓映射或规则校验，应明确标注为“IPS 草案/待确认”，而不是默认视为已生效约束。
>
> 当前仓库未见 IPS 专用数据库表、BFF 控制器或前端编辑器；因此本 skill 的核心产物仍是文本草案，`portfolio_manager` 只能提供持仓上下文，不能替代 IPS 的持久化、版本化和规则执行。


# 目标
将投资目标、约束、纪律与再平衡规则结构化为 IPS 模板。

# 使用流程
- 目标与期限：明确目标金额、投资期限、风险承受能力与最大回撤容忍。
- 约束条件：流动性需求、税费/监管限制、行业/个股回避清单。
- 资产配置：定义资产类别、目标区间与分散规则。
- 再平衡纪律：设定频率与触发阈值，写入执行规则。
- 行为约束：定义“禁止的临时决策”与例外条件。
- 输出模板：生成 IPS 草案并等待用户确认。

# 失败与兜底
- 用户目标不清晰：先输出目标问卷与示例答案范围。
- 工具分流：`portfolio_manager` 不可用时改为用户手工提供当前持仓与约束，再生成可执行 IPS 草案并标记待系统同步。

# 参考
- 如需结合现有组合，可先调用 `portfolio_manager` 获取持仓。

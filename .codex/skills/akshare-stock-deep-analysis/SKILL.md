---
name: akshare-stock-deep-analysis
description: 统一的个股深度分析产品线：从标的解析、数据装配、evidence/gap/review/synthesis 到 standalone HTML 报告工件；适用于 quick_scan、deep_analysis、recover_gaps、rebuild_report 与 trade_plan。
capability_tier: live_orchestrated
runtime_status: executable
product_surfaces: ["mcp", "bff", "web", "resource", "artifact"]
artifacts: ["analysis_input", "analysis_evidence", "analysis_gap_report", "analysis_agent_review", "analysis_synthesis", "analysis_report_bundle"]
backing_tools: ["run_skill", "analyze_stock_product_workflow"]
backing_managers: ["decision_manager", "market_insight_manager"]
regulatory_scope: ["research_disclosure", "analysis_lineage"]
role_tags: ["buy_side_pm", "research", "trader", "quant", "risk"]
last_runtime_verified_at: "2026-04-19"
---

> 本 skill 的目标不是替代现有市场、基本面或量化工具，而是把这些能力收敛成一条可执行、可审计、可复用的个股深度分析主线。
>
> 首期默认聚焦 A 股；若标的解析不成功或关键字段缺失，必须先进入 gap report / recover 流程，不能直接发布最终报告。

# 目标

通过单入口输出一组协议化工件：

- `analysis_input`
- `analysis_evidence`
- `analysis_gap_report`
- `analysis_agent_review`
- `analysis_synthesis`
- `analysis_report_bundle`

同一个 run 会被 MCP workflow、resource、BFF 和 Web 共用，不允许各端自行拼装平行逻辑。

只读预检入口：`analyze_stock_workflow`。

# 推荐入口

```
run_skill(
  skill_id="akshare-stock-deep-analysis",
  params={
    "code": "600519",
    "task": "deep_analysis",
    "investment_style": "balanced"
  }
)
```

或直接调用 workflow：

```
analyze_stock_product_workflow(
  code="600519",
  task="deep_analysis",
  investment_style="balanced"
)
```

快速、只读的股票上下文预检可使用 `analyze_stock_workflow`，完整产品化报告仍以 `analyze_stock_product_workflow` 为准。

# 支持任务

## `quick_scan`

- 输出压缩版摘要与阶段结果。
- 保留 integrity gate、agent review、digest。
- 报告 section 数量少于完整深度分析。

## `deep_analysis`

- 走完整五段链路：
  1. 数据装配
  2. 证据归一
  3. AI 复核
  4. 综合合成
  5. 报告渲染
- 生成完整 HTML 报告工件。

## `recover_gaps`

- 优先读取缺口报告与恢复动作。
- 若关键缺口仍未关闭，不得伪装成完整报告。

## `rebuild_report`

- 基于已有 run 的输入、synthesis、gap 工件重建报告。
- 必须提供 `run_id`。

## `trade_plan`

- 在深度分析链路上追加交易计划工件。
- 保留 deep-analysis 的证据与报告输出。

# 强制门禁

1. 标的解析失败时必须阻断；名称歧义必须返回候选，不得自动猜测。
2. 关键字段缺失时必须先出 `analysis_gap_report`。
3. 定性结论必须绑定 evidence id 或结构化来源。
4. `final_check` 未通过时不能把 synthesis 当成正式报告输出。

# 资源与报告读取

- 最新标的运行：`resource://stock/{code}/deep-analysis`
- run 摘要：`resource://analysis-run/{run_id}/summary`
- run 报告：`resource://analysis-run/{run_id}/report`
- Prompt：`stock-analysis-deep`

# Web / BFF 对接

- BFF:
  - `POST /api/v1/analysis/deep-stock/runs`
  - `GET /api/v1/analysis/deep-stock/runs/:runId`
  - `GET /api/v1/analysis/deep-stock/runs/:runId/report`
- Web:
  - `/analysis/deep-stock`

# 使用规范

- 用户给简称或名称时，先做标的解析；候选多于一个必须显式展示候选。
- 优先复用已有 run 资源，不要在 Web/BFF 重新串 raw tools。
- 若用户只要摘要，优先 `quick_scan`。
- 若用户要可传播报告、证据链和缺口面板，使用 `deep_analysis`。

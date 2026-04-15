---
name: akshare-factor-mining
description: AI 因子挖掘、候选因子生成、候选验证、研究记忆、候选池治理与调度巡检等场景使用；适用于 llm_factor_mining 与因子研究流水线编排。
---

> 校准说明：本 skill 面向“候选因子生成与治理”，不是普通因子计算页的别名。
>
> 当前真实能力主要落在 `quant_manager` 的候选生成、候选验证、研究记忆、候选池治理与调度动作，以及 `strategy_factory` 内部的 `factor_research` / artifact 组装。
>
> 若缺少候选 artifact、横截面验证、研究记忆或 active_pool 证据，应明确标注“候选未闭环”。


# 目标
把“AI 因子挖掘”请求收敛到候选生成、验证、留痕、入池与后续 handoff 的真实能力上。

# 适用触发
- 用户提到“因子挖掘”“AI 因子”“候选因子”“候选池”“研究记忆”“active_pool”“调度刷新”。
- 需要把研究想法变成候选因子，并判断是否值得继续进入策略研究或策略工厂。

# 推荐流程
- 阶段 0（归类）：
  - 普通因子分析优先走 `akshare-quant` 或 `akshare-quant-research-process`
  - 只有涉及候选生成、治理、artifact 留痕时才用本 skill
- 阶段 1（准备）：
  - 用 `check_db_freshness` 先看候选样本窗口是否明显过期
  - 用 `get_factor_library`、`list_factors` 看已有因子族
  - 用 `get_kline_data`、`sync_stale_klines` 或 `data_warmup` 确保样本窗口可用
- 阶段 2（候选生成）：
  - 用 `quant_manager(action=llm_factor_mining)` 生成候选 artifact
  - 需要回看 artifact 元数据、阶段摘要或运行上下文时，用 `ai_workflow_artifact`
- 阶段 3（候选验证）：
  - 用 `quant_manager(action=validate_factor_candidate)` 做 DSL 编译与横截面验证
  - 补充证据时，可用 `calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`factor_robustness_check`
- 阶段 4（留痕与治理）：
  - 用 `quant_manager(action=factor_research_memory)` 做 `list|get|recall|stats`
  - 用 `quant_manager(action=factor_candidate_registry)` 看 `summary|active_pool|get|list`
  - 需要调度巡检时，用 `quant_manager(action=scheduler_status|scheduler_run_now)`
- 阶段 5（策略工厂 handoff）：
  - 当候选已经有 artifact、验证结论与治理状态时，才转入 `akshare-strategy-factory`
  - handoff 时优先保留 artifact id、验证结论、候选来源和研究记忆摘要，不要把“生成成功”误写成“已通过策略门禁”

# 失败与兜底
- `llm_factor_mining` 不可用：
  - 退到 `get_factor_library` + `calculate_factor` + `calculate_factor_ic` 的手工候选验证路径
- 验证失败：
  - 明确标注为“候选生成成功，但验证未通过/待补证据”
- `factor_research_memory` 或 `factor_candidate_registry` 不可用：
  - 说明“可生成/可验证，但无治理留痕证据”
- 页面只支持普通因子研究：
  - 不要把 `/factor` 或 `/factor-analysis` 的存在误判成候选治理闭环已上线

# 参考
- 主工具：`quant_manager`
- 配套工具：`ai_workflow_artifact`、`check_db_freshness`、`get_factor_library`、`list_factors`、`calculate_factor`、`calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`factor_robustness_check`、`get_kline_data`、`sync_stale_klines`、`data_warmup`
- 后续分流：`akshare-quant-research-process`、`akshare-strategy-factory`

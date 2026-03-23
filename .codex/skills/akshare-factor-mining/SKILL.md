---
name: akshare-factor-mining
description: AI 因子挖掘、候选因子生成、候选验证、研究记忆、候选池治理与调度巡检等场景使用；适用于 llm_factor_mining 与因子研究流水线编排。
---

> 校准说明：本 skill 面向“因子挖掘/候选治理”而不是普通因子计算页面，不代表当前 BFF/Web 已把该流程完整产品化。
>
> 当前真实能力主要落在 `quant_manager` 的候选生成、候选验证、研究记忆与候选池治理动作，以及 `strategy_factory` 内部的 `factor_research` artifact 组装。
>
> 若缺少候选 artifact、横截面验证、研究记忆或 active_pool 证据，应明确标注为“候选未闭环”，不要把普通 IC/回测页面当作因子挖掘已经完成。


# 目标
把“AI 因子挖掘”请求收敛到候选生成、验证、留痕、入池与调度巡检的真实能力上，避免和普通因子分析混淆。

# 适用触发
- 用户提到“因子挖掘”“AI 因子”“候选因子”“因子候选池”“研究记忆”“active_pool”“调度刷新”。
- 需要从研究想法生成候选因子，并验证是否值得进入后续研究或策略工厂。

# 推荐流程
- 阶段 0（问题归类）：
  - 先区分这是“普通因子分析”还是“候选因子挖掘”。
  - 普通因子分析优先走 `akshare-quant` 或 `akshare-quant-research-process`；只有涉及候选生成/治理时才用本 skill。
- 阶段 1（基础准备）：
  - 用 `get_factor_library`、`list_factors` 确认已有因子族。
  - 用 `get_kline_data` 或 `data_warmup` 确保样本窗口可用。
- 阶段 2（候选生成）：
  - 用 `quant_manager(action=llm_factor_mining)` 生成候选 artifact。
  - 若需要另类信息补充，可配合 `quant_manager(action=alternative_factors)`。
- 阶段 3（候选验证）：
  - 用 `quant_manager(action=validate_factor_candidate)` 做 DSL 编译与横截面验证。
  - 用 `calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`factor_robustness_check` 补充方向性、OOS 和稳健性证据。
- 阶段 4（留痕与治理）：
  - 用 `quant_manager(action=factor_research_memory)` 做 `list|get|recall|stats`。
  - 用 `quant_manager(action=factor_candidate_registry)` 看 `summary|active_pool|get|list`，确认是否进入治理池。
  - 需要复盘时，用 `quant_manager(action=replay_factor_episode|factor_ic_history)`。
- 阶段 5（调度与产品面）：
  - 用 `quant_manager(action=scheduler_status|scheduler_run_now)` 核查调度器是否健康。
  - 如果只需要产品页承载，当前仅能退到 `/factor` 与 `/factor-analysis` 做普通研究展示，不能假定它们覆盖候选治理闭环。

# 失败与兜底
- `llm_factor_mining` 不可用：退到 `get_factor_library` + `calculate_factor` + `calculate_factor_ic` 的手工候选验证路径。
- 验证失败：不要直接入池，明确标注为“候选生成成功但验证未通过”。
- `factor_research_memory` 或 `factor_candidate_registry` 不可用：说明“可生成/可验证，但无治理留痕证据”。
- BFF/Web 只支持普通因子研究：不要把 `/factor` 页面存在误判为 AI 因子挖掘闭环已上线。

# 参考
- 主工具：`quant_manager`
- 配套原子工具：`get_factor_library`、`list_factors`、`calculate_factor`、`calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`factor_robustness_check`、`get_kline_data`、`data_warmup`
- 产品入口：`apps/bff/src/factor/`、`apps/web/app/factor/`、`apps/web/app/factor-analysis/`

---
name: akshare-quant-research-process
description: 量化研究流程编排：数据→信号→组合→回测→执行与复盘。
---

> 校准说明：本 skill 定义量化研究的推荐门禁与阶段顺序，不代表每个阶段在当前环境都已有完全自动化、同口径且稳定通过的执行链路。
>
> 当前“因子挖掘”主要落在 `quant_manager` 的候选生成/验证/研究记忆与 `strategy_factory` 的 research artifact 组装；当前“策略工厂”主链主要落在 `strategy_review_workflow`、`resource://strategy/{id}/review` 与 `strategy_manager`。
>
> 若某阶段缺少数据、工具或验证证据，应明确标注“未通过/待补证据”，不要默认视为完成。


# 目标
把量化研究流程升级为“可复现、可审计、可 handoff”的阶段化管线。

# 强制阶段流程
- 阶段 0（研究定义）：
  - 明确研究假设、标的池、观察窗口、再平衡频率和成本假设
  - 新接入工具或流程不确定时，先用 `get_tool_contract`
- 阶段 1（数据门禁）：
  - 先用 `check_db_freshness` 看样本是否过期
  - 主路径用 `get_kline_data`，需要时先 `sync_stale_klines` 或 `data_warmup`
  - 数据不达标则不进入下一阶段
- 阶段 2（信号构建）：
  - 用 `get_factor_library`、`calculate_factor`、`quant_manager(action=calculate_factors)`、`technical_analysis_manager(action=calculate)` 构建信号
- 阶段 3（有效性检验）：
  - 用 `calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`factor_robustness_check`
  - 只有保留稳定性门槛通过的信号，才进入组合阶段
- 阶段 4（组合与回测）：
  - 用 `optimize_portfolio`
  - 用 `run_simple_backtest` / `run_batch_backtest`
  - 同时记录手续费、滑点、换手和调仓频率
- 阶段 5（风险与归因）：
  - 用 `analyze_portfolio_risk`、`stress_test_portfolio`、`risk_manager(action=risk_exposure)`
  - 用 `performance_manager(action=attribution|benchmark_comparison)`
- 阶段 6（结果留痕）：
  - 用 `backtest_manager(action=save)` 保存结果
  - 输出可复现实验卡片
- 阶段 7（向策略工厂 handoff）：
  - 若研究产物要进入策略工厂，不要直接把“回测可看”当成“可上线”
  - 优先把 artifact id、验证结论、成本假设、风险结论和样本外表现交给 `akshare-strategy-factory`
  - 进入工厂后，优先用 `strategy_review_workflow` / `resource://strategy/{id}/review` 做只读审查，再用 `strategy_manager` 看提交门禁、孵化、运行时与治理状态

# 失败与兜底
- 数据不可用：
  - `get_kline_data` 失败时降级到 `sync_stale_klines`、`batch_sync_klines` 或 `get_kline`
- 因子不可用：
  - `calculate_factor` 失败时降级到 `calculate_technical_indicators` 或 `technical_analysis_manager`
- 向量检索不可用：
  - `vector_search_manager` 失败时用 `search_by_kline` / `search_similar_stocks`
- 批量回测失败：
  - `run_batch_backtest` 失败时降级到 `run_simple_backtest`
- 管理器不可用：
  - `quant_manager` 失败时，使用原子工具链继续

# 参考
- 管理器与工具：`check_db_freshness`、`sync_stale_klines`、`quant_manager`、`technical_analysis_manager`、`vector_search_manager`、`backtest_manager`、`risk_manager`、`performance_manager`、`calculate_factor`、`calculate_factor_ic`、`backtest_factor`、`validate_factor_oos`、`run_simple_backtest`、`run_batch_backtest`
- 相邻 skill：`akshare-factor-mining`、`akshare-strategy-factory`

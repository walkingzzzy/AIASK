---
name: akshare-quant-research-process
description: 量化研究流程编排：数据→信号→组合→回测→执行与复盘。
---

> 校准说明：本 skill 用于定义量化研究的推荐门禁与阶段顺序，不代表文中列出的每个阶段在当前环境都已有完全自动化、同口径且稳定通过的执行链路。
>
> 实际研究能力应以当次运行时注册结果、数据质量、成本参数披露、回测契约与测试产物为准；若某阶段缺少数据、工具或验证证据，应明确标注“未通过/待补证据”，而不是默认视为完成。


# 目标
把量化研究流程升级为“可复现、可审计、可落地”的强制阶段管线。

# 强制阶段流程（每阶段都要给出通过/不通过）
- 阶段 0（研究定义）：
  - 明确研究假设、标的池、观察窗口、再平衡频率和成本假设。
  - 先记录基准（如指数代码）和评估指标（收益、回撤、夏普、换手）。
- 阶段 1（数据门禁）：
  - 主路径用 `get_kline_data` 拉取历史数据；需要时先 `data_warmup`。
  - 输出数据质量结论：缺失值、异常值、样本长度是否达标。
  - 不达标则不进入下一阶段。
- 阶段 2（信号构建）：
  - 用 `get_factor_library` 选择候选因子。
  - 用 `calculate_factor`、`quant_manager(action=calculate_factors)`、`technical_analysis_manager(action=calculate)` 生成信号。
- 阶段 3（有效性检验）：
  - 用 `calculate_factor_ic` 与 `backtest_factor` 检验因子方向性和稳定性。
  - 用 `factor_robustness_check` 做多窗口稳定性、参数敏感性与子样本一致性检查。
  - 至少保留通过稳定性门槛的信号。
- 阶段 4（组合构建）：
  - 用 `optimize_portfolio` 产出权重（或等权作为对照组）。
  - 给出约束条件（单票上限、行业偏离、风险预算）。
- 阶段 5（回测验证）：
  - 用 `run_simple_backtest` / `run_batch_backtest` 完成样本内回测。
  - 同时记录手续费、滑点、调仓频率等成本假设。
- 阶段 6（样本外/OOS）：
  - 优先使用 `validate_factor_oos`（Walk-Forward + Purged KFold + Bootstrap CI）输出统一 OOS 报告。
  - 使用滚动窗口重复阶段 4-5，输出样本外表现与衰减情况。
  - 样本外显著劣化则回退到阶段 2 调整信号。
- 阶段 7（风险与归因）：
  - 用 `analyze_portfolio_risk`、`stress_test_portfolio`、`risk_manager(action=risk_exposure)` 评估风险暴露。
  - 用 `performance_manager(action=attribution|benchmark_comparison)` 做归因与基准对比。
- 阶段 8（结果留痕）：
  - 用 `backtest_manager(action=save)` 保存回测结果与参数。
  - 输出复现实验卡片（标的池、参数、数据窗口、结论、限制）。

# 失败与兜底
- 数据不可用：`get_kline_data` 失败时降级到 `sync_kline_data` 或 `get_kline`。
- 因子不可用：`calculate_factor` 失败时降级到 `calculate_technical_indicators` 或 `technical_analysis_manager`。
- 向量检索不可用：`vector_search_manager` 失败时用 `search_by_kline` / `search_similar_stocks`。
- 批量回测失败：`run_batch_backtest` 失败时降级到 `run_simple_backtest` 分标的回测。
- 管理器不可用：`quant_manager` 失败时使用同等原子工具链（factor + backtest + risk）继续。

# 参考
- 管理器与原子工具：`quant_manager`、`technical_analysis_manager`、`vector_search_manager`、`backtest_manager`、`risk_manager`、`performance_manager`、`calculate_factor`、`run_simple_backtest`、`run_batch_backtest`。

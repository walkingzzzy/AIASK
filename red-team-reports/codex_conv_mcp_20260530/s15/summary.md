# N15 · 因子稳健性与分组回测

- 调用次数: 30 | 判定: pass_with_high_finding
- 覆盖工具: factor_robustness_check（全崩）、backtest_factor（19 因子多参数）
- 前提说明: DB 仅约 250 根日线 / 8 只标的，分组各组 1-2 只样本极小，收益指标仅供工具行为审计。

## 关键发现

- **F-N15-1 (high)**: `factor_robustness_check` 100% 崩溃 `"'str' object has no attribute 'get'"`（未捕获 AttributeError），对所有因子和参数均失败，工具完全不可用（类似 N11 research_manager）。
- **F-N15-2 (high)**: `backtest_factor(turnover_20d/volume_ratio)` 崩 `"index -21 is out of bounds for axis 0 with size 20"`，与 N14 的 IC 管道同源——这两个因子在 IC + backtest 双管道均越界。
- **F-N15-3 (medium)**: `backtest_factor(stoch_k)` 与 `backtest_factor(willr_14)` 产出完全逐位相同结果（sharpe 都 2.447），两个数学定义不同的因子回测结果碰撞，疑似因子取值管道混淆。
- **F-N15-4 (low)**: `slippage_model`（fixed/volume_aware）参数未回显，costs.slippage_model 始终空字符串。
- **F-N15-5 (low)**: 8 只分 5 组不均衡（group5 固定 4 只），floor 分配使余数全给最后组，long-short 多空样本悬殊。

## 正向能力

- `backtest_factor` 结构完整：group_returns + period_group_results(逐期) + equity_curve + sharpe + max_dd + win_rate + costs + tradability + perf_breakdown。
- 滑点数值生效（fixed 模型成本叠加正确）。
- 边界处理优秀：2 只<5 组 graceful + 完整 stats；非法因子 Unsupported + supported 列表。
- tradability 字段提供成交可行性审计；max_drawdown 基于实际 equity curve 并在 notes 说明。

## turnover_20d/volume_ratio 跨场景 bug 汇总

| 工具 | 错误 |
|---|---|
| calculate_factor_ic (N14) | list index out of range |
| backtest_factor (N15) | index -21 is out of bounds for axis 0 with size 20 |

两个因子在所有 quant 多股管道均不可用，但 calculate_factor 单股算 turnover_20d 正常（N13），说明 bug 在多股面板对齐环节。

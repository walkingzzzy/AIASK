# N16 · 单股回测与绩效

**工具**: run_simple_backtest / backtest_manager / performance_manager / benchmark_manager
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- `run_simple_backtest`: 6 标的 × 4 策略(buy_and_hold/ma_cross/momentum/rsi)
- `backtest_manager`: help / run(持久化 artifact_id) / list / get
- `performance_manager`: help / backtest_metrics(461a7cd2/eea536b8/47e9149f/不存在) / attribution / benchmark_comparison
- `benchmark_manager`: help / get_report(即时报告)

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N16-4 | **high** | `backtest_manager(list/run)` payload 爆炸——每条记录把 ~250 根 benchmark_klines 嵌入 params/signal_definition/params_snapshot 三处，list 5 条记录输出体积失控 |
| F-N16-1 | medium | `run_simple_backtest` 的 `buy_and_hold` 策略 `sharpe_ratio` 恒为 0.0（而 sortino/vol/calmar 均非零），指标被短路 |
| F-N16-3 | medium | `run_simple_backtest` 的 benchmark_return/excess/IR 全 null，但 `backtest_manager(run)` 同参可返回 benchmark_return=0.268，双入口能力割裂 |
| F-N16-2 | low | `ma_cross` equity_curve 预热期前置 0.0 而非 initial_capital，资金曲线起点失真 |
| F-N16-5 | low | `buy_and_hold` 返回标的全历史 equity_curve(2007 点)，与其他策略窗口口径不一致且无采样 |
| F-N16-6 | low | `benchmark_manager(get_report)` top_results 含逐位相同的重复 ma_cross 记录，未去重 |

## 正向能力
- `run_simple_backtest` 的 `execution_reality`（4 条警告 + promotion_gate + liquidity_gate）+ `capacity_summary` + `tradability_summary` + `PIT` + `cost_assumptions` 审计链极完整，诚实披露"回测≠实盘"。
- `performance_manager(backtest_metrics)` 紧凑指标卡是回测查询的理想形态：仅核心 15 字段 + artifact_id 溯源。
- `performance_manager` 错误/空态处理优秀：不存在 backtest_id → `error_code=BACKTEST_RESULT_NOT_FOUND` + suggested_action；无持仓/组合 → quick_start 分步引导 + example_portfolios。
- `backtest_manager(run)` 相比 run_simple_backtest 额外提供 benchmark_return / information_ratio，互补。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的；buy_and_hold 会拉取标的全历史（000001 返回 2007 根 equity_curve）。收益指标仅供工具行为审计，不代表策略真实有效性。

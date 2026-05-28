# S07 · 回测/绩效

- **判定**: ✅ 通过 (Pass=3 / Degraded=2 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `run_simple_backtest(600519, ma_cross, 1y)` | ✅ Pass | total_return=-14.49% / sharpe=-3.26 / max_drawdown=-22.1%,完整 PIT 元数据(price_source_chain[3] / data_quality.passed),trades=18 笔,initial=1000000 |
| `backtest_manager(action=run, ma_cross)` | ✅ Pass | run_id=bt_codex_full_mcp_20260526_001,artifact 持久化,可复现回放(seed=固定),benchmark=000300 |
| `benchmark_manager(action=run_daily)` | ⚠️ Degraded | report 存在但 yesterday 不是交易日,部分指标 stale_warning=true,quality_gate=passed |
| `run_batch_backtest([600519, 000001, 000651], ma_cross)` | ✅ Pass | 3 只全部完成,parallel=true,total_returns=[-14.49%, -8.2%, -2.1%],consistency_check=passed |
| `analyze_research_report(600519)` | ⚠️ Degraded | 5 篇研报全部 quality_gate=stale(>30 天),source=tushare report_rc,degraded=true 显式,sentiment=positive 4/5 |

## v1 → v2 Delta
- ✅ run_simple_backtest envelope + price_source_chain 完整
- ✅ run_batch_backtest 并行 ray-style 路径稳定
- ⚠️ benchmark_manager run_daily 在非交易日仍正常 stale 标识
- ✅ backtest_manager 持久化/重放工作流稳定

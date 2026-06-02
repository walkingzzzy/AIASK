# N17 · 批量回测

**工具**: run_batch_backtest / benchmark_manager(run_daily/get_report)
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- `run_batch_backtest`: 多标的(3只/2只/1只) × ma_cross/momentum/rsi；并行/串行；warmup；不同 short/long period；commission 异常值
- 边界：空列表、重复代码、混合有效/无效、纯字母、超长、坐标化探测 8 组
- `benchmark_manager`: run_daily ×2、get_report(真实 run_id / 不存在 run_id)

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N17-1 | **high** | 非法代码被**静默坐标化**为真实股票：`BAD1`→000001(平安银行)、`ZZZ9`→000009、`foo123`→000123、`sh600000`→600000。typo 会回测到完全无关的真实股票且无告警 |
| F-N17-6 | medium | `benchmark_manager(get_report)` 的 `run_id` 参数**未生效**——传任意 run_id(含不存在)均返回同一份即时报告 |
| F-N17-3 | medium | 空 `codes=[]` 抛裸 pydantic ValidationError 而非业务层 error_code |
| F-N17-2 | low | `use_parallel=true` 静默回退 `local_sequential`(Ray 不可用)，无降级提示 |
| F-N17-4 | low | 重复代码 `failed_count` 含重复但 `failure_reasons` 去重，计数口径不一致 |
| F-N17-5 | low | `commission=0.5`(50%)被接受，total_cost_bps=5000，无参数合理性校验 |

## 正向能力
- **跨入口一致性**：000858 momentum 批量(+51.28%)与 N16 单股 run_simple(+51.3%)逐位一致；600519 ma_cross 批量(+14.6%)与 backtest_manager(run) 一致 → 回测引擎确定性良好。
- 部分成功语义正确：混合有效/无效代码时有效标的继续，failure_reasons 逐项含 code+reason。
- `warmup_before_fetch`、`source_stats`、`timings` 提供同步/来源/性能可观测性。
- 每只标的携带完整 execution_reality / promotion_gate / capacity_summary / PIT。
- benchmark_manager case_mapping 透明标注 proxy/direct 映射与阈值。

## 复现既往发现
- F-N16-2(equity_curve 预热期前置 0.0)与 F-N16-5(全历史窗口不统一)在批量路径复现。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的；批量对每只标的拉取全历史(2003-2010 根)equity_curve。收益指标仅供工具行为审计。

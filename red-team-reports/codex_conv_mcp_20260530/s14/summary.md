# N14 · 因子 IC 与 OOS 验证

- 调用次数: 30 | 判定: pass_with_high_finding
- 覆盖工具: calculate_factor_ic（19 因子 + 多参数）、validate_factor_oos（4 因子多参数）
- 前提说明: 测试 DB 仅约 250 根日线 / 8 只标的池，截面与时序样本均不足，多数 IC reliable=false 属预期数据限制，重点审计错误处理与指标自洽性。

## 关键发现

- **F-N14-1 (high)**: `calculate_factor_ic(turnover_20d)` 连续 2 次 + `volume_ratio` 均返回未捕获的 `"list index out of range"`（裸 Python IndexError，无 error_code）。同标的池同 period 下其他 18 个因子均正常，`turnover_5d` 正常。特定因子在 IC 管道内索引越界 bug。
- **F-N14-2 (high)**: `validate_factor_oos` 在 n_folds=0 空验证下，`deflated_sharpe` 仍输出 observed_sharpe=3.1~17.7、dsr=1.0、psr=1.0（net_margin 夏普 17.7 荒谬），与同报告 grade=D 直接矛盾。两个权威指标互斥且无 reconcile，会误导决策。
- **F-N14-3 (medium)**: 主指标与 bootstrap_ci 可反号。downside_vol `significant=true`(p=0.028) 却 bootstrap rank_ic=-0.5。根因小样本（已被 warnings 显式标注 reliable=false，护栏到位）。
- **F-N14-4 (low)**: OOS 的 `n_periods` 报告请求值而非实际可用面板长度（n_periods=200 但实际不足切 fold）。

## 正向能力

- `calculate_factor_ic` 高质量：dual IC(normal Pearson + rank Spearman) + ic_ir + 双 p_value + win_rate + bootstrap_ci(1000 次) + 中性化(industry+market_cap 残差统计) + perf_breakdown。
- 全部 IC 结果显式 `reliable=false` + warnings 主指标/bootstrap 反向告警，优秀小样本自检护栏。
- 中性化开关透明：关中性化后 momentum IC 0.143→0.571，可见中性化效果。
- `validate_factor_oos` 集成 walk_forward + purged_kfold + bootstrap + deflated_sharpe + rating，insufficient_sample / n_stocks<10 显式告警。
- 错误路径分级清晰：Unsupported factor 列表 / Not enough valid data 阈值 / sample_size<3 拒绝。

## 与历史报告对照

deflated_sharpe 在空验证下输出 dsr=1.0 是新观察到的指标自洽性问题（F-N14-2），与 F-N07-1（consensus 内部失败但独立成功）同属"内部子计算与汇总指标脱节"模式。

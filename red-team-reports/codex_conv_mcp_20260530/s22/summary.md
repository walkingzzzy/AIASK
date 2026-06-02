# N22 · 买卖单点决策

**工具**: should_i_buy / should_i_sell
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- should_i_buy：8 标的 × aggressive/balanced/conservative；explain/strict_mode；非法 style；BADX
- should_i_sell：多 profit/loss 档（+314%/+65%/+10%/0%/-11%/-21%/-29%/-92%）× 多 holding_days；无 buy_price

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N22-1 | **high** | `decision_probability` 严重失校准——002594 buy_prob=0.13% 但历史胜率 54.8%(ECE=0.546)；300750 buy_prob=0.4% 但胜率 75%(ECE=0.746) |
| F-N22-2 | **high** | "avoid" 结论与自身 `offline_decision_baseline` 矛盾——002594 avoid 但 benchmark_delta=+0.328、threshold80 胜率 77.8%/+4.59% |
| F-N22-3 | medium | score↔recommendation 非单调——601318 score=60(达阈值)+7 条正面证据仍 avoid，而 score=45 的 000651 反而 hold |
| F-N22-4 | medium | threshold_backtest 普遍 `threshold_inversion`(更严格阈值胜率反更低)，评分与未来收益负相关 |
| F-N22-6 | medium | 各标的 analysis_date 不一(05-20~05-29，最多差 9 天)，data_freshness_warning 恒 null |
| F-N22-5 | low | 非法 investment_style 静默接受(回退 balanced) |
| F-N22-7 | low | should_i_sell 接受与标的价格严重不符的 buy_price(1326 vs 实际 96)无 sanity check |

## 正向能力
- **★ should_i_sell 自适应优秀**：按 profit 分档(止盈/减仓/持有/止损)+ATR 止损位+持仓时间惩罚，多场景结论合理。
- should_i_buy 结构极完整：score_breakdown 四维 + signal_breakdown 逐条 + evidence_summary + diagnostic.trace。
- **★ 工具自带强自检**：threshold_inversion / insufficient_sample warnings、calibration_gap/ECE/brier、offline benchmark_delta——诚实披露了模型缺陷(虽然缺陷本身即 F-N22-1/2)。
- explain=false / strict_mode 正确生效；BADX 优雅拒绝；无 buy_price 时 technical_only 降级。
- 与 N21 build_stock_context 结论方向一致(600519 均偏空)。

## standing caveat
测试 DB 仅约 250 根日线 / 8 只标的；buy_probability 校准样本小(1-43 条)；各标的数据新鲜度不一。

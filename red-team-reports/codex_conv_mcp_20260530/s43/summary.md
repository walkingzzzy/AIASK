# N43 · AI 工作流-预测诊断 / 数据质量 / 治理

**31 次真实调用** · verdict = `fail_schema_platt_param_noop_and_quality_subsystem_disagreement_and_hardcoded_crowding`
判定分布: Pass 14 / Degraded 4 / Fail-graceful 6 / Fail-schema 7

覆盖工具: `prediction_diagnosis_workflow`、`data_quality_workflow`、`data_validation`、`governance_check_workflow`、`experiment_tracker`(全生命周期)、`ai_workflow_artifact`。全部受控合成输入，`persist_artifact=false`，隔离 experiment_name/governance target_id。

## 关键发现

### ★★ F-N43-2（HIGH）platt_a / platt_b 死参数
`method=platt` 下分别传 `(1.2, -0.3)` 与 `(3.0, -1.5)`，两次输出的 `calibrated_probability` 与 `calibration_report.probabilities` **逐位完全相同**。根因：`sklearn_calibrated_classifier_cv` 后端恒抛 ValueError 降级 `builtin_lightweight`，builtin 自行用数据拟合 sigmoid，完全无视外部传入的 Platt 系数。工具签名暴露了一组 no-op 参数。

### ★★ F-N43-4（HIGH）数据质量子系统判定互斥 + null 内容从不校验
- 5 行数据 close/volume 各含 1 个 null：顶层字段级 `accepted_ratio=0.6 / quality_gate_failed`（正确），但同一响应内嵌 GX `validation_result.passed=true / quality_score=1.0`（只查列存在）。同响应两套互斥结论。
- `data_validation` 传 `expectations.non_null_fields=[close,volume]` 被**静默忽略**，仅评估 3 个 `expect_column_to_exist`，`passed=true` 尽管有 null。null 单元格内容从未被校验，下游信任 `validation_result.passed` 会放行脏数据。

### ★★ F-N43-6（HIGH）governance crowding_score 疑为常量占位
三次 `include_crowding`（空池 / 3 因子池 / 10 因子且含与目标表达式**完全相同**的 `close/ma_20-1`）——`crowding_score` 恒 = `0.85`、`band=high`、`similar_factor_count=0`、`token_hits=0`。传入精确重复因子仍报 0 相似。crowding 维度未真正基于因子池计算，对所有 momentum 因子一律误报高拥挤（虚假风险信号）。

### F-N43-7（MED）model_drift 静默忽略不识别的指标键
传 `auc/ic/sharpe`（AUC 0.68→0.51 明显漂移）全维度 `unknown`，无"未识别键"告警，模型被判 `drift_status=unknown/severity=low/continue_monitoring`。仅认 `brier/ece/rank_ic/stability` 键名。

### F-N43-8（MED）strategy_health 硬编码 strategy_id='system'
`target_id=redteam_n43_model` 但内层 `strategy_health.strategy_id='system'`。与 N42 factory_run 错误血缘同族（内层实体 id 与顶层 target 脱节）。

### F-N43-1（MED）空数组裸 Pydantic 栈
`probabilities=[]` → 裸 `'probabilities Field required'`；而越界/长度不匹配走干净 PARAM_ERROR。边界错误结构不一致。

### F-N43-3（MED）sklearn 校准后端 100% 失败
所有 platt/isotonic 调用 `fallback_reason='sklearn_calibration_failed:ValueError'`，主校准路径从不工作，每次静默 try-fail-降级。

### F-N43-5（MED）空 records 跨工具不一致
`data_quality_workflow([])` 真空通过 `accepted_ratio=1.0`；`data_validation([])` 干净 PARAM_ERROR 拒绝。

### F-N43-9（LOW）factor_decay 欠告警
近期 IC 转负 + 半衰期 1.4 周期 + `rolling_ic_trend=decaying` 仍判 `decay_status=stable`。

## 正向亮点

- **★★ 样本不足护栏**：10<30 样本拒绝计算 platt/isotonic（"refusing to compute"），不硬算小样本。
- **★★ 线上线下一致性**：自动检出 `slippage_bps` gap=20 / `market_impact_bps` gap=3，warnings 提示回测零滑点假设与执行差距，`consistency_status=inconsistent`。
- **★ 校准算法本身正确**：isotonic 真实改善（ECE 0.19→0.085）；platt 在有 raw_scores 时改善（ECE 0.265→0.114）。问题只在 sklearn 后端失败与 platt 系数无效。
- **★ experiment_tracker 全生命周期稳健**（log_run/log_metric 多 step/log_artifact/get_run/list_runs + NOT_FOUND），mlflow 未装诚实降级 builtin。
- **★ freshness/stale 计算与 minimum_quality_threshold 门控正确**；coverage_target 正确传播；quality_band 诚实标注。

## 跨场景关联

- F-N43-6/F-N43-7（静默忽略非预期输入 + 常量占位）延续全局"静默坐标化/静默回退"模式（N17/N18/N19/N28/N30/N36/N41）。
- F-N43-8（strategy_id 写死 system）延续 N42 错误血缘归属模式。
- F-N43-2（文档化参数 no-op）+ F-N43-4（子系统判定打架）为本场景新增模式。

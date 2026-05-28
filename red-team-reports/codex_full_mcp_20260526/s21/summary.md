# S21 · AI 工作流/诊断/工件

- **判定**: ✅ 通过 (Pass=1 / Degraded=0 / Fail-graceful=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `data_quality_workflow(test_dataset_001, 3 records)` | ✅ Pass | **great_expectations runtime backend 完整生效** — passed=true,4 expectations(table_row_count + 3 column_to_exist code/price/date)全 passed,quality_score=1.0 / suite_name=runtime_suite_9ddab0f617f2,checkpoint test_dataset_001_runtime_checkpoint 持久化,3 个 remediation_hints 智能推荐 |
| `prediction_diagnosis_workflow(platt method, 5 samples)` | 🟡 Fail-graceful | **样本数护栏完美** — error_code=INSUFFICIENT_SAMPLES,error="insufficient_sample_size=5<30: calibration unreliable, refusing to compute platt/isotonic. Increase samples or use method='raw'.",quality.status=rejected_sample_too_small / minimum_required=30 显式 |

## v1 → v2 Delta
- ✅ data_quality_workflow great_expectations runtime backend 升级完成(v1 builtin 简化校验 → v2 真实 GX backend + suite + checkpoint 持久化)
- ✅ prediction_diagnosis_workflow 样本数护栏(<30 拒绝 platt/isotonic)显式 INSUFFICIENT_SAMPLES error_code 完美
- ✅ data_quality_workflow lineage.run_id + dataset_id 完整 + pit.as_of 时间戳精确

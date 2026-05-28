
    @mcp.tool(
        title="Prediction Diagnosis Workflow",
        description="Diagnose predicted probabilities with calibration, uncertainty and lineage-ready metadata.",
        structured_output=True,
        meta=build_tool_meta("prediction_diagnosis_workflow"),
    )
    async def prediction_diagnosis_workflow(
        probabilities: list[float],
        labels: list[Any] | None = None,
        outcomes: list[Any] | None = None,
        raw_scores: list[float] | None = None,
        method: str = "raw",
        platt_a: float = 1.0,
        platt_b: float = 0.0,
        coverage_target: float = 0.9,
        dataset_id: str | None = None,
        run_id: str | None = None,
        persist_artifact: bool = False,
        output_artifact_id: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        from ..services.probability_calibration import (
            build_calibration_quality_report,
            calibrate_probability_series,
            estimate_prediction_interval,
            isotonic_calibrate,
            platt_scale,
        )
        from ..services.adapters.mapie_adapter import get_conformal_adapter

        started_at = time.perf_counter()
        workflow_method = str(method or "raw").strip().lower()
        source_chain = ["workflow.prediction_diagnosis", "service.probability_calibration"]
        lineage_ctx = LineageContext.create(
            "prediction_diagnosis_workflow",
            dataset_id=dataset_id,
        )
        try:
            probs = [float(item) for item in list(probabilities or [])]
            if any((value < 0.0 or value > 1.0) for value in probs):
                return fail_with_meta(
                    "probabilities must stay within [0, 1]",
                    tool_name="prediction_diagnosis_workflow",
                    action=workflow_method,
                    started_at=started_at,
                    source_chain=source_chain,
                    error_code="PARAM_ERROR",
                    extra_meta={
                        "quality": {"status": "failed", "workflow": "prediction_diagnosis_workflow"},
                        "side_effect": {"level": "read_only", "target": "prediction_inputs", "confirmation_required": False},
                        "lineage": {"dataset_id": dataset_id, "run_id": run_id},
                        "degraded": True,
                    },
                )
            label_values = outcomes if outcomes is not None else labels
            ys = _normalize_binary_outcomes(label_values)
            if not probs or len(probs) != len(ys):
                return fail_with_meta(
                    "probabilities and labels/outcomes must be non-empty and share the same length",
                    tool_name="prediction_diagnosis_workflow",
                    action=workflow_method,
                    started_at=started_at,
                    source_chain=source_chain,
                    error_code="PARAM_ERROR",
                    extra_meta={
                        "quality": {"status": "failed", "workflow": "prediction_diagnosis_workflow"},
                        "side_effect": {"level": "read_only", "target": "prediction_inputs", "confirmation_required": False},
                        "lineage": {"dataset_id": dataset_id, "run_id": run_id},
                        "degraded": True,
                    },
                )

            # P2-4.3.7 fix(诊断报告 §4.3.7):sample_size<30 强制 reject
            # 历史问题:method=platt 但 sample=5 时 sklearn+mapie 双重降级 silent 输出 platt_a/b 校准建议
            # 修复:sample<30 时 fail-graceful,不输出不可信的 calibration 建议
            if len(probs) < 30:
                return fail_with_meta(
                    f"insufficient_sample_size={len(probs)}<30: calibration unreliable, "
                    f"refusing to compute platt/isotonic. Increase samples or use method='raw'.",
                    tool_name="prediction_diagnosis_workflow",
                    action=workflow_method,
                    started_at=started_at,
                    source_chain=source_chain,
                    error_code="INSUFFICIENT_SAMPLES",
                    extra_meta={
                        "quality": {
                            "status": "rejected_sample_too_small",
                            "sample_size": len(probs),
                            "minimum_required": 30,
                        },
                        "side_effect": {"level": "read_only", "confirmation_required": False},
                        "lineage": {"dataset_id": dataset_id, "run_id": run_id},
                        "degraded": True,
                    },
                )

            calibration_result = None
            report_method = workflow_method
            if workflow_method in {"platt", "sigmoid", "calibrated_sigmoid", "calibrated_isotonic", "isotonic", "auto"}:
                target_method = (
                    "sigmoid"
                    if workflow_method in {"platt", "sigmoid", "calibrated_sigmoid", "auto"}
                    else "isotonic"
                )
                calibration_result = calibrate_probability_series(
                    probs,
                    ys,
                    raw_scores=raw_scores,
                    method=target_method,
                )
                calibrated = list(calibration_result.probabilities)
                report_method = calibration_result.method
            elif workflow_method == "legacy_platt":
                calibrated = [platt_scale(raw_scores[idx] if raw_scores and idx < len(raw_scores) else probs[idx], a=platt_a, b=platt_b) for idx in range(len(probs))]
            elif workflow_method == "legacy_isotonic":
                calibration_table = [(float(i) / max(len(probs) - 1, 1), probs[i]) for i in range(len(probs))]
                calibrated = [isotonic_calibrate(raw_scores[idx] if raw_scores and idx < len(raw_scores) else probs[idx], calibration_table) for idx in range(len(probs))]
            else:
                calibrated = list(probs)

            report = build_calibration_quality_report(
                calibrated,
                ys,
                calibration_method=report_method,
                calibration_version="workflow_v2",
                calibration_backend=calibration_result.backend_used if calibration_result else "builtin_lightweight",
                backend_requested=calibration_result.backend_requested if calibration_result else "raw",
                backend_used=calibration_result.backend_used if calibration_result else "raw",
                fallback_used=bool(calibration_result.fallback_used) if calibration_result else False,
                fallback_reason=calibration_result.fallback_reason if calibration_result else None,
                cv_folds=calibration_result.cv_folds if calibration_result else None,
            )
            interval_examples = [
                estimate_prediction_interval(
                    calibrated_probability=probability,
                    sample_size=max(20, len(calibrated)),
                    coverage_target=coverage_target,
                    calibrated=workflow_method != "raw",
                ).to_dict()
                for probability in calibrated[: min(5, len(calibrated))]
            ]
            conformal_result = get_conformal_adapter(prefer_mapie=True).predict_set(
                calibration_scores=calibrated,
                calibration_labels=ys,
                test_scores=calibrated[: min(5, len(calibrated))],
                alpha=max(0.001, min(0.499, 1.0 - float(coverage_target or 0.9))),
                n_classes=max(2, len(set(ys))),
            )
            # P1-3: Build uncertainty report
            uncertainty_payload: dict[str, Any] | None = None
            try:
                from ..services.uncertainty_contract import build_uncertainty_report

                avg_calibrated = sum(calibrated) / len(calibrated) if calibrated else None
                avg_raw = sum(probs) / len(probs) if probs else None
                uncertainty = build_uncertainty_report(
                    raw_probability=avg_raw,
                    calibrated_probability=avg_calibrated if report_method != "raw" else None,
                    calibration_method=report_method,
                    sample_size=len(calibrated),
                    ece=report.ece,
                    brier_score=report.brier_score,
                    coverage_target=coverage_target,
                    calibration_report=report,
                )
                uncertainty_payload = uncertainty.to_dict()
            except Exception:
                pass

            diagnosis_payload: dict[str, Any] = {
                "workflow": "prediction_diagnosis_workflow",
                "method": workflow_method,
                "effective_method": report_method,
                "sample_size": len(calibrated),
                "probabilities": calibrated,
                "labels": ys,
                "label_source": "outcomes" if outcomes is not None else "labels",
                "calibration_report": report.to_dict(),
                "interval_examples": interval_examples,
                "conformal_prediction": conformal_result.to_dict(),
                "recommendations": list(report.notes),
            }
            if uncertainty_payload:
                diagnosis_payload["uncertainty"] = uncertainty_payload

            persisted_artifact_id = await _persist_optional_artifact(
                enabled=bool(persist_artifact),
                artifact_id=output_artifact_id,
                strategy="prediction_diagnosis",
                payload={
                    "artifact_type": "prediction_diagnosis",
                    "dataset_id": dataset_id,
                    "run_id": run_id,
                    "payload": diagnosis_payload,
                },
            )
            if persisted_artifact_id:
                diagnosis_payload["artifact_id"] = persisted_artifact_id

            if persisted_artifact_id:
                lineage_ctx.set_artifact(persisted_artifact_id)

            return ok_with_meta(
                diagnosis_payload,
                tool_name="prediction_diagnosis_workflow",
                action=workflow_method,
                started_at=started_at,
                source_chain=source_chain,
                extra_meta={
                    "quality": {
                        "status": report.quality_band,
                        "brier_score": report.brier_score,
                        "ece": report.ece,
                        "sample_size": report.sample_size,
                        "conformal_backend_used": conformal_result.backend_used,
                    },
                    "side_effect": {
                        "level": "stateful" if persisted_artifact_id else "read_only",
                        "target": persisted_artifact_id or "prediction_inputs",
                        "confirmation_required": False,
                        "idempotent": not bool(persisted_artifact_id),
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "degraded": report.quality_band in {"poor", "unknown"} or bool(conformal_result.fallback_used),
                },
            )
        except Exception as exc:
            return fail_with_meta(
                str(exc),
                tool_name="prediction_diagnosis_workflow",
                action=workflow_method,
                started_at=started_at,
                source_chain=source_chain,
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "quality": {"status": "failed", "workflow": "prediction_diagnosis_workflow"},
                    "side_effect": {"level": "stateful" if persist_artifact or output_artifact_id else "read_only", "target": "prediction_inputs"},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "degraded": True,
                },
            )

    @mcp.tool(
        title="Data Quality Workflow",
        description="Assess dataset completeness and minimum quality gates with machine-readable diagnostics.",
        structured_output=True,
        meta=build_tool_meta("data_quality_workflow"),
    )
    async def data_quality_workflow(
        dataset_id: str | None = None,
        records: list[dict[str, Any]] | None = None,
        required_fields: list[str] | None = None,
        as_of_field: str | None = None,
        as_of_value: str | None = None,
        source: str = "workflow.input",
        source_chain: list[str] | None = None,
        minimum_quality_threshold: float = 0.95,
        persist_artifact: bool = False,
        output_artifact_id: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        rows = list(records or [])
        required = [str(item).strip() for item in list(required_fields or []) if str(item).strip()]
        chain = [str(item).strip() for item in list(source_chain or ["workflow.data_quality"]) if str(item).strip()]
        lineage_ctx = LineageContext.create("data_quality_workflow", dataset_id=dataset_id)
        missing_counter: dict[str, int] = {field: 0 for field in required}
        failed_row_indices: list[int] = []

        try:
            import json as _json
            from ..services.adapters.data_validation_adapter import get_data_validation_adapter

            for idx, row in enumerate(rows):
                missing = infer_missing_fields(row, required)
                if missing:
                    failed_row_indices.append(idx)
                for field in missing:
                    missing_counter[field] = missing_counter.get(field, 0) + 1

            accepted_count = len(rows) - len(failed_row_indices)
            ratio = 1.0 if not rows else accepted_count / len(rows)
            adapter = get_data_validation_adapter(prefer_gx=True)
            validation_result = adapter.validate_dataset(
                rows,
                {
                    "required_fields": required,
                    "min_record_count": 1 if rows else 0,
                    "min_quality_threshold": minimum_quality_threshold,
                },
            )
            checkpoint = adapter.create_checkpoint(
                checkpoint_name=f"{dataset_id or 'dataset'}_runtime_checkpoint",
                validation_results=[validation_result],
            )
            minimum_quality_passed = ratio >= float(minimum_quality_threshold) and bool(validation_result.passed)
            representative_asof = as_of_value
            if representative_asof is None and as_of_field:
                for row in rows:
                    if isinstance(row, dict) and row.get(as_of_field):
                        representative_asof = row.get(as_of_field)
                        break

            quality_meta = build_quality_meta(
                source=source,
                source_chain=chain,
                asof_value=representative_asof,
                missing_fields=[field for field, count in missing_counter.items() if count > 0],
                degraded=not minimum_quality_passed,
                success=True,
                accepted_count=accepted_count,
                rejected_count=len(failed_row_indices),
                minimum_quality_threshold=minimum_quality_threshold,
                minimum_quality_passed=minimum_quality_passed,
            )
            quality_meta["validation_backend_requested"] = validation_result.backend_requested
            quality_meta["validation_backend_used"] = validation_result.backend_used
            quality_meta["validation_fallback_used"] = validation_result.fallback_used
            quality_meta["validation_fallback_reason"] = validation_result.fallback_reason

            validation_payload = validation_result.to_dict()
            checkpoint_payload = dict(checkpoint or {})
            checkpoint_payload["validations"] = list(checkpoint_payload.get("validations") or [])[:3]

            payload = {
                "workflow": "data_quality_workflow",
                "dataset_id": dataset_id,
                "row_count": len(rows),
                "required_fields": required,
                "failed_row_indices": failed_row_indices[:50],
                "missing_by_field": missing_counter,
                "accepted_ratio": round(ratio, 6),
                "quality_meta": quality_meta,
                "validation_result": validation_payload,
                "checkpoint": checkpoint_payload,
                "remediation_hints": [
                    "补齐 required_fields 中缺失最多的字段",
                    "为每条记录补充统一的 as_of 时间或日期字段",
                    "若当前快照仅为抽样，请在写入下游前补做全量校验",
                ],
            }
            payload = _json.loads(_json.dumps(payload, ensure_ascii=False, default=str))

            persisted_artifact_id = await _persist_optional_artifact(
                enabled=bool(persist_artifact),
                artifact_id=output_artifact_id,
                strategy="dataset_quality_snapshot",
                payload={
                    "artifact_type": "dataset_quality_snapshot",
                    "dataset_id": dataset_id,
                    "quality": quality_meta,
                    "payload": payload,
                },
            )
            if persisted_artifact_id:
                payload["artifact_id"] = persisted_artifact_id

            if persisted_artifact_id:
                lineage_ctx.set_artifact(persisted_artifact_id)

            return ok_with_meta(
                payload,
                tool_name="data_quality_workflow",
                action="validate",
                started_at=started_at,
                source_chain=chain,
                extra_meta={
                    "quality": quality_meta,
                    "side_effect": {
                        "level": "stateful" if persisted_artifact_id else "read_only",
                        "target": persisted_artifact_id or (dataset_id or "dataset"),
                        "confirmation_required": False,
                        "idempotent": not bool(persisted_artifact_id),
                    },
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "degraded": not minimum_quality_passed or bool(validation_result.fallback_used),
                },
            )
        except Exception as exc:
            return fail_with_meta(
                str(exc),
                tool_name="data_quality_workflow",
                action="validate",
                started_at=started_at,
                source_chain=chain,
                error_code="INTERNAL_ERROR",
                extra_meta={
                    "quality": {"status": "failed", "workflow": "data_quality_workflow"},
                    "side_effect": {"level": "stateful" if persist_artifact or output_artifact_id else "read_only", "target": dataset_id or "dataset"},
                    "pit": build_pit_meta_simple(as_of),
                    "lineage": lineage_ctx.to_meta(),
                    "degraded": True,
                },
            )

    @mcp.tool()
    async def ai_workflow_artifact(artifact_id: str) -> dict[str, Any]:
        """Inspect a persisted AI workflow artifact by artifact_id."""
        started_at = time.perf_counter()
        artifact = await get_artifact_async(artifact_id)
        if artifact is None:
            return fail_with_meta(
                f"artifact not found: {artifact_id}",
                tool_name="ai_workflow_artifact",
                action="get",
                started_at=started_at,
                source_chain=["services.artifact_registry"],
                error_code="NOT_FOUND",
                extra_meta={
                    "quality": {"status": "not_found"},
                    "side_effect": {"level": "read_only", "target": artifact_id, "confirmation_required": False},
                    "lineage": {"artifact_id": artifact_id},
                    "degraded": True,
                },
            )
        return ok_with_meta(
            {"artifact": artifact},
            tool_name="ai_workflow_artifact",
            action="get",
            started_at=started_at,
            source_chain=["services.artifact_registry"],
            extra_meta={
                "quality": {"status": "available"},
                "side_effect": {"level": "read_only", "target": artifact_id, "confirmation_required": False},
                "lineage": {"artifact_id": artifact_id},
                "degraded": False,
            },
        )

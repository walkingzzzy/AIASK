

def maybe_grant_provisional_incubation(
    strategy: Optional[dict],
    quality_gate: Optional[dict],
    *,
    validation_report: Optional[dict] = None,
    risk_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict:
    gate = normalize_quality_gate_result(quality_gate)
    if gate.get("passed"):
        return gate
    if not is_factory_ai_prototype_strategy(strategy):
        return gate
    if not has_only_statistical_gate_failures(gate):
        return gate

    # Fix #3: 风险报告为空时不能通过临时孵化（0.0 默认值会绕过阈值检查）
    if not risk_report:
        return gate

    # Fix #7: AI 原型不能完全绕过统计验证 — 至少通过 4 项中的 2 项
    checks_passed, passed_names, failed_names = _count_statistical_checks_passed(gate)
    if checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED:
        logger.info(
            "Provisional incubation denied: only %d/%d statistical checks passed (%s failed)",
            checks_passed, checks_passed + len(failed_names), ", ".join(failed_names),
        )
        return gate

    metrics = dict(backtest_metrics or {})
    # Fix #1/#2: 使用独立的临时孵化阈值，比回测初筛更严格
    sharpe_ratio = safe_metric_value(metrics, "sharpe_ratio")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    trades_count = safe_metric_value(metrics, "trade_count", "trades_count")
    if (
        sharpe_ratio < PROVISIONAL_PASS_THRESHOLDS["sharpe_min"]
        or max_drawdown > PROVISIONAL_PASS_THRESHOLDS["mdd_max"]
        or trades_count < PROVISIONAL_PASS_THRESHOLDS["trades_min"]
    ):
        return gate

    risk = dict(risk_report or {})
    var_percent = safe_metric_value(risk, "var_percent")
    cvar_percent = safe_metric_value(risk, "cvar_percent")
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if (
        var_percent > RISK_REPORT_THRESHOLDS["var_percent_max"]
        or cvar_percent > RISK_REPORT_THRESHOLDS["cvar_percent_max"]
        or stress_loss_percent <= RISK_REPORT_THRESHOLDS["stress_loss_percent_min"]
    ):
        return gate

    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    validation_grade = str(rating.get("grade") or "").strip().upper()

    warnings = list(gate.get("reasons") or [])
    if validation_grade == "D" and "validation_grade_d" not in warnings:
        warnings.append("validation_grade_d")
    # 将未通过的统计检查加入 warnings（而非彻底忽略）
    for fname in failed_names:
        tag = f"provisional_skip:{fname}"
        if tag not in warnings:
            warnings.append(tag)
    warnings = list(dict.fromkeys(warnings))
    return normalize_quality_gate_result({
        **gate,
        "passed": True,
        "passed_strict": False,
        "provisional_pass": True,
        "review_mode": "incubation_only",
        "reasons": [],
        "reason": "",
        "warnings": warnings,
        "original_reasons": gate.get("reasons") or [],
        "original_reason_codes": gate.get("reason_codes") or [],
        "statistical_checks_passed": checks_passed,
        "statistical_checks_passed_names": passed_names,
        "statistical_checks_failed_names": failed_names,
    })


def build_quality_report(
    strategy_id: str,
    strategy_type: Optional[str],
    quality_gate: Optional[dict],
    validation_report: Optional[dict],
    risk_report: Optional[dict],
    dedup_report: Optional[dict],
    backtest_metrics: Optional[dict],
    snapshot: Optional[dict],
    status_after_review: Optional[str],
    review_source: str,
    report_type: str,
    spawn_reason: Optional[str] = None,
    submission_audit: Optional[dict] = None,
) -> dict:
    return _shared_build_quality_report(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        quality_gate=quality_gate,
        validation_report=validation_report,
        risk_report=risk_report,
        dedup_report=dedup_report,
        backtest_metrics=backtest_metrics,
        snapshot=snapshot,
        status_after_review=status_after_review,
        review_source=review_source,
        report_type=report_type,
        spawn_reason=spawn_reason,
        submission_audit=submission_audit,
    )


def normalize_quality_report_contract(
    report: Optional[dict],
    *,
    strategy_id: Optional[str] = None,
    strategy_type: Optional[str] = None,
    default_review_source: str = "strategy_manager.review_report",
) -> dict:
    raw = dict(report or {})
    if not raw:
        return {}

    summary = dict(raw.get("summary") or {})
    quality_gate = dict(raw.get("quality_gate") or {})
    validation_profile = dict(raw.get("validation_profile") or {})
    run_correction = dict(raw.get("run_correction") or {})
    attempt_adjustment = dict(raw.get("attempt_adjustment") or {})
    backtest_metrics = dict(raw.get("backtest_metrics") or {})

    mirrored_backtest_fields = (
        "constraint_check",
        "event_window_config",
        "event_window_metrics",
        "position_assumption",
        "cost_assumptions",
        "explicit_cost_breakdown",
        "implicit_cost_breakdown",
        "tradability_summary",
        "capacity_summary",
        "implementation_shortfall_model_source",
        "implementation_shortfall_components",
        "backtest_assumptions",
    )
    for field_name in mirrored_backtest_fields:
        if backtest_metrics.get(field_name) in (None, "", [], {}) and raw.get(field_name) not in (None, "", [], {}):
            backtest_metrics[field_name] = deepcopy(raw.get(field_name))

    if quality_gate.get("attempt_adjustment") in (None, "", [], {}) and attempt_adjustment:
        quality_gate["attempt_adjustment"] = attempt_adjustment
    if not quality_gate.get("primary_validation_layer"):
        quality_gate["primary_validation_layer"] = (
            summary.get("primary_validation_layer")
            or validation_profile.get("primary_validation_layer")
        )
    if not quality_gate.get("profile"):
        quality_gate["profile"] = validation_profile.get("profile")
    if not quality_gate.get("validation_focus"):
        quality_gate["validation_focus"] = validation_profile.get("validation_focus")
    run_correction_key_map = {
        "mode": "run_correction_mode",
        "raw_sharpe_proxy": "raw_sharpe_proxy",
        "deflated_sharpe_proxy": "deflated_sharpe_proxy",
        "pbo_proxy": "pbo_proxy",
        "reality_check_pvalue_proxy": "reality_check_pvalue_proxy",
        "spa_pvalue_proxy": "spa_pvalue_proxy",
        "multiple_testing_mode": "multiple_testing_mode",
        "deflated_sharpe_ratio": "deflated_sharpe_ratio",
        "deflated_sharpe_reference_sharpe": "deflated_sharpe_reference_sharpe",
        "deflated_sharpe_effective_trials": "deflated_sharpe_effective_trials",
        "pbo": "pbo",
        "white_reality_check_pvalue": "white_reality_check_pvalue",
        "hansen_spa_pvalue": "hansen_spa_pvalue",
        "multiple_testing": "multiple_testing",
    }
    for source_key, target_key in run_correction_key_map.items():
        if quality_gate.get(target_key) in (None, "", [], {}) and run_correction.get(source_key) not in (None, "", [], {}):
            quality_gate[target_key] = deepcopy(run_correction.get(source_key))

    submission_audit_fields = (
        "committee_review",
        "task_signature",
        "refresh_mode",
        "submission_lane",
        "direct_trade_candidate",
        "live_review_ready",
        "paper_lane_ready",
        "paper_account_id",
        "paper_account_status",
        "runtime_control_mode",
        "runtime_control_status",
        "promotion_review_id",
        "promotion_review_status",
        "promotion_review_recommendation",
        "pool_admission_applied",
        "promotion_applied_transition",
        "formal_track_requested",
        "formal_track_eligible",
        "formal_track_blockers",
        "submission_action",
        "submission_action_type",
        "submission_action_trigger",
        "submission_action_gaps",
        "submission_action_fallback_conditions",
        "submission_action_next_step",
        "submission_action_completed",
        "task_preference",
        "candidate_provenance",
    )
    submission_audit = {}
    for field_name in submission_audit_fields:
        value = raw.get(field_name)
        if value in (None, "", [], {}):
            value = summary.get(field_name)
        if value not in (None, "", [], {}):
            submission_audit[field_name] = deepcopy(value)

    raw_strategy = raw.get("strategy")
    strategy_payload = dict(raw_strategy) if isinstance(raw_strategy, dict) else {}

    normalized = _shared_build_quality_report(
        strategy_id=str(strategy_id or summary.get("strategy_id") or raw.get("strategy_id") or "").strip(),
        strategy_type=(
            strategy_type
            or summary.get("strategy_type")
            or raw.get("strategy_type")
            or strategy_payload.get("strategy_type")
        ),
        quality_gate=quality_gate,
        validation_report=dict(raw.get("validation_report") or {}),
        risk_report=dict(raw.get("risk_report") or {}),
        dedup_report=dict(raw.get("dedup_report") or {}),
        backtest_metrics=backtest_metrics,
        snapshot=dict(raw.get("snapshot") or {}),
        status_after_review=summary.get("status_after_review") or raw.get("status_after_review"),
        review_source=summary.get("review_source") or default_review_source,
        report_type=str(raw.get("report_type") or "submission"),
        spawn_reason=summary.get("spawn_reason"),
        submission_audit=submission_audit or None,
    )
    normalized_summary = dict(normalized.get("summary") or {})
    for field_name in (
        "prediction_trace_id",
        "trace_id",
        "research_protocol_version",
        "candidate_contract_version",
        "spec_completeness",
        "field_provenance_summary",
        "completion_issues",
        "hard_failures",
        "gate_a",
        "gate_b",
        "gate_c",
    ):
        value = raw.get(field_name)
        if value in (None, "", [], {}):
            value = summary.get(field_name)
        if value in (None, "", [], {}):
            continue
        normalized[field_name] = deepcopy(value)
        normalized_summary[field_name] = deepcopy(value)
    normalized["summary"] = normalized_summary
    return {**raw, **normalized}


def normalize_factory_run_summary_contract(row: Optional[dict]) -> dict:
    raw = dict(row or {})
    if not raw:
        return {}
    dto = normalize_run_result_to_summary(raw).to_dict()
    detail_dto = normalize_run_result_to_detail(raw).to_dict()
    summary_payload = dict(raw.get("summary") or dto.get("summary") or {})
    try:
        from strategy_factory.application.factory_market_views import (
            build_research_window_status,
            hydrate_full_market_topn_payload,
        )

        research_window = {
            **dict(raw.get("research_window") or summary_payload.get("research_window") or {}),
            **build_research_window_status(summary_payload),
        }
        full_market_topn = hydrate_full_market_topn_payload(
            raw.get("full_market_topn")
            or summary_payload.get("full_market_topn")
            or {}
        )
    except Exception:
        research_window = dict(raw.get("research_window") or summary_payload.get("research_window") or {})
        full_market_topn = dict(
            raw.get("full_market_topn")
            or summary_payload.get("full_market_topn")
            or {}
        )
    return {
        **raw,
        **dto,
        "artifact_refs": list(raw.get("artifact_refs") or dto.get("artifact_refs") or []),
        "parity_result": dict(raw.get("parity_result") or dto.get("parity_result") or {}),
        "submission_artifact": dict(
            raw.get("submission_artifact") or detail_dto.get("submission_artifact") or {}
        ),
        "research_window": research_window,
        "full_market_topn": full_market_topn,
    }


def merge_factory_run_summary_observability(
    summary: Optional[dict],
    payload: Optional[dict],
) -> dict:
    merged = dict(summary or {})
    source = dict(payload or {})
    for field in _FACTORY_SUMMARY_OBSERVABILITY_FIELDS:
        value = source.get(field)
        if value in (None, "", [], {}):
            continue
        merged[field] = value
    return merged


def normalize_factory_run_detail_contract(row: Optional[dict]) -> dict:
    raw = dict(row or {})
    if not raw:
        return {}
    dto = normalize_run_result_to_detail(raw).to_dict()
    summary_payload = dict(raw.get("summary") or dto.get("summary") or {})
    try:
        from strategy_factory.application.factory_market_views import (
            build_research_window_status,
            hydrate_full_market_topn_payload,
        )

        research_window = {
            **dict(raw.get("research_window") or summary_payload.get("research_window") or {}),
            **build_research_window_status(summary_payload),
        }
        full_market_topn = hydrate_full_market_topn_payload(
            raw.get("full_market_topn")
            or summary_payload.get("full_market_topn")
            or dict(dict(raw.get("stages") or {}).get("autonomy") or {}).get("full_market_topn")
            or {}
        )
    except Exception:
        research_window = dict(raw.get("research_window") or summary_payload.get("research_window") or {})
        full_market_topn = dict(
            raw.get("full_market_topn")
            or summary_payload.get("full_market_topn")
            or dict(dict(raw.get("stages") or {}).get("autonomy") or {}).get("full_market_topn")
            or {}
        )
    raw_submission_artifact = dict(raw.get("submission_artifact") or {})
    submission_artifact = dict(dto.get("submission_artifact") or {})
    if raw_submission_artifact:
        for key, value in raw_submission_artifact.items():
            if value in (None, "", [], {}):
                continue
            submission_artifact[key] = deepcopy(value)
    raw_stages = dict(raw.get("stages") or {})
    stage_payloads = {
        name: dict(payload or {})
        for name, payload in raw_stages.items()
        if isinstance(payload, dict)
    }
    stage_storage_meta = {
        name: payload
        for name, payload in raw_stages.items()
        if not isinstance(payload, dict)
    }
    return {
        **raw,
        **dto,
        "summary": merge_factory_run_summary_observability(
            raw.get("summary") or {},
            dto,
        ),
        "artifact_refs": list(raw.get("artifact_refs") or dto.get("artifact_refs") or []),
        "parity_result": dict(raw.get("parity_result") or dto.get("parity_result") or {}),
        "stages": stage_payloads or dict(dto.get("stages") or {}),
        "stage_storage_meta": stage_storage_meta,
        "snapshot_summary": dict(raw.get("snapshot_summary") or dto.get("snapshot_summary") or {}),
        "quality_gate": dict(raw.get("quality_gate") or raw.get("gate_report") or dto.get("quality_gate") or {}),
        "research_summary": dict(dto.get("research_summary") or {}),
        "research_plane": dict(dto.get("research_plane") or raw.get("research_plane") or {}),
        "research_artifact": dict(dto.get("research_artifact") or {}),
        "task_artifact": dict(dto.get("task_artifact") or {}),
        "candidate_artifact": dict(dto.get("candidate_artifact") or {}),
        "evidence_artifact": dict(dto.get("evidence_artifact") or {}),
        "governance_plane": dict(dto.get("governance_plane") or raw.get("governance_plane") or {}),
        "gate_artifact": dict(dto.get("gate_artifact") or {}),
        "gate_artifact_v2": dict(dto.get("gate_artifact_v2") or {}),
        "dedup_artifact": dict(dto.get("dedup_artifact") or {}),
        "submission_artifact": submission_artifact,
        "governance_evidence_artifact": dict(dto.get("governance_evidence_artifact") or {}),
        "gate_a": dict(dto.get("gate_a") or {}),
        "gate_b": dict(dto.get("gate_b") or {}),
        "gate_c": dict(dto.get("gate_c") or {}),
        "protocol_versions": dict(dto.get("protocol_versions") or {}),
        "prediction_trace_summary": dict(dto.get("prediction_trace_summary") or {}),
        "prediction_trace_ledger": dict(dto.get("prediction_trace_ledger") or {}),
        "feedback_summary": dict(dto.get("feedback_summary") or {}),
        "incubation_summary": dict(dto.get("incubation_summary") or {}),
        "live_ready_summary": dict(dto.get("live_ready_summary") or {}),
        "research_window": research_window,
        "full_market_topn": full_market_topn,
    }


def _build_capability_health_entry(
    *,
    supported: bool,
    enabled: bool,
    dependency_ready: bool,
    recent_run_ready: bool,
    degraded_reason: Optional[str] = None,
) -> dict[str, Any]:
    healthy = bool(supported and enabled and dependency_ready and recent_run_ready)
    reason = str(degraded_reason or "").strip() or None
    if reason is None:
        if not supported:
            reason = "storage_contract_missing"
        elif not enabled:
            reason = "feature_disabled"
        elif not dependency_ready:
            reason = "dependency_probe_failed"
        elif not recent_run_ready:
            reason = "missing_recent_run_evidence"
    return {
        "supported": bool(supported),
        "enabled": bool(enabled),
        "healthy": bool(healthy),
        "degraded_reason": reason,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }


def build_factory_capability_health(
    db,
    *,
    factory_constants: Optional[dict[str, Any]] = None,
    latest_run: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    constants = dict(factory_constants or {})
    run_payload = dict(latest_run or {})
    parity_result = dict(run_payload.get("parity_result") or {})
    latest_status = str(run_payload.get("status") or "").strip().lower()
    parity_status = str(parity_result.get("status") or "").strip().lower()
    recent_run_ready = bool(run_payload) and latest_status not in {"failed", "error"}
    recent_run_reason = None
    if not run_payload:
        recent_run_reason = "missing_recent_run_evidence"
    elif latest_status in {"failed", "error"}:
        recent_run_reason = "latest_run_failed"
    elif parity_status in {"mismatch", "shadow_failed"}:
        recent_run_ready = False
        recent_run_reason = "latest_parity_mismatch"

    def _entry(
        *,
        supported: bool,
        enabled: bool = True,
        dependency_ready: bool = True,
        require_recent_run: bool = False,
    ) -> dict[str, Any]:
        return _build_capability_health_entry(
            supported=supported,
            enabled=enabled,
            dependency_ready=dependency_ready,
            recent_run_ready=(recent_run_ready if require_recent_run else True),
            degraded_reason=(recent_run_reason if require_recent_run else None),
        )

    health = {
        "factory_runs": _entry(
            supported=hasattr(db, "save_strategy_factory_run") and hasattr(db, "get_latest_strategy_factory_run"),
            require_recent_run=True,
        ),
        "factory_dispatch": _entry(
            supported=hasattr(db, "create_strategy_factory_dispatch")
            and hasattr(db, "get_strategy_factory_dispatch"),
            require_recent_run=True,
        ),
        "factory_bulk_lane": _entry(
            supported=hasattr(db, "list_stock_universe") and hasattr(db, "save_strategy_factory_run"),
            enabled=bool(constants.get("STOCK_STRATEGY_MATRIX_ENABLED")),
            require_recent_run=True,
        ),
        "paper_incubation": _entry(
            supported=hasattr(db, "save_strategy_incubation_account")
            and hasattr(db, "save_strategy_incubation_metric"),
        ),
        "paper_trading": _entry(
            supported=hasattr(db, "save_paper_account")
            and hasattr(db, "save_paper_order")
            and hasattr(db, "get_paper_nav_rows"),
        ),
        "incubation_pipeline": _entry(
            supported=hasattr(db, "save_strategy_incubation_pipeline_snapshot")
            and hasattr(db, "list_strategy_incubation_metrics"),
        ),
        "runtime_risk": _entry(
            supported=hasattr(db, "save_strategy_runtime_risk_event"),
        ),
        "runtime_controls": _entry(
            supported=hasattr(db, "save_strategy_runtime_control")
            and hasattr(db, "get_strategy_runtime_control"),
        ),
        "runtime_alerting": _entry(
            supported=hasattr(db, "save_strategy_runtime_alert")
            and hasattr(db, "list_strategy_runtime_alerts"),
        ),
        "promotion_pipeline": _entry(
            supported=hasattr(db, "save_strategy_promotion_review")
            and hasattr(db, "get_latest_strategy_promotion_review"),
        ),
        "projection_snapshots": _entry(
            supported=hasattr(db, "save_strategy_projection_snapshot")
            and hasattr(db, "get_latest_strategy_projection_snapshot"),
        ),
        "vector_platform": _entry(
            supported=hasattr(db, "save_strategy_vector_profile")
            and hasattr(db, "save_vector_index_registry"),
        ),
        "ai_generation": _entry(
            supported=hasattr(db, "save_strategy_generation_experiment")
            and hasattr(db, "save_strategy_task_run"),
        ),
        "quality_governance": _entry(
            supported=hasattr(db, "save_strategy_quality_report")
            and hasattr(db, "list_strategy_status_events"),
        ),
        "runtime_cycle": _entry(
            supported=hasattr(db, "save_strategy_task_run")
            and hasattr(db, "save_strategy_incubation_metric"),
        ),
    }
    return health

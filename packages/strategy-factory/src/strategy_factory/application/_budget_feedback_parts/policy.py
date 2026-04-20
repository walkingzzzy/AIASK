

def normalize_feedback_input_contract(
    snapshot_or_feedback: Any,
    *,
    reason: str | None = None,
    summary: dict[str, Any] | None = None,
    available: bool | None = None,
) -> dict[str, Any]:
    payload = _coerce_mapping(snapshot_or_feedback)
    feedback_root = extract_feedback_root(payload)
    summary_payload = dict(payload.get("summary") or {})
    if isinstance(summary, dict):
        summary_payload.update(summary)
    family_count = int(summary_payload.get("family_count") or len(feedback_root))
    target_pool_scope_count = int(
        summary_payload.get("target_pool_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="target_pool_feedback")
    )
    generator_mode_scope_count = int(
        summary_payload.get("generator_mode_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="generator_mode_feedback")
    )
    holding_bucket_scope_count = int(
        summary_payload.get("holding_bucket_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="holding_bucket_feedback")
    )
    contract_available = bool(feedback_root) if available is None else bool(available)
    resolved_reason = str(
        reason
        if reason is not None
        else payload.get("reason")
        or ("feedback_unavailable" if not contract_available else "")
    ).strip() or None
    if contract_available and resolved_reason == "feedback_unavailable":
        resolved_reason = None
    paper_hit_ratio = (
        safe_float(summary_payload.get("paper_hit_ratio"), 0.5)
        if "paper_hit_ratio" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_hit_ratio",
            default=0.5,
        )
    )
    paper_skill_lcb = (
        safe_float(summary_payload.get("paper_skill_lcb"))
        if "paper_skill_lcb" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_skill_lcb",
            default=0.0,
        )
    )
    paper_recent_skill_lcb = (
        safe_float(summary_payload.get("paper_recent_skill_lcb"))
        if "paper_recent_skill_lcb" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_recent_skill_lcb",
            default=0.0,
        )
    )
    paper_stability_gap = (
        safe_float(summary_payload.get("paper_stability_gap"))
        if "paper_stability_gap" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_stability_gap",
            default=0.0,
        )
    )
    paper_coverage_ratio = (
        safe_float(summary_payload.get("paper_coverage_ratio"), 1.0)
        if "paper_coverage_ratio" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_coverage_ratio",
            default=1.0,
        )
    )
    execution_conversion_efficiency_observed_count = int(
        summary_payload.get("execution_conversion_efficiency_observed_count")
        or sum(
            1
            for bucket in feedback_root.values()
            if isinstance(bucket, dict)
            and _metric_present(dict(bucket), "execution_conversion_efficiency")
        )
    )
    execution_conversion_efficiency = (
        safe_float(summary_payload.get("execution_conversion_efficiency"))
        if "execution_conversion_efficiency" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="execution_conversion_efficiency",
            default=0.0,
        )
    )
    legacy_control_mode_counts = (
        _merge_feedback_count_maps(summary_payload.get("legacy_control_mode_counts"))
        if "legacy_control_mode_counts" in summary_payload
        else _family_control_mode_counts(feedback_root, signal_mode="legacy")
    )
    skill_control_mode_counts = (
        _merge_feedback_count_maps(summary_payload.get("skill_control_mode_counts"))
        if "skill_control_mode_counts" in summary_payload
        else _family_control_mode_counts(feedback_root, signal_mode="skill")
    )
    dual_axis_summary = (
        {
            "budget_action_counts": _merge_feedback_count_maps(
                summary_payload.get("budget_action_counts")
            ),
            "execution_optimization_queue_count": _safe_int(
                summary_payload.get("execution_optimization_queue_count")
            ),
            "small_budget_observe_count": _safe_int(
                summary_payload.get("small_budget_observe_count")
            ),
            "prioritize_scale_count": _safe_int(
                summary_payload.get("prioritize_scale_count")
            ),
            "cool_or_freeze_count": _safe_int(
                summary_payload.get("cool_or_freeze_count")
            ),
            "retain_family_reduce_budget_count": _safe_int(
                summary_payload.get("retain_family_reduce_budget_count")
            ),
            "dual_axis_action_family_count": _safe_int(
                summary_payload.get("dual_axis_action_family_count")
            ),
        }
        if any(
            key in summary_payload
            for key in (
                "budget_action_counts",
                "execution_optimization_queue_count",
                "small_budget_observe_count",
                "prioritize_scale_count",
                "cool_or_freeze_count",
                "retain_family_reduce_budget_count",
                "dual_axis_action_family_count",
            )
        )
        else _dual_axis_feedback_summary(feedback_root)
    )
    normalized_summary = {
        **summary_payload,
        "family_count": family_count,
        "seeded_family_count": int(summary_payload.get("seeded_family_count") or family_count),
        "strategy_count": int(summary_payload.get("strategy_count") or 0),
        "runtime_alert_count": int(summary_payload.get("runtime_alert_count") or 0),
        "runtime_risk_event_count": int(summary_payload.get("runtime_risk_event_count") or 0),
        "signal_count_total": int(
            summary_payload.get("signal_count_total")
            or _sum_feedback_metric(feedback_root, metric_name="signal_count_total")
        ),
        "zero_signal_strategy_count": int(
            summary_payload.get("zero_signal_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="zero_signal_strategy_count")
        ),
        "low_signal_strategy_count": int(
            summary_payload.get("low_signal_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="low_signal_strategy_count")
        ),
        "observed_forward_window_count": int(
            summary_payload.get("observed_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="observed_forward_window_count")
        ),
        "missing_forward_window_count": int(
            summary_payload.get("missing_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="missing_forward_window_count")
        ),
        "expected_forward_window_count": int(
            summary_payload.get("expected_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="expected_forward_window_count")
        ),
        "promotion_ready_count": int(
            summary_payload.get("promotion_ready_count")
            or _sum_feedback_metric(feedback_root, metric_name="promotion_ready_count")
        ),
        "evidence_debt_strategy_count": int(
            summary_payload.get("evidence_debt_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="evidence_debt_strategy_count")
        ),
        "promotion_review_count": int(
            summary_payload.get("promotion_review_count")
            or _sum_feedback_metric(feedback_root, metric_name="promotion_review_count")
        ),
        "target_pool_scope_count": target_pool_scope_count,
        "generator_mode_scope_count": generator_mode_scope_count,
        "holding_bucket_scope_count": holding_bucket_scope_count,
        "promotion_review_status_counts": (
            _merge_feedback_count_maps(summary_payload.get("promotion_review_status_counts"))
            if dict(summary_payload.get("promotion_review_status_counts") or {})
            else _merge_feedback_count_maps(
                *[
                    dict(bucket.get("promotion_review_status_counts") or {})
                    for bucket in feedback_root.values()
                    if isinstance(bucket, dict)
                ]
            )
        ),
        "promotion_review_recommendation_counts": (
            _merge_feedback_count_maps(summary_payload.get("promotion_review_recommendation_counts"))
            if dict(summary_payload.get("promotion_review_recommendation_counts") or {})
            else _merge_feedback_count_maps(
                *[
                    dict(bucket.get("promotion_review_recommendation_counts") or {})
                    for bucket in feedback_root.values()
                    if isinstance(bucket, dict)
                ]
            )
        ),
        "paper_hit_ratio": round(paper_hit_ratio, 4),
        "paper_skill_lcb": round(paper_skill_lcb, 4),
        "paper_recent_skill_lcb": round(paper_recent_skill_lcb, 4),
        "paper_stability_gap": round(paper_stability_gap, 4),
        "paper_coverage_ratio": round(paper_coverage_ratio, 4),
        "execution_conversion_efficiency": (
            round(execution_conversion_efficiency, 4)
            if execution_conversion_efficiency_observed_count > 0
            else None
        ),
        "execution_conversion_efficiency_observed_count": (
            execution_conversion_efficiency_observed_count
        ),
        "legacy_control_mode_counts": legacy_control_mode_counts,
        "skill_control_mode_counts": skill_control_mode_counts,
        "budget_action_counts": dict(dual_axis_summary.get("budget_action_counts") or {}),
        "execution_optimization_queue_count": int(
            dual_axis_summary.get("execution_optimization_queue_count") or 0
        ),
        "small_budget_observe_count": int(
            dual_axis_summary.get("small_budget_observe_count") or 0
        ),
        "prioritize_scale_count": int(
            dual_axis_summary.get("prioritize_scale_count") or 0
        ),
        "cool_or_freeze_count": int(dual_axis_summary.get("cool_or_freeze_count") or 0),
        "retain_family_reduce_budget_count": int(
            dual_axis_summary.get("retain_family_reduce_budget_count") or 0
        ),
        "dual_axis_action_family_count": int(
            dual_axis_summary.get("dual_axis_action_family_count") or 0
        ),
    }
    strategy_count = int(normalized_summary.get("strategy_count") or 0)
    expected_forward_window_count = int(normalized_summary.get("expected_forward_window_count") or 0)
    zero_signal_ratio = (
        round(int(normalized_summary.get("zero_signal_strategy_count") or 0) / strategy_count, 4)
        if strategy_count
        else 0.0
    )
    low_signal_ratio = (
        round(int(normalized_summary.get("low_signal_strategy_count") or 0) / strategy_count, 4)
        if strategy_count
        else 0.0
    )
    forward_window_coverage_ratio = (
        round(
            int(normalized_summary.get("observed_forward_window_count") or 0)
            / expected_forward_window_count,
            4,
        )
        if expected_forward_window_count
        else 1.0
    )
    promotion_ready_ratio = (
        round(int(normalized_summary.get("promotion_ready_count") or 0) / strategy_count, 4)
        if strategy_count
        else 1.0
    )
    promotion_review_coverage_ratio = (
        round(int(normalized_summary.get("promotion_review_count") or 0) / strategy_count, 4)
        if strategy_count
        else 1.0
    )
    evidence_debt_ratio = round(
        min(
            max(
                zero_signal_ratio * 0.45
                + (1.0 - forward_window_coverage_ratio) * 0.25
                + (1.0 - promotion_ready_ratio) * 0.15
                + (1.0 - promotion_review_coverage_ratio) * 0.15,
                0.0,
            ),
            1.0,
        ),
        4,
    )
    gate_failure_rate = round(1.0 - promotion_ready_ratio, 4)
    trace_completeness_ratio = round(1.0 - evidence_debt_ratio, 4)
    admission_quality_objective = round(
        min(
            max(
                promotion_ready_ratio * 0.35
                + forward_window_coverage_ratio * 0.20
                + promotion_review_coverage_ratio * 0.15
                + trace_completeness_ratio * 0.15
                + (1.0 - gate_failure_rate) * 0.15,
                0.0,
            ),
            1.0,
        ),
        4,
    )
    paper_hit_ratio = min(max(safe_float(normalized_summary.get("paper_hit_ratio"), 0.5), 0.0), 1.0)
    paper_skill_lcb = min(max(safe_float(normalized_summary.get("paper_skill_lcb"), 0.0), -1.0), 1.0)
    realized_turnover = min(max(safe_float(normalized_summary.get("realized_turnover"), 0.0), 0.0), 2.0)
    high_precision_objective = round(
        min(
            max(
                promotion_ready_ratio * 0.25
                + trace_completeness_ratio * 0.15
                + (1.0 - gate_failure_rate) * 0.15
                + max(paper_hit_ratio - 0.5, 0.0) * 0.20
                + max(paper_skill_lcb, 0.0) * 0.15
                + max(0.8 - realized_turnover, 0.0) * 0.10,
                0.0,
            ),
            1.0,
        ),
        4,
    )
    normalized_summary.update(
        {
            "zero_signal_ratio": zero_signal_ratio,
            "low_signal_ratio": low_signal_ratio,
            "forward_window_coverage_ratio": forward_window_coverage_ratio,
            "promotion_ready_ratio": promotion_ready_ratio,
            "promotion_review_coverage_ratio": promotion_review_coverage_ratio,
            "evidence_debt_ratio": evidence_debt_ratio,
            "gate_failure_rate": gate_failure_rate,
            "trace_completeness_ratio": trace_completeness_ratio,
            "admission_quality_objective": admission_quality_objective,
            "high_precision_objective": high_precision_objective,
        }
    )
    return {
        "contract_version": LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
        "available": contract_available,
        "reason": resolved_reason if not contract_available else resolved_reason,
        "feedback": feedback_root,
        "summary": normalized_summary,
    }


def extract_target_pool_id(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    contract_snapshot = dict(item.get("candidate_contract_snapshot") or {})
    targeting = dict(contract_snapshot.get("targeting") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or {})
    research_task = dict(item.get("research_task") or {})

    for value in (
        item.get("target_pool_id"),
        targeting.get("target_pool_id"),
        candidate_provenance.get("target_pool_id"),
        params.get("target_pool_id"),
        research_task.get("target_pool_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token
    return None


def derive_target_pool_id(payload: dict[str, Any] | None) -> str | None:
    explicit = extract_target_pool_id(payload)
    if explicit:
        return explicit

    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    event_context = dict(item.get("event_context") or research_task.get("event_context") or {})

    for value in (
        item.get("theme_code"),
        research_task.get("theme_code"),
        event_context.get("theme_code"),
        item.get("event_id"),
        research_task.get("event_id"),
        event_context.get("event_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token

    def _resolve_symbols(values: Any) -> list[str]:
        try:
            from ..domain.targets import _normalize_target_codes

            return list(_normalize_target_codes(values, limit=12))
        except Exception:
            return []

    stock_pool = dict(item.get("stock_pool") or research_task.get("stock_pool") or {})
    selection_mode = str(stock_pool.get("selection_mode") or "").strip().lower()
    symbols = _resolve_symbols(
        [
            stock_pool.get("symbols"),
            stock_pool.get("target_symbols"),
            item.get("target_symbols"),
            research_task.get("target_symbols"),
            event_context.get("target_symbols"),
        ]
    )
    if selection_mode and symbols:
        return f"{selection_mode}:{','.join(symbols)}"
    if symbols:
        return f"symbols:{','.join(symbols)}"
    return None


def extract_generator_mode(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})
    for value in (
        item.get("generator_mode"),
        item.get("generator_type"),
        research_task.get("generator_mode"),
        research_task.get("generator_type"),
        candidate_provenance.get("generator_mode"),
        candidate_provenance.get("generator_type"),
        params.get("generator_mode"),
        strategy_profile.get("generator_mode"),
    ):
        token = normalize_text(value)
        if token:
            return token
    task_source = _resolve_research_task_source(item)
    if task_source == "snapshot":
        return "rule"
    return None


def extract_holding_bucket(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or item.get("candidate_provenance") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})
    for value in (
        item.get("holding_period_bucket"),
        strategy_profile.get("holding_period_bucket"),
        candidate_provenance.get("holding_period_bucket"),
        params.get("holding_period_bucket"),
        research_task.get("holding_period_bucket"),
    ):
        token = normalize_text(value)
        if token:
            return token

    holding_horizon = dict(
        item.get("holding_horizon")
        or params.get("holding_horizon")
        or research_task.get("holding_window")
        or {}
    )
    max_days = _safe_int(
        holding_horizon.get("max_days") or holding_horizon.get("alpha_half_life")
    )
    if max_days > 0:
        if max_days <= 5:
            return "short"
        if max_days <= 20:
            return "medium"
        return "long"

    strategy_type = normalize_text(
        item.get("strategy_type")
        or research_task.get("candidate_family")
        or research_task.get("strategy_type")
    )
    if strategy_type in {"momentum", "rsi", "volatility_breakout", "gap_fill", "mean_reversion_short"}:
        return "short"
    if strategy_type in {"value_factor"}:
        return "long"
    if strategy_type:
        return "medium"
    return None


def extract_feedback_families(payload: dict[str, Any] | None) -> list[str]:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    provenance = dict(params.get("candidate_provenance") or item.get("candidate_provenance") or {})
    research_task = dict(item.get("research_task") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})

    families: list[str] = []

    def _append(value: Any) -> None:
        token = normalize_text(value)
        if token and token not in families:
            families.append(token)

    def _append_list(values: Any) -> None:
        if isinstance(values, (list, tuple, set)):
            for value in values:
                _append(value)
            return
        if values not in (None, "", [], {}):
            _append(values)

    for source in (item, research_task, provenance, params, strategy_profile):
        if not isinstance(source, dict):
            continue
        for key in ("candidate_family", "family", "strategy_family", "strategy_type"):
            _append(source.get(key))
        for key in ("strategy_preferences", "preferred_strategy_types", "allowed_strategy_types"):
            _append_list(source.get(key))
    return families


def _metric_value(bucket: dict[str, Any], metric: str) -> float | None:
    if not isinstance(bucket, dict):
        return None
    for key in _METRIC_ALIASES.get(metric, (metric,)):
        if bucket.get(key) is not None:
            return safe_float(bucket.get(key))
    return None


def _metric_present(bucket: dict[str, Any], metric: str) -> bool:
    if not isinstance(bucket, dict):
        return False
    return any(bucket.get(key) is not None for key in _METRIC_ALIASES.get(metric, (metric,)))


def _coerce_control_mode(value: Any) -> str:
    token = normalize_text(value) or "normal"
    if token not in CONTROL_MODE_SEVERITY:
        return "normal"
    return token

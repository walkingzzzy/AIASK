

def _metric_payload(item: dict[str, Any], *keys: str) -> float | None:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    run_correction = dict(payload.get("run_correction") or {})
    gate = dict(payload.get("gate_3") or {})
    for source in (payload, quality_summary, run_correction, gate):
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except Exception:
                continue
    return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    p = max(0.0, min(float(percentile), 1.0))
    index = p * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    result = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(result, 4)


def _grade_rates(distribution: dict[str, int], total: int) -> dict[str, float]:
    denominator = max(int(total or 0), 1)
    return {
        "raw_validation_a_rate": round(int(distribution.get("A") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_b_rate": round(int(distribution.get("B") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_c_rate": round(int(distribution.get("C") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_d_rate": round(int(distribution.get("D") or 0) / denominator, 4) if total else 0.0,
    }


def _rate(count: int, total: int) -> float:
    return round(int(count or 0) / int(total or 0), 4) if total else 0.0


def _is_raw_b_or_above(grade: str) -> bool:
    return str(grade or "").strip().upper() in {"A", "B"}


def _aggregate_family_quality_panel(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in list(strategies or []):
        family = _candidate_family(item) or "unknown"
        holding_bucket = _holding_bucket(item) or "unknown"
        validation_focus = _validation_focus(item) or "unknown"
        key = (family, holding_bucket, validation_focus)
        bucket = buckets.setdefault(
            key,
            {
                "strategy_family": family,
                "holding_period_bucket": holding_bucket,
                "validation_focus": validation_focus,
                "strategy_count": 0,
                "raw_validation_grade_distribution": {},
                "effective_validation_grade_distribution": {},
                "raw_validation_total_scores": [],
                "strict_incubation_ready_count": 0,
                "live_candidate_ready_count": 0,
                "raw_b_or_above_count": 0,
                "strict_ready_given_raw_b_count": 0,
                "live_ready_given_raw_b_count": 0,
                "trade_density_values": [],
                "post_cost_sharpe_values": [],
                "deflated_sharpe_ratio_values": [],
                "pbo_values": [],
            },
        )
        bucket["strategy_count"] += 1
        raw_grade = _raw_validation_grade(item)
        effective_grade = _effective_validation_grade(item)
        if raw_grade:
            bucket["raw_validation_grade_distribution"][raw_grade] = (
                bucket["raw_validation_grade_distribution"].get(raw_grade, 0) + 1
            )
        if effective_grade:
            bucket["effective_validation_grade_distribution"][effective_grade] = (
                bucket["effective_validation_grade_distribution"].get(effective_grade, 0) + 1
            )
        raw_score = _validation_total_score(item, raw=True)
        if raw_score is not None:
            bucket["raw_validation_total_scores"].append(float(raw_score))
        strict_ready = _bool_payload(item, "strict_incubation_ready")
        live_ready = _bool_payload(item, "live_candidate_ready")
        if strict_ready:
            bucket["strict_incubation_ready_count"] += 1
        if live_ready:
            bucket["live_candidate_ready_count"] += 1
        if _is_raw_b_or_above(raw_grade):
            bucket["raw_b_or_above_count"] += 1
            if strict_ready:
                bucket["strict_ready_given_raw_b_count"] += 1
            if live_ready:
                bucket["live_ready_given_raw_b_count"] += 1
        trade_density = _metric_payload(item, "trade_density")
        if trade_density is not None:
            bucket["trade_density_values"].append(float(trade_density))
        post_cost_sharpe = _metric_payload(item, "post_cost_sharpe")
        if post_cost_sharpe is not None:
            bucket["post_cost_sharpe_values"].append(float(post_cost_sharpe))
        dsr = _metric_payload(item, "deflated_sharpe_ratio")
        if dsr is not None:
            bucket["deflated_sharpe_ratio_values"].append(float(dsr))
        pbo = _metric_payload(item, "pbo")
        if pbo is not None:
            bucket["pbo_values"].append(float(pbo))

    panel: list[dict[str, Any]] = []
    for bucket in buckets.values():
        strategy_count = int(bucket.get("strategy_count") or 0)
        raw_distribution = dict(bucket.get("raw_validation_grade_distribution") or {})
        raw_scores = list(bucket.get("raw_validation_total_scores") or [])
        trade_density_values = list(bucket.get("trade_density_values") or [])
        post_cost_sharpe_values = list(bucket.get("post_cost_sharpe_values") or [])
        dsr_values = list(bucket.get("deflated_sharpe_ratio_values") or [])
        pbo_values = list(bucket.get("pbo_values") or [])
        raw_b_or_above_count = int(bucket.get("raw_b_or_above_count") or 0)
        strict_ready_given_raw_b_count = int(
            bucket.get("strict_ready_given_raw_b_count") or 0
        )
        live_ready_given_raw_b_count = int(bucket.get("live_ready_given_raw_b_count") or 0)
        item = {
            "strategy_family": bucket.get("strategy_family"),
            "holding_period_bucket": bucket.get("holding_period_bucket"),
            "validation_focus": bucket.get("validation_focus"),
            "strategy_count": strategy_count,
            "raw_validation_grade_distribution": raw_distribution,
            "effective_validation_grade_distribution": dict(
                bucket.get("effective_validation_grade_distribution") or {}
            ),
            "raw_validation_total_score_mean": round(sum(raw_scores) / len(raw_scores), 4) if raw_scores else 0.0,
            "strict_incubation_ready_count": int(bucket.get("strict_incubation_ready_count") or 0),
            "strict_incubation_ready_rate": round(
                int(bucket.get("strict_incubation_ready_count") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "live_candidate_ready_count": int(bucket.get("live_candidate_ready_count") or 0),
            "live_candidate_ready_rate": round(
                int(bucket.get("live_candidate_ready_count") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "raw_b_or_above_count": raw_b_or_above_count,
            "raw_b_or_above_rate": _rate(raw_b_or_above_count, strategy_count),
            "strict_ready_given_raw_b_count": strict_ready_given_raw_b_count,
            "strict_ready_given_raw_b_rate": _rate(
                strict_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "live_ready_given_raw_b_count": live_ready_given_raw_b_count,
            "live_ready_given_raw_b_rate": _rate(
                live_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "mean_trade_density": round(sum(trade_density_values) / len(trade_density_values), 4)
            if trade_density_values else 0.0,
            "mean_post_cost_sharpe": round(sum(post_cost_sharpe_values) / len(post_cost_sharpe_values), 4)
            if post_cost_sharpe_values else 0.0,
            "mean_deflated_sharpe_ratio": round(sum(dsr_values) / len(dsr_values), 4)
            if dsr_values else 0.0,
            "mean_pbo": round(sum(pbo_values) / len(pbo_values), 4) if pbo_values else 0.0,
        }
        item.update(_grade_rates(raw_distribution, strategy_count))
        item.update(
            {
                "family_raw_a_rate": item.get("raw_validation_a_rate", 0.0),
                "family_raw_b_rate": item.get("raw_validation_b_rate", 0.0),
                "family_raw_c_rate": item.get("raw_validation_c_rate", 0.0),
                "family_raw_d_rate": item.get("raw_validation_d_rate", 0.0),
                "family_strict_incubation_ready_rate": item.get(
                    "strict_incubation_ready_rate",
                    0.0,
                ),
                "family_live_candidate_ready_rate": item.get(
                    "live_candidate_ready_rate",
                    0.0,
                ),
                "family_mean_trade_density": item.get("mean_trade_density", 0.0),
                "family_mean_post_cost_sharpe": item.get("mean_post_cost_sharpe", 0.0),
                "family_mean_dsr": item.get("mean_deflated_sharpe_ratio", 0.0),
                "family_mean_pbo": item.get("mean_pbo", 0.0),
            }
        )
        panel.append(item)
    panel.sort(
        key=lambda item: (
            int(item.get("strategy_count") or 0),
            float(item.get("raw_validation_b_rate") or 0.0),
            float(item.get("raw_validation_a_rate") or 0.0),
            str(item.get("strategy_family") or ""),
        ),
        reverse=True,
    )
    return panel[:24]


def _attempt_adjustment_payload(item: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(item or {}).get("attempt_adjustment") or {})


def _multiple_testing_registry_payload(item: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(item or {}).get("multiple_testing_registry") or {})


def _run_correction_payload(item: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(item or {}).get("run_correction") or {})


def _candidate_local_attempt_count(item: dict[str, Any]) -> int:
    payload = dict(item or {})
    attempt_adjustment = _attempt_adjustment_payload(payload)
    registry = _multiple_testing_registry_payload(payload)
    return _safe_int(
        payload.get("candidate_local_attempt_count")
        or attempt_adjustment.get("attempt_count")
        or registry.get("attempt_count")
    )


def _task_local_attempt_count(item: dict[str, Any]) -> int:
    payload = dict(item or {})
    registry = _multiple_testing_registry_payload(payload)
    return _safe_int(
        payload.get("task_local_attempt_count")
        or registry.get("task_attempt_count")
        or payload.get("task_attempt_count")
    )


def _cohort_effective_trials(item: dict[str, Any]) -> float:
    payload = dict(item or {})
    run_correction = _run_correction_payload(payload)
    registry = _multiple_testing_registry_payload(payload)
    multiple_testing = dict(registry.get("multiple_testing") or {})
    gate = dict(payload.get("gate_3") or {})
    return _safe_float(
        payload.get("cohort_effective_trials")
        or gate.get("cohort_effective_trials")
        or run_correction.get("deflated_sharpe_effective_trials")
        or multiple_testing.get("deflated_sharpe_effective_trials")
    )


def _research_only(item: dict[str, Any]) -> bool:
    payload = dict(item or {})
    return bool(payload.get("research_candidate_ready")) and not bool(
        payload.get("incubation_candidate_ready")
    )


def _economic_semantics_missing(item: dict[str, Any]) -> bool:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    execution_reality = dict(payload.get("execution_reality") or {})
    backtest_assumptions = dict(payload.get("backtest_assumptions") or {})
    cost_assumptions = dict(payload.get("cost_assumptions") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})

    holding_rationale = _string(
        payload.get("holding_rationale")
        or quality_summary.get("holding_rationale")
        or candidate_provenance.get("holding_rationale")
    )
    alpha_half_life = payload.get("alpha_half_life") or quality_summary.get("alpha_half_life")
    cost_sensitivity_grid = (
        payload.get("cost_sensitivity_grid")
        or quality_summary.get("cost_sensitivity_grid")
        or cost_assumptions.get("cost_sensitivity_grid")
    )
    position_model = _string(
        payload.get("position_model")
        or quality_summary.get("position_model")
        or execution_reality.get("position_model")
        or payload.get("position_assumption")
        or quality_summary.get("position_assumption")
        or execution_reality.get("position_assumption")
        or backtest_assumptions.get("position_assumption")
        or backtest_assumptions.get("target_weight_scheme")
    )
    capacity_assumption = (
        payload.get("capacity_assumption")
        or quality_summary.get("capacity_assumption")
        or backtest_assumptions.get("capacity_participation_rate")
        or backtest_assumptions.get("capacity_bucket")
    )
    market_regime_assumption = (
        payload.get("market_regime_assumption")
        or quality_summary.get("market_regime_assumption")
        or execution_reality.get("market_regime_assumption")
    )

    holding_present = bool(holding_rationale or alpha_half_life or _holding_bucket(payload))
    position_present = bool(position_model)
    cost_present = bool(cost_sensitivity_grid) or bool(
        cost_assumptions.get("slippage_bps") is not None
        or cost_assumptions.get("market_impact_bps") is not None
        or payload.get("explicit_cost_breakdown")
        or payload.get("implicit_cost_breakdown")
    )
    capacity_present = bool(capacity_assumption)
    regime_present = bool(market_regime_assumption)
    default_position = _normalized_text(position_model) in {
        "single_name_full_notional",
        "single_name",
        "equal_weight",
        "equal_weight_proxy",
    }
    return (
        not (holding_present and position_present and cost_present and capacity_present and regime_present)
        or (default_position and not bool(cost_sensitivity_grid) and not capacity_present)
    )


def _compact_committee_review(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    if not payload:
        return {}
    result = _compact_mapping(
        payload,
        allowed_keys=(
            "decision",
            "final_score",
            "rank",
            "is_champion",
            "execution_score",
            "capacity_score",
            "task_alignment_score",
            "novelty_score",
        ),
        limit=8,
    )
    for key in ("alignment_issues", "execution_issues", "capacity_issues", "accept_blockers"):
        items = _compact_list(payload.get(key), limit=4)
        if items:
            result[key] = items
    return result


def _strategy_brief(strategy: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})
    evidence_alignment_audit = dict(
        payload.get("evidence_alignment_audit")
        or params.get("evidence_alignment_audit")
        or {}
    )
    confidence_contract = dict(
        payload.get("confidence_contract") or params.get("confidence_contract") or {}
    )
    constraint_check = _compact_mapping(
        payload.get("constraint_check"),
        allowed_keys=(
            "constraint_violation",
            "intersection_ratio",
            "expansion_applied",
            "expansion_reason",
            "expansion_source",
            "alignment_contract_violation",
        ),
        limit=6,
    )
    validation_profile = _compact_mapping(
        payload.get("validation_profile"),
        allowed_keys=("profile", "validation_focus", "primary_validation_layer"),
        limit=3,
    )
    event_window_config = _compact_mapping(payload.get("event_window_config"), limit=6)
    cost_assumptions = _compact_mapping(payload.get("cost_assumptions"), limit=6)
    explicit_cost_breakdown = _compact_mapping(payload.get("explicit_cost_breakdown"), limit=6)
    implicit_cost_breakdown = _compact_mapping(payload.get("implicit_cost_breakdown"), limit=6)
    attempt_adjustment = _compact_mapping(
        payload.get("attempt_adjustment"),
        allowed_keys=("attempt_count", "selected_count", "selection_ratio", "penalty", "applied"),
        limit=5,
    )
    primary_validation_layer = (
        _string(payload.get("primary_validation_layer"))
        or _string(validation_profile.get("primary_validation_layer"))
        or None
    )
    refresh_mode = _string(payload.get("refresh_mode")) or None
    position_assumption = _string(payload.get("position_assumption")) or None
    task_signature = _string(payload.get("task_signature")) or None
    committee_review = _compact_committee_review(payload.get("committee_review"))
    validation_grade = _effective_validation_grade(payload) or None
    raw_validation_grade = _raw_validation_grade(payload) or None
    effective_validation_grade = _effective_validation_grade(payload) or None
    validation_grade_adjustment_reason = _validation_grade_adjustment_reason(payload) or None
    confidence_contract_status = (
        _string(payload.get("confidence_contract_status"))
        or _string(params.get("confidence_contract_status"))
        or _confidence_contract_status(confidence_contract)
    )
    return {
        "strategy_id": _string(payload.get("strategy_id")) or None,
        "name": _string(payload.get("name")) or None,
        "status": _string(payload.get("status")) or None,
        "submission_lane": _string(payload.get("submission_lane")) or None,
        "submission_action_type": _string(payload.get("submission_action_type")) or None,
        "primary_validation_layer": primary_validation_layer,
        "refresh_mode": refresh_mode,
        "position_assumption": position_assumption,
        "task_signature": task_signature,
        "candidate_family": (
            _string(payload.get("candidate_family"))
            or _string(candidate_provenance.get("candidate_family"))
            or None
        ),
        "holding_period_bucket": _holding_bucket(payload) or None,
        "validation_grade": validation_grade,
        "raw_validation_grade": raw_validation_grade,
        "effective_validation_grade": effective_validation_grade,
        "validation_grade_adjustment_reason": validation_grade_adjustment_reason,
        "raw_validation_total_score": _validation_total_score(payload, raw=True),
        "validation_total_score": _validation_total_score(payload, raw=False),
        "raw_b_or_above": _is_raw_b_or_above(raw_validation_grade),
        "prediction_quality_label": (
            _string(payload.get("prediction_quality_label"))
            or _string(params.get("prediction_quality_label"))
            or None
        ),
        "execution_quality_label": (
            _string(payload.get("execution_quality_label"))
            or _string(params.get("execution_quality_label"))
            or None
        ),
        "confidence_contract_status": confidence_contract_status,
        "evidence_alignment_status": (
            _string(evidence_alignment_audit.get("evidence_alignment_status")) or None
        ),
        "legacy_semantic_contract": bool(
            payload.get("legacy_semantic_contract")
            if payload.get("legacy_semantic_contract") is not None
            else params.get("legacy_semantic_contract")
        )
        if (
            payload.get("legacy_semantic_contract") is not None
            or params.get("legacy_semantic_contract") is not None
        )
        else None,
        "generator_mode": (
            _string(payload.get("generator_mode"))
            or _string(candidate_provenance.get("generator_mode"))
            or None
        ),
        "source_candidate_artifact_id": _string(payload.get("source_candidate_artifact_id")) or None,
        "target_pool_id": _string(payload.get("target_pool_id")) or None,
        "vector_profile_id": _string(payload.get("vector_profile_id")) or None,
        "multiple_testing_registry_record_id": (
            _string(payload.get("multiple_testing_registry_record_id")) or None
        ),
        "constraint_check": constraint_check,
        "validation_profile": validation_profile,
        "event_window_config": event_window_config,
        "cost_assumptions": cost_assumptions,
        "explicit_cost_breakdown": explicit_cost_breakdown,
        "implicit_cost_breakdown": implicit_cost_breakdown,
        "attempt_adjustment": attempt_adjustment,
        "committee_review": committee_review,
        "candidate_local_attempt_count": _candidate_local_attempt_count(payload),
        "task_local_attempt_count": _task_local_attempt_count(payload),
        "cohort_effective_trials": round(_cohort_effective_trials(payload), 4),
        "economic_semantics_missing": _economic_semantics_missing(payload),
        "has_constraint_check": bool(constraint_check),
        "has_validation_profile": bool(validation_profile),
        "has_event_window_config": bool(event_window_config),
        "has_cost_assumptions": bool(cost_assumptions),
        "has_explicit_cost_breakdown": bool(explicit_cost_breakdown),
        "has_implicit_cost_breakdown": bool(implicit_cost_breakdown),
        "has_attempt_adjustment": bool(attempt_adjustment),
        "has_committee_review": bool(committee_review),
        "created_strategy_pool": bool(payload.get("created_strategy_pool")),
        "created_audit_only": bool(payload.get("created_audit_only")),
        "refreshed_existing": bool(payload.get("refreshed_existing")),
        "live_candidate_ready": bool(payload.get("live_candidate_ready")),
        "live_review_ready": bool(payload.get("live_review_ready")),
        "runtime_bootstrap_eligible": (
            bool(payload.get("runtime_bootstrap_eligible"))
            if payload.get("runtime_bootstrap_eligible") is not None
            else None
        ),
        "runtime_bootstrap_reason": _string(payload.get("runtime_bootstrap_reason")) or None,
        "runtime_bootstrap_budget_tier": _string(payload.get("runtime_bootstrap_budget_tier")) or None,
        "runtime_playbook_present": (
            bool(payload.get("runtime_playbook_present"))
            if payload.get("runtime_playbook_present") is not None
            else None
        ),
        "stage_clock_days": _safe_int(payload.get("stage_clock_days")) if payload.get("stage_clock_days") is not None else None,
        "signal_vacuum_days": _safe_int(payload.get("signal_vacuum_days")) if payload.get("signal_vacuum_days") is not None else None,
        "remediation_action": _string(payload.get("remediation_action")) or None,
        "remediation_reason": _string(payload.get("remediation_reason")) or None,
        "paper_lane_ready": (
            bool(payload.get("paper_lane_ready"))
            if payload.get("paper_lane_ready") is not None
            else None
        ),
        "direct_trade_candidate": bool(payload.get("direct_trade_candidate")),
    }


def _dedup_brief(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate or {})
    dedup = dict(payload.get("dedup_result") or {})
    profile = dict(payload.get("strategy_profile") or {})
    return {
        "strategy_type": _string(payload.get("strategy_type")) or None,
        "generator_type": _string(payload.get("generator_type")) or None,
        "candidate_family_id": (
            _string(payload.get("candidate_family_id"))
            or _string(profile.get("candidate_family_id"))
            or None
        ),
        "target_symbols": _compact_list(payload.get("target_symbols"), limit=12),
        "duplicate": bool(dedup.get("duplicate")),
        "duplicate_level": _string(dedup.get("duplicate_level")) or None,
        "refresh_existing": bool(dedup.get("refresh_existing")),
        "refresh_mode": _string(dedup.get("refresh_mode")) or None,
        "matched_strategy_id": _string(dedup.get("matched_strategy_id")) or None,
        "refresh_decision_basis": _string(dedup.get("refresh_decision_basis")) or None,
        "revision_trigger_reason": _string(dedup.get("revision_trigger_reason")) or None,
        "target_overlap": round(_safe_float(dedup.get("target_overlap")), 4),
    }


def build_gate_artifact(
    *,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = dict(quality_gate_report or {})
    backtest = dict(backtest_report or {})
    backtest_summary = dict(backtest.get("summary") or {})
    gate_0 = dict(quality.get("gate_0") or {})
    pre_gate = dict(quality.get("pre_gate") or {})
    gate_1 = dict(quality.get("gate_1") or {})
    gate_2 = dict(quality.get("gate_2") or {})
    gate_3 = dict(quality.get("gate_3") or {})
    legacy_gate_executed = quality.get("legacy_gate_executed")
    if legacy_gate_executed is None:
        legacy_gate_executed = bool(gate_0 or pre_gate or gate_1 or gate_2)
    legacy_funnel_executed = quality.get("legacy_funnel_executed")
    if legacy_funnel_executed is None:
        legacy_funnel_executed = bool(legacy_gate_executed)
    evidence_scoring_mode = _string(quality.get("evidence_scoring_mode")) or None
    return {
        "contract_version": GATE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(quality or backtest),
        "artifact_mode": evidence_scoring_mode or "legacy_gate_report",
        "legacy_gate_executed": bool(legacy_gate_executed),
        "legacy_funnel_executed": bool(legacy_funnel_executed),
        "legacy_gate_report_mode": _string(quality.get("legacy_gate_report_mode")) or None,
        "evidence_scoring_mode": evidence_scoring_mode,
        "pre_observe_gate_removed": bool(quality.get("pre_observe_gate_removed")),
        "gate_0_passed": _safe_int(gate_0.get("passed_count")),
        "gate_0_failed": _safe_int(gate_0.get("failed_count")),
        "pre_gate_passed": _safe_int(pre_gate.get("passed_count")),
        "pre_gate_failed": _safe_int(pre_gate.get("failed_count")),
        "gate_1_passed": _safe_int(gate_1.get("passed_count")),
        "gate_1_failed": _safe_int(gate_1.get("failed_count")),
        "gate_2_input": _safe_int(gate_2.get("input_count"), _safe_int(backtest_summary.get("input_count"))),
        "gate_2_passed": _safe_int(gate_2.get("passed_count"), _safe_int(backtest_summary.get("passed_count"))),
        "gate_2_failed": _safe_int(gate_2.get("failed_count"), _safe_int(backtest_summary.get("failed_count"))),
        "gate_3_input": _safe_int(gate_3.get("input_count")),
        "gate_3_pending_count": _safe_int(gate_3.get("pending_count")),
        "gate_3_passed": _safe_int(gate_3.get("passed_count")),
        "gate_3_failed": _safe_int(gate_3.get("failed_count")),
        "gate_3_provisional_passed": _safe_int(gate_3.get("provisional_passed_count")),
        "backtest_failed_reason_counts": dict(backtest_summary.get("failed_reason_counts") or {}),
        "backtest_thresholds_by_type": dict(backtest_summary.get("thresholds_by_type") or {}),
        "gate_3_failure_reason_topn": _compact_reason_topn(gate_3.get("failure_reason_topn")),
    }

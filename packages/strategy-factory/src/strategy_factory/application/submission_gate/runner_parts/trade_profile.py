

def _derive_trade_aware_validation_grade(
    strategy: dict,
    gate: Optional[dict[str, Any]],
    *,
    raw_validation_grade: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    grade = str(raw_validation_grade or "").strip().upper() or None
    if grade != "D":
        return grade, None
    payload = dict(strategy or {})
    strategy_profile = dict(_strategy_payload_value(payload, "strategy_profile") or payload.get("strategy_profile") or {})
    candidate_provenance = dict(
        _strategy_payload_value(payload, "candidate_provenance") or payload.get("candidate_provenance") or {}
    )
    task_preference = dict(gate or {}).get("task_preference") if isinstance(gate, dict) else {}
    preferred_strategy_types = list(dict(task_preference or {}).get("preferred_strategy_types") or [])
    strategy_type = str(
        payload.get("strategy_type")
        or _strategy_payload_value(payload, "candidate_family")
        or candidate_provenance.get("candidate_family")
        or strategy_profile.get("strategy_family")
        or (preferred_strategy_types[0] if preferred_strategy_types else "")
        or ""
    ).strip().lower()
    if strategy_type not in _TRADE_AWARE_VALIDATION_GRADE_FAMILIES:
        return grade, None
    normalized_gate = dict(gate or {})
    profile_name = str(normalized_gate.get("profile") or "").strip().lower()
    validation_focus = str(
        normalized_gate.get("validation_focus")
        or dict(payload.get("params") or {}).get("validation_focus")
        or dict(dict(payload.get("params") or {}).get("validation_profile") or {}).get("validation_focus")
        or dict(payload.get("research_task") or {}).get("validation_focus")
        or ""
    ).strip().lower()
    if profile_name not in _TRADE_PRIMARY_PROFILES:
        return grade, None
    if validation_focus not in _TARGET_ONLY_VALIDATION_FOCUSES:
        return grade, None

    trade_density = safe_metric_value(normalized_gate, "trade_density")
    post_cost_sharpe = safe_metric_value(normalized_gate, "post_cost_sharpe")
    target_layer_oos_return = safe_metric_value(normalized_gate, "target_layer_oos_return")
    trade_stability = safe_metric_value(normalized_gate, "parameter_perturbation_trade_stability")
    dsr = safe_metric_value(normalized_gate, "deflated_sharpe_ratio")
    pbo = safe_metric_value(normalized_gate, "pbo")
    rc_pvalue = safe_metric_value(normalized_gate, "white_reality_check_pvalue")
    spa_pvalue = safe_metric_value(normalized_gate, "hansen_spa_pvalue")

    if trade_density <= 0 or trade_density > 1.2:
        return grade, None

    evidence_score = 0.0
    if trade_density <= 1.0:
        evidence_score += 2.0
    elif trade_density <= 1.2:
        evidence_score += 1.0
    if post_cost_sharpe >= 1.0:
        evidence_score += 2.0
    elif post_cost_sharpe >= 0.8:
        evidence_score += 1.0
    if target_layer_oos_return >= 0.18:
        evidence_score += 1.5
    elif target_layer_oos_return >= 0.08:
        evidence_score += 1.0
    if trade_stability >= 0.5:
        evidence_score += 1.0
    elif trade_stability >= 0.25:
        evidence_score += 0.5
    if dsr >= 0.1:
        evidence_score += 1.0
    elif dsr >= 0.03:
        evidence_score += 0.5
    if pbo <= 0.7:
        evidence_score += 1.0
    elif pbo <= 0.85:
        evidence_score += 0.5
    if rc_pvalue <= 0.2 and spa_pvalue <= 0.2:
        evidence_score += 0.5

    if evidence_score < 5.0:
        return grade, None
    return "C", f"trade_aware_validation_grade_upgrade:{strategy_type}:score={evidence_score:.2f}"


def _resolve_admission_review_context(
    strategy: dict,
    *,
    validation_report: Optional[dict] = None,
    gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    quality_summary = dict(_strategy_payload_value(payload, "quality_summary") or payload.get("quality_summary") or {})
    review_report = dict(_strategy_payload_value(payload, "quality_report") or payload.get("quality_report") or payload.get("review_report") or {})
    committee_review = _committee_review_snapshot(payload)
    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    trade_quality_adjustment = dict(validation.get("trade_quality_adjustment") or {})
    validation_profile = dict(validation.get("validation_profile") or {})
    reported_validation_grade = str(
        rating.get("grade")
        or _strategy_payload_value(payload, "validation_grade")
        or quality_summary.get("validation_grade")
        or dict(review_report.get("summary") or {}).get("validation_grade")
        or ""
    ).strip().upper() or None
    baseline_validation_grade = str(
        rating.get("base_grade")
        or reported_validation_grade
        or ""
    ).strip().upper() or None
    raw_validation_grade = reported_validation_grade
    validation_grade, validation_grade_adjustment_reason = _derive_trade_aware_validation_grade(
        payload,
        gate,
        raw_validation_grade=raw_validation_grade,
    )
    if not validation_grade_adjustment_reason and bool(trade_quality_adjustment.get("applied")):
        validation_grade_adjustment_reason = str(
            trade_quality_adjustment.get("adjustment_reason") or ""
        ).strip() or None
    committee_decision = _normalize_text(
        committee_review.get("decision")
        or _strategy_payload_value(payload, "promotion_review_recommendation")
        or payload.get("promotion_review_recommendation")
    ) or None
    committee_final_score = committee_review.get("final_score")
    try:
        committee_final_score = None if committee_final_score is None else round(float(committee_final_score), 4)
    except Exception:
        committee_final_score = None
    promotion_review_score = (
        _strategy_payload_value(payload, "promotion_review_score")
        or quality_summary.get("promotion_review_score")
        or payload.get("promotion_review_score")
    )
    try:
        promotion_review_score = None if promotion_review_score is None else round(float(promotion_review_score), 4)
    except Exception:
        promotion_review_score = None
    accept_blockers = [
        str(item or "").strip()
        for item in list(committee_review.get("accept_blockers") or [])
        if str(item or "").strip()
    ]
    validation_focus = str(
        dict(gate or {}).get("validation_focus")
        or dict(params.get("validation_profile") or {}).get("validation_focus")
        or dict(params.get("research_task") or {}).get("validation_focus")
        or validation_profile.get("validation_focus")
        or ""
    ).strip().lower() or None
    return {
        "validation_grade": validation_grade,
        "raw_validation_grade": raw_validation_grade,
        "validation_baseline_grade": baseline_validation_grade,
        "effective_validation_grade": validation_grade,
        "validation_grade_adjustment_reason": validation_grade_adjustment_reason,
        "validation_focus": validation_focus,
        "validation_focus_layer": _resolve_validation_focus_layer(validation_focus or ""),
        "committee_decision": committee_decision,
        "committee_final_score": committee_final_score,
        "promotion_review_score": promotion_review_score,
        "accept_blockers": accept_blockers,
    }


def _review_stage_blockers(
    strategy: dict,
    *,
    admission_level: str,
    validation_report: Optional[dict] = None,
    gate: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    semantic_runtime_context = _resolve_semantic_runtime_context(strategy, gate=gate)
    if admission_level == "research":
        context = _resolve_admission_review_context(strategy, validation_report=validation_report, gate=gate)
        context.update(semantic_runtime_context)
        return [], context
    context = _resolve_admission_review_context(strategy, validation_report=validation_report, gate=gate)
    context.update(semantic_runtime_context)
    thresholds = _review_gate_thresholds(admission_level)
    blockers: list[str] = []
    validation_grade = str(context.get("validation_grade") or "").strip().upper()
    committee_decision = _normalize_text(context.get("committee_decision"))
    committee_final_score = context.get("committee_final_score")
    promotion_review_score = context.get("promotion_review_score")
    accept_blockers = list(context.get("accept_blockers") or [])

    if validation_grade in _NON_PROMOTABLE_VALIDATION_GRADES:
        blockers.append(f"validation_grade_{validation_grade.lower()}_not_allowed_for_{admission_level}")
    if committee_decision in _NON_PROMOTABLE_REVIEW_DECISIONS or committee_decision in _NON_PROMOTABLE_REVIEW_RECOMMENDATIONS:
        blockers.append(f"committee_review_{committee_decision}_not_allowed_for_{admission_level}")
    if committee_final_score is not None and committee_final_score < thresholds["committee_final_score_min"]:
        blockers.append(
            f"committee_final_score {committee_final_score:.3f} < {thresholds['committee_final_score_min']:.3f}"
        )
    if promotion_review_score is not None and promotion_review_score < thresholds["promotion_review_score_min"]:
        blockers.append(
            f"promotion_review_score {promotion_review_score:.3f} < {thresholds['promotion_review_score_min']:.3f}"
        )
    if accept_blockers:
        blockers.extend(f"committee_accept_blocker:{item}" for item in accept_blockers)
    semantic_contract_missing_fields = list(context.get("semantic_contract_missing_fields") or [])
    if semantic_contract_missing_fields:
        blockers.append("final_strategy_missing_semantic_contract")
    if not bool(context.get("semantic_runtime_match", True)):
        blockers.append("runtime_family_semantic_mismatch")
    if bool(context.get("proxy_runtime_used")):
        blockers.append("proxy_runtime_not_allowed_for_formal_incubation")
    if bool(context.get("default_profile_not_allowed")):
        blockers.append("default_profile_not_allowed_for_single_name_runtime")
    if bool(context.get("diagnostic_only")):
        blockers.append(f"diagnostic_only_not_allowed_for_{admission_level}")
    if str(context.get("execution_readiness_tier") or "").strip().lower() not in {"", "formal_runtime_ready"}:
        blockers.append(f"execution_readiness_tier:{context.get('execution_readiness_tier')}")
    return blockers, context


def _attach_admission_evaluations(
    strategy: dict,
    profile: dict[str, Any],
    gate: dict[str, Any],
    *,
    risk_report: Optional[dict] = None,
    validation_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict[str, Any]:
    normalized_gate = normalize_quality_gate_result(gate)
    materialized_backtest_metrics = _materialize_backtest_metrics_contract(backtest_metrics)
    admission_metric_gate = normalize_quality_gate_result(
        _merge_authoritative_backtest_metrics(normalized_gate, materialized_backtest_metrics)
    )
    attempt_adjustment = resolve_attempt_adjustment(strategy, gate=normalized_gate)
    evaluations: dict[str, dict[str, Any]] = {}
    profile_name = str(profile.get("profile") or "").strip().lower()
    research_only_due_to_trade_audit_gap = bool(normalized_gate.get("research_only_due_to_trade_audit_gap"))
    research_protocol_adapter = _resolve_research_protocol_submission_adapter(strategy)
    research_protocol_evaluation = evaluate_research_validation_contract_admission(
        research_protocol_adapter,
        observed=_resolve_research_protocol_observed_payload(
            strategy,
            backtest_metrics=materialized_backtest_metrics,
        ),
        spec_completeness_mode=STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE,
    )
    research_protocol_available = bool(research_protocol_evaluation.get("available"))
    research_protocol_review_decision = str(
        research_protocol_evaluation.get("review_decision") or "pending"
    ).strip().lower()
    research_protocol_blockers = list(research_protocol_evaluation.get("blocking_reasons") or [])
    research_protocol_warnings = list(research_protocol_evaluation.get("warnings") or [])
    high_precision_evaluation = _evaluate_high_precision_admission(
        strategy,
        profile,
        normalized_gate,
        backtest_metrics=materialized_backtest_metrics,
    )
    high_precision_available = bool(high_precision_evaluation.get("available"))
    high_precision_review_decision = _normalize_text(
        high_precision_evaluation.get("decision") or "pass"
    ) or "pass"
    high_precision_blockers = list(high_precision_evaluation.get("blocking_reasons") or [])
    high_precision_warnings = list(high_precision_evaluation.get("warnings") or [])
    merged_gate_b_review_decision = _merge_review_decision(
        research_protocol_review_decision if research_protocol_available else "pass",
        high_precision_review_decision if high_precision_available else "pass",
    )

    if research_protocol_available:
        merged_gate_payload = {
            **normalized_gate,
            "warnings": _merge_text_items(normalized_gate.get("warnings"), research_protocol_warnings),
            "business_admission_decision": dict(
                research_protocol_evaluation.get("business_admission_decision") or {}
            ),
            "benchmark_comparison": dict(research_protocol_evaluation.get("benchmark_comparison") or {}),
            "cost_sensitivity_summary": dict(
                research_protocol_evaluation.get("cost_sensitivity_summary") or {}
            ),
            "cash_sleeve_audit": dict(research_protocol_evaluation.get("cash_sleeve_audit") or {}),
            "family_holding_bucket": dict(research_protocol_evaluation.get("family_holding_bucket") or {}),
            "gate_b_review_decision": merged_gate_b_review_decision,
            "artifact_ids": list(research_protocol_evaluation.get("artifact_ids") or []),
            "retrieval_context_ids": list(research_protocol_evaluation.get("retrieval_context_ids") or []),
            "prediction_trace_id": research_protocol_evaluation.get("prediction_trace_id"),
        }
        if research_protocol_review_decision in {"revise", "reject"}:
            merged_gate_payload.update(
                {
                    "passed": False,
                    "passed_strict": False,
                    "provisional_pass": False,
                    "reasons": _merge_text_items(normalized_gate.get("reasons"), research_protocol_blockers),
                }
            )
        normalized_gate = normalize_quality_gate_result(merged_gate_payload)
    if high_precision_available:
        merged_gate_payload = {
            **normalized_gate,
            "warnings": _merge_text_items(normalized_gate.get("warnings"), high_precision_warnings),
            "objective_profile": high_precision_evaluation.get("objective_profile"),
            "precision_readiness": high_precision_evaluation.get("precision_readiness"),
            "regime_validation_summary": dict(
                high_precision_evaluation.get("regime_validation_summary") or {}
            ),
            "cost_robustness_summary": dict(
                high_precision_evaluation.get("cost_robustness_summary") or {}
            ),
            "trade_density_summary": dict(
                high_precision_evaluation.get("trade_density_summary") or {}
            ),
            "event_prefilter_summary": dict(
                high_precision_evaluation.get("event_prefilter_summary") or {}
            ),
            "event_anchor_summary": dict(
                high_precision_evaluation.get("event_anchor_summary") or {}
            ),
            "backtest_metrics_contract_status": normalized_gate.get("backtest_metrics_contract_status"),
            "gate_b_review_decision": merged_gate_b_review_decision,
        }
        if high_precision_review_decision in {"revise", "reject"}:
            merged_gate_payload.update(
                {
                    "passed": False,
                    "passed_strict": False,
                    "provisional_pass": False,
                    "reasons": _merge_text_items(normalized_gate.get("reasons"), high_precision_blockers),
                }
            )
        normalized_gate = normalize_quality_gate_result(merged_gate_payload)

    for admission_level in _ADMISSION_LEVEL_ORDER:
        if profile_name in _TRADE_PRIMARY_PROFILES:
            stage_result = _evaluate_trade_profile_for_admission(
                strategy,
                profile,
                admission_metric_gate,
                risk_report,
                admission_level=admission_level,
                attempt_adjustment=attempt_adjustment,
            )
        else:
            stage_result = _evaluate_statistical_admission(
                strategy,
                profile,
                normalized_gate,
                admission_level=admission_level,
                attempt_adjustment=attempt_adjustment,
            )
        review_blockers, review_context = _review_stage_blockers(
            strategy,
            admission_level=admission_level,
            validation_report=validation_report,
            gate=normalized_gate,
        )
        stage_reasons = _merge_text_items(stage_result.get("reasons"), review_blockers)
        stage_warnings = list(stage_result.get("warnings") or [])
        if research_protocol_available:
            if research_protocol_review_decision in {"revise", "reject"}:
                stage_reasons = _merge_text_items(stage_reasons, research_protocol_blockers)
            stage_warnings = _merge_text_items(stage_warnings, research_protocol_warnings)
        if high_precision_available:
            if high_precision_review_decision in {"revise", "reject"}:
                stage_reasons = _merge_text_items(stage_reasons, high_precision_blockers)
            stage_warnings = _merge_text_items(stage_warnings, high_precision_warnings)
        evaluations[admission_level] = {
            "passed": len(stage_reasons) == 0 and bool(stage_result.get("passed")),
            "reasons": stage_reasons,
            "warnings": stage_warnings,
            "thresholds": dict(stage_result.get("thresholds") or {}),
            "review_context": {
                **dict(review_context or {}),
                "business_admission_decision": dict(
                    research_protocol_evaluation.get("business_admission_decision") or {}
                ),
                "benchmark_comparison": dict(
                    research_protocol_evaluation.get("benchmark_comparison") or {}
                ),
                "cost_sensitivity_summary": dict(
                    research_protocol_evaluation.get("cost_sensitivity_summary") or {}
                ),
                "cash_sleeve_audit": dict(research_protocol_evaluation.get("cash_sleeve_audit") or {}),
                "family_holding_bucket": dict(
                    research_protocol_evaluation.get("family_holding_bucket") or {}
                ),
                "objective_profile": high_precision_evaluation.get("objective_profile"),
                "precision_readiness": high_precision_evaluation.get("precision_readiness"),
                "regime_validation_summary": dict(
                    high_precision_evaluation.get("regime_validation_summary") or {}
                ),
                "cost_robustness_summary": dict(
                    high_precision_evaluation.get("cost_robustness_summary") or {}
                ),
                "trade_density_summary": dict(
                    high_precision_evaluation.get("trade_density_summary") or {}
                ),
                "event_prefilter_summary": dict(
                    high_precision_evaluation.get("event_prefilter_summary") or {}
                ),
                "event_anchor_summary": dict(
                    high_precision_evaluation.get("event_anchor_summary") or {}
                ),
                "backtest_metrics_contract_status": normalized_gate.get("backtest_metrics_contract_status"),
                "metric_source_audit": dict(admission_metric_gate.get("metric_source_audit") or {}),
            },
        }

    if research_only_due_to_trade_audit_gap:
        research_passed = bool(normalized_gate.get("passed"))
        base_reasons = list(normalized_gate.get("reasons") or [])
        base_warnings = list(normalized_gate.get("warnings") or [])
        evaluations["research"] = {
            "passed": research_passed,
            "reasons": [] if research_passed else list(base_reasons),
            "warnings": list(base_warnings),
            "thresholds": dict((evaluations.get("research") or {}).get("thresholds") or {}),
        }
        evaluations["incubation"] = {
            "passed": False,
            "reasons": _merge_text_items(base_reasons, ["trade_validation_audit_missing_for_incubation_admission"]),
            "warnings": list(base_warnings),
            "thresholds": dict((evaluations.get("incubation") or {}).get("thresholds") or {}),
        }
        evaluations["live"] = {
            "passed": False,
            "reasons": _merge_text_items(base_reasons, ["trade_validation_audit_missing_for_live_admission"]),
            "warnings": list(base_warnings),
            "thresholds": dict((evaluations.get("live") or {}).get("thresholds") or {}),
        }
        strict_incubation_ready = False
        incubation_candidate_ready = False
        live_candidate_ready = False
        research_candidate_ready = research_passed
        if research_candidate_ready:
            admission_stage = "research"
            block_reasons = list((evaluations.get("incubation") or {}).get("reasons") or [])
        else:
            admission_stage = "rejected"
            block_reasons = list(base_reasons or (evaluations.get("incubation") or {}).get("reasons") or [])
    else:
        strict_incubation_ready = bool((evaluations.get("incubation") or {}).get("passed"))
        strict_incubation_blocked = bool((evaluations.get("incubation") or {}).get("reasons") or []) and bool(normalized_gate.get("passed"))
        incubation_candidate_ready = bool(normalized_gate.get("passed")) and not strict_incubation_blocked
        live_candidate_ready = bool(
            incubation_candidate_ready
            and not normalized_gate.get("provisional_pass")
            and (evaluations.get("live") or {}).get("passed")
        )
        research_candidate_ready = bool((evaluations.get("research") or {}).get("passed"))

        if live_candidate_ready:
            admission_stage = "live"
            block_reasons = []
        elif incubation_candidate_ready:
            admission_stage = "incubation"
            block_reasons = list((evaluations.get("live") or {}).get("reasons") or [])
        elif research_candidate_ready:
            admission_stage = "research"
            block_reasons = list((evaluations.get("incubation") or {}).get("reasons") or [])
        else:
            admission_stage = "rejected"
            block_reasons = list(normalized_gate.get("reasons") or (evaluations.get("incubation") or {}).get("reasons") or [])

    incubation_pass_mode = (
        "provisional"
        if normalized_gate.get("provisional_pass")
        else ("strict" if strict_incubation_ready and incubation_candidate_ready else "failed")
    )
    return normalize_quality_gate_result(
        {
            **normalized_gate,
            "admission_stage": admission_stage,
            "incubation_pass_mode": incubation_pass_mode,
            "research_candidate_ready": research_candidate_ready,
            "incubation_candidate_ready": incubation_candidate_ready,
            "live_candidate_ready": live_candidate_ready,
            "admission_evaluations": evaluations,
            "admission_block_reasons": block_reasons,
            "research_only_due_to_trade_audit_gap": research_only_due_to_trade_audit_gap,
            "strict_incubation_ready": strict_incubation_ready,
            "strict_incubation_blocked": bool((evaluations.get("incubation") or {}).get("reasons") or [])
            and bool(normalized_gate.get("passed")),
            "admission_review_context": dict((evaluations.get("incubation") or {}).get("review_context") or {}),
            "validation_grade": dict((evaluations.get("incubation") or {}).get("review_context") or {}).get("validation_grade"),
            "raw_validation_grade": dict((evaluations.get("incubation") or {}).get("review_context") or {}).get("raw_validation_grade"),
            "effective_validation_grade": dict((evaluations.get("incubation") or {}).get("review_context") or {}).get("effective_validation_grade"),
            "validation_grade_adjustment_reason": dict((evaluations.get("incubation") or {}).get("review_context") or {}).get("validation_grade_adjustment_reason"),
            "gate_b_review_decision": merged_gate_b_review_decision if (
                research_protocol_available or high_precision_available
            ) else ("pass" if normalized_gate.get("passed") else "reject"),
            "business_admission_decision": dict(
                research_protocol_evaluation.get("business_admission_decision") or {}
            ),
            "benchmark_comparison": dict(research_protocol_evaluation.get("benchmark_comparison") or {}),
            "cost_sensitivity_summary": dict(
                research_protocol_evaluation.get("cost_sensitivity_summary") or {}
            ),
            "cash_sleeve_audit": dict(research_protocol_evaluation.get("cash_sleeve_audit") or {}),
            "family_holding_bucket": dict(research_protocol_evaluation.get("family_holding_bucket") or {}),
            "objective_profile": high_precision_evaluation.get("objective_profile"),
            "precision_readiness": high_precision_evaluation.get("precision_readiness"),
            "regime_validation_summary": dict(
                high_precision_evaluation.get("regime_validation_summary") or {}
            ),
            "cost_robustness_summary": dict(
                high_precision_evaluation.get("cost_robustness_summary") or {}
            ),
            "trade_density_summary": dict(
                high_precision_evaluation.get("trade_density_summary") or {}
            ),
            "event_prefilter_summary": dict(
                high_precision_evaluation.get("event_prefilter_summary") or {}
            ),
            "event_anchor_summary": dict(
                high_precision_evaluation.get("event_anchor_summary") or {}
            ),
            "backtest_metrics_contract_status": normalized_gate.get("backtest_metrics_contract_status"),
            "metric_source_audit": dict(admission_metric_gate.get("metric_source_audit") or {}),
        }
    )


def _resolve_multiple_testing_panel(
    strategy: dict,
    profile: dict[str, Any],
    contract_snapshot: Optional[dict[str, Any]] = None,
) -> tuple[list[str], str]:
    payload = dict(strategy or {})
    contract = dict(contract_snapshot or {})
    research_task = dict(profile.get("research_task") or {})
    target_codes = _extract_target_codes_from_payload(payload)
    targeting = dict(contract.get("targeting") or {})
    stock_pool = dict(targeting.get("stock_pool") or {})
    candidate_provenance = dict(_strategy_payload_value(payload, "candidate_provenance") or payload.get("candidate_provenance") or {})
    strategy_profile = dict(contract.get("strategy_profile") or {})
    if not strategy_profile:
        strategy_profile = infer_candidate_strategy_profile(payload, research_task=research_task)
    validation_focus = _normalize_text(profile.get("validation_focus"))
    if validation_focus in _TARGET_ONLY_VALIDATION_FOCUSES or len(target_codes) <= 1:
        return list(dict.fromkeys(target_codes)), "target_only"

    pool_symbols = _normalize_symbol_list(
        research_task.get("target_pool_symbols"),
        research_task.get("peer_symbols"),
        research_task.get("same_theme_symbols"),
        research_task.get("theme_members"),
        stock_pool.get("symbols"),
        stock_pool.get("codes"),
        candidate_provenance.get("peer_symbols"),
        limit=8,
    )
    if pool_symbols:
        return list(dict.fromkeys([*target_codes, *pool_symbols]))[:8], "task_pool"

    if _normalize_text(strategy_profile.get("generator_mode")) in {"bulk_stock_matrix", "snapshot"} and len(target_codes) <= 2:
        return list(dict.fromkeys(target_codes)), "target_only"

    return list(dict.fromkeys([*target_codes, "600519", "000858", "601318"]))[:6], "representative_fallback"


# PR-C1: 补充缺失的 _run_statistical_gate 函数（修复 NameError）
async def _run_statistical_gate(
    db,
    strategy: dict,
    *,
    profile: dict = None,
    klass=None,
) -> dict:
    """执行统计门禁评估（factor_rank_validation 路径）。

    调用 _evaluate_statistical_admission 并包装为标准 gate result。
    PR-R0: 修复 TypeError — 不再传 db=db/klass=klass（签名不接受），
    改为传入空 gate_payload（supplemental metrics 当前不可用时走默认 0 值）。
    """
    import inspect as _inspect
    profile = profile or {}
    # gate_payload 为空 dict 时，_evaluate_statistical_admission 内部
    # 会把 wf_ic_ir / pkf_ic / bootstrap_ci_lower / param_sensitivity 全取 0，
    # 这比抛 TypeError 后 100% False 要好——至少 period_robustness 等有值时能真正评估。
    gate_payload: dict = {}
    try:
        result = _evaluate_statistical_admission(
            strategy,
            profile,
            gate_payload,
        )
        if _inspect.isawaitable(result):
            result = await result
        return normalize_quality_gate_result(result or {"passed": False, "reason": "empty_result"})
    except Exception as exc:
        return normalize_quality_gate_result(
            {
                "passed": False,
                "reason": f"statistical_gate_error: {type(exc).__name__}: {exc}",
                "warnings": [f"statistical_gate_exception:{type(exc).__name__}"],
            }
        )

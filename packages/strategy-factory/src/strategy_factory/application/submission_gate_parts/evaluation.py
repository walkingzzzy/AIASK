

def _build_attempt_adjustment(strategy: dict) -> dict[str, Any]:
    candidate_local_attempt_count = int(_strategy_payload_value(strategy, "candidate_local_attempt_count", 0) or 0)
    candidate_local_selected_count = int(_strategy_payload_value(strategy, "candidate_local_selected_count", 0) or 0)
    task_local_attempt_count = int(_strategy_payload_value(strategy, "task_local_attempt_count", 0) or 0)
    task_local_selected_count = int(_strategy_payload_value(strategy, "task_local_selected_count", 0) or 0)
    factory_global_attempt_count = int(_strategy_payload_value(strategy, "factory_global_attempt_count", 0) or 0)
    factory_global_selected_count = int(_strategy_payload_value(strategy, "factory_global_selected_count", 0) or 0)
    factory_attempt_count = int(_strategy_payload_value(strategy, "factory_attempt_count", 0) or 0)
    factory_selected_count = int(_strategy_payload_value(strategy, "factory_selected_count", 0) or 0)
    task_attempt_count = int(_strategy_payload_value(strategy, "task_attempt_count", 0) or 0)
    task_selected_count = int(_strategy_payload_value(strategy, "task_selected_count", 0) or 0)
    external_attempt_count = int(_strategy_payload_value(strategy, "external_llm_attempt_count", 0) or 0)
    external_selected_count = int(_strategy_payload_value(strategy, "external_llm_selected_count", 0) or 0)
    attempt_count = max(
        candidate_local_attempt_count,
        task_local_attempt_count,
        task_attempt_count,
        external_attempt_count,
        1,
    )
    selected_count = max(
        candidate_local_selected_count,
        task_local_selected_count,
        task_selected_count,
        external_selected_count,
        0,
    )
    selection_ratio = selected_count / max(attempt_count, 1)
    penalty = 0.0
    if attempt_count >= 10:
        penalty += 0.03
    if attempt_count >= 25:
        penalty += 0.05
    if attempt_count >= 50:
        penalty += 0.05
    if selected_count > 0 and selection_ratio < 0.2:
        penalty += 0.03
    adjustment = {
        "attempt_count": attempt_count,
        "selected_count": selected_count,
        "selection_ratio": round(selection_ratio, 4),
        "penalty": round(penalty, 4),
        "applied": penalty > 0,
        "candidate_local_attempt_count": candidate_local_attempt_count,
        "candidate_local_selected_count": candidate_local_selected_count,
        "task_local_attempt_count": task_local_attempt_count,
        "task_local_selected_count": task_local_selected_count,
        "factory_global_attempt_count": max(factory_global_attempt_count, factory_attempt_count, 0),
        "factory_global_selected_count": max(factory_global_selected_count, factory_selected_count, 0),
        "legacy_factory_attempt_count": factory_attempt_count,
        "legacy_task_attempt_count": task_attempt_count,
        "legacy_external_llm_attempt_count": external_attempt_count,
    }
    adjustment.update(_estimate_batch_correlation_adjustment(strategy, adjustment))
    return adjustment


def _estimate_batch_correlation_adjustment(
    strategy: dict,
    attempt_adjustment: dict[str, Any],
) -> dict[str, Any]:
    generator_mode = _resolve_submission_generator_mode(strategy)
    attempt_count = max(1, int(attempt_adjustment.get("attempt_count") or 1))
    selected_count = max(0, int(attempt_adjustment.get("selected_count") or 0))
    task_local_selected_count = max(
        0,
        int(
            attempt_adjustment.get("task_local_selected_count")
            or _strategy_payload_value(strategy, "task_local_selected_count", 0)
            or 0
        ),
    )
    candidate_local_attempt_count = max(
        0,
        int(
            attempt_adjustment.get("candidate_local_attempt_count")
            or _strategy_payload_value(strategy, "candidate_local_attempt_count", 0)
            or 0
        ),
    )
    sibling_count = max(task_local_selected_count, selected_count, 1)
    if generator_mode not in _LLM_CORRELATED_GENERATOR_MODES:
        return {
            "batch_correlation_mode": "independent_local_trials",
            "batch_correlation_multiplier": 1.0,
            "batch_correlation_sibling_count": sibling_count,
            "batch_correlation_generator_mode": generator_mode,
            "cohort_effective_trials": round(float(attempt_count), 4),
        }
    if sibling_count <= 1:
        return {
            "batch_correlation_mode": "llm_single_candidate_batch",
            "batch_correlation_multiplier": 1.0,
            "batch_correlation_sibling_count": sibling_count,
            "batch_correlation_generator_mode": generator_mode,
            "cohort_effective_trials": round(float(attempt_count), 4),
        }
    sibling_multiplier = math.sqrt(float(sibling_count))
    effective_multiplier = 1.0 + (
        (sibling_multiplier - 1.0)
        * (max(candidate_local_attempt_count, 1) / max(float(attempt_count), 1.0))
    )
    effective_trials = max(float(attempt_count), float(attempt_count) * effective_multiplier)
    return {
        "batch_correlation_mode": "llm_same_batch_sibling_proxy",
        "batch_correlation_multiplier": round(float(effective_multiplier), 4),
        "batch_correlation_sibling_count": sibling_count,
        "batch_correlation_generator_mode": generator_mode,
        "cohort_effective_trials": round(float(effective_trials), 4),
    }


def resolve_attempt_adjustment(
    strategy: dict,
    *,
    gate: Optional[dict[str, Any]] = None,
    attempt_adjustment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if attempt_adjustment not in (None, {}, ""):
        return dict(
            normalize_quality_gate_result({"attempt_adjustment": attempt_adjustment}).get("attempt_adjustment") or {}
        )
    if gate:
        normalized_gate = normalize_quality_gate_result(gate)
        resolved = dict(normalized_gate.get("attempt_adjustment") or {})
        if resolved:
            return resolved
    return dict(
        normalize_quality_gate_result({"attempt_adjustment": _build_attempt_adjustment(strategy)}).get("attempt_adjustment")
        or {}
    )


def _build_multiple_testing_registry(
    strategy: dict,
    profile: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    normalized_gate = normalize_quality_gate_result(gate)
    research_task = dict(profile.get("research_task") or {})
    generation_reason = dict(
        _strategy_payload_value(strategy, "generation_reason")
        or strategy.get("generation_reason")
        or {}
    )
    target_codes = _extract_target_codes_from_payload(strategy)
    candidate_provenance = dict(
        _strategy_payload_value(strategy, "candidate_provenance")
        or strategy.get("candidate_provenance")
        or {}
    )
    dedup_result = dict(
        _strategy_payload_value(strategy, "dedup_result")
        or strategy.get("dedup_result")
        or {}
    )
    attempt_adjustment = resolve_attempt_adjustment(strategy, gate=normalized_gate)
    multiple_testing = dict(normalized_gate.get("multiple_testing") or {})
    contract_snapshot = dict(
        _strategy_payload_value(strategy, "candidate_contract_snapshot")
        or strategy.get("candidate_contract_snapshot")
        or {}
    )
    if not contract_snapshot:
        try:
            contract_snapshot = build_portfolio_candidate_contract(strategy)
        except Exception:
            contract_snapshot = {}
    targeting = dict(contract_snapshot.get("targeting") or {})
    lineage = dict(contract_snapshot.get("lineage") or {})
    task_signature = str(
        _strategy_payload_value(strategy, "task_signature")
        or research_task.get("task_signature")
        or lineage.get("task_signature")
        or _build_task_signature(research_task)
    ).strip()
    target_symbols_signature = ",".join(sorted(dict.fromkeys(target_codes)))
    strategy_family = str(
        candidate_provenance.get("candidate_family")
        or _strategy_payload_value(strategy, "candidate_family")
        or strategy.get("strategy_type")
        or "unknown"
    ).strip().lower()
    family_matrix_artifact_id = str(
        candidate_provenance.get("source_generation_artifact_id")
        or candidate_provenance.get("source_validation_artifact_id")
        or _strategy_payload_value(strategy, "source_generation_artifact_id")
        or _strategy_payload_value(strategy, "source_validation_artifact_id")
        or ""
    ).strip() or None
    strategy_type = str(strategy.get("strategy_type") or "").strip().lower() or "unknown"
    strategy_family_id = str(
        candidate_provenance.get("candidate_family_id")
        or _strategy_payload_value(strategy, "candidate_family_id")
        or strategy_family
        or ""
    ).strip() or None
    candidate_contract_hash = str(
        _strategy_payload_value(strategy, "candidate_contract_hash")
        or strategy.get("candidate_contract_hash")
        or ""
    ).strip()
    if not candidate_contract_hash:
        candidate_contract_hash = (
            build_candidate_contract_hash(contract=contract_snapshot)
            if contract_snapshot
            else build_candidate_contract_hash(strategy)
        )
    execution_contract_hash = str(
        _strategy_payload_value(strategy, "execution_contract_hash")
        or strategy.get("execution_contract_hash")
        or ""
    ).strip()
    if not execution_contract_hash:
        execution_contract_hash = (
            build_execution_contract_hash(contract=contract_snapshot)
            if contract_snapshot
            else build_execution_contract_hash(strategy)
        )
    candidate_identity_signature = str(
        _strategy_payload_value(strategy, "candidate_identity_signature")
        or strategy.get("candidate_identity_signature")
        or ""
    ).strip()
    if not candidate_identity_signature:
        candidate_identity_signature = build_candidate_identity_signature(strategy)
    tested_object_hash = str(
        _strategy_payload_value(strategy, "tested_object_hash")
        or strategy.get("tested_object_hash")
        or ""
    ).strip()
    if not tested_object_hash:
        tested_object_hash = build_tested_object_hash(strategy)
    logic_signature = str(
        _strategy_payload_value(strategy, "logic_signature")
        or strategy.get("logic_signature")
        or build_logic_signature(strategy)
        or ""
    ).strip() or None
    dsl_signature = str(
        _strategy_payload_value(strategy, "dsl_signature")
        or strategy.get("dsl_signature")
        or build_dsl_signature(strategy)
        or ""
    ).strip() or None
    factor_signature = str(
        _strategy_payload_value(strategy, "factor_signature")
        or strategy.get("factor_signature")
        or build_factor_signature(strategy)
        or ""
    ).strip() or None
    entry_exit_signature = str(
        _strategy_payload_value(strategy, "entry_exit_signature")
        or strategy.get("entry_exit_signature")
        or build_entry_exit_signature(strategy)
        or ""
    ).strip() or None
    lineage_id = str(
        lineage.get("lineage_id")
        or _strategy_payload_value(strategy, "lineage_id")
        or task_signature
        or ""
    ).strip() or None
    target_pool_id = str(
        targeting.get("target_pool_id")
        or _strategy_payload_value(strategy, "target_pool_id")
        or ""
    ).strip() or None
    template_generation_profile = str(
        research_task.get("template_generation_profile")
        or generation_reason.get("template_generation_profile")
        or dict(generation_reason.get("rule_template_contract") or {}).get("template_generation_profile")
        or candidate_provenance.get("template_generation_profile")
        or _strategy_payload_value(strategy, "template_generation_profile")
        or ""
    ).strip().lower() or None
    refresh_mode = str(
        dedup_result.get("refresh_mode")
        or _strategy_payload_value(strategy, "refresh_mode")
        or candidate_provenance.get("refresh_mode")
        or ""
    ).strip().lower() or None
    revision_mode = str(
        _strategy_payload_value(strategy, "revision_mode")
        or research_task.get("revision_mode")
        or candidate_provenance.get("revision_mode")
        or ("spawn_revision_from_existing" if refresh_mode == "spawn_revision_from_existing" else "baseline")
    ).strip().lower() or None
    formal_coverage = all(
        normalized_gate.get(field) is not None
        for field in (
            "deflated_sharpe_ratio",
            "pbo",
            "white_reality_check_pvalue",
            "hansen_spa_pvalue",
        )
    )
    strategy_profile = dict(contract_snapshot.get("strategy_profile") or {})
    if not strategy_profile:
        strategy_profile = infer_candidate_strategy_profile(strategy, research_task=research_task)
    holding_period_bucket = str(
        strategy_profile.get("holding_period_bucket")
        or _strategy_payload_value(strategy, "holding_period_bucket")
        or strategy.get("holding_period_bucket")
        or ""
    ).strip().lower() or None
    generator_mode = _resolve_submission_generator_mode(
        strategy,
        research_task=research_task,
        contract_snapshot=contract_snapshot,
    )
    validation_profile_name = str(
        dict(contract_snapshot.get("validation_profile") or {}).get("profile")
        or strategy_profile.get("validation_profile")
        or profile.get("profile")
        or ""
    ).strip().lower() or None
    validation_focus = str(profile.get("validation_focus") or "").strip().lower() or None
    primary_validation_layer = str(profile.get("primary_validation_layer") or "").strip().lower() or None

    def _axis_key(prefix: str, *parts: Any, fallback: str = "unknown") -> str:
        tokens = [str(part).strip() for part in parts if str(part or "").strip()]
        return f"{prefix}|{'|'.join(tokens)}" if tokens else f"{prefix}|{fallback}"

    task_key = _axis_key("task", task_signature)
    family_key = _axis_key("family", strategy_family_id or strategy_family, strategy_type)
    universe_key = _axis_key("universe", target_pool_id, target_symbols_signature)
    holding_key = _axis_key("holding", holding_period_bucket)
    generator_key = _axis_key("generator", generator_mode)
    validation_key = _axis_key("validation", validation_profile_name, validation_focus, primary_validation_layer)
    template_key = _axis_key(
        "template",
        template_generation_profile,
        str(profile.get("profile") or "").strip().lower(),
        strategy_type,
    )
    revision_key = _axis_key("revision", lineage_id, revision_mode, refresh_mode)
    tested_object_key = _axis_key("tested", tested_object_hash)
    registry_key = "|".join(
        (
            task_key,
            family_key,
            universe_key,
            holding_key,
            generator_key,
            validation_key,
            template_key,
            revision_key,
            tested_object_key,
        )
    )
    cohort_effective_trials = float(
        normalized_gate.get("deflated_sharpe_effective_trials")
        or normalized_gate.get("cohort_effective_trials")
        or attempt_adjustment.get("cohort_effective_trials")
        or dict(multiple_testing.get("deflated_sharpe") or {}).get("effective_trials")
        or attempt_adjustment.get("attempt_count")
        or 1.0
    )
    batch_correlation_mode = str(
        normalized_gate.get("batch_correlation_mode")
        or attempt_adjustment.get("batch_correlation_mode")
        or ""
    ).strip().lower() or None
    batch_correlation_multiplier = float(
        normalized_gate.get("batch_correlation_multiplier")
        or attempt_adjustment.get("batch_correlation_multiplier")
        or 1.0
    )
    batch_correlation_sibling_count = int(
        normalized_gate.get("batch_correlation_sibling_count")
        or attempt_adjustment.get("batch_correlation_sibling_count")
        or 0
    )

    return {
        "registry_key": registry_key,
        "task_signature": task_signature,
        "task_key": task_key,
        "strategy_family": strategy_family,
        "strategy_family_id": strategy_family_id,
        "family_key": family_key,
        "strategy_type": strategy_type,
        "target_symbols_signature": target_symbols_signature,
        "target_pool_id": target_pool_id,
        "universe_key": universe_key,
        "holding_period_bucket": holding_period_bucket,
        "holding_key": holding_key,
        "generator_mode": generator_mode,
        "generator_key": generator_key,
        "validation_profile": validation_profile_name,
        "validation_focus": validation_focus,
        "primary_validation_layer": primary_validation_layer,
        "validation_key": validation_key,
        "template_generation_profile": template_generation_profile,
        "template_key": template_key,
        "lineage_id": lineage_id,
        "revision_mode": revision_mode,
        "refresh_mode": refresh_mode,
        "revision_key": revision_key,
        "tested_object_key": tested_object_key,
        "candidate_contract_hash": candidate_contract_hash or None,
        "execution_contract_hash": execution_contract_hash or None,
        "tested_object_hash": tested_object_hash or None,
        "candidate_identity_signature": candidate_identity_signature or None,
        "logic_signature": logic_signature,
        "dsl_signature": dsl_signature,
        "factor_signature": factor_signature,
        "entry_exit_signature": entry_exit_signature,
        "attempt_count": int(attempt_adjustment.get("attempt_count") or 1),
        "selected_count": int(attempt_adjustment.get("selected_count") or 0),
        "selection_ratio": float(attempt_adjustment.get("selection_ratio") or 0.0),
        "candidate_local_attempt_count": int(
            attempt_adjustment.get("candidate_local_attempt_count")
            or _strategy_payload_value(strategy, "candidate_local_attempt_count", 0)
            or 0
        ),
        "task_local_attempt_count": int(
            attempt_adjustment.get("task_local_attempt_count")
            or _strategy_payload_value(strategy, "task_local_attempt_count", 0)
            or 0
        ),
        "factory_global_attempt_count": int(
            attempt_adjustment.get("factory_global_attempt_count")
            or _strategy_payload_value(strategy, "factory_global_attempt_count", 0)
            or 0
        ),
        "factory_attempt_count": int(_strategy_payload_value(strategy, "factory_attempt_count", 0) or 0),
        "task_attempt_count": int(_strategy_payload_value(strategy, "task_attempt_count", 0) or 0),
        "external_llm_attempt_count": int(_strategy_payload_value(strategy, "external_llm_attempt_count", 0) or 0),
        "family_matrix_artifact_id": family_matrix_artifact_id,
        "formal_coverage": formal_coverage,
        "formal_runtime_ready": formal_coverage and str(normalized_gate.get("multiple_testing_mode") or "").strip().lower() == "formal_runtime",
        "multiple_testing_mode": normalized_gate.get("multiple_testing_mode"),
        "multiple_testing_cohort_mode": normalized_gate.get("multiple_testing_cohort_mode"),
        "multiple_testing_panel_size": int(normalized_gate.get("multiple_testing_panel_size") or 0),
        "multiple_testing_panel_symbols": list(normalized_gate.get("multiple_testing_panel_symbols") or []),
        "cohort_effective_trials": round(cohort_effective_trials, 4),
        "batch_correlation_mode": batch_correlation_mode,
        "batch_correlation_multiplier": round(batch_correlation_multiplier, 4),
        "batch_correlation_sibling_count": batch_correlation_sibling_count,
        "registry_axes": {
            "task": task_key,
            "family": family_key,
            "universe": universe_key,
            "holding": holding_key,
            "generator": generator_key,
            "validation": validation_key,
            "template": template_key,
            "revision": revision_key,
            "tested_object": tested_object_key,
        },
        "multiple_testing": {
            "deflated_sharpe": dict(multiple_testing.get("deflated_sharpe") or {}),
            "pbo": dict(multiple_testing.get("pbo") or {}),
            "white_reality_check": dict(multiple_testing.get("white_reality_check") or {}),
            "hansen_spa": dict(multiple_testing.get("hansen_spa") or {}),
            "deflated_sharpe_ratio": normalized_gate.get("deflated_sharpe_ratio"),
            "pbo_value": normalized_gate.get("pbo"),
            "white_reality_check_pvalue": normalized_gate.get("white_reality_check_pvalue"),
            "hansen_spa_pvalue": normalized_gate.get("hansen_spa_pvalue"),
            "deflated_sharpe_proxy": normalized_gate.get("deflated_sharpe_proxy"),
            "pbo_proxy": normalized_gate.get("pbo_proxy"),
            "reality_check_pvalue_proxy": normalized_gate.get("reality_check_pvalue_proxy"),
            "spa_pvalue_proxy": normalized_gate.get("spa_pvalue_proxy"),
        },
    }


def _admission_threshold_bundle(admission_level: str) -> dict[str, Any]:
    normalized = str(admission_level or "incubation").strip().lower()
    return dict(_ADMISSION_THRESHOLD_SETS.get(normalized) or INCUBATION_ADMISSION_THRESHOLDS)


def _multiple_testing_thresholds(admission_level: str) -> dict[str, float]:
    base = dict(_admission_threshold_bundle(admission_level).get("multiple_testing") or {})
    return {
        "deflated_sharpe_ratio_min": float(base.get("deflated_sharpe_ratio_min", -0.10)),
        "pbo_max": float(base.get("pbo_max", 0.75)),
        "white_reality_check_pvalue_max": float(base.get("white_reality_check_pvalue_max", 0.35)),
        "hansen_spa_pvalue_max": float(base.get("hansen_spa_pvalue_max", 0.35)),
    }


def _review_gate_thresholds(admission_level: str) -> dict[str, float]:
    base = dict(_admission_threshold_bundle(admission_level).get("review") or {})
    return {
        "committee_final_score_min": float(base.get("committee_final_score_min", 0.0)),
        "promotion_review_score_min": float(base.get("promotion_review_score_min", 0.0)),
    }


def _statistical_gate_thresholds(
    attempt_adjustment: dict[str, Any],
    *,
    admission_level: str = "incubation",
) -> dict[str, float]:
    penalty = float(attempt_adjustment.get("penalty") or 0.0)
    base = dict(_admission_threshold_bundle(admission_level).get("statistical_validation") or QUALITY_GATE_THRESHOLDS)
    return {
        "walk_forward_ic_ir_min": float(base.get("walk_forward_ic_ir_min", 0.30)) + penalty,
        "purged_kfold_ic_min": float(base.get("purged_kfold_ic_min", 0.02)) + penalty / 2.0,
        "bootstrap_ci_lower_min": float(base.get("bootstrap_ci_lower_min", 0.0)) + penalty / 3.0,
        "param_sensitivity_max": float(base.get("param_sensitivity_max", 0.30)),
    }


def _first_float_value(payload: Optional[dict], *keys: str) -> Optional[float]:
    data = dict(payload or {})
    for key in keys:
        if key not in data or data.get(key) is None:
            continue
        try:
            return float(data.get(key) or 0.0)
        except Exception:
            continue
    return None

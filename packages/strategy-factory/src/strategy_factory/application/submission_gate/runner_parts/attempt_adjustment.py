

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


def _live_multiple_testing_reasons(payload: Optional[dict], thresholds: dict[str, float]) -> list[str]:
    normalized = dict(payload or {})
    reasons: list[str] = []
    multiple_testing_mode = str(normalized.get("multiple_testing_mode") or "").strip().lower()
    if multiple_testing_mode != "formal_runtime":
        reasons.append("formal_multiple_testing_mode_required_for_live_admission")

    deflated_sharpe = _first_float_value(normalized, "deflated_sharpe_ratio")
    pbo = _first_float_value(normalized, "pbo")
    white_rc = _first_float_value(normalized, "white_reality_check_pvalue")
    spa_pvalue = _first_float_value(normalized, "hansen_spa_pvalue")

    if deflated_sharpe is None:
        reasons.append("deflated_sharpe_missing_for_live_admission")
    elif deflated_sharpe < thresholds["deflated_sharpe_ratio_min"]:
        reasons.append(
            f"deflated_sharpe {deflated_sharpe:.3f} < {thresholds['deflated_sharpe_ratio_min']:.3f}"
        )
    if pbo is None:
        reasons.append("pbo_missing_for_live_admission")
    elif pbo > thresholds["pbo_max"]:
        reasons.append(f"pbo {pbo:.3f} > {thresholds['pbo_max']:.3f}")
    if white_rc is None:
        reasons.append("white_reality_check_missing_for_live_admission")
    elif white_rc > thresholds["white_reality_check_pvalue_max"]:
        reasons.append(
            "white_reality_check_pvalue "
            f"{white_rc:.3f} > {thresholds['white_reality_check_pvalue_max']:.3f}"
        )
    if spa_pvalue is None:
        reasons.append("hansen_spa_missing_for_live_admission")
    elif spa_pvalue > thresholds["hansen_spa_pvalue_max"]:
        reasons.append(
            f"hansen_spa_pvalue {spa_pvalue:.3f} > {thresholds['hansen_spa_pvalue_max']:.3f}"
        )
    return reasons


def _target_only_live_trade_family(
    strategy: dict,
    profile: dict[str, Any],
    payload: Optional[dict] = None,
) -> str | None:
    profile_name = _normalize_text(profile.get("profile"))
    validation_focus = _normalize_text(
        profile.get("validation_focus") or dict(payload or {}).get("validation_focus")
    )
    multiple_testing_cohort_mode = _normalize_text(dict(payload or {}).get("multiple_testing_cohort_mode"))
    if profile_name != "trade_rule_validation":
        return None
    if validation_focus not in _TARGET_ONLY_VALIDATION_FOCUSES:
        return None
    if multiple_testing_cohort_mode and multiple_testing_cohort_mode != "target_only":
        return None
    family = _normalize_text(
        _strategy_payload_value(strategy, "candidate_family")
        or _strategy_payload_value(strategy, "candidate_family_id")
        or strategy.get("strategy_type")
    )
    if family in _TRADE_AWARE_VALIDATION_GRADE_FAMILIES:
        return family
    return None


def _effective_live_multiple_testing_thresholds(
    strategy: dict,
    profile: dict[str, Any],
    payload: Optional[dict],
) -> dict[str, float]:
    thresholds = dict(_multiple_testing_thresholds("live"))
    family = _target_only_live_trade_family(strategy, profile, payload)
    if not family:
        return thresholds
    thresholds["deflated_sharpe_ratio_min"] = min(
        thresholds["deflated_sharpe_ratio_min"],
        0.0,
    )
    if family == "quality_factor":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.80)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.20,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.20,
        )
    elif family == "ma_cross":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.75)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.30,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.30,
        )
    elif family == "momentum":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.70)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.25,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.25,
        )
    return thresholds


def _observed_sharpe_proxy(series: Optional[np.ndarray], fallback_score: float) -> float:
    arr = np.asarray(series if series is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size >= 3:
        std = float(np.std(arr, ddof=1))
        if std > 1e-9:
            return float(np.mean(arr) / std * np.sqrt(252.0))
    return float(fallback_score or 0.0)


def _strategy_return_series_for_params(
    klass,
    params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    series_list: list[np.ndarray] = []
    for closes in close_panels:
        window = np.asarray(closes[:min_len], dtype=float)
        if window.size < min_len:
            continue
        instance = klass()
        instance.set_parameters(params or {})
        signals = np.asarray(instance.generate_signals(window), dtype=float)
        if signals.size < min_len:
            continue
        aligned = signals[:min_len]
        forward_returns = np.zeros(min_len, dtype=float)
        valid_prev = np.maximum(window[:-1], 1e-12)
        forward_returns[:-1] = (window[1:] - window[:-1]) / valid_prev
        series_list.append((aligned * forward_returns).astype(float))
    if not series_list:
        return None
    return np.mean(np.column_stack(series_list), axis=1).astype(float)


def _build_strategy_family_returns(
    klass,
    strategy_params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    if min_len < 24 or not close_panels:
        return None
    family_series: list[np.ndarray] = []

    base_series = _strategy_return_series_for_params(klass, strategy_params, close_panels, min_len=min_len)
    if base_series is None:
        return None
    family_series.append(base_series)

    for key, value in sorted((strategy_params or {}).items()):
        if not isinstance(value, (int, float)) or value == 0:
            continue
        for mult in (0.8, 1.2):
            varied_params = dict(strategy_params or {})
            varied_value = float(value) * mult
            if isinstance(value, int):
                varied_params[key] = max(1, int(round(varied_value)))
            else:
                varied_params[key] = float(varied_value)
            varied_series = _strategy_return_series_for_params(klass, varied_params, close_panels, min_len=min_len)
            if varied_series is None:
                continue
            if any(np.allclose(varied_series, existing, atol=1e-9, rtol=1e-6) for existing in family_series):
                continue
            family_series.append(varied_series)

    if len(family_series) < 2:
        return np.column_stack(family_series)
    return np.column_stack(family_series)



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
                normalized_gate,
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


async def _run_statistical_gate(
    db,
    strategy: dict,
    *,
    profile: dict[str, Any],
    klass,
) -> dict[str, Any]:
    normalize_klines = get_normalize_klines()
    validation_runtime = get_validation_runtime()

    instance = klass()
    strategy_params = strategy.get("params") or {}
    instance.set_parameters(strategy_params)

    contract_snapshot = {}
    try:
        contract_snapshot = build_portfolio_candidate_contract(strategy)
    except Exception:
        contract_snapshot = {}
    codes, cohort_mode = _resolve_multiple_testing_panel(strategy, profile, contract_snapshot)
    all_closes = []
    for code in codes:
        klines = await db.get_klines(code, limit=500)
        if klines and len(klines) >= 100:
            ordered = normalize_klines(klines)
            closes = np.array([float(k.get("close", 0)) for k in ordered], dtype=float)
            all_closes.append(closes)

    if not all_closes:
        return normalize_quality_gate_result({"passed": False, "reason": "Insufficient kline data for quality gate"})

    min_len = min(len(c) for c in all_closes)
    n_stocks = len(all_closes)
    factor_panel = np.zeros((min_len, n_stocks))
    return_panel = np.zeros((min_len, n_stocks))
    for j, closes in enumerate(all_closes):
        closes = closes[:min_len]
        signals = instance.generate_signals(closes)
        factor_panel[:, j] = signals[:min_len].astype(float)
        for i in range(min_len - 1):
            return_panel[i, j] = (closes[i + 1] - closes[i]) / closes[i] if closes[i] > 0 else 0

    flat_factors = factor_panel.flatten()
    flat_returns = return_panel.flatten()
    strategy_return_series = np.nanmean(factor_panel * return_panel, axis=1)
    family_returns = _build_strategy_family_returns(
        klass,
        strategy_params,
        [np.asarray(c[:min_len], dtype=float) for c in all_closes],
        min_len=min_len,
    )

    reasons = []
    attempt_adjustment = resolve_attempt_adjustment(strategy)

    statistical_thresholds = _statistical_gate_thresholds(
        attempt_adjustment,
        admission_level="incubation",
    )
    _wf_min = statistical_thresholds["walk_forward_ic_ir_min"]
    try:
        wf = validation_runtime.WalkForwardValidator(train_window=60, test_window=20, step=20)
        wf_summary = wf.validate(factor_panel, return_panel)
        wf_sharpe = wf_summary.oos_ic_ir
        if wf_sharpe < _wf_min:
            reasons.append(f"Walk-Forward IC IR {wf_sharpe:.3f} < {_wf_min}")
    except Exception as e:
        reasons.append(f"Walk-Forward error: {e}")
        wf_sharpe = 0

    _pkf_min = statistical_thresholds["purged_kfold_ic_min"]
    try:
        pkf = validation_runtime.PurgedKFoldCV(n_folds=5, purge_gap=5)
        pkf_summary = pkf.validate(factor_panel, return_panel)
        pkf_ic = pkf_summary.oos_ic_mean
        if pkf_ic < _pkf_min:
            reasons.append(f"Purged K-Fold IC {pkf_ic:.4f} < {_pkf_min}")
    except Exception as e:
        reasons.append(f"Purged K-Fold error: {e}")
        pkf_ic = 0

    _bs_min = statistical_thresholds["bootstrap_ci_lower_min"]
    try:
        bs = validation_runtime.bootstrap_ic_ci(flat_factors, flat_returns)
        ci_lower = bs.get("ci_lower", 0)
        if ci_lower < _bs_min:
            reasons.append(f"Bootstrap CI lower {ci_lower:.4f} < {_bs_min}")
    except Exception as e:
        reasons.append(f"Bootstrap error: {e}")
        ci_lower = 0

    _sens_max = statistical_thresholds["param_sensitivity_max"]
    sensitivity = 0.0
    try:
        ref_closes = all_closes[0][:min_len]
        ref_returns = return_panel[:, 0]
        base_signals = instance.generate_signals(ref_closes)[:min_len]
        base_ic = float(np.corrcoef(base_signals.astype(float), ref_returns)[0, 1])
        if not np.isnan(base_ic) and abs(base_ic) > 0.001:
            variations = []
            for key, val in strategy_params.items():
                if isinstance(val, (int, float)) and val != 0:
                    for mult in [0.8, 1.2]:
                        test_params = {**strategy_params, key: type(val)(val * mult)}
                        test_instance = klass()
                        test_instance.set_parameters(test_params)
                        test_signals = test_instance.generate_signals(ref_closes)[:min_len]
                        test_ic = float(np.corrcoef(test_signals.astype(float), ref_returns)[0, 1])
                        if not np.isnan(test_ic):
                            variations.append(abs(test_ic - base_ic) / abs(base_ic))
            if variations:
                sensitivity = float(np.mean(variations))
        if sensitivity > _sens_max:
            reasons.append(f"Parameter sensitivity {sensitivity:.2%} > {_sens_max:.0%}")
    except Exception as e:
        reasons.append(f"Sensitivity error: {e}")

    period_robustness = {"first_half_ic": 0.0, "second_half_ic": 0.0, "ic_consistency": 0.0}
    try:
        half = min_len // 2
        if half >= 50:
            first_factors = factor_panel[:half, :].flatten()
            first_returns = return_panel[:half, :].flatten()
            second_factors = factor_panel[half:, :].flatten()
            second_returns = return_panel[half:, :].flatten()
            ic_first = float(np.corrcoef(first_factors, first_returns)[0, 1])
            ic_second = float(np.corrcoef(second_factors, second_returns)[0, 1])
            if np.isnan(ic_first):
                ic_first = 0.0
            if np.isnan(ic_second):
                ic_second = 0.0
            period_robustness = {
                "first_half_ic": round(ic_first, 4),
                "second_half_ic": round(ic_second, 4),
                "ic_consistency": round(min(ic_first, ic_second), 4),
            }
            if ic_first < -0.02 or ic_second < -0.02:
                reasons.append(
                    f"Multi-period IC inconsistent: first_half={ic_first:.4f}, second_half={ic_second:.4f} (both must be >= -0.02)"
                )
            elif ic_first > 0.01 and ic_second < -0.01:
                reasons.append(
                    f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                )
            elif ic_first < -0.01 and ic_second > 0.01:
                reasons.append(
                    f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                )
    except Exception as e:
        reasons.append(f"Multi-period robustness error: {e}")

    observed_score = max(wf_sharpe, pkf_ic, ci_lower)
    run_correction = _estimate_run_correction_metrics(
        attempt_adjustment,
        observed_score=observed_score,
        score_series=strategy_return_series,
        family_returns=family_returns,
        validation_runtime=validation_runtime,
    )
    warnings = list(run_correction.pop("warnings", []))

    passed = len(reasons) == 0
    return normalize_quality_gate_result(
        {
            "passed": passed,
            "passed_strict": passed,
            "profile": profile.get("profile"),
            "validation_focus": profile.get("validation_focus"),
            "primary_validation_layer": profile.get("primary_validation_layer"),
            "attempt_adjustment": attempt_adjustment,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "period_robustness": period_robustness,
            "reasons": reasons,
            "warnings": warnings,
            "multiple_testing_cohort_mode": cohort_mode,
            "multiple_testing_panel_symbols": list(codes),
            "multiple_testing_panel_size": len(codes),
            **run_correction,
            "cohort_effective_trials": round(
                float(
                    run_correction.get("deflated_sharpe_effective_trials")
                    or run_correction.get("cohort_effective_trials")
                    or attempt_adjustment.get("cohort_effective_trials")
                    or attempt_adjustment.get("attempt_count")
                    or 1.0
                ),
                4,
            ),
        }
    )

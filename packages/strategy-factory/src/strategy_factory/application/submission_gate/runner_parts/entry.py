

async def run_submission_quality_gate(
    db,
    strategy: dict,
    *,
    validation_report: dict | None = None,
    risk_report: dict | None = None,
    backtest_metrics: dict | None = None,
    incubation_budget_track: str | None = None,
    submission_lane: str | None = None,
) -> Dict[str, Any]:
    """Run the submission-stage quality gate and return the final authority result."""
    try:
        strategy = apply_resolved_candidate_envelope(strategy)
        materialized_backtest_metrics = _materialize_backtest_metrics_contract(backtest_metrics)
        backtest_metrics_contract_status = _normalize_text(
            materialized_backtest_metrics.get("backtest_metrics_contract_status")
        ) or "missing"
        try:
            from strategy_factory.application.research.statistical_robustness import (
                enrich_validation_report_with_robustness_derivations,
            )

            validation_report = enrich_validation_report_with_robustness_derivations(
                validation_report,
                backtest_metrics=materialized_backtest_metrics,
            )
        except Exception:
            pass
        profile = _resolve_validation_profile(strategy)
        profile_name = str(profile.get("profile") or "").strip().lower()
        strategy_type = str(strategy.get("strategy_type", "") or "").strip().lower()
        strategy_registry = get_strategy_registry()
        klass = strategy_registry.get(strategy_type) if strategy_type else None
        if klass is None:
            return normalize_quality_gate_result(
                {
                    "passed": False,
                    "reason": f"Strategy type not in registry: {strategy_type}",
                    "attempt_adjustment": resolve_attempt_adjustment(strategy),
                }
            )

        normalized: dict[str, Any]
        if profile_name == "factor_rank_validation":
            statistical_gate = await _run_statistical_gate(
                db,
                strategy,
                profile=profile,
                klass=klass,
                backtest_metrics=materialized_backtest_metrics,
                validation_report=validation_report,
            )
            normalized = _with_gate_protocol(
                statistical_gate,
                "factor_rank_validation:statistical_primary",
            )
        elif profile_name in _TRADE_PRIMARY_PROFILES:
            if _has_trade_validation_audit(materialized_backtest_metrics):
                trade_gate = _with_gate_protocol(
                    _evaluate_trade_profile(strategy, profile, materialized_backtest_metrics, risk_report),
                    f"{profile_name}:trade_primary",
                )
                supplemental_gate: dict[str, Any]
                try:
                    supplemental_gate = await _run_statistical_gate(
                        db,
                        strategy,
                        profile=profile,
                        klass=klass,
                        backtest_metrics=materialized_backtest_metrics,
                        validation_report=validation_report,
                    )
                except Exception as exc:
                    supplemental_gate = normalize_quality_gate_result(
                        {
                            "passed": False,
                            "reason": f"Supplemental statistical gate error: {exc}",
                            "warnings": [f"supplemental_statistical_gate_error:{type(exc).__name__}"],
                        }
                    )
                normalized = _merge_trade_primary_gate(trade_gate, supplemental_gate)
            else:
                audit_mode = _trade_validation_audit_mode(
                    incubation_budget_track=incubation_budget_track,
                    submission_lane=submission_lane,
                )
                if audit_mode == "hard_fail":
                    hard_fail_reasons = [f"{profile_name}:trade_validation_audit_missing"]
                    if backtest_metrics_contract_status == "missing":
                        hard_fail_reasons.append("missing_backtest_metrics_contract")
                    normalized = normalize_quality_gate_result(
                        {
                            "passed": False,
                            "gate_protocol": f"{profile_name}:hard_fail_missing_trade_audit",
                            "reasons": hard_fail_reasons,
                            "trade_validation_audit_missing": True,
                            "trade_validation_audit_mode": audit_mode,
                            "backtest_metrics_contract_status": backtest_metrics_contract_status,
                        }
                    )
                else:
                    statistical_gate = await _run_statistical_gate(
                        db,
                        strategy,
                        profile=profile,
                        klass=klass,
                        backtest_metrics=materialized_backtest_metrics,
                        validation_report=validation_report,
                    )
                    warnings = _merge_text_items(
                        statistical_gate.get("warnings"),
                        _merge_text_items(
                            [f"{profile_name}:trade_validation_audit_missing"],
                            ["missing_backtest_metrics_contract"] if backtest_metrics_contract_status == "missing" else [],
                        ),
                    )
                    normalized = normalize_quality_gate_result(
                        {
                            **statistical_gate,
                            "gate_protocol": f"{profile_name}:statistical_fallback_research_only",
                            "warnings": warnings,
                            "trade_validation_audit_missing": True,
                            "trade_validation_audit_mode": audit_mode,
                            "research_only_due_to_trade_audit_gap": True,
                            "backtest_metrics_contract_status": backtest_metrics_contract_status,
                        }
                    )
        else:
            statistical_gate = await _run_statistical_gate(
                db,
                strategy,
                profile=profile,
                klass=klass,
                backtest_metrics=materialized_backtest_metrics,
                validation_report=validation_report,
            )
            warnings = list(statistical_gate.get("warnings") or [])
            protocol = f"{profile_name or 'unknown'}:statistical_fallback"
            if profile_name in _TRADE_PRIMARY_PROFILES:
                warnings = _merge_text_items(
                    warnings,
                    [f"{profile_name}:trade_validation_audit_missing"],
                )
            normalized = normalize_quality_gate_result(
                {
                    **statistical_gate,
                    "gate_protocol": protocol,
                    "warnings": warnings,
                }
            )
        normalized = maybe_grant_provisional_incubation(
            strategy,
            normalized,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=materialized_backtest_metrics,
        )
        normalized = normalize_quality_gate_result(
            {
                **normalized,
                "backtest_metrics_contract_status": backtest_metrics_contract_status,
                "attempt_adjustment": resolve_attempt_adjustment(strategy, gate=normalized),
                "cohort_effective_trials": float(
                    normalized.get("deflated_sharpe_effective_trials")
                    or normalized.get("cohort_effective_trials")
                    or dict(normalized.get("attempt_adjustment") or {}).get("cohort_effective_trials")
                    or 0.0
                ),
                "multiple_testing_registry": _build_multiple_testing_registry(
                    strategy,
                    profile,
                    normalized,
                ),
            }
        )
        semantic_runtime_context = _resolve_semantic_runtime_context(strategy, gate=normalized)
        normalized = normalize_quality_gate_result(
            {
                **normalized,
                **semantic_runtime_context,
            }
        )
        return _attach_admission_evaluations(
            strategy,
            profile,
            normalized,
            risk_report=risk_report,
            validation_report=validation_report,
            backtest_metrics=materialized_backtest_metrics,
        )
    except Exception as e:
        return normalize_quality_gate_result(
            {
                "passed": False,
                "reason": str(e),
                "attempt_adjustment": resolve_attempt_adjustment(strategy),
            }
        )

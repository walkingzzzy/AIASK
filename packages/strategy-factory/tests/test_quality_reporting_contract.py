from strategy_factory.application.quality_reporting import (
    build_quality_report,
    maybe_grant_provisional_incubation,
    normalize_quality_gate_result,
    quality_gate_reason_code,
)


def test_quality_gate_reason_code_normalizes_known_labels():
    assert quality_gate_reason_code("insufficient kline data for gate") == "insufficient_kline_data"


def test_normalize_quality_gate_result_deduplicates_reason_and_warning_lists():
    normalized = normalize_quality_gate_result(
        {
            "passed": False,
            "reason": "validation_grade_d",
            "reasons": ["validation_grade_d", "validation_grade_d"],
            "warnings": ["foo", "foo"],
        }
    )

    assert normalized["reasons"] == ["validation_grade_d"]
    assert normalized["reason_codes"] == ["validation_grade_d"]
    assert normalized["warnings"] == ["foo"]
    assert normalized["warning_codes"] == ["foo"]


def test_build_quality_report_keeps_summary_fields():
    report = build_quality_report(
        strategy_id="s1",
        strategy_type="momentum",
        quality_gate={
            "passed": True,
            "admission_stage": "live",
            "incubation_pass_mode": "strict",
            "research_candidate_ready": True,
            "incubation_candidate_ready": True,
            "live_candidate_ready": True,
            "admission_block_reasons": [],
            "admission_evaluations": {
                "research": {"passed": True, "thresholds": {"sharpe_min": 0.2}},
                "incubation": {"passed": True, "thresholds": {"sharpe_min": 0.4}},
                "live": {"passed": True, "thresholds": {"sharpe_min": 0.8}},
            },
            "run_correction_mode": "bootstrap_family_proxy",
            "deflated_sharpe_proxy": 0.18,
            "pbo_proxy": 0.32,
            "reality_check_pvalue_proxy": 0.11,
            "spa_pvalue_proxy": 0.09,
            "multiple_testing_mode": "formal_runtime",
            "deflated_sharpe_ratio": 0.88,
            "pbo": 0.21,
            "white_reality_check_pvalue": 0.08,
            "hansen_spa_pvalue": 0.05,
            "multiple_testing": {
                "deflated_sharpe": {"dsr": 0.88},
                "pbo": {"pbo": 0.21},
            },
            "attempt_adjustment": {
                "attempt_count": 12,
                "selection_ratio": 0.16,
                "penalty": 0.03,
            },
            "profile": "event_trade_validation",
            "validation_focus": "event_target_only",
            "primary_validation_layer": "target_layer_metrics",
        },
        validation_report={"rating": {"grade": "B"}},
        risk_report={"var_percent": 1.2},
        dedup_report={"duplicate": False},
        backtest_metrics={
            "sharpe_ratio": 1.0,
            "position_assumption": "single_name_full_notional",
            "cost_assumptions": {
                "commission_bps": 8,
                "slippage_bps": 12,
                "market_ruleset": "cn_equity",
                "sell_tax_rate": 0.001,
                "min_trade_lot": 100,
                "t_plus_one": True,
                "arrival_price_policy": "next_open_proxy",
                "market_impact_bps": 4.5,
                "implementation_shortfall_proxy": 18.2,
            },
            "explicit_cost_breakdown": {"commission_cost": 120.0},
            "implicit_cost_breakdown": {"slippage_cost": 36.0},
            "tradability_summary": {"tradable_ratio": 0.92},
            "capacity_summary": {"adv_utilization": 1.4},
            "implementation_shortfall_model_source": "estimated",
            "implementation_shortfall_components": {"capacity_bps": 11.2},
            "event_window_config": {"lookback_days": 3, "forward_days": 5},
            "event_window_metrics": {"abnormal_return": 0.064, "car": 0.061, "bhar": 0.063, "hit_ratio": 0.75},
            "backtest_assumptions": {
                "slippage_bps": 8,
                "max_position_pct": 0.2,
                "target_weight_scheme": "equal_weight",
                "tradability_filter": True,
                "market_ruleset": "cn_equity",
                "sell_tax_rate": 0.001,
                "min_trade_lot": 100,
                "t_plus_one": True,
            },
            "constraint_check": {
                "intersection_ratio": 1.0,
                "constraint_violation": None,
                "expansion_applied": False,
            },
        },
        snapshot={"date": "2026-03-19"},
        status_after_review="incubating",
        review_source="factory",
        report_type="submission",
        spawn_reason="unit-test",
        submission_audit={
            "task_signature": "event_driven|evt_1|ai||event_target_only|600519",
            "refresh_mode": "refresh_metrics_only",
            "submission_lane": "live_ready_review",
            "direct_trade_candidate": True,
            "live_review_ready": True,
            "paper_account_id": "paper_001",
            "runtime_control_mode": "monitor",
            "runtime_control_status": "active",
            "promotion_review_id": "pr_001",
            "promotion_review_status": "watch",
            "promotion_review_recommendation": "observe",
            "task_preference": {
                "preferred_strategy_types": ["momentum"],
                "preference_strength": "medium",
                "preference_reason": "event_theme_bias:momentum",
                "override_applied": True,
            },
            "candidate_provenance": {
                "source_candidate_artifact_id": "candidate_001",
                "candidate_family": "sentiment",
                "validation_score": 83.5,
                "expected_regime": ["trend"],
            },
        },
    )

    assert report["passed"] is True
    assert report["summary"]["strategy_id"] == "s1"
    assert report["summary"]["validation_grade"] == "B"
    assert report["summary"]["spawn_reason"] == "unit-test"
    assert report["summary"]["admission_stage"] == "live"
    assert report["summary"]["live_candidate_ready"] is True
    assert report["summary"]["submission_lane"] == "live_ready_review"
    assert report["summary"]["direct_trade_candidate"] is True
    assert report["summary"]["live_review_ready"] is True
    assert report["summary"]["paper_account_id"] == "paper_001"
    assert report["summary"]["runtime_control_mode"] == "monitor"
    assert report["summary"]["promotion_review_status"] == "watch"
    assert report["summary"]["market_ruleset"] == "cn_equity"
    assert report["summary"]["target_weight_scheme"] == "equal_weight"
    assert report["task_signature"] == "event_driven|evt_1|ai||event_target_only|600519"
    assert report["refresh_mode"] == "refresh_metrics_only"
    assert report["backtest_assumptions"]["slippage_bps"] == 8
    assert report["validation_profile"]["profile"] == "event_trade_validation"
    assert report["validation_profile"]["validation_focus"] == "event_target_only"
    assert report["admission_stage"] == "live"
    assert report["incubation_pass_mode"] == "strict"
    assert report["research_candidate_ready"] is True
    assert report["incubation_candidate_ready"] is True
    assert report["live_candidate_ready"] is True
    assert report["submission_lane"] == "live_ready_review"
    assert report["direct_trade_candidate"] is True
    assert report["live_review_ready"] is True
    assert report["paper_account_id"] == "paper_001"
    assert report["runtime_control_status"] == "active"
    assert report["promotion_review_id"] == "pr_001"
    assert report["promotion_review_recommendation"] == "observe"
    assert report["admission_evaluations"]["live"]["passed"] is True
    assert report["position_assumption"] == "single_name_full_notional"
    assert report["cost_assumptions"]["commission_bps"] == 8
    assert report["cost_assumptions"]["market_ruleset"] == "cn_equity"
    assert report["explicit_cost_breakdown"]["commission_cost"] == 120.0
    assert report["implicit_cost_breakdown"]["slippage_cost"] == 36.0
    assert report["tradability_summary"]["tradable_ratio"] == 0.92
    assert report["capacity_summary"]["adv_utilization"] == 1.4
    assert report["implementation_shortfall_model_source"] == "estimated"
    assert report["implementation_shortfall_components"]["capacity_bps"] == 11.2
    assert report["event_window_metrics"]["car"] == 0.061
    assert report["constraint_check"]["intersection_ratio"] == 1.0
    assert report["execution_reality"]["market_ruleset"] == "cn_equity"
    assert report["execution_reality"]["sell_tax_rate"] == 0.001
    assert report["execution_reality"]["min_trade_lot"] == 100
    assert report["execution_reality"]["t_plus_one"] is True
    assert report["execution_reality"]["target_weight_scheme"] == "equal_weight"
    assert report["execution_reality"]["max_position_pct"] == 0.2
    assert report["attempt_adjustment"]["penalty"] == 0.03
    assert report["run_correction"]["mode"] == "bootstrap_family_proxy"
    assert report["run_correction"]["multiple_testing_mode"] == "formal_runtime"
    assert report["run_correction"]["deflated_sharpe_ratio"] == 0.88
    assert report["run_correction"]["pbo"] == 0.21
    assert report["run_correction"]["multiple_testing"]["pbo"]["pbo"] == 0.21
    assert report["task_preference"]["override_applied"] is True
    assert report["summary"]["source_candidate_artifact_id"] == "candidate_001"
    assert report["summary"]["candidate_family"] == "sentiment"
    assert report["candidate_provenance"]["validation_score"] == 83.5


def test_maybe_grant_provisional_incubation_allows_technical_fallback_for_degenerate_validation_stats():
    gate = maybe_grant_provisional_incubation(
        strategy={
            "strategy_type": "momentum",
            "tags": ["factory", "auto_generated", "ai_generated"],
        },
        quality_gate={
            "passed": False,
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": -0.0311,
            "param_sensitivity": 1.0293,
            "period_robustness": {"first_half_ic": 0.0, "second_half_ic": 0.0},
            "reasons": [
                "Walk-Forward IC IR 0.000 < 0.3",
                "Purged K-Fold IC 0.0000 < 0.02",
                "Bootstrap CI lower -0.0311 < 0.0",
                "Parameter sensitivity 102.93% > 30%",
            ],
        },
        validation_report={
            "rating": {
                "grade": "D",
                "total_score": 0.0,
                "scores": {
                    "oos_ic": 0.0,
                    "oos_ir": 0.0,
                    "stability": 0.0,
                    "ci_significance": 0.0,
                    "positive_ratio": 0.0,
                },
            },
            "walk_forward": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
            "purged_kfold": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
            "bootstrap_ci": {"sample_size": 0, "ci_lower": 0.0, "ci_upper": 0.0},
        },
        risk_report={"var_percent": 1.1201, "cvar_percent": 1.5402, "stress_loss_percent": -20.0},
        backtest_metrics={"sharpe_ratio": 0.6456, "max_drawdown": 0.1146, "trades_count": 18},
    )

    assert gate["passed"] is True
    assert gate["passed_strict"] is False
    assert gate["provisional_pass"] is True
    assert "validation_report_degenerate" in gate["warning_codes"]
    assert "provisional_path_technical_validation_fallback" in gate["warning_codes"]
    assert gate["statistical_checks_passed"] == 1


def test_maybe_grant_provisional_incubation_allows_factory_technical_strategy_without_ai_tags():
    gate = maybe_grant_provisional_incubation(
        strategy={
            "strategy_type": "rsi",
            "tags": ["factory", "auto_generated", "rsi"],
        },
        quality_gate={
            "passed": False,
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": -0.0311,
            "param_sensitivity": 0.28,
            "period_robustness": {"first_half_ic": 0.0, "second_half_ic": 0.0},
            "reasons": [
                "Walk-Forward IC IR 0.000 < 0.3",
                "Purged K-Fold IC 0.0000 < 0.02",
                "Bootstrap CI lower -0.0311 < 0.0",
            ],
        },
        validation_report={
            "rating": {
                "grade": "D",
                "total_score": 0.0,
                "scores": {
                    "oos_ic": 0.0,
                    "oos_ir": 0.0,
                    "stability": 0.0,
                    "ci_significance": 0.0,
                    "positive_ratio": 0.0,
                },
            },
            "walk_forward": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
            "purged_kfold": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
            "bootstrap_ci": {"sample_size": 0, "ci_lower": 0.0, "ci_upper": 0.0},
        },
        risk_report={"var_percent": 1.1201, "cvar_percent": 1.5402, "stress_loss_percent": -20.0},
        backtest_metrics={"sharpe_ratio": 0.22, "max_drawdown": 0.1146, "trades_count": 16},
    )

    assert gate["passed"] is True
    assert gate["provisional_pass"] is True
    assert "validation_grade_d" in gate["warning_codes"]
    assert gate["statistical_checks_passed"] >= 2


def test_maybe_grant_provisional_incubation_rejects_when_validation_stats_are_not_degenerate():
    gate = maybe_grant_provisional_incubation(
        strategy={
            "strategy_type": "momentum",
            "tags": ["factory", "auto_generated", "ai_generated"],
        },
        quality_gate={
            "passed": False,
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": -0.0311,
            "param_sensitivity": 1.0293,
            "period_robustness": {"first_half_ic": 0.0, "second_half_ic": 0.0},
            "reasons": [
                "Walk-Forward IC IR 0.000 < 0.3",
                "Purged K-Fold IC 0.0000 < 0.02",
                "Bootstrap CI lower -0.0311 < 0.0",
                "Parameter sensitivity 102.93% > 30%",
            ],
        },
        validation_report={
            "rating": {
                "grade": "D",
                "total_score": 18.0,
                "scores": {
                    "oos_ic": 5.0,
                    "oos_ir": 3.0,
                    "stability": 4.0,
                    "ci_significance": 0.0,
                    "positive_ratio": 6.0,
                },
            },
            "walk_forward": {"n_folds": 4, "oos_rank_ic_mean": 0.01, "oos_rank_ic_ir": 0.10},
            "purged_kfold": {"n_folds": 5, "oos_rank_ic_mean": 0.02, "oos_rank_ic_ir": 0.12},
            "bootstrap_ci": {"sample_size": 28, "ci_lower": -0.01, "ci_upper": 0.03},
        },
        risk_report={"var_percent": 1.1201, "cvar_percent": 1.5402, "stress_loss_percent": -20.0},
        backtest_metrics={"sharpe_ratio": 0.6456, "max_drawdown": 0.1146, "trades_count": 18},
    )

    assert gate["passed"] is False
    assert gate.get("provisional_pass") is not True

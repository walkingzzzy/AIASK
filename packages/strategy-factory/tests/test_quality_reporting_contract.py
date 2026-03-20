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
        quality_gate={"passed": True},
        validation_report={"rating": {"grade": "B"}},
        risk_report={"var_percent": 1.2},
        dedup_report={"duplicate": False},
        backtest_metrics={"sharpe_ratio": 1.0},
        snapshot={"date": "2026-03-19"},
        status_after_review="incubating",
        review_source="factory",
        report_type="submission",
        spawn_reason="unit-test",
    )

    assert report["passed"] is True
    assert report["summary"]["strategy_id"] == "s1"
    assert report["summary"]["validation_grade"] == "B"
    assert report["summary"]["spawn_reason"] == "unit-test"


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

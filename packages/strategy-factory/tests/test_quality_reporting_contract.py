from strategy_factory.application.quality_reporting import (
    build_quality_report,
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

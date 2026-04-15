import pytest

from strategy_factory.application.market_evidence import (
    build_market_fact_gate_audit,
    normalize_market_evidence_fact,
    summarize_market_fact_gate,
)
from strategy_factory.application.quality_reporting import build_quality_report


def test_normalize_market_evidence_fact_marks_same_day_close_as_hard_fact():
    fact = normalize_market_evidence_fact(
        {
            "metric": "close",
            "trade_date": "2026-04-14",
            "source_as_of_date": "2026-04-14",
            "window_scope": "same_day",
            "unit": "cny",
        }
    )

    assert fact["hard_fact_eligible"] is True
    assert fact["same_day_pass"] is True
    assert fact["unit_pass"] is True
    assert fact["downgrade_reason"] is None


def test_normalize_market_evidence_fact_degrades_non_same_day_flow_metric():
    fact = normalize_market_evidence_fact(
        {
            "metric": "5d_fund_flow",
            "trade_date": "2026-04-14",
            "source_as_of_date": "2026-04-11",
            "window_scope": "5d",
            "unit": "cny",
        }
    )

    assert fact["hard_fact_eligible"] is False
    assert fact["same_day_pass"] is False
    assert fact["downgrade_reason"] == "non_same_day_source"


@pytest.mark.parametrize("metric", ["volume_ratio", "main_fund_flow"])
def test_normalize_market_evidence_fact_keeps_same_day_proxy_metrics_out_of_hard_facts(metric):
    fact = normalize_market_evidence_fact(
        {
            "metric": metric,
            "trade_date": "2026-04-14",
            "source_as_of_date": "2026-04-14",
            "window_scope": "same_day",
            "unit": "ratio" if metric == "volume_ratio" else "cny",
        }
    )

    assert fact["hard_fact_eligible"] is False
    assert fact["same_day_pass"] is True
    assert fact["downgrade_reason"] == "unsupported_metric_for_hard_fact"


def test_summarize_market_fact_gate_counts_hard_and_degraded_facts():
    summary = summarize_market_fact_gate(
        [
            {
                "metric": "close",
                "trade_date": "2026-04-14",
                "source_as_of_date": "2026-04-14",
                "window_scope": "same_day",
                "unit": "cny",
            },
            {
                "metric": "volume_ratio",
                "trade_date": "2026-04-14",
                "source_as_of_date": "2026-04-14",
                "window_scope": "same_day",
                "unit": "ratio",
            },
            {
                "metric": "5d_fund_flow",
                "trade_date": "2026-04-14",
                "source_as_of_date": "2026-04-11",
                "window_scope": "5d",
                "unit": "cny",
            },
        ]
    )

    assert summary["market_fact_gate_status"] == "mixed_with_degraded"
    assert summary["hard_fact_count"] == 1
    assert summary["degraded_fact_count"] == 2
    assert summary["evidence_debt_reasons"] == [
        "unsupported_metric_for_hard_fact",
        "non_same_day_source",
    ]
    assert build_market_fact_gate_audit(summary["market_facts"]) == {
        "market_fact_gate_status": "mixed_with_degraded",
        "hard_fact_count": 1,
        "degraded_fact_count": 2,
        "evidence_debt_reasons": [
            "unsupported_metric_for_hard_fact",
            "non_same_day_source",
        ],
    }


def test_build_quality_report_marks_non_same_day_market_fact_as_degraded_evidence():
    report = build_quality_report(
        strategy_id="s_market_gate",
        strategy_type="ma_cross",
        quality_gate={"passed": True, "validation_grade": "B"},
        validation_report={"rating": {"grade": "B", "total_score": 0.61}},
        risk_report={},
        dedup_report={},
        backtest_metrics={"backtest_assumptions": {"stop_loss_mode": "atr_bucketed"}},
        snapshot={},
        status_after_review="reviewed",
        review_source="test",
        report_type="submission",
        submission_audit={
            "candidate_provenance": {
                "pool_profile": "high_vol_growth",
                "volatility_bucket": "high",
                "liquidity_bucket": "high_liquidity",
                "regime_fit": "trend_expansion",
            },
            "evidence_chain": {
                "market_facts": [
                    {
                        "metric": "close",
                        "trade_date": "2026-04-14",
                        "source_as_of_date": "2026-04-14",
                        "window_scope": "same_day",
                        "unit": "cny",
                    },
                    {
                        "metric": "5d_fund_flow",
                        "trade_date": "2026-04-14",
                        "source_as_of_date": "2026-04-11",
                        "window_scope": "5d",
                        "unit": "cny",
                    },
                ]
            },
        },
    )

    assert report["summary"]["evidence_gate_status"] == "mixed_with_degraded"
    assert report["summary"]["hard_fact_count"] == 1
    assert report["summary"]["degraded_fact_count"] == 1
    assert "non_same_day_source" in report["summary"]["evidence_debt_reasons"]
    assert report["summary"]["stop_rule_source"] == "atr_bucketed"
    assert report["evidence_alignment_audit"]["market_fact_gate_status"] == "mixed_with_degraded"
    assert report["evidence_chain"]["market_facts"][0]["hard_fact_eligible"] is True
    assert report["evidence_chain"]["market_facts"][1]["hard_fact_eligible"] is False

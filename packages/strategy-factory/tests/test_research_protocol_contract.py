from strategy_factory.application.research_protocol_contract import (
    adapt_research_validation_contract_for_submission,
    build_field_provenance_summary,
    build_research_validation_contract,
    evaluate_research_validation_contract_admission,
)


def test_research_protocol_contract_maps_legacy_default_to_missing():
    summary = build_field_provenance_summary(
        {
            "walk_forward_config": "legacy_default",
            "baseline_reference": "provided",
        }
    )

    assert summary["counts"]["missing"] == 1
    assert "legacy_default" not in summary["counts"]
    assert summary["fields"]["walk_forward_config"] == "missing"
    assert summary["missing_required_fields"] == ["walk_forward_config", "cash_sleeve_policy", "cost_sensitivity_grid", "capacity_execution", "multiple_testing", "admission_thresholds", "family_holding_bucket"]


def test_research_protocol_contract_separates_effective_contract_from_recommended_defaults():
    contract = build_research_validation_contract(
        baseline_reference={"benchmark": "510300"},
        field_provenance={
            "walk_forward_config": "legacy_default",
            "baseline_reference": "provided",
        },
        recommended_defaults={
            "walk_forward_config": {"train_months": 60, "test_months": 12},
        },
        hard_failures=[
            {
                "reason_code": "semantic_contract_missing:confidence_contract",
                "issue": "semantic_contract_missing_field",
                "field": "confidence_contract",
            }
        ],
    )

    assert contract["effective_contract"] == {"baseline_reference": {"benchmark": "510300"}}
    assert contract["recommended_defaults"] == {
        "walk_forward_config": {"train_months": 60, "test_months": 12}
    }
    assert contract["spec_completeness"] == "incomplete"
    assert any(issue["decision"] == "revise" for issue in contract["completion_issues"])
    assert any(issue["decision"] == "reject" for issue in contract["completion_issues"])
    adapted = adapt_research_validation_contract_for_submission(
        {
            **contract,
            "field_provenance": {"walk_forward_config": "legacy_default"},
        }
    )
    assert adapted["effective_contract"] == {"baseline_reference": {"benchmark": "510300"}}
    assert adapted["recommended_defaults"]["walk_forward_config"]["train_months"] == 60
    assert adapted["hard_failures"][0]["reason_code"] == "semantic_contract_missing:confidence_contract"


def test_research_protocol_submission_adapter_and_admission_evaluator_cover_gate_b_fields():
    contract = build_research_validation_contract(
        baseline_reference={"name": "510300", "benchmark_oos_cagr": 0.04, "benchmark_oos_max_drawdown": 0.12},
        cash_sleeve_policy={"enabled": True, "schedule_clock": "monthly"},
        cost_sensitivity_grid={"slippage_bps_grid": [0, 5, 10]},
        admission_thresholds={
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
                "primary_validation_layer": "target",
            },
            "business_admission_gate": {
                "benchmark_return_multiple_min": 2.0,
                "benchmark_drawdown_mode": "lte",
                "cost_sensitivity_required_bps": [0, 5, 10],
            },
        },
        family_holding_bucket={"family": "510300_default", "holding_bucket": "medium"},
        field_provenance={
            "walk_forward_config": "derived",
            "baseline_reference": "derived",
            "cash_sleeve_policy": "derived",
            "cost_sensitivity_grid": "derived",
            "capacity_execution": "derived",
            "multiple_testing": "derived",
            "admission_thresholds": "derived",
            "family_holding_bucket": "derived",
        },
    )

    adapted = adapt_research_validation_contract_for_submission(contract)

    assert adapted["cash_sleeve_policy"]["enabled"] is True
    assert adapted["cost_sensitivity_grid"]["slippage_bps_grid"] == [0, 5, 10]

    evaluation = evaluate_research_validation_contract_admission(
        adapted,
        observed={
            "oos_cagr": 0.06,
            "benchmark_oos_cagr": 0.04,
            "oos_max_drawdown": 0.15,
            "benchmark_oos_max_drawdown": 0.12,
            "cost_sensitivity_results": {
                "0": {"slippage_bps": 0, "post_cost_sharpe": 1.12},
                "5": {"slippage_bps": 5, "post_cost_sharpe": 0.92},
                "10": {"slippage_bps": 10, "post_cost_sharpe": 0.71},
            },
            "cash_sleeve": {"enabled": True, "schedule_clock": "monthly"},
            "family": "510300_default",
            "holding_bucket": "medium",
        },
    )

    assert evaluation["review_decision"] == "reject"
    assert evaluation["benchmark_comparison"]["passed"] is False
    assert evaluation["cost_sensitivity_summary"]["observed_bps"] == [0.0, 5.0, 10.0]
    assert evaluation["cash_sleeve_audit"]["passed"] is True

"""Smoke tests for StrategySubmitter import and basic structure."""

from __future__ import annotations

import asyncio


def test_submitter_import():
    from strategy_factory.application.submitter import StrategySubmitter

    submitter = StrategySubmitter()
    assert submitter is not None
    assert hasattr(submitter, "submit")


def test_submitter_mro_chain():
    """Verify the mixin chain is correctly assembled."""
    from strategy_factory.application.submitter import StrategySubmitter

    mro_names = [c.__name__ for c in StrategySubmitter.__mro__]
    assert "_StrategySubmitterHelpersMixin" in mro_names
    assert "_StrategySubmitterPolicyMixin" in mro_names
    assert "_StrategySubmitterActionsMixin" in mro_names


def test_submission_quality_gate_importable():
    from strategy_factory.application.submission_gate import run_submission_quality_gate

    assert callable(run_submission_quality_gate)


def test_candidate_semantic_contract_backfill_is_complete():
    from strategy_factory.application.semantic_contract import (
        audit_candidate_semantic_contract,
        ensure_candidate_semantic_contract,
    )

    candidate = ensure_candidate_semantic_contract(
        {
            "strategy_type": "value_factor",
            "name": "value rotation",
            "params": {"lookback": 20},
            "target_symbols": ["600000"],
            "holding_horizon": {"max_days": 20},
            "risk_rules": {"max_holding_days": 20},
        }
    )

    assert candidate["evidence_chain"]["evidences"]
    assert candidate["prediction_contract"]["claims"]
    assert candidate["confidence_contract"]["prediction_quality"]
    assert candidate["claim_to_trade_plan_map"]["mapped_claim_count"] == 2
    audit = audit_candidate_semantic_contract(candidate)
    assert audit["using_new_contract"] is True
    assert audit["hard_fail_reasons"] == []


def test_candidate_semantic_contract_backfills_trade_plan_claim_ids_from_real_claims():
    from strategy_factory.application.semantic_contract import (
        audit_candidate_semantic_contract,
        ensure_candidate_semantic_contract,
    )

    candidate = ensure_candidate_semantic_contract(
        {
            "strategy_type": "momentum",
            "name": "real claim candidate",
            "target_symbols": ["600000"],
            "holding_horizon": {"max_days": 10},
            "trade_plan": {
                "entry": {"node_id": "entry_real", "summary": "enter on signal"},
                "exit": {"node_id": "exit_real", "summary": "exit on invalidation"},
            },
            "evidence_chain": {
                "evidences": [
                    {"evidence_id": "ev_up", "source_type": "technical", "direction": "up"},
                    {"evidence_id": "ev_exit", "source_type": "risk_contract", "direction": "down"},
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "momentum_claim_entry",
                        "claim_type": "entry",
                        "expected_move": "up",
                        "evidence_ids": ["ev_up"],
                    },
                    {
                        "claim_id": "momentum_claim_exit",
                        "claim_type": "exit",
                        "expected_move": "down",
                        "evidence_ids": ["ev_exit"],
                    },
                ]
            },
        }
    )

    assert candidate["trade_plan"]["entry"]["claim_ids"] == ["momentum_claim_entry"]
    assert candidate["trade_plan"]["entry"]["evidence_ids"] == ["ev_up"]
    assert candidate["trade_plan"]["exit"]["claim_ids"] == ["momentum_claim_exit"]
    assert candidate["trade_plan"]["exit"]["evidence_ids"] == ["ev_exit"]
    assert candidate["claim_to_trade_plan_map"]["trade_step_to_claim_ids"]["entry_real"] == [
        "momentum_claim_entry"
    ]
    assert candidate["claim_to_trade_plan_map"]["trade_step_to_claim_ids"]["exit_real"] == [
        "momentum_claim_exit"
    ]

    audit = audit_candidate_semantic_contract(candidate)
    assert "trade_plan_node_missing_claim_ids" not in audit["hard_fail_reasons"]
    assert audit["trade_plan_missing_claim_ids"] == 0


def test_candidate_semantic_contract_preserves_invalid_explicit_claim_ids_as_hard_fail():
    from strategy_factory.application.semantic_contract import (
        audit_candidate_semantic_contract,
        ensure_candidate_semantic_contract,
    )

    candidate = ensure_candidate_semantic_contract(
        {
            "strategy_type": "momentum",
            "name": "bad explicit claim candidate",
            "target_symbols": ["600000"],
            "trade_plan": {
                "entry": {
                    "node_id": "entry_bad",
                    "claim_ids": ["not_a_real_claim"],
                }
            },
            "evidence_chain": {
                "evidences": [
                    {"evidence_id": "ev_up", "source_type": "technical", "direction": "up"},
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "momentum_claim_entry",
                        "claim_type": "entry",
                        "expected_move": "up",
                        "evidence_ids": ["ev_up"],
                    }
                ]
            },
        }
    )

    assert candidate["trade_plan"]["entry"]["claim_ids"] == ["not_a_real_claim"]
    audit = audit_candidate_semantic_contract(candidate)
    assert "trade_plan_node_missing_claim_ids" in audit["hard_fail_reasons"]


def test_submitter_reports_factor_pool_performance():
    from strategy_factory.application.submitter import StrategySubmitter

    class FactorPoolGateway:
        def __init__(self):
            self.calls = []

        async def report_factor_performance(self, factor_id, strategy_id, metrics):
            self.calls.append((factor_id, strategy_id, dict(metrics)))

    gateway = FactorPoolGateway()
    submitter = StrategySubmitter(factor_pool_gateway=gateway)

    result = asyncio.run(
        submitter._report_factor_performance_after_submit(
            candidate={"params": {"factor_pool_factor_id": "factor-1"}},
            strategy_id="strategy-1",
            metrics={"ic_mean": 0.07, "turnover_rate": 0.2},
            validation_report=None,
            gate={"passed": True},
            read_only=False,
        )
    )

    assert result["reported"] is True
    assert gateway.calls == [
        (
            "factor-1",
            "strategy-1",
            {
                "realized_ic": 0.07,
                "realized_turnover": 0.2,
                "realized_cost": 0.0,
                "period": "submission",
            },
        )
    ]

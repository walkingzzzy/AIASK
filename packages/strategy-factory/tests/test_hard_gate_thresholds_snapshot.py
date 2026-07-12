"""Hard-gate contract ownership + threshold snapshot (P1-B S2).

Must not change production semantics without an explicit gate-change RFC:
- production_trade_floor default == 20
- trade_expectancy > 0
- pnl_conversion_efficiency > 0
- execution_conversion_efficiency >= 0.20
"""

from __future__ import annotations

import pytest

from strategy_factory.api import contracts as api_contracts
from strategy_factory.contracts.hard_gate import (
    EXECUTION_CONVERSION_EFFICIENCY_MIN,
    HARD_GATE_STATUSES,
    PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE,
    PRODUCTION_TRADE_FLOOR_DEFAULT,
    TRADE_EXPECTANCY_MIN_EXCLUSIVE,
    evaluate_execution_audit_gate,
)
from strategy_factory.contracts.promotion_ready import (
    PROMOTION_COVERAGE_RATIO_MIN,
    PROMOTION_PRIMARY_EFFECTIVE_N_MIN,
    PROMOTION_SECONDARY_EFFECTIVE_N_MIN,
    PROMOTION_STABILITY_GAP_MAX,
    evaluate_promotion_ready,
)
from strategy_factory.contracts.evidence_gaps import (
    evaluate_evidence_gap_summary,
    evaluate_signal_id_coverage,
)


def test_hard_gate_owned_by_strategy_factory_contracts() -> None:
    assert evaluate_execution_audit_gate.__module__ == "strategy_factory.contracts.hard_gate"
    assert api_contracts.evaluate_execution_audit_gate is evaluate_execution_audit_gate


def test_threshold_snapshot_locked() -> None:
    assert PRODUCTION_TRADE_FLOOR_DEFAULT == 20
    assert TRADE_EXPECTANCY_MIN_EXCLUSIVE == 0.0
    assert PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE == 0.0
    assert EXECUTION_CONVERSION_EFFICIENCY_MIN == 0.20
    assert PROMOTION_PRIMARY_EFFECTIVE_N_MIN == 60
    assert PROMOTION_SECONDARY_EFFECTIVE_N_MIN == 30
    assert PROMOTION_COVERAGE_RATIO_MIN == 0.75
    assert PROMOTION_STABILITY_GAP_MAX == 0.05
    assert "passed" in HARD_GATE_STATUSES
    assert "failed_metrics" in HARD_GATE_STATUSES


def _passed_audit(**overrides):
    base = {
        "realized_trade_count": 28,
        "mapped_position_count": 28,
        "order_count": 40,
        "filled_order_count": 36,
        "trade_count": 32,
        "nav_observation_days": 18,
        "trade_expectancy": 0.03,
        "pnl_conversion_efficiency": 0.18,
        "execution_conversion_efficiency": 0.42,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "audit,expected_status",
    [
        (None, "missing"),
        ({}, "missing"),
        (
            {
                "account_id": "acct-1",
                "realized_trade_count": 0,
                "order_count": 2,
            },
            "bootstrap_pending",
        ),
        (
            {
                "realized_trade_count": 1,
                "trade_expectancy": 0.1,
                "pnl_conversion_efficiency": 0.1,
                "execution_conversion_efficiency": 0.5,
            },
            "insufficient_samples",
        ),
        (
            _passed_audit(
                realized_trade_count=5,
                trade_expectancy=-0.01,
            ),
            "failed_metrics",
        ),
        (
            _passed_audit(
                realized_trade_count=10,
                trade_expectancy=0.02,
                pnl_conversion_efficiency=0.1,
                execution_conversion_efficiency=0.5,
            ),
            "bootstrap_ready",
        ),
        (_passed_audit(), "passed"),
    ],
)
def test_execution_audit_gate_status_matrix(audit, expected_status) -> None:
    status, reasons, passes, metrics = evaluate_execution_audit_gate(audit)
    assert status == expected_status
    assert metrics["required_trade_count"] == 20
    if expected_status == "passed":
        assert reasons == []
        assert passes["realized_trade_count"] is True
        assert passes["trade_expectancy"] is True
        assert passes["pnl_conversion_efficiency"] is True
        assert passes["execution_conversion_efficiency"] is True
    if expected_status == "failed_metrics":
        assert "trade_expectancy<=0" in reasons


def test_execution_conversion_floor_is_point_two() -> None:
    status, reasons, passes, _metrics = evaluate_execution_audit_gate(
        _passed_audit(execution_conversion_efficiency=0.1999)
    )
    assert status == "failed_metrics"
    assert passes["execution_conversion_efficiency"] is False
    assert "execution_conversion_efficiency<0.20" in reasons


def test_promotion_ready_pure_floors() -> None:
    ready = evaluate_promotion_ready(
        primary_effective_n=72,
        secondary_effective_n=36,
        primary_skill_lcb=0.04,
        secondary_skill_lcb=0.02,
        recent_primary_skill_lcb=0.01,
        coverage_ratio=0.85,
        stability_gap=0.03,
        execution_hard_gate_passed=True,
        risk_hard_gate_status="passed",
        blockers=[],
    )
    assert ready["promotion_ready"] is True
    assert ready["failed_checks"] == []

    blocked = evaluate_promotion_ready(
        primary_effective_n=10,
        secondary_effective_n=36,
        primary_skill_lcb=0.04,
        secondary_skill_lcb=0.02,
        recent_primary_skill_lcb=0.01,
        coverage_ratio=0.85,
        stability_gap=0.03,
        execution_hard_gate_passed=True,
        risk_hard_gate_status="passed",
        blockers=[],
    )
    assert blocked["promotion_ready"] is False
    assert "primary_effective_n" in blocked["failed_checks"]


def test_promotion_ready_cross_regime_opt_in() -> None:
    base_kwargs = dict(
        primary_effective_n=72,
        secondary_effective_n=36,
        primary_skill_lcb=0.04,
        secondary_skill_lcb=0.02,
        recent_primary_skill_lcb=0.01,
        coverage_ratio=0.85,
        stability_gap=0.03,
        execution_hard_gate_passed=True,
        risk_hard_gate_status="passed",
        blockers=[],
    )
    off = evaluate_promotion_ready(**base_kwargs, cross_regime_enabled=False, cross_regime_passed=False)
    assert off["promotion_ready"] is True
    on = evaluate_promotion_ready(
        **base_kwargs,
        cross_regime_enabled=True,
        cross_regime_passed=False,
        cross_regime_negative_labels=["bull"],
    )
    assert on["promotion_ready"] is False
    assert any(item.startswith("cross_regime_skill_lcb_non_positive:") for item in on["blockers"])


def test_promotion_ready_fails_closed_when_stability_gap_is_missing() -> None:
    result = evaluate_promotion_ready(
        primary_effective_n=72,
        secondary_effective_n=36,
        primary_skill_lcb=0.04,
        secondary_skill_lcb=0.02,
        recent_primary_skill_lcb=0.01,
        coverage_ratio=0.85,
        stability_gap=None,
        execution_hard_gate_passed=True,
        risk_hard_gate_status="passed",
        blockers=[],
    )

    assert result["promotion_ready"] is False
    assert result["checks"]["stability_gap"] is False
    assert "stability_gap" in result["failed_checks"]
    assert "stability_gap_missing" in result["blockers"]


def test_evidence_gap_helpers() -> None:
    cov = evaluate_signal_id_coverage(order_count=10, orders_with_signal_id=10)
    assert cov["signal_id_coverage"] == 1.0
    assert cov["gaps"] == []
    incomplete = evaluate_evidence_gap_summary(
        order_count=10,
        orders_with_signal_id=8,
        trade_count=5,
        trades_with_position_link=4,
        hard_gate_status="failed_metrics",
    )
    assert "signal_id_coverage_below_required" in incomplete["gaps"]
    assert incomplete["evidence_complete"] is False

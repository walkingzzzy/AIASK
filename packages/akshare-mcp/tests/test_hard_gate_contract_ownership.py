"""P1-B S2: host re-export must match Strategy Factory hard-gate ownership."""

from __future__ import annotations

from akshare_mcp.services.strategy_lifecycle_shared.confidence import (
    EVALUATE_EXECUTION_AUDIT_GATE_OWNER,
    evaluate_execution_audit_gate as host_gate,
)
from strategy_factory.contracts.hard_gate import (
    evaluate_execution_audit_gate as sf_gate,
)


def test_host_gate_is_strategy_factory_contract() -> None:
    assert host_gate is sf_gate
    assert host_gate.__module__ == "strategy_factory.contracts.hard_gate"
    assert EVALUATE_EXECUTION_AUDIT_GATE_OWNER == "strategy_factory.contracts.hard_gate"


def test_host_and_sf_gate_same_verdict_on_fixture() -> None:
    fixture = {
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
    assert host_gate(fixture) == sf_gate(fixture)

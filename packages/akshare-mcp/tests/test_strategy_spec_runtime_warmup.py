from __future__ import annotations

from akshare_mcp.services.strategy_spec.runtime_contracts import (
    _build_parameter_coherence_audit,
    _default_runtime_playbook,
)


def test_default_runtime_playbook_uses_density_aware_warmup() -> None:
    playbook = _default_runtime_playbook(
        "value_factor",
        holding_horizon={"min_days": 30, "max_days": 84, "cooldown_window_days": 7},
        backtest_metrics={"trade_count": 4},
    )
    incubation_policy = playbook["incubation_policy"]

    assert 4 <= incubation_policy["warmup_target_signals"] <= 8
    assert incubation_policy["warmup_target_signals"] != 20

    audit = _build_parameter_coherence_audit(
        "value_factor",
        holding_horizon={"min_days": 30, "max_days": 84},
        rebalance_rule={},
        runtime_playbook=playbook,
        instrument_profile={},
        backtest_metrics={"trade_count": 4},
    )

    assert "warmup_target_exceeds_signal_density" not in audit["blockers"]
    assert "warmup_target_exceeds_signal_density" not in audit["warnings"]

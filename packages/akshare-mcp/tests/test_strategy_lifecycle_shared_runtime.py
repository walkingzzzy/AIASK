from __future__ import annotations

import asyncio

from akshare_mcp.services.strategy_lifecycle_shared.confidence import evaluate_execution_audit_gate
from akshare_mcp.services.strategy_lifecycle_shared.incubation import resolve_incubation_pipeline_stage
from akshare_mcp.services.strategy_lifecycle_shared.overview import _resolve_risk_hard_gate
from akshare_mcp.services.strategy_lifecycle_shared.prediction_trace import _build_execution_lineage


class _SignalEvidenceDb:
    async def list_strategy_signal_evidence(self, strategy_id: str, limit: int = 500):
        assert strategy_id == "strategy-runtime"
        assert limit >= 2
        return [
            {
                "signal_id": "sig-1",
                "signal_date": "2026-04-15",
                "signal_ts": "2026-04-15T10:00:00+00:00",
                "created_at": "2026-04-15T10:00:01+00:00",
                "applied_claim_id": "claim-a",
                "applied_trade_step_id": "trade-step-1",
                "runtime_action_reason": "reduce_risk",
                "runtime_action_source": "runtime_control",
            },
            {
                "signal_id": "sig-2",
                "signal_date": "2026-04-16",
                "signal_ts": "2026-04-16T10:00:00+00:00",
                "created_at": "2026-04-16T10:00:01+00:00",
                "applied_claim_id": "claim-a",
                "runtime_action_reason": "freeze_reentry",
                "runtime_action_source": "risk_event",
            },
        ]


def test_execution_audit_gate_drives_incubation_stage_without_name_errors():
    audit_summary = {
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
    status, reasons, passes, metrics = evaluate_execution_audit_gate(audit_summary)
    assert status == "passed"
    assert reasons == []
    assert passes["realized_trade_count"] is True
    assert metrics["realized_trade_count"] == 28

    stage = resolve_incubation_pipeline_stage(
        {
            "primary_effective_n": 72,
            "secondary_effective_n": 36,
            "primary_skill_lcb": 0.04,
            "secondary_skill_lcb": 0.02,
            "recent_primary_skill_lcb": 0.01,
            "coverage_ratio": 0.85,
            "stability_gap": 0.03,
        },
        audit_summary=audit_summary,
    )
    assert stage == "graduation_ready"


def test_execution_audit_gate_supports_bootstrap_ready_family_thresholds():
    audit_summary = {
        "strategy_type": "margin_divergence",
        "realized_trade_count": 5,
        "mapped_position_count": 5,
        "order_count": 8,
        "filled_order_count": 8,
        "trade_count": 8,
        "nav_observation_days": 12,
        "trade_expectancy": 0.03,
        "pnl_conversion_efficiency": 0.02,
        "execution_conversion_efficiency": 1.0,
    }
    status, reasons, passes, metrics = evaluate_execution_audit_gate(audit_summary)

    assert status == "bootstrap_ready"
    assert reasons == ["realized_trade_count<20"]
    assert passes["bootstrap_trade_count"] is True
    assert passes["realized_trade_count"] is False
    assert metrics["bootstrap_trade_floor"] == 3
    assert metrics["required_trade_count"] == 20


def test_prediction_trace_execution_lineage_uses_runtime_helpers():
    lineage = asyncio.run(_build_execution_lineage(_SignalEvidenceDb(), "strategy-runtime"))

    assert lineage["signal_evidence_count"] == 2
    assert lineage["runtime_action_count"] == 2
    assert lineage["unmapped_runtime_action_count"] == 1
    assert lineage["recent_signal_ids"] == ["sig-2", "sig-1"]
    assert lineage["runtime_action_reason_counts"] == {
        "freeze_reentry": 1,
        "reduce_risk": 1,
    }


def test_overview_risk_gate_helper_resolves_contracts_without_name_errors():
    result = _resolve_risk_hard_gate(
        {
            "drawdown_invalidation_contract": {
                "apply_as_hard_gate": True,
                "review_drawdown_pct": 0.05,
                "kill_drawdown_pct": 0.07,
            },
            "parameter_coherence_audit": {
                "blockers": ["missing_stop_loss_mapping"],
            },
        },
        max_drawdown=0.08,
    )

    assert result["status"] == "kill_switch"
    assert "parameter_coherence:missing_stop_loss_mapping" in result["reasons"]
    assert "max_drawdown>=7%" in result["reasons"]

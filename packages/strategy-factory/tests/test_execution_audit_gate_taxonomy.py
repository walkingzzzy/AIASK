from __future__ import annotations

from strategy_factory.application.governance_plane_contract import build_gate_c_artifact


def test_governance_gate_c_artifact_marks_bootstrap_ready_as_evidence_gap():
    artifact = build_gate_c_artifact(
        submit_result={
            "strategies": [
                {
                    "strategy_id": "strategy-gap",
                    "execution_audit_gate_status": "bootstrap_ready",
                    "gate_blockers": [],
                    "evidence_gap_codes": [],
                }
            ]
        }
    )

    assert "execution_audit_gate:bootstrap_ready" in artifact["evidence_gap_codes"]

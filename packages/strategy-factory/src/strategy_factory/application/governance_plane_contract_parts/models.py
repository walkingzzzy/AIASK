

def build_governance_plane_artifact(
    *,
    candidates: list[dict[str, Any]] | None = None,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    dedup_report: dict[str, Any] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_artifact = build_gate_artifact(
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
    )
    dedup_artifact = build_dedup_artifact(
        dedup_report=dedup_report,
    )
    submission_artifact = build_submission_artifact(
        submit_result=submit_result,
    )
    evidence_artifact = build_governance_evidence_artifact(
        submit_result=submit_result,
    )
    gate_artifact_v2 = build_gate_artifact_v2(
        candidates=candidates,
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
        submit_result=submit_result,
    )
    available = any(
        bool(item.get("available"))
        for item in (
            gate_artifact,
            dedup_artifact,
            submission_artifact,
            evidence_artifact,
            gate_artifact_v2,
        )
    )
    source_chain: list[str] = []
    if gate_artifact.get("available"):
        source_chain.append("governance.gate_artifact")
    if dedup_artifact.get("available"):
        source_chain.append("governance.dedup_artifact")
    if submission_artifact.get("available"):
        source_chain.append("governance.submission_artifact")
    if evidence_artifact.get("available"):
        source_chain.append("governance.evidence_artifact")
    if gate_artifact_v2.get("available"):
        source_chain.append("governance.gate_artifact_v2")
    governance_plane_v2 = {
        "contract_version": GOVERNANCE_PLANE_V2_CONTRACT_VERSION,
        "available": bool(gate_artifact_v2.get("available")),
        "plane": "governance_v2",
        "gate_artifact_v2": gate_artifact_v2,
        "gate_a": dict(gate_artifact_v2.get("gate_a") or {}),
        "gate_b": dict(gate_artifact_v2.get("gate_b") or {}),
        "gate_c": dict(gate_artifact_v2.get("gate_c") or {}),
        "legacy_gate_mapping": dict(gate_artifact_v2.get("legacy_gate_mapping") or {}),
        "protocol_versions": dict(gate_artifact_v2.get("protocol_versions") or {}),
        "prediction_trace_summary": dict(gate_artifact_v2.get("prediction_trace_summary") or {}),
        "prediction_trace_ledger": dict(gate_artifact_v2.get("prediction_trace_ledger") or {}),
    }
    return {
        "contract_version": GOVERNANCE_PLANE_CONTRACT_VERSION,
        "available": available,
        "plane": "governance",
        "gate_artifact": gate_artifact,
        "gate_artifact_v2": gate_artifact_v2,
        "dedup_artifact": dedup_artifact,
        "submission_artifact": submission_artifact,
        "evidence_artifact": evidence_artifact,
        "governance_plane_v2": governance_plane_v2,
        "gate_a": dict(gate_artifact_v2.get("gate_a") or {}),
        "gate_b": dict(gate_artifact_v2.get("gate_b") or {}),
        "gate_c": dict(gate_artifact_v2.get("gate_c") or {}),
        "legacy_gate_mapping": dict(gate_artifact_v2.get("legacy_gate_mapping") or {}),
        "protocol_versions": dict(gate_artifact_v2.get("protocol_versions") or {}),
        "prediction_trace_summary": dict(gate_artifact_v2.get("prediction_trace_summary") or {}),
        "prediction_trace_ledger": dict(gate_artifact_v2.get("prediction_trace_ledger") or {}),
        "source_chain": source_chain,
    }


__all__ = [
    "DEDUP_ARTIFACT_CONTRACT_VERSION",
    "GATE_ARTIFACT_CONTRACT_VERSION",
    "GATE_ARTIFACT_V2_CONTRACT_VERSION",
    "GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION",
    "GOVERNANCE_PLANE_CONTRACT_VERSION",
    "GOVERNANCE_PLANE_V2_CONTRACT_VERSION",
    "PREDICTION_TRACE_CONTRACT_VERSION",
    "PREDICTION_TRACE_LEDGER_CONTRACT_VERSION",
    "SUBMISSION_ARTIFACT_CONTRACT_VERSION",
    "build_gate_artifact_v2",
    "build_dedup_artifact",
    "build_gate_artifact",
    "build_governance_evidence_artifact",
    "build_governance_plane_artifact",
    "build_submission_artifact",
]

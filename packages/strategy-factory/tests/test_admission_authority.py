from __future__ import annotations

from typing import Any


def _formal_runtime(_gate: dict[str, Any], *, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "runtime_bootstrap_eligible": True,
        "runtime_bootstrap_reason": "quality_passed_non_d_candidate_with_complete_runtime_contract",
        "runtime_bootstrap_budget_tier": "standard",
        "semantic_runtime_match": True,
        "proxy_runtime_used": False,
        "diagnostic_only": False,
        "execution_readiness_tier": "formal_runtime_ready",
        "execution_semantic_gap": False,
        "execution_semantic_gap_reasons": [],
    }


def _resolve(
    gate: dict[str, Any],
    *,
    track: str = "formal_incubation",
    read_only: bool = False,
) -> dict[str, Any]:
    from strategy_factory.application.services.admission_authority import (
        ADMISSION_DECISION_CONTRACT_VERSION,
        SubmissionAdmissionAuthority,
    )

    result = SubmissionAdmissionAuthority.resolve(
        gate,
        candidate={"strategy_type": "momentum"},
        refresh_existing=False,
        existing_status="draft",
        incubation_budget_track=track,
        runtime_bootstrap_resolver=_formal_runtime,
        read_only=read_only,
    )

    assert result["admission_decision_contract_version"] == ADMISSION_DECISION_CONTRACT_VERSION
    assert result["submission_action"]["admission_decision_contract_version"] == ADMISSION_DECISION_CONTRACT_VERSION
    return result


def test_admission_authority_accepts_formal_incubation_candidate() -> None:
    result = _resolve(
        {
            "passed": True,
            "strict_incubation_ready": True,
            "incubation_pass_mode": "strict",
        }
    )

    assert result["admission_decision"] == "accept"
    assert result["submission_lane"] == "formal_incubation"
    assert result["final_status"] == "incubating"


def test_admission_authority_marks_provisional_pass() -> None:
    result = _resolve(
        {
            "passed": True,
            "provisional_pass": True,
            "research_candidate_ready": True,
            "incubation_candidate_ready": True,
        },
        track="deferred_budget_queue",
    )

    assert result["admission_decision"] == "provisional"
    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"


def test_admission_authority_rejects_failed_gate() -> None:
    result = _resolve(
        {
            "passed": False,
            "gate_a_decision": "reject",
            "admission_block_reasons": ["missing_research_protocol"],
        }
    )

    assert result["admission_decision"] == "reject"
    assert result["submission_lane"] == "rejected"
    assert result["final_status"] == "rejected"


def test_admission_authority_defers_revision_gate() -> None:
    result = _resolve(
        {
            "passed": False,
            "gate_a_decision": "revise",
            "admission_block_reasons": ["contract_revision_required"],
        }
    )

    assert result["admission_decision"] == "revise"
    assert result["submission_lane"] == "deferred_submission"
    assert result["final_status"] == "draft"


def test_admission_authority_read_only_keeps_legacy_lane_but_marks_decision() -> None:
    result = _resolve(
        {
            "passed": True,
            "strict_incubation_ready": True,
            "incubation_pass_mode": "strict",
        },
        read_only=True,
    )

    assert result["admission_decision"] == "read_only"
    assert result["submission_lane"] == "formal_incubation"
    assert result["final_status"] == "incubating"

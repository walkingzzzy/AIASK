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


# === DEV-V1 P0: D 级 + Gate passed 候选 toggle 化测试 ===
# 这两个用例不再 mock runtime resolver,而是用真实 StrategySubmitter._runtime_bootstrap_context,
# 验证 STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED toggle 的实际效果。

import pytest


@pytest.fixture(autouse=True)
def _clear_dev_v1_env(monkeypatch):
    monkeypatch.delenv("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED", raising=False)
    yield


def _resolve_with_real_resolver(gate: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """直接用真实 _runtime_bootstrap_context (不再 mock)。

    这样能完整验证 toggle 与 _runtime_bootstrap_context 的集成。
    """
    from strategy_factory.application.services.admission_authority import (
        SubmissionAdmissionAuthority,
    )
    from strategy_factory.application.submitter import StrategySubmitter

    return SubmissionAdmissionAuthority.resolve(
        gate,
        candidate=candidate,
        refresh_existing=False,
        existing_status="draft",
        incubation_budget_track="formal_incubation",
        runtime_bootstrap_resolver=StrategySubmitter._runtime_bootstrap_context,
    )


def test_dev_v1_p0_d_grade_observe_disabled_by_default() -> None:
    """toggle 默认 OFF: D 级 + Gate passed 仍归 deferred_submission,行为与 V4 修改前一致。"""
    gate = {
        "passed": True,
        "validation_grade": "D",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
    }
    candidate = {"strategy_type": "volatility_breakout", "params": {}}
    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "deferred_submission"
    assert result["runtime_bootstrap_eligible"] is False
    assert result["runtime_bootstrap_reason"] == "validation_grade_d_not_allowed_for_runtime"
    assert result["formal_track_eligible"] is False


def test_dev_v1_p0_d_grade_observe_enabled_routes_to_observe(monkeypatch) -> None:
    """toggle ON: D 级 + Gate passed 候选走 observe_incubation,budget_tier=micro,
    formal 严格性零变化(formal_track_eligible 仍为 False)。
    """
    monkeypatch.setenv("STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED", "1")

    gate = {
        "passed": True,
        "validation_grade": "D",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
    }
    candidate = {"strategy_type": "volatility_breakout", "params": {}}
    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"
    assert result["runtime_bootstrap_eligible"] is True
    assert result["runtime_bootstrap_reason"] == "d_grade_observe_only_micro_budget"
    assert result["runtime_bootstrap_budget_tier"] == "micro"
    # formal 严格性零变化
    assert result["formal_track_eligible"] is False
    assert "strict_incubation_pass_required_for_formal_track" in result["formal_track_blockers"]
    assert result["admission_decision"] == "observe_only"

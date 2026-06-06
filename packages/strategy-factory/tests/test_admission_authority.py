from __future__ import annotations

from typing import Any


def _ready_trade_prediction_fields(strategy_id: str = "strategy-1") -> dict[str, Any]:
    from strategy_factory.application.trade_prediction_contract import freeze_trade_prediction_contract

    frozen = freeze_trade_prediction_contract(
        {
            "strategy_id": strategy_id,
            "stock_code": "600000",
            "prediction_as_of": "2026-06-05T09:30:00+08:00",
            "target_trading_date": "2026-06-08",
            "direction": "up",
            "confidence": 0.71,
            "horizon": "next_day",
            "evidence_refs": ["ev-1"],
        }
    )
    return {
        "trade_prediction_contract": frozen["contract"],
        "trade_prediction_contract_status": frozen["status"],
        "trade_prediction_contract_hash": frozen["contract_hash"],
        "trade_prediction_contract_missing_fields": list(frozen.get("missing_fields") or []),
        "trade_prediction_contract_reject_reasons": list(frozen.get("reject_reasons") or []),
    }


def _runtime_ready_candidate(
    strategy_id: str = "strategy-1",
    *,
    observe_first: bool = False,
    **overrides: Any,
) -> dict[str, Any]:
    params = {
        **_ready_trade_prediction_fields(strategy_id),
    }
    candidate = {
        "id": strategy_id,
        "strategy_type": "volatility_breakout",
        "target_symbols": ["600000"],
        "params": params,
    }
    if observe_first:
        candidate["observe_first_intake"] = True
        candidate["incubation_budget"] = {
            "track": "observe_incubation",
            "budget_tier": "micro",
            "observe_first_intake": True,
        }
        params["observe_first_intake"] = True
    candidate.update(overrides)
    return candidate


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
    candidate = _runtime_ready_candidate("d-grade-disabled")
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
    candidate = _runtime_ready_candidate("d-grade-enabled")
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


def test_gate3_statistical_failure_routes_to_observe_when_observe_first_requested() -> None:
    gate = {
        "passed": False,
        "validation_grade": "C",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": [
            "insufficient_statistical_evidence",
            "weak_bootstrap_ci_lower",
            "factory_policy_backtest_trade_count_0_4",
            "profit_factor_0_860_1_000",
        ],
        "admission_block_reasons": [
            "insufficient_statistical_evidence",
            "weak_bootstrap_ci_lower",
            "factory_policy_backtest_trade_count_0_4",
        ],
    }
    candidate = _runtime_ready_candidate("gate3-audit-only", observe_first=True)

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"
    assert result["runtime_bootstrap_eligible"] is True
    assert result["wide_intake_admitted"] is True
    assert result["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["admission_decision"] == "observe_only"
    assert result["formal_track_eligible"] is False
    assert result["pre_observe_hard_reject_reasons"] == []


def test_missing_ready_trade_prediction_contract_still_blocks_observe_first() -> None:
    gate = {
        "passed": False,
        "validation_grade": "C",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": ["insufficient_statistical_evidence"],
    }
    candidate = {
        "id": "missing-trade-prediction",
        "strategy_type": "volatility_breakout",
        "target_symbols": ["600000"],
        "observe_first_intake": True,
        "incubation_budget": {
            "track": "observe_incubation",
            "budget_tier": "micro",
            "observe_first_intake": True,
        },
        "params": {"observe_first_intake": True},
    }

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "rejected"
    assert result["final_status"] == "rejected"
    assert result["runtime_bootstrap_eligible"] is False
    assert result["wide_intake_admitted"] is False
    assert result["runtime_bootstrap_reason"] == "trade_prediction_contract_not_ready"
    assert "trade_prediction_contract_not_ready" in result["pre_observe_hard_reject_reasons"]


def test_semantic_hard_fail_still_blocks_observe_first() -> None:
    gate = {
        "passed": False,
        "validation_grade": "C",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": ["temporal_coherence_audit_failed"],
        "hard_fail_reasons": ["temporal_coherence_audit_failed"],
    }
    candidate = _runtime_ready_candidate("semantic-hard-fail", observe_first=True)

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "rejected"
    assert result["final_status"] == "rejected"
    assert result["runtime_bootstrap_eligible"] is False
    assert result["wide_intake_admitted"] is False
    assert result["runtime_bootstrap_reason"] == "temporal_coherence_audit_failed"
    assert "temporal_coherence_audit_failed" in result["pre_observe_hard_reject_reasons"]


@pytest.mark.asyncio
async def test_submit_one_keeps_wide_intake_in_observe_lane(monkeypatch) -> None:
    from strategy_factory.application._submitter_actions import runner as submitter_runner
    from strategy_factory.application.submitter import StrategySubmitter

    monkeypatch.setenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_HEALTH_GUARD_ENABLED", "0")

    async def _gate3_audit_failure(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "passed": False,
            "passed_strict": False,
            "validation_grade": "C",
            "research_candidate_ready": True,
            "live_candidate_ready": False,
            "strict_incubation_ready": False,
            "reason_codes": [
                "weak_bootstrap_ci_lower",
                "factory_policy_backtest_trade_count_0_4",
            ],
            "admission_block_reasons": ["weak_bootstrap_ci_lower"],
        }

    class _Gateway:
        async def run_validation_report(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

        async def run_risk_report(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

    class _Coordinator:
        def __init__(self) -> None:
            self.persisted: list[dict[str, Any]] = []
            self.handled: list[dict[str, Any]] = []

        async def persist_candidate(self, **kwargs: Any) -> bool:
            self.persisted.append(dict(kwargs))
            return True

        async def handle_new_candidate(self, **kwargs: Any) -> dict[str, Any]:
            self.handled.append(dict(kwargs))
            action = dict(kwargs.get("submission_action") or {})
            return {
                "submission_lane": kwargs.get("submission_lane"),
                "final_status": action.get("final_status") or "submitted",
                "submission_action": dict(action.get("submission_action") or {}),
                "submission_action_type": action.get("submission_action_type"),
                "submission_action_trigger": action.get("submission_action_trigger"),
                "submission_action_gaps": list(action.get("submission_action_gaps") or []),
                "submission_action_fallback_conditions": list(
                    action.get("submission_action_fallback_conditions") or []
                ),
                "submission_action_next_step": action.get("submission_action_next_step"),
                "submission_action_completed": bool(action.get("submission_action_completed")),
                "runtime_bootstrap_reason": action.get("runtime_bootstrap_reason"),
                "wide_intake_admitted": bool(action.get("wide_intake_admitted")),
                "formal_track_requested": bool(action.get("formal_track_requested")),
                "formal_track_eligible": bool(action.get("formal_track_eligible")),
                "formal_track_blockers": list(action.get("formal_track_blockers") or []),
            }

        async def save_quality_report(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class _DB:
        pass

    monkeypatch.setattr(submitter_runner, "_local_run_submission_quality_gate", _gate3_audit_failure)

    submitter = StrategySubmitter(validation_gateway=_Gateway(), risk_gateway=_Gateway())
    coordinator = _Coordinator()
    submitter._submission_coordinator = coordinator
    candidate = _runtime_ready_candidate("submit-one-wide-intake", observe_first=True)
    candidate.update(
        {
            "name": "wide intake candidate",
            "dedup_result": {"duplicate": False, "refresh_existing": False},
            "backtest_metrics": {
                "trade_count": 12,
                "trades_count": 12,
                "max_drawdown": 0.12,
            },
            "backtest_outcome": {"passed": True, "reason_code": "passed"},
        }
    )

    result = await submitter._submit_one(
        candidate,
        {"date": "2026-06-05", "factory_run_id": "run-gate3-audit"},
        _DB(),
    )

    assert result["created_strategy_pool"] is True
    assert result["created_audit_only"] is False
    assert result["admission_decision"] == "observe_only"
    assert result["summary"]["submission_lane"] == "observe_incubation"
    assert result["summary"]["status"] == "submitted"
    assert result["summary"]["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["summary"]["wide_intake_admitted"] is True
    assert not result["summary"].get("diagnostic_observation")
    assert coordinator.handled[0]["submission_lane"] == "observe_incubation"

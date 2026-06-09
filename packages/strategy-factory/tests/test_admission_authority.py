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
    monkeypatch.delenv("STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED", raising=False)
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


def test_derived_sparse_trade_prediction_contract_routes_to_observe_first() -> None:
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
        "params": {
            "observe_first_intake": True,
            "holding_horizon": {"horizon": "next_day"},
            "trade_plan": {"entry_bias": "long", "holding_horizon": "next_day"},
            "risk_rules": {"max_drawdown": 0.12},
            "execution_assumptions": {"order_style": "paper"},
            "trade_prediction_contract": {
                "contract_source": "derived_from_legacy_contract",
            },
            "trade_prediction_contract_status": "rejected",
            "trade_prediction_contract_reject_reasons": [
                "missing:direction",
                "missing:confidence",
            ],
            "trade_prediction_contract_missing_fields": [
                "direction",
                "confidence",
            ],
        },
    }

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"
    assert result["runtime_bootstrap_eligible"] is True
    assert result["wide_intake_admitted"] is True
    assert result["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["pre_observe_hard_reject_reasons"] == []
    assert result["trade_prediction_contract_observation_gap"] is True
    assert result["diagnostic_only"] is True
    assert result["execution_readiness_tier"] == "observe_diagnostic_only"
    assert result["formal_track_eligible"] is False
    assert "diagnostic_only_runtime" in result["formal_track_blockers"]


def test_ready_trade_prediction_contract_downgrades_semantic_conflict_rule_gap_for_observe_first() -> None:
    gate = {
        "passed": False,
        "validation_grade": "A",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": [
            "prediction_contract_conflict_resolution_rule_missing",
            "weak_wf_ic_ir",
        ],
        "hard_fail_reasons": [
            "prediction_contract_conflict_resolution_rule_missing",
        ],
    }
    candidate = _runtime_ready_candidate("semantic-conflict-gap", observe_first=True)

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"
    assert result["runtime_bootstrap_eligible"] is True
    assert result["wide_intake_admitted"] is True
    assert result["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["pre_observe_hard_reject_reasons"] == []
    assert result["trade_prediction_contract_status"] == "ready"
    assert result["trade_prediction_contract_hash"]
    assert result["formal_track_eligible"] is False


def test_ready_trade_prediction_contract_downgrades_evidence_audit_conflict_rule_gap_for_observe_first() -> None:
    gate = {
        "passed": False,
        "validation_grade": "A",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": ["weak_wf_ic_ir"],
    }
    candidate = _runtime_ready_candidate(
        "semantic-audit-conflict-gap",
        observe_first=True,
        evidence_alignment_audit={
            "hard_fail_reasons": [
                "prediction_contract_conflict_resolution_rule_missing",
            ],
        },
    )

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "observe_incubation"
    assert result["final_status"] == "submitted"
    assert result["runtime_bootstrap_eligible"] is True
    assert result["wide_intake_admitted"] is True
    assert result["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["pre_observe_hard_reject_reasons"] == []
    assert result["trade_prediction_contract_status"] == "ready"
    assert result["formal_track_eligible"] is False


def test_explicit_invalid_trade_prediction_contract_still_blocks_observe_first() -> None:
    gate = {
        "passed": False,
        "validation_grade": "C",
        "research_candidate_ready": True,
        "live_candidate_ready": False,
        "strict_incubation_ready": False,
        "reason_codes": ["insufficient_statistical_evidence"],
    }
    candidate = {
        "id": "explicit-invalid-trade-prediction",
        "strategy_type": "volatility_breakout",
        "target_symbols": ["600000"],
        "observe_first_intake": True,
        "incubation_budget": {
            "track": "observe_incubation",
            "budget_tier": "micro",
            "observe_first_intake": True,
        },
        "params": {
            "observe_first_intake": True,
            "holding_horizon": {"horizon": "next_day"},
            "trade_plan": {"entry_bias": "long", "holding_horizon": "next_day"},
            "risk_rules": {"max_drawdown": 0.12},
            "execution_assumptions": {"order_style": "paper"},
            "trade_prediction_contract": {
                "contract_source": "explicit",
                "direction": "moon",
            },
            "trade_prediction_contract_status": "rejected",
            "trade_prediction_contract_reject_reasons": ["invalid:direction"],
            "trade_prediction_contract_missing_fields": [],
        },
    }

    result = _resolve_with_real_resolver(gate, candidate)

    assert result["submission_lane"] == "rejected"
    assert result["final_status"] == "rejected"
    assert result["runtime_bootstrap_eligible"] is False
    assert result["wide_intake_admitted"] is False
    assert result["runtime_bootstrap_reason"] == "trade_prediction_contract_not_ready"
    assert "trade_prediction_contract_not_ready" in result["pre_observe_hard_reject_reasons"]
    assert result["trade_prediction_contract_observation_gap"] is False


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
    monkeypatch.setenv("STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_MIN_VALIDATION_GRADE", "S")

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
            self.reports: list[dict[str, Any]] = []

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
            self.reports.append({"args": _args, "kwargs": _kwargs})
            return None

    class _DB:
        def __init__(self) -> None:
            self.evidence: list[dict[str, Any]] = []
            self.experiments: list[dict[str, Any]] = []

        async def save_factory_task_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
            row = {"id": f"ev-{len(self.evidence) + 1}", **payload}
            self.evidence.append(row)
            return row

        async def save_strategy_generation_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.experiments.append(dict(payload))
            return dict(payload)

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
            "experiment_id": "exp-gate3-record-only",
        }
    )

    db = _DB()
    result = await submitter._submit_one(
        candidate,
        {"date": "2026-06-05", "factory_run_id": "run-gate3-audit"},
        db,
    )

    assert result["created_strategy_pool"] is False
    assert result["created_audit_only"] is True
    assert result["gate_3_recorded"] is True
    assert result["gate3_quality_recorded"] is False
    assert result["gate3_record_quality_qualified"] is False
    assert result["gate3_record_diagnostic_only"] is True
    assert result["gate3_record_only_min_grade"] == "S"
    assert result["gate3_record_grade"] == "C"
    assert result["record_only"] is True
    assert result["submitted"] is False
    assert result["admission_decision"] == "observe_only"
    assert result["summary"]["submission_lane"] == "gate3_record_only"
    assert result["summary"]["planned_submission_lane"] == "observe_incubation"
    assert result["summary"]["status"] == "gate3_recorded"
    assert result["summary"]["runtime_bootstrap_reason"] == "wide_intake_observe_gate3_not_required"
    assert result["summary"]["wide_intake_admitted"] is True
    assert result["summary"]["gate_3_recorded"] is True
    assert result["summary"]["gate3_quality_recorded"] is False
    assert result["summary"]["gate3_record_quality_qualified"] is False
    assert result["summary"]["gate3_record_diagnostic_only"] is True
    assert result["summary"]["submission_action_type"] == "gate3_record_only"
    assert result["summary"]["submission_action_next_step"] == "await_manual_record_review"
    assert result["summary"]["strategy_created"] is False
    assert result["summary"]["lifecycle_action_executed"] is False
    assert result["summary"]["automatic_downstream_action"] is False
    assert result["summary"]["quality_report_persisted"] is False
    assert result["summary"]["gate3_audit_evidence_persisted"] is True
    assert not result["summary"].get("diagnostic_observation")
    assert coordinator.persisted == []
    assert coordinator.handled == []
    assert len(coordinator.reports) == 1
    assert coordinator.reports[0]["kwargs"]["options"].record_only is True
    assert db.evidence[0]["evidence_type"] == "gate3_record_only_audit"
    assert db.evidence[0]["evidence_payload"]["strategy_created"] is False
    assert db.evidence[0]["evidence_payload"]["lifecycle_action_executed"] is False
    assert db.evidence[0]["evidence_payload"]["quality_report_persisted"] is False
    assert db.evidence[0]["evidence_payload"]["gate3_audit_evidence_persisted"] is True
    assert db.evidence[0]["evidence_payload"]["automatic_downstream_action"] is False
    assert db.evidence[0]["evidence_payload"]["gate3_quality_recorded"] is False
    assert db.evidence[0]["evidence_payload"]["gate3_record_diagnostic_only"] is True
    assert db.evidence[0]["weight"] == 0.0
    assert db.evidence[0]["evidence_payload"]["quality_report"]
    assert result["summary"]["gate3_audit_evidence_id"] == "ev-1"
    assert db.experiments[0]["strategy_id"] is None
    assert db.experiments[0]["generated_strategy_id"] is None
    assert db.experiments[0]["result"]["candidate_id"] == result["summary"]["strategy_id"]
    assert db.experiments[0]["result"]["strategy_id"] is None
    assert db.experiments[0]["result"]["generated_strategy_id"] is None
    assert db.experiments[0]["result"]["record_only"] is True


@pytest.mark.asyncio
async def test_gate3_record_only_counts_s_grade_as_quality_record_without_lifecycle_action(monkeypatch) -> None:
    from strategy_factory.application._submitter_actions import runner as submitter_runner
    from strategy_factory.application.submitter import StrategySubmitter

    monkeypatch.setenv("STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_MIN_VALIDATION_GRADE", "S")

    async def _gate3_s_pass(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "passed_strict": True,
            "validation_grade": "S",
            "effective_validation_grade": "S",
            "validation_total_score": 82.0,
            "research_candidate_ready": True,
            "incubation_candidate_ready": True,
            "live_candidate_ready": False,
            "strict_incubation_ready": True,
            "incubation_pass_mode": "strict",
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
            self.reports: list[dict[str, Any]] = []

        async def persist_candidate(self, **kwargs: Any) -> bool:
            self.persisted.append(dict(kwargs))
            return True

        async def handle_new_candidate(self, **kwargs: Any) -> dict[str, Any]:
            self.handled.append(dict(kwargs))
            return {"submission_lane": kwargs.get("submission_lane"), "final_status": "incubating"}

        async def save_quality_report(self, *_args: Any, **_kwargs: Any) -> None:
            self.reports.append({"args": _args, "kwargs": _kwargs})

    class _DB:
        def __init__(self) -> None:
            self.evidence: list[dict[str, Any]] = []
            self.experiments: list[dict[str, Any]] = []

        async def save_factory_task_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
            row = {"id": f"ev-{len(self.evidence) + 1}", **payload}
            self.evidence.append(row)
            return row

        async def save_strategy_generation_experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.experiments.append(dict(payload))
            return dict(payload)

    monkeypatch.setattr(submitter_runner, "_local_run_submission_quality_gate", _gate3_s_pass)

    submitter = StrategySubmitter(validation_gateway=_Gateway(), risk_gateway=_Gateway())
    coordinator = _Coordinator()
    submitter._submission_coordinator = coordinator
    candidate = _runtime_ready_candidate(
        "submit-one-s-record-only",
        name="s record only candidate",
        dedup_result={"duplicate": False, "refresh_existing": False},
        backtest_metrics={"trade_count": 24, "trades_count": 24, "max_drawdown": 0.05},
        backtest_outcome={"passed": True, "reason_code": "passed"},
        experiment_id="exp-gate3-s-record-only",
    )

    db = _DB()
    result = await submitter._submit_one(
        candidate,
        {"date": "2026-06-05", "factory_run_id": "run-gate3-s-audit"},
        db,
    )

    assert result["created_strategy_pool"] is False
    assert result["submitted"] is False
    assert result["gate_3_recorded"] is True
    assert result["gate3_quality_recorded"] is True
    assert result["gate3_record_quality_qualified"] is True
    assert result["gate3_record_diagnostic_only"] is False
    assert result["gate3_record_grade"] == "S"
    assert result["summary"]["gate3_quality_recorded"] is True
    assert result["summary"]["strategy_created"] is False
    assert result["summary"]["lifecycle_action_executed"] is False
    assert result["summary"]["gate3_audit_evidence_persisted"] is True
    assert coordinator.persisted == []
    assert coordinator.handled == []
    assert db.evidence[0]["weight"] == 1.0
    assert db.evidence[0]["evidence_payload"]["gate3_record_quality_qualified"] is True
    assert db.evidence[0]["evidence_payload"]["validation_grade"] == "S"
    assert db.evidence[0]["evidence_payload"]["gate3_audit_evidence_persisted"] is True
    assert db.evidence[0]["evidence_payload"]["automatic_downstream_action"] is False
    assert db.experiments[0]["strategy_id"] is None
    assert db.experiments[0]["generated_strategy_id"] is None
    assert db.experiments[0]["evaluation"]["gate3_record_quality_qualified"] is True
    assert db.experiments[0]["result"]["gate3_record_quality_qualified"] is True
    assert db.experiments[0]["result"]["automatic_downstream_action"] is False


@pytest.mark.asyncio
async def test_submit_one_can_opt_out_of_gate3_record_only(monkeypatch) -> None:
    from strategy_factory.application._submitter_actions import runner as submitter_runner
    from strategy_factory.application.submitter import StrategySubmitter

    monkeypatch.setenv("STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED", "0")

    async def _gate3_pass(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "passed_strict": True,
            "validation_grade": "S",
            "research_candidate_ready": True,
            "incubation_candidate_ready": True,
            "live_candidate_ready": False,
            "strict_incubation_ready": True,
            "incubation_pass_mode": "strict",
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
                "final_status": action.get("final_status") or "incubating",
                "submission_action": dict(action.get("submission_action") or {}),
                "submission_action_type": action.get("submission_action_type"),
                "submission_action_trigger": action.get("submission_action_trigger"),
                "submission_action_completed": True,
                "formal_track_requested": bool(action.get("formal_track_requested")),
                "formal_track_eligible": bool(action.get("formal_track_eligible")),
                "formal_track_blockers": list(action.get("formal_track_blockers") or []),
            }

        async def save_quality_report(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class _DB:
        pass

    monkeypatch.setattr(submitter_runner, "_local_run_submission_quality_gate", _gate3_pass)

    submitter = StrategySubmitter(validation_gateway=_Gateway(), risk_gateway=_Gateway())
    coordinator = _Coordinator()
    submitter._submission_coordinator = coordinator
    candidate = _runtime_ready_candidate("submit-one-opt-out")
    candidate.update(
        {
            "name": "opt out candidate",
            "dedup_result": {"duplicate": False, "refresh_existing": False},
            "backtest_metrics": {"trade_count": 12, "trades_count": 12, "max_drawdown": 0.08},
            "backtest_outcome": {"passed": True, "reason_code": "passed"},
        }
    )

    result = await submitter._submit_one(
        candidate,
        {"date": "2026-06-05", "factory_run_id": "run-gate3-opt-out"},
        _DB(),
    )

    assert result["record_only"] is False
    assert result["created_strategy_pool"] is True
    assert result["submitted"] is True
    assert coordinator.persisted
    assert coordinator.handled[0]["submission_lane"] in {"formal_incubation", "observe_incubation"}


@pytest.mark.asyncio
async def test_default_observe_handoff_creates_paper_account_and_quality_summary(monkeypatch) -> None:
    from strategy_factory.application._submitter_actions import runner as submitter_runner
    from strategy_factory.application.submitter import StrategySubmitter

    monkeypatch.delenv("STRATEGY_FACTORY_GATE3_RECORD_ONLY_ENABLED", raising=False)

    async def _gate3_audit_failure(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "passed": False,
            "passed_strict": False,
            "provisional_pass": False,
            "validation_grade": "C",
            "research_candidate_ready": True,
            "live_candidate_ready": False,
            "strict_incubation_ready": False,
            "reason_codes": ["weak_bootstrap_ci_lower"],
            "admission_block_reasons": ["weak_bootstrap_ci_lower"],
        }

    class _Gateway:
        async def run_validation_report(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

        async def run_risk_report(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {}

    class _IncubationGateway:
        def __init__(self) -> None:
            self.accounts: list[dict[str, Any]] = []

        async def ensure_account(self, _db: Any, strategy: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            account = {
                "account_id": f"paper-{strategy['id']}",
                "status": "active",
                "strategy_id": strategy["id"],
                "kwargs": dict(kwargs),
            }
            self.accounts.append(account)
            return account

        async def update_account_stage(
            self,
            _db: Any,
            *,
            account_id: str,
            stage: str,
            metadata: dict[str, Any] | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            return {
                "account_id": account_id,
                "stage": stage,
                "status": "active",
                "metadata": dict(metadata or {}),
            }

    class _DB:
        def __init__(self) -> None:
            self.strategies: list[dict[str, Any]] = []
            self.status_updates: list[tuple[str, str]] = []
            self.quality_reports: list[tuple[str, str, dict[str, Any]]] = []

        async def save_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.strategies.append(dict(payload))
            return dict(payload)

        async def save_strategy_metrics(
            self,
            strategy_id: str,
            period: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            return {"strategy_id": strategy_id, "period": period, **dict(payload)}

        async def save_strategy_quality_report(
            self,
            strategy_id: str,
            report_type: str,
            quality_report: dict[str, Any],
        ) -> dict[str, Any]:
            self.quality_reports.append((strategy_id, report_type, dict(quality_report)))
            return {"strategy_id": strategy_id, "report_type": report_type}

    async def _status_update(db: _DB, strategy_id: str, status: str, **_kwargs: Any) -> dict[str, Any]:
        db.status_updates.append((strategy_id, status))
        return {"strategy_id": strategy_id, "status": status}

    monkeypatch.setattr(submitter_runner, "_local_run_submission_quality_gate", _gate3_audit_failure)
    monkeypatch.setattr(submitter_runner, "_local_update_strategy_status", _status_update)

    incubation_gateway = _IncubationGateway()
    submitter = StrategySubmitter(
        validation_gateway=_Gateway(),
        risk_gateway=_Gateway(),
        incubation_gateway=incubation_gateway,
    )
    candidate = {
        "id": "submit-one-default-observe",
        "name": "default observe handoff candidate",
        "strategy_type": "volatility_breakout",
        "target_symbols": ["600000"],
        "observe_first_intake": True,
        "incubation_budget": {
            "track": "observe_incubation",
            "budget_tier": "micro",
            "observe_first_intake": True,
        },
        "params": {
            "target_symbols": ["600000"],
            "as_of_date": "2026-06-05",
            "observe_first_intake": True,
            "holding_horizon": {"horizon": "next_day"},
            "trade_plan": {"holding_horizon": "next_day"},
            "risk_rules": {"max_drawdown": 0.12},
            "execution_assumptions": {"order_style": "paper"},
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "target_trading_date": "2026-06-08",
                        "horizon": "next_day",
                        "evidence_ids": ["ev-1"],
                    }
                ]
            },
            "evidence_chain": {
                "evidences": [{"evidence_id": "ev-1", "source": "pure_backtest"}]
            },
        },
        "dedup_result": {"duplicate": False, "refresh_existing": False},
        "backtest_metrics": {"trade_count": 12, "trades_count": 12, "max_drawdown": 0.08},
        "backtest_outcome": {"passed": True, "reason_code": "passed"},
    }

    db = _DB()
    result = await submitter._submit_one(
        candidate,
        {"date": "2026-06-05", "factory_run_id": "run-default-observe"},
        db,
    )

    assert result["record_only"] is False
    assert result["created_strategy_pool"] is True
    assert result["gate_3_recorded"] is False
    assert result["admission_decision"] == "observe_only"
    assert result["summary"]["submission_lane"] == "observe_incubation"
    assert result["summary"]["status"] == "submitted"
    assert result["summary"]["final_status"] == "submitted"
    assert result["summary"]["paper_lane_ready"] is True
    assert result["summary"]["paper_account_id"].startswith("paper-factory_")
    assert result["summary"]["paper_account_status"] == "active"
    assert result["summary"]["incubation_factory_required"] is True
    assert result["summary"]["paper_observation_backlog_status"] == "queued"
    assert result["summary"].get("paper_observation_handoff_warning") is None
    assert result["summary"]["trade_prediction_contract_observation_gap"] is True
    assert result["summary"]["diagnostic_only"] is False
    assert db.strategies and db.strategies[0]["status"] == "submitted"
    assert db.status_updates[-1][1] == "submitted"
    assert incubation_gateway.accounts
    report_summary = db.quality_reports[-1][2]["summary"]
    assert report_summary["submission_lane"] == "observe_incubation"
    assert report_summary["final_status"] == "submitted"
    assert report_summary["paper_lane_ready"] is True
    assert report_summary["paper_account_id"] == result["summary"]["paper_account_id"]
    assert report_summary["incubation_factory_required"] is True

"""P4 验收测试 – 候选域模型与研究任务域模型。

验收标准：
- CandidateSpec / CandidateEvaluation / CandidateDedupDecision / CandidateSubmissionDecision 可构造、可序列化。
- ResearchTaskSpec / ResearchTaskResult / ResearchBatchResult 字段正确、overall_status 逻辑正确。
- CandidatePipelineReport.to_dict() 包含所有必要字段。
"""

from __future__ import annotations

import pytest

from strategy_factory.domain.candidates import (
    CandidateDedupDecision,
    CandidateEvaluation,
    CandidatePipelineReport,
    CandidateSource,
    CandidateSpec,
    CandidateSubmissionDecision,
)
from strategy_factory.domain.research_tasks import (
    ResearchBatchResult,
    ResearchTaskResult,
    ResearchTaskSpec,
    ResearchTaskStatus,
)


# ---------------------------------------------------------------------------
# CandidateSpec
# ---------------------------------------------------------------------------

class TestCandidateSpec:
    def test_from_dict_basic(self):
        data = {
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "source": "autonomy",
            "tags": ["ai_generated"],
            "target_symbols": ["000001"],
        }
        spec = CandidateSpec.from_dict(data)
        assert spec.strategy_type == "momentum"
        assert spec.params == {"lookback": 20}
        assert spec.source == CandidateSource.AUTONOMY
        assert spec.tags == ["ai_generated"]
        assert spec.target_symbols == ["000001"]

    def test_from_dict_unknown_source(self):
        spec = CandidateSpec.from_dict({"strategy_type": "x", "source": "not_a_source"})
        assert spec.source == CandidateSource.UNKNOWN

    def test_to_dict_round_trip(self):
        data = {
            "strategy_type": "reversion",
            "params": {"threshold": 2.0},
            "source": "snapshot",
            "tags": [],
            "target_symbols": [],
        }
        spec = CandidateSpec.from_dict(data)
        d = spec.to_dict()
        assert d["strategy_type"] == "reversion"
        assert d["source"] == "snapshot"
        assert d["params"] == {"threshold": 2.0}

    def test_empty_dict(self):
        spec = CandidateSpec.from_dict({})
        assert spec.strategy_type == ""
        assert spec.source == CandidateSource.UNKNOWN
        assert spec.tags == []


# ---------------------------------------------------------------------------
# CandidateEvaluation
# ---------------------------------------------------------------------------

class TestCandidateEvaluation:
    def test_from_dict(self):
        ev = CandidateEvaluation.from_dict({
            "strategy_type": "ma_cross",
            "gate": "gate_1",
            "passed": True,
            "score": 0.82,
            "failure_reason": None,
        })
        assert ev.passed is True
        assert ev.gate == "gate_1"
        assert ev.score == pytest.approx(0.82)

    def test_failed_evaluation(self):
        ev = CandidateEvaluation.from_dict({
            "strategy_type": "rsi",
            "gate": "gate_2",
            "passed": False,
            "failure_reason": "low_sharpe",
        })
        assert ev.passed is False
        assert ev.failure_reason == "low_sharpe"

    def test_to_dict(self):
        ev = CandidateEvaluation.from_dict({"strategy_type": "x", "gate": "g0", "passed": True})
        d = ev.to_dict()
        assert "strategy_type" in d
        assert "gate" in d
        assert "passed" in d


# ---------------------------------------------------------------------------
# CandidateDedupDecision
# ---------------------------------------------------------------------------

class TestCandidateDedupDecision:
    def test_not_duplicate(self):
        dec = CandidateDedupDecision.from_dict({
            "strategy_type": "bollinger",
            "is_duplicate": False,
        })
        assert dec.is_duplicate is False
        assert dec.duplicate_of is None

    def test_duplicate(self):
        dec = CandidateDedupDecision.from_dict({
            "strategy_type": "macd",
            "is_duplicate": True,
            "duplicate_of": "strat_abc",
            "similarity_score": 0.97,
        })
        assert dec.is_duplicate is True
        assert dec.duplicate_of == "strat_abc"

    def test_to_dict(self):
        dec = CandidateDedupDecision.from_dict({"strategy_type": "x", "is_duplicate": False})
        d = dec.to_dict()
        assert "is_duplicate" in d


# ---------------------------------------------------------------------------
# CandidateSubmissionDecision
# ---------------------------------------------------------------------------

class TestCandidateSubmissionDecision:
    def test_submitted(self):
        sd = CandidateSubmissionDecision.from_dict({
            "strategy_type": "trend",
            "submitted": True,
            "passed_quality_gate": True,
            "strategy_id": "strat_001",
        })
        assert sd.submitted is True
        assert sd.strategy_id == "strat_001"

    def test_provisional(self):
        sd = CandidateSubmissionDecision.from_dict({
            "strategy_type": "mean_rev",
            "submitted": True,
            "passed_quality_gate": False,
            "provisional": True,
        })
        assert sd.provisional is True
        assert sd.passed_quality_gate is False


# ---------------------------------------------------------------------------
# CandidatePipelineReport
# ---------------------------------------------------------------------------

class TestCandidatePipelineReport:
    def test_default_values(self):
        r = CandidatePipelineReport()
        assert r.submitted == 0
        assert r.failure_reason_counts == {}

    def test_to_dict_has_all_keys(self):
        r = CandidatePipelineReport(total_spawned=10, gate_2_passed=5, submitted=3)
        d = r.to_dict()
        for key in [
            "total_spawned", "gate_0_passed", "gate_1_passed", "gate_2_passed",
            "after_dedup", "gate_3_passed", "submitted",
        ]:
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# ResearchTaskSpec
# ---------------------------------------------------------------------------

class TestResearchTaskSpec:
    def test_from_dict(self):
        data = {
            "task_id": "tid_001",
            "task_key": "key_001",
            "task_source": "event",
            "opportunity_type": "breakout",
            "candidate_family": "momentum",
            "generation_limit": 3,
        }
        spec = ResearchTaskSpec.from_dict(data)
        assert spec.task_id == "tid_001"
        assert spec.task_source == "event"
        assert spec.generation_limit == 3

    def test_to_dict(self):
        spec = ResearchTaskSpec.from_dict({"task_id": "x", "task_key": "x", "task_source": "snapshot"})
        d = spec.to_dict()
        assert "task_id" in d
        assert "task_source" in d


# ---------------------------------------------------------------------------
# ResearchTaskResult
# ---------------------------------------------------------------------------

class TestResearchTaskResult:
    def _make_spec(self) -> ResearchTaskSpec:
        return ResearchTaskSpec.from_dict({
            "task_id": "t1",
            "task_key": "t1",
            "task_source": "event",
        })

    def test_ok_when_completed(self):
        r = ResearchTaskResult(
            task_spec=self._make_spec(),
            status=ResearchTaskStatus.COMPLETED,
        )
        assert r.ok is True

    def test_not_ok_when_failed(self):
        r = ResearchTaskResult(
            task_spec=self._make_spec(),
            status=ResearchTaskStatus.FAILED,
        )
        assert r.ok is False

    def test_to_dict_has_required_keys(self):
        r = ResearchTaskResult(
            task_spec=self._make_spec(),
            status=ResearchTaskStatus.COMPLETED,
            generated_count=2,
        )
        d = r.to_dict()
        for key in ["task", "status", "generated_count", "evidence_count"]:
            assert key in d

    def test_to_brief(self):
        r = ResearchTaskResult(
            task_spec=self._make_spec(),
            status=ResearchTaskStatus.COMPLETED,
            generated_count=1,
        )
        brief = r.to_brief()
        assert "task_id" in brief
        assert "generated_count" in brief


# ---------------------------------------------------------------------------
# ResearchBatchResult
# ---------------------------------------------------------------------------

class TestResearchBatchResult:
    def _make_spec(self, source: str = "event") -> ResearchTaskSpec:
        return ResearchTaskSpec.from_dict({
            "task_id": "t",
            "task_key": "t",
            "task_source": source,
        })

    def test_overall_status_succeeded(self):
        r = ResearchBatchResult(task_results=[
            ResearchTaskResult(
                task_spec=self._make_spec(),
                status=ResearchTaskStatus.COMPLETED,
                external_llm_status="succeeded",
            )
        ])
        assert r.overall_external_status == "succeeded"

    def test_overall_status_failed(self):
        r = ResearchBatchResult(task_results=[
            ResearchTaskResult(
                task_spec=self._make_spec(),
                status=ResearchTaskStatus.FAILED,
                external_llm_status="failed",
            )
        ])
        assert r.overall_external_status == "failed"

    def test_overall_status_partial(self):
        r = ResearchBatchResult(task_results=[
            ResearchTaskResult(task_spec=self._make_spec(), status=ResearchTaskStatus.COMPLETED),
            ResearchTaskResult(task_spec=self._make_spec(), status=ResearchTaskStatus.FAILED),
        ])
        assert r.overall_external_status == "partial"

    def test_overall_status_skipped_when_empty(self):
        r = ResearchBatchResult()
        assert r.overall_external_status == "skipped"

    def test_to_stage_dict_has_required_keys(self):
        r = ResearchBatchResult(
            task_results=[
                ResearchTaskResult(
                    task_spec=self._make_spec("event"),
                    status=ResearchTaskStatus.COMPLETED,
                    generated_count=1,
                )
            ],
            generated_candidates=[{"strategy_type": "x"}],
        )
        d = r.to_stage_dict()
        for key in [
            "task_count", "completed_task_count", "failed_task_count",
            "generated_count", "external_llm_status", "task_results",
        ]:
            assert key in d, f"Missing key: {key}"

    def test_completed_and_failed_counts(self):
        specs = [self._make_spec() for _ in range(3)]
        r = ResearchBatchResult(task_results=[
            ResearchTaskResult(task_spec=specs[0], status=ResearchTaskStatus.COMPLETED),
            ResearchTaskResult(task_spec=specs[1], status=ResearchTaskStatus.FAILED),
            ResearchTaskResult(task_spec=specs[2], status=ResearchTaskStatus.COMPLETED),
        ])
        assert r.completed_count == 2
        assert r.failed_count == 1

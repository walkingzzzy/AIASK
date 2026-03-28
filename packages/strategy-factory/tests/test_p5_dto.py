"""P5 验收测试 – 稳定 DTO 层。

验收标准：
- StageResultDTO / FactoryRunSummaryDTO / FactoryRunDetailDTO / FactoryStatusDTO 可从 dict 构造。
- to_dict() 输出包含所有必要字段。
- 状态枚举归一化正确（别名 'success' → 'success' / 'partial' 等）。
- normalize_run_result_to_detail / normalize_run_result_to_summary 工具函数可用。
"""

from __future__ import annotations

import pytest

from strategy_factory.api.dto import (
    FactoryRunDetailDTO,
    FactoryRunSummaryDTO,
    FactoryStatusDTO,
    StageResultDTO,
    normalize_run_result_to_detail,
    normalize_run_result_to_summary,
)


# ---------------------------------------------------------------------------
# StageResultDTO
# ---------------------------------------------------------------------------

class TestStageResultDTO:
    def test_from_dict_completed(self):
        dto = StageResultDTO.from_dict("collect", {
            "status": "completed",
            "ok": True,
            "hard_failure": False,
            "degraded": False,
            "warning_count": 0,
            "blocker_count": 0,
            "persistence_failure_count": 0,
        })
        assert dto.stage == "collect"
        assert dto.status == "completed"
        assert dto.ok is True
        assert dto.hard_failure is False

    def test_from_dict_partial(self):
        dto = StageResultDTO.from_dict("readiness", {"status": "partial", "degraded": True})
        assert dto.status == "partial"
        assert dto.degraded is True

    def test_from_dict_with_skip_reason(self):
        dto = StageResultDTO.from_dict("readiness", {
            "status": "skipped",
            "ok": True,
            "skip_reason": "runtime_disabled",
        })
        assert dto.skip_reason == "runtime_disabled"

    def test_to_dict_has_required_keys(self):
        dto = StageResultDTO.from_dict("spawn", {"status": "completed", "ok": True})
        d = dto.to_dict()
        for key in ["stage", "status", "ok", "hard_failure", "degraded"]:
            assert key in d

    def test_skip_reason_omitted_when_none(self):
        dto = StageResultDTO.from_dict("spawn", {"status": "completed"})
        d = dto.to_dict()
        assert "skip_reason" not in d

    def test_status_alias_success_normalized(self):
        dto = StageResultDTO.from_dict("collect", {"status": "success"})
        assert dto.status == "completed"

    def test_status_alias_error_normalized(self):
        dto = StageResultDTO.from_dict("factor_research", {"status": "error"})
        assert dto.status == "failed"


# ---------------------------------------------------------------------------
# FactoryRunSummaryDTO
# ---------------------------------------------------------------------------

_SAMPLE_RUN_RESULT = {
    "run_id": "run_001",
    "trace_id": "trace_001",
    "status": "success",
    "started_at": "2026-01-01T10:00:00+08:00",
    "completed_at": "2026-01-01T10:05:00+08:00",
    "elapsed_seconds": 300.0,
    "summary": {
        "trace_id": "trace_001",
        "candidates_spawned": 12,
        "submitted": 3,
        "eliminated": 1,
        "factory_readiness_score": 0.92,
        "factory_readiness_can_proceed": True,
    },
    "_run_audit": {
        "hard_failure_count": 0,
        "degraded_stage_count": 0,
        "persistence_failure_count": 0,
    },
    "stages": {
        "collect": {"status": "completed", "ok": True},
        "readiness": {"status": "completed", "ok": True},
        "spawn": {"status": "completed", "ok": True},
        "submit": {"status": "completed", "ok": True},
    },
}


class TestFactoryRunSummaryDTO:
    def test_from_dict_basic(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.run_id == "run_001"
        assert dto.status == "success"
        assert dto.candidates_spawned == 12
        assert dto.submitted == 3
        assert dto.elapsed_seconds == pytest.approx(300.0)

    def test_from_dict_partial(self):
        data = {**_SAMPLE_RUN_RESULT, "status": "partial"}
        data["_run_audit"] = {"degraded_stage_count": 1, "hard_failure_count": 0, "persistence_failure_count": 0}
        dto = FactoryRunSummaryDTO.from_dict(data)
        assert dto.status == "partial"
        assert dto.degraded_stage_count == 1

    def test_from_dict_skipped(self):
        data = {
            "run_id": "r", "trace_id": "t",
            "status": "skipped",
            "summary": {"skip_reason": "runtime_disabled"},
            "_run_audit": {},
        }
        dto = FactoryRunSummaryDTO.from_dict(data)
        assert dto.status == "skipped"
        assert dto.skip_reason == "runtime_disabled"

    def test_to_dict_has_required_keys(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        for key in ["run_id", "status", "elapsed_seconds", "submitted", "candidates_spawned"]:
            assert key in d

    def test_error_omitted_when_none(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        assert "error" not in d

    def test_error_included_when_present(self):
        data = {**_SAMPLE_RUN_RESULT, "status": "failed", "error": "something went wrong"}
        dto = FactoryRunSummaryDTO.from_dict(data)
        d = dto.to_dict()
        assert d["error"] == "something went wrong"

    def test_readiness_fields(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.readiness_score == pytest.approx(0.92)
        assert dto.readiness_can_proceed is True


# ---------------------------------------------------------------------------
# FactoryRunDetailDTO
# ---------------------------------------------------------------------------

class TestFactoryRunDetailDTO:
    def test_from_dict_stages(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.summary.run_id == "run_001"
        stage_names = [s.stage for s in dto.stages]
        assert "collect" in stage_names
        assert "readiness" in stage_names

    def test_get_stage(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        stage = dto.get_stage("collect")
        assert stage is not None
        assert stage.stage == "collect"

    def test_get_stage_missing(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.get_stage("nonexistent") is None

    def test_failed_stages_empty_when_all_pass(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.failed_stages() == []

    def test_failed_stages_detected(self):
        data = dict(_SAMPLE_RUN_RESULT)
        data["stages"] = {
            "factor_research": {"status": "failed", "ok": False},
            "collect": {"status": "completed", "ok": True},
        }
        dto = FactoryRunDetailDTO.from_dict(data)
        assert "factor_research" in dto.failed_stages()

    def test_to_dict_includes_stages(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        assert "stages" in d
        assert isinstance(d["stages"], dict)


# ---------------------------------------------------------------------------
# FactoryStatusDTO
# ---------------------------------------------------------------------------

class TestFactoryStatusDTO:
    def _sample_status(self) -> dict:
        return {
            "running": True,
            "schedule_mode": "continuous",
            "runtime_enabled": True,
            "event_runtime_mode": "live",
            "last_run": "2026-01-01T10:00:00",
            "last_result": {"status": "success"},
            "daily_run_count": 1,
            "max_daily_runs": 3,
            "cycle_count": 42,
            "factor_auto_refresh_enabled": True,
            "readiness_hard_block_enabled": False,
            "readiness_min_score": 0.6,
        }

    def test_from_dict_basic(self):
        dto = FactoryStatusDTO.from_dict(self._sample_status())
        assert dto.running is True
        assert dto.schedule_mode == "continuous"
        assert dto.cycle_count == 42
        assert dto.last_status == "success"

    def test_last_status_none_when_no_last_result(self):
        data = {**self._sample_status(), "last_result": None}
        dto = FactoryStatusDTO.from_dict(data)
        assert dto.last_status is None

    def test_to_dict(self):
        dto = FactoryStatusDTO.from_dict(self._sample_status())
        d = dto.to_dict()
        for key in ["running", "schedule_mode", "runtime_enabled", "cycle_count"]:
            assert key in d


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestNormalizeHelpers:
    def test_normalize_to_detail(self):
        dto = normalize_run_result_to_detail(_SAMPLE_RUN_RESULT)
        assert isinstance(dto, FactoryRunDetailDTO)
        assert dto.summary.status == "success"

    def test_normalize_to_summary(self):
        dto = normalize_run_result_to_summary(_SAMPLE_RUN_RESULT)
        assert isinstance(dto, FactoryRunSummaryDTO)
        assert dto.run_id == "run_001"

    def test_normalize_empty_dict(self):
        dto = normalize_run_result_to_summary({})
        assert dto.status == "failed"

    def test_normalize_detail_empty_stages(self):
        dto = normalize_run_result_to_detail({"run_id": "r", "status": "skipped", "stages": {}})
        assert dto.stages == []


# ---------------------------------------------------------------------------
# Import contract – api/__init__ exports
# ---------------------------------------------------------------------------

def test_api_init_exports_dtos():
    from strategy_factory import api
    for name in [
        "FactoryRunDetailDTO",
        "FactoryRunSummaryDTO",
        "FactoryStatusDTO",
        "StageResultDTO",
        "normalize_run_result_to_detail",
        "normalize_run_result_to_summary",
    ]:
        assert hasattr(api, name), f"strategy_factory.api missing: {name}"

from __future__ import annotations

import asyncio

from strategy_factory.application.services.candidate_pipeline import CandidatePipeline


class FakeBacktestFilter:
    def __init__(self) -> None:
        self._kline_cache = {}

    def get_last_report(self) -> dict:
        return {
            "summary": {
                "input_count": 2,
                "passed_count": 1,
                "failed_count": 1,
                "failed_reason_counts": {"weak_score": 1},
            }
        }


class FakeDeduplicator:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    async def deduplicate(self, candidates, db):
        self.seen = [dict(item or {}) for item in list(candidates or [])]
        return self.seen

    def get_last_report(self) -> dict:
        return {"input_count": len(self.seen), "kept_count": len(self.seen)}


class FakeSubmitter:
    def __init__(self) -> None:
        self.seen: list[dict] = []

    async def submit(self, candidates, snapshot, db, *, read_only=False):
        self.seen = [dict(item or {}) for item in list(candidates or [])]
        strategies = [
            {
                "strategy_id": f"strategy_{idx}",
                "status": "submitted",
                "submission_lane": "observe_incubation",
            }
            for idx, _candidate in enumerate(self.seen)
        ]
        return {
            "submitted": 0,
            "created_total": len(self.seen),
            "created_strategy_pool": len(self.seen),
            "gate_3_input": len(self.seen),
            "gate_3_passed": 0,
            "gate_3_failed": len(self.seen),
            "strategies": strategies,
        }


class FakeScheduler:
    def __init__(self) -> None:
        self.deduplicator = FakeDeduplicator()
        self.submitter = FakeSubmitter()

    def _build_deduplicator(self, pkg):
        return self.deduplicator

    def _build_submitter(self, pkg):
        return self.submitter


class FakePkg:
    BacktestFilter = FakeBacktestFilter

    def __init__(self) -> None:
        self.gated_filter_calls = 0

    async def run_gated_filter(self, candidates, db, backtest_filter, *, kline_cache=None):
        self.gated_filter_calls += 1
        return {
            "passed": [dict(candidates[0])],
            "gate_report": {
                "gate_1": {"passed_count": 1, "failed_count": 1},
                "gate_2": {
                    "passed_count": 1,
                    "failed_count": 1,
                    "report": backtest_filter.get_last_report(),
                },
            },
        }

    def finalize_gate_report(self, quality_gate_report, submit_result):
        report = dict(quality_gate_report or {})
        report["gate_3"] = {
            "input_count": submit_result.get("gate_3_input", 0),
            "passed_count": submit_result.get("gate_3_passed", 0),
            "failed_count": submit_result.get("gate_3_failed", 0),
        }
        return report


class FakeDb:
    async def get_klines(self, *args, **kwargs):
        return []


def test_observe_first_pipeline_skips_legacy_gate_and_intakes_all_candidates(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGY_FACTORY_OBSERVE_FIRST_ENABLED", "1")
    scheduler = FakeScheduler()
    candidates = [
        {"candidate_id": "c1", "params": {"family": "trend"}},
        {"candidate_id": "c2", "params": {"family": "quality"}},
    ]

    pkg = FakePkg()
    result = asyncio.run(
        CandidatePipeline(pkg, scheduler).run(
            candidates,
            {"date": "2026-06-04"},
            FakeDb(),
        )
    )

    observe_first = result.quality_gate_report["observe_first"]
    assert observe_first["enabled"] is True
    assert observe_first["mode"] == "no_legacy_gate"
    assert observe_first["pre_observe_gate_removed"] is True
    assert observe_first["legacy_gate_executed"] is False
    assert observe_first["legacy_funnel_executed"] is False
    assert observe_first["evidence_scoring_mode"] == "observe_first_no_legacy_gate"
    assert observe_first["gate_passed_count"] == 0
    assert observe_first["observe_intake_count"] == 2
    assert observe_first["deduped_observe_intake_count"] == 2
    assert observe_first["pre_observe_hard_reject_count"] == 0
    assert result.quality_gate_report["legacy_gate_executed"] is False
    assert result.quality_gate_report["legacy_funnel_executed"] is False
    assert result.quality_gate_report["evidence_scoring_mode"] == "observe_first_no_legacy_gate"
    assert result.backtest_report["summary"]["mode"] == "not_run_pre_observe"
    assert result.backtest_report["summary"]["pre_observe_backtest_skipped"] is True
    assert result.gate_artifact["legacy_gate_executed"] is False
    assert result.gate_artifact["legacy_funnel_executed"] is False
    assert result.gate_artifact["evidence_scoring_mode"] == "observe_first_no_legacy_gate"
    assert pkg.gated_filter_calls == 0
    assert all(candidate["observe_first_intake"] for candidate in scheduler.submitter.seen)
    assert {
        candidate["incubation_budget"]["track"] for candidate in scheduler.submitter.seen
    } == {"observe_incubation"}


def test_stock_first_execution_mode_enables_observe_first_without_env(monkeypatch) -> None:
    monkeypatch.delenv("STRATEGY_FACTORY_OBSERVE_FIRST_ENABLED", raising=False)
    scheduler = FakeScheduler()
    candidates = [
        {"candidate_id": "c1", "params": {"family": "trend"}},
        {"candidate_id": "c2", "params": {"family": "quality"}},
    ]

    pkg = FakePkg()
    result = asyncio.run(
        CandidatePipeline(pkg, scheduler).run(
            candidates,
            {"date": "2026-06-04"},
            FakeDb(),
            execution_mode="stock_first_observe_primary",
        )
    )

    assert result.quality_gate_report["observe_first"]["enabled"] is True
    assert result.quality_gate_report["observe_first"]["legacy_gate_executed"] is False
    assert result.quality_gate_report["observe_first"]["execution_mode"] == "stock_first_observe_primary"
    assert pkg.gated_filter_calls == 0
    assert len(scheduler.submitter.seen) == 2

from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.strategy_factory import StrategyFactoryScheduler
from akshare_mcp.services.strategy_factory.quality_gates import (
    GateResult,
    finalize_gate_report,
    run_gated_filter,
    run_gated_submission_pipeline,
)


def _base_gate_report() -> dict:
    return {
        "gate_0": {"passed_count": 2, "failed_count": 1, "failed": [{"strategy_type": "invalid"}]},
        "gate_1": {"passed_count": 1, "failed_count": 1, "failed": [{"strategy_type": "momentum"}]},
        "gate_2": {"input_count": 1, "passed_count": 1, "report": {"summary": {"passed_count": 1, "failed_count": 0}}},
        "gate_3": {"status": "pending_submission_gate", "passed_count": 0, "failed_count": 0, "pending_count": 1},
        "final_decision": {"stage": "gate_2", "passed_count": 1, "pending_submission_gate_count": 1},
    }


@pytest.mark.asyncio
async def test_run_gated_filter_returns_complete_gate_report(monkeypatch):
    import akshare_mcp.services.strategy_factory.quality_gates as gates_mod

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            return [candidate for candidate in candidates if candidate["candidate_id"] == "gate_2_pass"]

        def get_last_report(self):
            return {
                "summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}},
                "passed": [],
                "failed": [],
            }

    async def _fake_gate_1(candidate, _db, **_kwargs):
        if candidate["candidate_id"] == "gate_1_fail":
            return GateResult(passed=False, gate="gate_1", reasons=["avg_sharpe_below_threshold"], metrics={"avg_sharpe": 0.05})
        return GateResult(passed=True, gate="gate_1", reasons=[], metrics={"avg_sharpe": 0.42})

    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)

    candidates = [
        {"candidate_id": "gate_0_fail", "strategy_type": "not_supported", "params": {}},
        {"candidate_id": "gate_1_fail", "strategy_type": "momentum", "params": {"lookback": 10}},
        {"candidate_id": "gate_2_pass", "strategy_type": "momentum", "params": {"lookback": 20}},
    ]

    report = await run_gated_filter(candidates, MagicMock(), _DummyBacktestFilter())

    gate_report = report["gate_report"]
    assert set(gate_report.keys()) == {"gate_0", "gate_1", "gate_2", "gate_3", "final_decision"}
    assert gate_report["gate_0"]["failed_count"] == 1
    assert gate_report["gate_1"]["failed_count"] == 1
    assert gate_report["gate_2"]["passed_count"] == 1
    assert gate_report["gate_3"]["status"] == "pending_submission_gate"
    assert gate_report["final_decision"]["stage"] == "gate_2"


def test_finalize_gate_report_merges_submission_stage_decision():
    merged = finalize_gate_report(
        _base_gate_report(),
        {
            "submitted": 1,
            "passed_quality_gate": 0,
            "gate_3_passed": 0,
            "gate_3_failed": 1,
            "gate_3_provisional_passed": 0,
            "gate_3_failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
            "gate_report": {
                "gate_3": {
                    "status": "completed_submission_gate",
                    "input_count": 1,
                    "passed_count": 0,
                    "failed_count": 1,
                    "provisional_passed_count": 0,
                    "failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
                },
                "final_decision": {"stage": "gate_3", "passed_count": 0, "failed_count": 1},
            },
        },
    )

    assert merged["gate_3"]["status"] == "completed_submission_gate"
    assert merged["gate_3"]["failed_count"] == 1
    assert merged["gate_3"]["failure_reason_topn"][0]["reason_code"] == "insufficient_kline_data"
    assert merged["final_decision"]["stage"] == "gate_3"


@pytest.mark.asyncio
async def test_run_gated_submission_pipeline_unifies_gate_3_stage():
    class _DummyBacktestFilter:
        def get_last_report(self):
            return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0}}

    class _DummyDedup:
        async def deduplicate(self, candidates, _db):
            return [{**candidate, "dedup": True} for candidate in candidates]

        def get_last_report(self):
            return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}}

    class _DummySubmitter:
        async def submit(self, candidates, _snapshot, _db):
            assert candidates[0]["dedup"] is True
            return {
                "submitted": 1,
                "passed_quality_gate": 0,
                "gate_3_passed": 0,
                "gate_3_failed": 1,
                "gate_3_provisional_passed": 0,
                "gate_3_failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
                "gate_report": {
                    "gate_3": {
                        "status": "completed_submission_gate",
                        "input_count": 1,
                        "passed_count": 0,
                        "failed_count": 1,
                        "provisional_passed_count": 0,
                        "failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
                    },
                    "final_decision": {"stage": "gate_3", "passed_count": 0, "failed_count": 1},
                },
                "strategies": [{"strategy_id": "sid_1"}],
            }

    async def _fake_gate_runner(_candidates, _db, _backtest_filter, **_kwargs):
        return {
            "passed": [{"strategy_type": "momentum", "params": {"lookback": 20}}],
            "gate_report": _base_gate_report(),
        }

    result = await run_gated_submission_pipeline(
        [{"strategy_type": "momentum", "params": {"lookback": 20}}],
        {"date": "2026-03-13"},
        MagicMock(),
        backtest_filter=_DummyBacktestFilter(),
        deduplicator=_DummyDedup(),
        submitter=_DummySubmitter(),
        gated_runner=_fake_gate_runner,
    )

    assert result["gate_report"]["gate_3"]["status"] == "completed_submission_gate"
    assert result["gate_report"]["gate_3"]["failed_count"] == 1
    assert result["gate_report"]["final_decision"]["stage"] == "gate_3"
    assert result["dedup_report"]["summary"]["kept_count"] == 1
    assert result["submit_result"]["gate_3_failed"] == 1
    assert result["submitted"][0]["strategy_id"] == "sid_1"


@pytest.mark.asyncio
async def test_scheduler_persists_full_gate_report_when_gate_3_fails(monkeypatch):
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=[])
    db.save_strategy_factory_run = AsyncMock()

    class _DummyCollector:
        async def collect(self, _db):
            return {
                "date": "2026-03-13",
                "fear_greed_index": 50,
                "fg_level": "neutral",
                "listed_count": 10,
                "degraded": False,
                "completeness": {"completion_ratio": 1.0, "missing_sources": []},
                "failure_reasons": [],
            }

    class _DummySpawner:
        def spawn(self, _snapshot):
            return [{"strategy_type": "momentum", "params": {"lookback": 20}, "spawn_reason": "test"}]

        def get_last_report(self):
            return {"summary": {"candidate_count": 1, "quota_fill_count": 0, "signal_trigger_count": 1}}

    class _DummyBacktestFilter:
        def get_last_report(self):
            return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}}

    class _DummyDedup:
        async def deduplicate(self, candidates, _db):
            return candidates

        def get_last_report(self):
            return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}, "kept": [], "dropped": []}

    class _DummySubmitter:
        async def submit(self, candidates, _snapshot, _db):
            return {
                "submitted": len(candidates),
                "passed_quality_gate": 0,
                "gate_3_passed": 0,
                "gate_3_failed": 1,
                "gate_3_provisional_passed": 0,
                "gate_3_failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
                "gate_report": {
                    "gate_3": {
                        "status": "completed_submission_gate",
                        "input_count": len(candidates),
                        "passed_count": 0,
                        "failed_count": 1,
                        "provisional_passed_count": 0,
                        "failure_reason_topn": [{"reason_code": "insufficient_kline_data", "count": 1}],
                    },
                    "final_decision": {"stage": "gate_3", "passed_count": 0, "failed_count": 1},
                },
                "strategies": [],
            }

    class _DummyEliminator:
        async def check(self, _db, _fg_level):
            return []

    async def _fake_run_gated_filter(candidates, _db, _backtest_filter, **_kwargs):
        return {
            "passed": candidates,
            "summary": {
                "input_count": 1,
                "gate_0_passed": 1,
                "gate_0_failed": 0,
                "gate_1_passed": 1,
                "gate_1_failed": 0,
                "gate_2_input": 1,
                "gate_2_passed": 1,
                "gate_3_pending": 1,
            },
            "gate_report": _base_gate_report(),
        }

    async def _fake_factor_research_build(_db, _snapshot):
        return {"summary": {"active_factor_count": 0, "top_factor_names": []}, "degraded": False}

    async def _fake_run_autonomy_batches(self, _db, _snapshot):
        return {"stage": {"generated_count": 0}, "candidates": [], "experiments": []}

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyBacktestFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.run_gated_filter", _fake_run_gated_filter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.FactorResearchBuilder.build", AsyncMock(side_effect=_fake_factor_research_build))
    monkeypatch.setattr(StrategyFactoryScheduler, "_run_autonomy_batches", _fake_run_autonomy_batches)

    result = await StrategyFactoryScheduler().run_once()

    assert result["status"] == "success"
    assert result["summary"]["gate_0_passed"] == 2
    assert result["summary"]["gate_1_failed"] == 1
    assert result["summary"]["gate_3_failed"] == 1
    assert result["quality_gate"]["final_decision"]["stage"] == "gate_3"
    saved_run = db.save_strategy_factory_run.await_args.args[0]
    assert saved_run["stages"]["quality_gate"]["gate_3"]["failed_count"] == 1
    assert saved_run["gate_report"]["gate_3"]["failure_reason_topn"][0]["reason_code"] == "insufficient_kline_data"

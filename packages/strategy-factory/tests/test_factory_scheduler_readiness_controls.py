from unittest.mock import AsyncMock, MagicMock

import pytest

from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
from strategy_factory.domain.targets import _extract_target_codes_from_payload


class _RefreshingFactorResearchGateway:
    def __init__(self):
        self.build_calls = 0
        self.refresh_calls = 0

    async def build_artifact(self, db, snapshot):
        self.build_calls += 1
        if self.refresh_calls == 0:
            return {
                "degraded": True,
                "summary": {
                    "active_factor_count": 1,
                    "top_factor_names": ["value"],
                    "preferred_strategy_types": ["value_factor"],
                    "degraded": True,
                    "stale": True,
                    "freshness_days": 5,
                },
            }
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "top_factor_names": ["value"],
                "preferred_strategy_types": ["value_factor"],
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
            },
        }

    def status(self):
        return {"running": False}

    async def refresh(self):
        self.refresh_calls += 1
        return {"computed": 8, "errors": 0, "quality_flags": []}


class _StaleFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": True,
            "summary": {
                "active_factor_count": 0,
                "top_factor_names": [],
                "preferred_strategy_types": [],
                "degraded": True,
                "stale": True,
                "freshness_days": 6,
            },
        }

    def status(self):
        return {"running": False}

    async def refresh(self):
        return {"computed": 0, "errors": 1, "quality_flags": ["failed"]}


class _GovernedPoolStaleFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "ranked_factor_count": 0,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum", "ma_cross"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": True,
                "freshness_days": 7,
            },
        }

    def status(self):
        return {"running": False}


class _GovernedPoolSnapshotFactorResearchGateway:
    async def build_artifact(self, db, snapshot):
        return {
            "degraded": False,
            "source_chain": ["quant_manager.factor_candidate_registry(active_pool)", "artifact_v2"],
            "active_candidate_pool": {
                "count": 2,
                "family_summary": [
                    {
                        "family": "sentiment",
                        "count": 2,
                        "promote_count": 1,
                        "review_count": 1,
                        "avg_total_score": 82.5,
                        "max_total_score": 84.0,
                    }
                ],
                "regime_summary": [{"regime": "trend", "count": 2}],
                "top_candidates": [
                    {
                        "artifact_id": "factor_validation_001",
                        "name": "sentiment_breakout_factor",
                        "family": "sentiment",
                        "expected_regime": ["trend"],
                        "grade": "A",
                        "recommendation": "promote",
                        "total_score": 84.0,
                    }
                ],
            },
            "summary": {
                "active_factor_count": 1,
                "active_candidate_count": 2,
                "ranked_factor_count": 0,
                "top_factor_names": ["sentiment"],
                "top_candidate_names": ["sentiment_breakout_factor"],
                "active_family_names": ["sentiment"],
                "active_regime_names": ["trend"],
                "preferred_strategy_types": ["momentum"],
                "factor_source_mode": "governed_candidate_pool",
                "degraded": False,
                "stale": False,
                "freshness_days": 0,
                "latest_factor_date": "2026-03-23",
                "quality_flags": ["governed_candidate_pool_active"],
            },
        }

    def status(self):
        return {"running": False}


class _DummyCollector:
    def __init__(self, *, degraded=False, completion_ratio=1.0):
        self._degraded = degraded
        self._completion_ratio = completion_ratio

    async def collect(self, _db):
        return {
            "date": "2026-03-20",
            "fear_greed_index": 58,
            "fg_level": "neutral",
            "listed_count": 1,
            "incubating_count": 0,
            "degraded": self._degraded,
            "completeness": {
                "completion_ratio": self._completion_ratio,
                "missing_sources": [] if not self._degraded else ["factor_ic"],
            },
            "failure_reasons": [] if not self._degraded else [{"source": "factor_ic"}],
            "sources": {
                "event_driven": {"status": "success"},
            },
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [],
            },
        }


class _DummySpawner:
    def spawn(self, _snapshot):
        return []

    def get_last_report(self):
        return {"summary": {"candidate_count": 0, "quota_fill_count": 0, "signal_trigger_count": 0}}


class _DummyFilter:
    async def filter(self, candidates, _db):
        return candidates

    def get_last_report(self):
        return {
            "summary": {
                "input_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }


class _DummyDedup:
    async def deduplicate(self, candidates, _db):
        return candidates

    def get_last_report(self):
        return {"summary": {"input_count": 0, "kept_count": 0, "dropped_count": 0}, "kept": [], "dropped": []}


class _DummySubmitter:
    async def submit(self, candidates, _snapshot, _db):
        return {
            "submitted": len(candidates),
            "passed_quality_gate": len(candidates),
            "gate_3_passed": len(candidates),
            "gate_3_failed": 0,
            "gate_3_provisional_passed": 0,
            "gate_3_failure_reason_topn": [],
            "strategies": list(candidates),
        }


class _DummyEliminator:
    async def check(self, _db, _fg_level):
        return []


class _AuditSpawner:
    def spawn(self, _snapshot):
        return [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519"],
                "dedup_result": {"refresh_mode": "refresh_metrics_only"},
            },
            {
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
                "target_symbols": ["601398"],
                "dedup_result": {"refresh_mode": "spawn_revision_from_existing"},
            },
        ]

    def get_last_report(self):
        return {"summary": {"candidate_count": 2, "quota_fill_count": 0, "signal_trigger_count": 2}}


class _AuditFilter:
    def __init__(self):
        self._last_report = {"summary": {}, "passed": [], "failed": []}

    async def filter(self, candidates, _db):
        candidates[0]["backtest_result"] = {
            "passed": True,
            "reason_code": "passed",
            "validation_focus": "event_target_only",
            "contamination_summary": {"representative_included": True, "mixed_layer_used": True},
            "cost_assumptions": {},
            "position_assumption": None,
        }
        candidates[0]["backtest_metrics"] = {}
        candidates[1]["backtest_result"] = {
            "passed": True,
            "reason_code": "passed",
            "validation_focus": "target_plus_representative",
            "contamination_summary": {"representative_included": False, "mixed_layer_used": False},
            "cost_assumptions": {"commission_bps": 8},
            "position_assumption": "equal_weight_proxy",
        }
        candidates[1]["backtest_metrics"] = {"cost_assumptions": {"commission_bps": 8}}
        self._last_report = {
            "summary": {
                "input_count": 2,
                "passed_count": 2,
                "failed_count": 0,
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [
                {"strategy_type": item["strategy_type"], "backtest_result": dict(item.get("backtest_result") or {})}
                for item in candidates
            ],
            "failed": [],
        }
        return candidates

    def get_last_report(self):
        return self._last_report


class _AuditSubmitter:
    async def submit(self, candidates, _snapshot, _db):
        return {
            "submitted": len(candidates),
            "passed_quality_gate": 1,
            "gate_3_passed": 1,
            "gate_3_failed": 1,
            "gate_3_provisional_passed": 0,
            "gate_3_failure_reason_topn": [],
            "strategies": [
                {
                    "strategy_id": "sid_1",
                    "refresh_mode": "refresh_metrics_only",
                    "constraint_check": {
                        "constraint_violation": "strict_intersection_empty",
                        "expansion_applied": True,
                        "intersection_ratio": 0.5,
                    },
                    "warning_codes": ["preference_mismatch_warning"],
                    "gate_3": {
                        "passed": False,
                        "attempt_adjustment": {"penalty": 0.03},
                        "deflated_sharpe_proxy": -0.12,
                        "pbo_proxy": 0.71,
                        "multiple_testing_mode": "formal_runtime",
                        "deflated_sharpe_ratio": 0.12,
                        "pbo": 0.68,
                        "white_reality_check_pvalue": 0.24,
                        "hansen_spa_pvalue": 0.31,
                    },
                },
                {
                    "strategy_id": "sid_2",
                    "refresh_mode": "spawn_revision_from_existing",
                    "constraint_check": {
                        "constraint_violation": None,
                        "expansion_applied": False,
                        "intersection_ratio": 1.0,
                    },
                    "warning_codes": [],
                    "gate_3": {
                        "passed": True,
                        "attempt_adjustment": {"penalty": 0.05},
                        "deflated_sharpe_proxy": 0.18,
                        "pbo_proxy": 0.24,
                        "multiple_testing_mode": "formal_runtime",
                        "deflated_sharpe_ratio": 0.84,
                        "pbo": 0.19,
                        "white_reality_check_pvalue": 0.07,
                        "hansen_spa_pvalue": 0.05,
                    },
                },
            ],
        }


async def _empty_scan(_self, _db, _snapshot):
    return {"summary": {"task_count": 0, "task_sources": {}, "task_types": {}}, "tasks": []}


def _patch_factory(monkeypatch, db, collector):
    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", collector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _empty_scan)


def test_extract_target_codes_from_payload_reads_research_task_context():
    payload = {
        "research_task": {
            "target_symbols": ["601398", "601288"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600036"]},
            "event_context": {"target_symbols": ["601166"]},
        }
    }

    assert _extract_target_codes_from_payload(payload, limit=6) == ["601398", "601288", "600036", "601166"]


def test_scheduler_enriches_candidate_targeting_from_research_task():
    candidate = {
        "strategy_type": "dsl_rule",
        "params": {"dsl": {"entry": {"all": []}, "metadata": {}}},
        "tags": ["ai_generated"],
    }
    task = {
        "task_id": "event_hot_banks",
        "task_source": "event_driven",
        "target_symbols": ["601398", "601288", "600036"],
        "event_context": {
            "event_id": "evt_hot_banks",
            "theme_code": "high_dividend_banks",
            "target_symbols": ["601398", "601288", "600036"],
        },
    }

    enriched = StrategyFactoryScheduler._enrich_candidate_targeting(candidate, task)

    assert enriched["target_symbols"] == ["601398", "601288", "600036"]
    assert enriched["stock_pool"]["symbols"] == ["601398", "601288", "600036"]
    assert enriched["research_task"]["task_id"] == "event_hot_banks"
    assert enriched["event_context"]["event_id"] == "evt_hot_banks"
    assert enriched["params"]["target_symbols"] == ["601398", "601288", "600036"]
    assert enriched["params"]["stock_pool"]["symbols"] == ["601398", "601288", "600036"]
    assert enriched["params"]["dsl"]["metadata"]["target_symbols"] == ["601398", "601288", "600036"]
    assert "targeted_universe" in enriched["tags"]


@pytest.mark.asyncio
async def test_scheduler_refreshes_stale_factor_research_before_continuing(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    gateway = _RefreshingFactorResearchGateway()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=gateway)

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert gateway.refresh_calls == 1
    assert gateway.build_calls == 2
    assert result["stages"]["factor_research"]["refresh_attempted"] is True
    assert result["stages"]["factor_research"]["refresh_status"] == "success"
    assert result["summary"]["factor_research_stale"] is False
    assert result["summary"]["factor_research_refresh_status"] == "success"
    assert result["summary"]["factory_readiness_can_proceed"] is True


@pytest.mark.asyncio
async def test_scheduler_runs_startup_warmup_before_collect(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    gateway = _RefreshingFactorResearchGateway()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=gateway)
    warmup_calls = []

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    async def _fake_warmup_runner(**kwargs):
        warmup_calls.append(dict(kwargs))
        return {
            "ok": True,
            "status": "completed",
            "task_type": kwargs.get("task_type"),
            "force": bool(kwargs.get("force")),
            "matched": 1,
            "executed": 1,
            "failed": 0,
            "executed_task_ids": ["sync_core_market_1"],
            "failed_schedule_ids": [],
            "schedules": [],
        }

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setattr("strategy_factory.application.factory_scheduler.get_runtime_warmup_runner", lambda: _fake_warmup_runner)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert len(warmup_calls) == 1
    assert warmup_calls[0]["task_type"] == "core_market,factor_context"
    assert result["stages"]["warmup"]["status"] == "completed"
    assert result["stages"]["warmup"]["executed"] == 1
    assert result["summary"]["warmup_status"] == "completed"
    assert result["summary"]["warmup_executed"] == 1


@pytest.mark.asyncio
async def test_scheduler_can_hard_block_on_factory_readiness(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_StaleFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=True, completion_ratio=0.4)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    result = await scheduler.run_once()

    assert result["status"] == "skipped"
    assert result["summary"]["skip_reason"] == "readiness_blocked"
    assert result["summary"]["factory_readiness_can_proceed"] is False
    assert result["summary"]["factory_readiness_blocker_count"] >= 1
    assert "snapshot_completion_too_low" in result["stages"]["readiness"]["blockers"]


@pytest.mark.asyncio
async def test_scheduler_governed_candidate_pool_can_bypass_legacy_factor_stale_block(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_GovernedPoolStaleFactorResearchGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert result["stages"]["readiness"]["can_proceed"] is True
    assert result["stages"]["readiness"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["stages"]["readiness"]["governed_candidate_pool_active"] is True
    assert result["stages"]["readiness"]["active_candidate_count"] == 2
    assert "factor_research_history_stale_governed_pool_active" in result["stages"]["readiness"]["warnings"]
    assert result["stages"]["factor_research"]["active_family_count"] == 1
    assert result["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert result["summary"]["active_candidate_count"] == 2
    assert result["summary"]["governed_candidate_pool_active"] is True


@pytest.mark.asyncio
async def test_scheduler_snapshot_summary_persists_compact_active_pool(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(
        factor_research_gateway=_GovernedPoolSnapshotFactorResearchGateway()
    )

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)

    result = await scheduler.run_once()

    persisted = db.save_strategy_factory_run.await_args.args[0]
    compact_pool = result["snapshot_summary"]["factor_research"]["active_candidate_pool"]

    assert result["status"] == "success"
    assert compact_pool["count"] == 2
    assert compact_pool["top_candidates"][0]["artifact_id"] == "factor_validation_001"
    assert compact_pool["top_candidates"][0]["recommendation"] == "promote"
    assert compact_pool["family_summary"][0]["family"] == "sentiment"
    assert persisted["snapshot_summary"]["factor_research"]["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert persisted["snapshot_summary"]["factor_research"]["active_candidate_pool"]["top_candidates"][0]["name"] == "sentiment_breakout_factor"


@pytest.mark.asyncio
async def test_scheduler_summary_exposes_run_level_audit_metrics(monkeypatch):
    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    scheduler = StrategyFactoryScheduler(factor_research_gateway=_RefreshingFactorResearchGateway())

    class _Collector(_DummyCollector):
        def __init__(self):
            super().__init__(degraded=False, completion_ratio=1.0)

    _patch_factory(monkeypatch, db, _Collector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _AuditSpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _AuditFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _AuditSubmitter)

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert result["summary"]["attempt_adjusted_gate_failed"] == 1
    assert result["summary"]["attempt_adjusted_score_avg"] == pytest.approx(0.04)
    assert result["summary"]["constraint_violation_count"] == 1
    assert result["summary"]["target_symbol_intersection_ratio_avg"] == pytest.approx(0.75)
    assert result["summary"]["universe_expansion_count"] == 1
    assert result["summary"]["preference_mismatch_warning_count"] == 1
    assert result["summary"]["event_window_contamination_warning_count"] == 1
    assert result["summary"]["cost_audit_missing_count"] == 1
    assert result["summary"]["deflated_sharpe_proxy_avg"] == pytest.approx(0.03)
    assert result["summary"]["deflated_sharpe_ratio_avg"] == pytest.approx(0.48)
    assert result["summary"]["high_pbo_proxy_count"] == 1
    assert result["summary"]["high_pbo_count"] == 1
    assert result["summary"]["formal_multiple_testing_count"] == 2
    assert result["summary"]["weak_white_reality_check_count"] == 1
    assert result["summary"]["weak_hansen_spa_count"] == 1
    assert result["summary"]["refresh_metrics_only_count"] == 1
    assert result["summary"]["spawn_revision_from_existing_count"] == 1

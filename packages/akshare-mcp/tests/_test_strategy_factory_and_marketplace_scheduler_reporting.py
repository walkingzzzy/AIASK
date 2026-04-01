from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestStrategyFactorySchedulerReportingMixin:
    async def test_run_once_persists_factory_run_history(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_factory_run = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-06",
                    "fear_greed_index": 55,
                    "fg_level": "neutral",
                    "listed_count": 12,
                    "factor_ic": {"value": 0.05, "quality": 0.04},
                    "factor_ic_trend": {"value": "rising", "quality": "rising"},
                    "degraded": True,
                    "completeness": {"completion_ratio": 0.83, "missing_sources": ["margin_data"]},
                    "failure_reasons": [{"source": "margin_data", "reason": "timeout"}],
                }

        class _DummySpawner:
            def __init__(self):
                self.last_report = {
                    "summary": {
                        "candidate_count": 2,
                        "source_counts": {"fear_greed": 2},
                        "strategy_type_counts": {"momentum": 1, "value_factor": 1},
                        "quota_fill_count": 0,
                        "signal_trigger_count": 2,
                        "threshold_hit_count": 2,
                    }
                }

            def spawn(self, _snapshot):
                return [
                    {
                        "strategy_type": "momentum",
                        "params": {"lookback": 20},
                        "spawn_reason": "test",
                        "generation_reason": {
                            "kind": "signal_trigger",
                            "source": "fear_greed",
                            "summary": "test",
                            "trigger_signal": {"field": "fear_greed_index", "value": 55, "level": "neutral"},
                            "trigger_thresholds": [{"field": "fear_greed_index", "operator": ">=", "threshold": 30, "actual": 55, "matched": True}],
                            "quota_fill": None,
                        },
                        "trigger_signal": {"field": "fear_greed_index", "value": 55, "level": "neutral"},
                        "trigger_thresholds": [{"field": "fear_greed_index", "operator": ">=", "threshold": 30, "actual": 55, "matched": True}],
                        "quota_fill": None,
                    },
                    {
                        "strategy_type": "value_factor",
                        "params": {"lookback": 60},
                        "spawn_reason": "test-2",
                        "generation_reason": {
                            "kind": "signal_trigger",
                            "source": "fear_greed",
                            "summary": "test-2",
                            "trigger_signal": {"field": "fear_greed_index", "value": 55, "level": "neutral"},
                            "trigger_thresholds": [{"field": "fear_greed_index", "operator": ">=", "threshold": 30, "actual": 55, "matched": True}],
                            "quota_fill": None,
                        },
                        "trigger_signal": {"field": "fear_greed_index", "value": 55, "level": "neutral"},
                        "trigger_thresholds": [{"field": "fear_greed_index", "operator": ">=", "threshold": 30, "actual": 55, "matched": True}],
                        "quota_fill": None,
                    },
                ]

            def get_last_report(self):
                return self.last_report

        class _DummyFilter:
            def __init__(self):
                self.last_report = {
                    "summary": {
                        "input_count": 2,
                        "passed_count": 1,
                        "failed_count": 1,
                        "strategy_type_counts": {"momentum": 1, "value_factor": 1},
                        "passed_strategy_type_counts": {"momentum": 1},
                        "failed_strategy_type_counts": {"value_factor": 1},
                        "failed_reason_counts": {"sharpe_below_threshold": 1},
                        "thresholds_by_type": {
                            "momentum": {"sharpe_min": 0.35, "mdd_max": 0.32, "trades_min": 4, "min_samples": 3},
                            "value_factor": {"sharpe_min": 0.25, "mdd_max": 0.30, "trades_min": 3, "min_samples": 3},
                        },
                    },
                    "passed": [],
                    "failed": [],
                }

            async def filter(self, candidates, _db):
                candidates[0]["backtest_result"] = {
                    "passed": True,
                    "reason_code": "passed",
                    "reason": "通过初筛回测",
                    "thresholds": {"sharpe_min": 0.35, "mdd_max": 0.32, "trades_min": 4, "min_samples": 3},
                    "metrics": {"sharpe_ratio": 0.42, "total_return": 0.12, "max_drawdown": 0.18, "win_rate": 0.56, "trades_count": 6},
                }
                candidates[0]["backtest_metrics"] = candidates[0]["backtest_result"]["metrics"]
                candidates[1]["backtest_result"] = {
                    "passed": False,
                    "reason_code": "sharpe_below_threshold",
                    "reason": "Sharpe 0.2200 低于阈值 0.25",
                    "thresholds": {"sharpe_min": 0.25, "mdd_max": 0.30, "trades_min": 3, "min_samples": 3},
                    "metrics": {"sharpe_ratio": 0.22, "total_return": 0.06, "max_drawdown": 0.12, "win_rate": 0.51, "trades_count": 5},
                }
                return [candidates[0]]

            def get_last_report(self):
                return self.last_report

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {
                    "submitted": len(candidates),
                    "passed_quality_gate": len(candidates),
                    "gate_3_passed": len(candidates),
                    "gate_3_failed": 0,
                    "gate_3_provisional_passed": 0,
                    "gate_3_failure_reason_topn": [],
                    "strategies": [],
                }

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        from strategy_factory.application.factor_research import FactorResearchBuilder as _FRB

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)

        with patch.object(
            _FRB, "_load_governed_candidate_pool",
            new_callable=AsyncMock, return_value={"available": False, "reason": "test_isolation"},
        ):
            scheduler = StrategyFactoryScheduler()
            result = await scheduler.run_once()

        assert result["status"] == "partial"
        assert result["summary"]["partial_stage_count"] >= 1
        db.save_strategy_factory_run.assert_awaited_once()
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run["run_id"] == result["run_id"]
        assert saved_run["summary"]["candidates_spawned"] == 2
        assert saved_run["summary"]["quota_fill_candidates"] == 0
        assert saved_run["summary"]["signal_trigger_candidates"] == 2
        assert saved_run["summary"]["candidates_passed_backtest"] == 1
        assert saved_run["summary"]["candidates_failed_backtest"] == 1
        assert saved_run["summary"]["backtest_failed_reason_counts"]["sharpe_below_threshold"] == 1
        assert saved_run["summary"]["gate_3_passed"] == 1
        assert saved_run["summary"]["gate_3_failed"] == 0
        assert saved_run["summary"]["gate_3_provisional_passed"] == 0
        assert saved_run["summary"]["gate_3_failure_reason_topn"] == []
        assert saved_run["summary"]["factor_research_used"] is True
        assert saved_run["summary"]["active_factor_count"] == 2
        assert saved_run["summary"]["top_factor_names"][:2] == ["value", "quality"]
        assert saved_run["summary"]["factor_research_degraded"] is False
        assert saved_run["snapshot_summary"]["degraded"] is True
        assert saved_run["snapshot_summary"]["completion_ratio"] == 0.83
        assert saved_run["stages"]["factor_research"]["active_factor_count"] == 2
        assert saved_run["stages"]["spawn"]["count"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["candidate_count"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["source_counts"]["fear_greed"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["threshold_hit_count"] == 2
        assert saved_run["stages"]["backtest"]["input_count"] == 2
        assert saved_run["stages"]["backtest"]["summary"]["failed_reason_counts"]["sharpe_below_threshold"] == 1
        assert saved_run["stages"]["backtest"]["summary"]["thresholds_by_type"]["momentum"]["sharpe_min"] == 0.35
        assert saved_run["stages"]["submit"]["gate_3_passed"] == 1

    def test_strategy_pipeline_initial_input_includes_factor_research_summary(self):
        from akshare_mcp.services.strategy_pipeline import MultiStageStrategyPipeline

        initial = MultiStageStrategyPipeline._build_initial_input(
            {
                "date": "2026-03-08",
                "factor_research": {
                    "active_factors": ["value", "quality"],
                    "preferred_strategy_types": ["value_factor", "quality_factor"],
                    "summary": {"top_factor_names": ["value", "quality"]},
                    "degraded": False,
                },
            }
        )

        assert initial["factor_research"]["active_factors"] == ["value", "quality"]
        assert initial["factor_research"]["top_factor_names"] == ["value", "quality"]
        assert initial["factor_research"]["preferred_strategy_types"] == ["value_factor", "quality_factor"]

    def test_strategy_pipeline_initial_input_accepts_collector_field_aliases(self):
        from akshare_mcp.services.strategy_pipeline import MultiStageStrategyPipeline

        initial = MultiStageStrategyPipeline._build_initial_input(
            {
                "snapshot_date": "2026-03-08",
                "fear_greed_index": 67,
                "fg_level": "greed",
                "north_fund_3d_net": 123456789.0,
            }
        )

        assert initial["market_snapshot"]["date"] == "2026-03-08"
        assert initial["market_snapshot"]["fear_greed"] == 67
        assert initial["market_snapshot"]["fear_greed_index"] == 67
        assert initial["market_snapshot"]["sentiment"] == "greed"
        assert initial["market_snapshot"]["north_fund"]["net_3d"] == 123456789.0

    def test_rule_generator_prioritizes_factor_research_preferences(self):
        from akshare_mcp.services.strategy_autonomy import RuleStrategyGenerator

        specs = RuleStrategyGenerator().generate(
            {
                "fear_greed_index": 72,
                "factor_research": {
                    "preferred_strategy_types": ["quality_factor", "value_factor"],
                    "summary": {"top_factor_names": ["quality", "value"]},
                    "degraded": False,
                },
            },
            limit=2,
        )

        assert [spec.strategy_type for spec in specs] == ["quality_factor", "value_factor"]
        assert specs[0].metadata["generation_reason"]["source"] == "factor_research"

    def test_reviewer_uses_factor_research_alignment(self):
        from akshare_mcp.services.strategy_autonomy import MultiAgentStrategyReviewer, StrategySpec

        reviewer = MultiAgentStrategyReviewer()
        spec = StrategySpec(strategy_type="quality_factor", params={"lookback": 50}, name="q")
        _, aligned = reviewer.review(
            spec,
            {
                "fear_greed_index": 70,
                "factor_research": {
                    "preferred_strategy_types": ["quality_factor", "value_factor"],
                    "summary": {"top_factor_names": ["quality"]},
                    "degraded": False,
                },
            },
        )
        _, baseline = reviewer.review(spec, {"fear_greed_index": 70})

        assert aligned["planner_context"]["aligned"] is True
        assert aligned["planner_score"] > baseline["planner_score"]

    @pytest.mark.asyncio
    async def test_run_once_persists_external_llm_observability(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_factory_run = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-06",
                    "fear_greed_index": 55,
                    "fg_level": "neutral",
                    "listed_count": 1,
                    "incubating_count": 0,
                    "degraded": False,
                    "completeness": {"completion_ratio": 1.0, "missing_sources": []},
                    "failure_reasons": [],
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
                return {"summary": {"input_count": 0, "passed_count": 0, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 0, "kept_count": 0, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {
                    "submitted": 0,
                    "passed_quality_gate": 0,
                    "gate_3_passed": 0,
                    "gate_3_failed": 0,
                    "gate_3_provisional_passed": 0,
                    "gate_3_failure_reason_topn": [],
                    "strategies": [],
                }

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        class _DummyAutonomy:
            async def generate_factory_candidates(self, _db, _snapshot, limit=3):
                return {
                    'generated_count': 0,
                    'experiments': [],
                    'task_run_id': 99,
                    'candidates': [],
                    'llm_generation': {
                        'external_provider': {
                            'status': 'failed',
                            'requests': [{'request_limit': 4, 'status': 'failed'}],
                            'selected_count': 0,
                            'last_error_type': 'ReadTimeout',
                            'last_error': 'timeout',
                            'elapsed_seconds': 12.5,
                        },
                    },
                }

        from strategy_factory.application.factor_research import FactorResearchBuilder as _FRB

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        with patch.object(
            _FRB, "_load_governed_candidate_pool",
            new_callable=AsyncMock, return_value={"available": False, "reason": "test_isolation"},
        ):
            result = await StrategyFactoryScheduler().run_once()

        assert result['status'] == 'partial'
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['summary']['failed_stage_count'] >= 1
        assert saved_run['stages']['autonomy']['status'] == 'failed'
        assert saved_run['stages']['autonomy']['external_llm_status'] == 'failed'
        assert saved_run['stages']['autonomy']['external_llm_last_error_type'] == 'ReadTimeout'
        assert saved_run['summary']['external_llm_status'] == 'failed'
        assert saved_run['summary']['external_llm_last_error_type'] == 'ReadTimeout'
        assert saved_run['summary']['external_llm_elapsed_seconds'] == 12.5
        assert saved_run['summary']['gate_3_passed'] == 0
        assert saved_run['summary']['gate_3_failed'] == 0
        assert saved_run['summary']['gate_3_provisional_passed'] == 0
        assert saved_run['summary']['gate_3_failure_reason_topn'] == []
        assert saved_run['stages']['submit']['gate_3_passed'] == 0

    @pytest.mark.asyncio
    async def test_run_once_persists_factor_research_back_to_daily_snapshot(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_factory_run = AsyncMock()
        db.save_daily_snapshot = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-09",
                    "fear_greed_index": 58,
                    "fg_level": "neutral",
                    "listed_count": 1,
                    "incubating_count": 0,
                    "degraded": False,
                    "completeness": {"completion_ratio": 1.0, "missing_sources": []},
                    "failure_reasons": [],
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
                return {"summary": {"input_count": 0, "passed_count": 0, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 0, "kept_count": 0, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {
                    "submitted": 0,
                    "passed_quality_gate": 0,
                    "gate_3_passed": 0,
                    "gate_3_failed": 0,
                    "gate_3_provisional_passed": 0,
                    "gate_3_failure_reason_topn": [],
                    "strategies": [],
                }

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        async def _fake_factor_research_build(_db, _snapshot):
            return {
                "active_factors": ["value"],
                "preferred_strategy_types": ["value_factor"],
                "summary": {"active_factor_count": 1, "top_factor_names": ["value"], "preferred_strategy_types": ["value_factor"]},
                "degraded": False,
            }

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.FactorResearchBuilder.build", AsyncMock(side_effect=_fake_factor_research_build))

        await StrategyFactoryScheduler().run_once()

        persisted_snapshot = db.save_daily_snapshot.await_args.args[1]
        assert persisted_snapshot["factor_research"]["active_factors"] == ["value"]
        assert persisted_snapshot["factor_research"]["preferred_strategy_types"] == ["value_factor"]

    @pytest.mark.asyncio
    async def test_run_autonomy_batches_records_pre_generation_failures(self, monkeypatch):
        scheduler = StrategyFactoryScheduler()
        db = MagicMock()

        class _DummyScanner:
            async def scan(self, _db, _snapshot):
                return {
                    "tasks": [{
                        "task_id": "task_fail_1",
                        "task_key": "task_fail_1",
                        "task_source": "snapshot",
                        "opportunity_type": "factor_acceleration",
                    }],
                    "summary": {"task_sources": {"snapshot": 1}, "event_task_count": 0},
                }

        class _DummyAutonomy:
            generation_service = MagicMock()

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("evidence persistence failed")

        monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner", _DummyScanner)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())
        monkeypatch.setattr(scheduler, "_persist_task_evidence", _boom)

        report = await scheduler._run_autonomy_batches(db, {"date": "2026-03-09", "fear_greed_index": 50})

        assert report["stage"]["failed_task_count"] == 1
        assert report["stage"]["external_llm_status"] == "failed"
        assert report["stage"]["persistence_failure_count"] == 1
        assert report["stage"]["task_results"][0]["status"] == "failed"
        assert report["stage"]["task_results"][0]["lifecycle_summary"]["failed_phase"] == "generating"

from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestStrategyFactorySchedulerScannerMixin:
    async def test_market_opportunity_scanner_creates_multiple_research_tasks(self):
        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "600519", "name": "贵州茅台", "industry": "白酒", "sector": "消费", "market": "SH", "market_cap": 2_000_000_000_000},
            {"code": "300750", "name": "宁德时代", "industry": "新能源", "sector": "电池", "market": "SZ", "market_cap": 1_100_000_000_000},
            {"code": "002594", "name": "比亚迪", "industry": "新能源", "sector": "整车", "market": "SZ", "market_cap": 900_000_000_000},
            {"code": "688981", "name": "中芯国际", "industry": "芯片", "sector": "半导体", "market": "SH", "market_cap": 700_000_000_000},
            {"code": "002371", "name": "北方华创", "industry": "芯片", "sector": "设备", "market": "SZ", "market_cap": 400_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-08",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["芯片", "新能源"],
            "cold_sectors": ["银行"],
            "factor_ic_trend": {"growth": "rising", "value": "falling"},
        })

        tasks = report["tasks"]
        assert report["summary"]["task_count"] == len(tasks)
        assert len(tasks) >= 4
        assert tasks[0]["opportunity_type"] == "trend_expansion"
        assert any(task["opportunity_type"] == "sector_breakout" for task in tasks)
        assert any(task["opportunity_type"] == "factor_acceleration" for task in tasks)
        assert any("芯片" in list(task.get("focus_industries") or []) for task in tasks)
        assert any(code in {"688981", "002371", "300750", "002594"} for code in tasks[0]["target_symbols"])

    @pytest.mark.asyncio
    async def test_market_opportunity_scanner_prefers_event_driven_tasks(self):
        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 720_000_000_000},
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_550_000_000_000},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_200_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-09",
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [{
                    "event_id": "evt_oil_1",
                    "event_type": "geopolitics",
                    "event_name": "中东战事升级",
                    "summary": "中东局势升级提升原油供给扰动预期。",
                    "direction": "positive",
                    "confidence": 0.92,
                    "intensity": 0.88,
                    "horizon": "swing_5_20d",
                    "themes": [{
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "signal_count": 3,
                        "target_symbols": ["601857", "600938", "600028"],
                        "supporting_reasons": ["油价中枢抬升", "供给扰动强化"],
                        "score_summary": {
                            "avg_final_score": 0.87,
                            "max_final_score": 0.93,
                            "top_symbols": ["601857", "600938", "600028"],
                        },
                    }],
                }],
            },
        })

        tasks = report["tasks"]
        assert report["summary"]["task_sources"]["event_driven"] >= 1
        assert report["summary"]["task_sources"].get("snapshot", 0) >= 1
        assert tasks[0]["task_source"] == "event_driven"
        assert tasks[0]["event_id"] == "evt_oil_1"
        assert tasks[0]["theme_code"] == "upstream_oil_gas"
        assert tasks[0]["target_symbols"][:2] == ["601857", "600938"]
        assert tasks[0]["opportunity_type"] == "sector_breakout"
        assert tasks[0]["direction"] == "positive"
        assert any(task.get("task_source") == "snapshot" for task in tasks)

    @pytest.mark.asyncio
    async def test_market_opportunity_scanner_mixes_distinct_snapshot_tasks_with_event_priority(self):
        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 720_000_000_000},
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_550_000_000_000},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_200_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-09",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["石油石化"],
            "factor_ic_trend": {"quality": "rising"},
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [{
                    "event_id": "evt_oil_1",
                    "event_type": "geopolitics",
                    "event_name": "中东战事升级",
                    "summary": "中东局势升级提升原油供给扰动预期。",
                    "direction": "positive",
                    "confidence": 0.92,
                    "intensity": 0.88,
                    "horizon": "swing_5_20d",
                    "themes": [{
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "signal_count": 3,
                        "target_symbols": ["601857", "600938", "600028"],
                        "score_summary": {
                            "avg_final_score": 0.87,
                            "max_final_score": 0.93,
                            "top_symbols": ["601857", "600938", "600028"],
                        },
                    }],
                }],
            },
        })

        tasks = report["tasks"]
        snapshot_tasks = [task for task in tasks if task.get("task_source") == "snapshot"]

        assert tasks[0]["task_source"] == "event_driven"
        assert snapshot_tasks
        assert {task["opportunity_type"] for task in snapshot_tasks} <= {"trend_expansion", "factor_acceleration", "industry_leadership", "rotation_balanced", "mean_reversion"}
        assert all(task["opportunity_type"] != "sector_breakout" for task in snapshot_tasks)

    @pytest.mark.asyncio
    async def test_market_opportunity_scanner_keeps_non_overlapping_sector_breakout_snapshot_tasks(self):
        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 720_000_000_000},
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_550_000_000_000},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_200_000_000_000},
            {"code": "688981", "name": "中芯国际", "industry": "芯片", "sector": "半导体", "market": "SH", "market_cap": 700_000_000_000},
            {"code": "002371", "name": "北方华创", "industry": "芯片", "sector": "设备", "market": "SZ", "market_cap": 400_000_000_000},
            {"code": "300750", "name": "宁德时代", "industry": "新能源", "sector": "电池", "market": "SZ", "market_cap": 1_100_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-09",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["芯片", "新能源", "石油石化"],
            "factor_ic_trend": {"quality": "rising"},
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [{
                    "event_id": "evt_oil_1",
                    "event_type": "geopolitics",
                    "event_name": "中东战事升级",
                    "summary": "中东局势升级提升原油供给扰动预期。",
                    "direction": "positive",
                    "confidence": 0.92,
                    "intensity": 0.88,
                    "horizon": "swing_5_20d",
                    "themes": [{
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "signal_count": 3,
                        "target_symbols": ["601857", "600938", "600028"],
                        "score_summary": {
                            "avg_final_score": 0.87,
                            "max_final_score": 0.93,
                            "top_symbols": ["601857", "600938", "600028"],
                        },
                    }],
                }],
            },
        })

        snapshot_breakouts = [
            task for task in report["tasks"]
            if task.get("task_source") == "snapshot" and task.get("opportunity_type") == "sector_breakout"
        ]

        assert snapshot_breakouts
        assert any(set(task.get("focus_industries") or []) & {"芯片", "新能源"} for task in snapshot_breakouts)
        assert all(not (set(task.get("focus_industries") or []) & {"石油石化"}) for task in snapshot_breakouts)

    @pytest.mark.asyncio
    async def test_market_opportunity_scanner_uses_factor_research_active_factors(self):
        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_550_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-09",
            "fear_greed_index": 55,
            "fg_level": "neutral",
            "factor_ic_trend": {},
            "factor_research": {
                "active_factors": ["quality"],
                "positive_rising_factors": ["quality"],
            },
            "event_driven": {"enabled": False, "event_count": 0, "tasks_ready_count": 0, "events": []},
        })

        factor_tasks = [task for task in report["tasks"] if task.get("opportunity_type") == "factor_acceleration"]
        assert factor_tasks
        assert factor_tasks[0]["factor_name"] == "quality"

    @pytest.mark.asyncio
    async def test_market_opportunity_scanner_boosts_generation_limit_for_strong_event_evidence(self):
        from akshare_mcp.services.strategy_factory.constants import AUTONOMY_CANDIDATES_PER_TASK, EVENT_TASK_GENERATION_LIMIT_MAX

        scanner = MarketOpportunityScanner()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_550_000_000_000},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1_200_000_000_000},
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 720_000_000_000},
        ])

        report = await scanner.scan(db, {
            "date": "2026-03-09",
            "event_driven": {
                "enabled": True,
                "event_count": 1,
                "tasks_ready_count": 1,
                "events": [{
                    "event_id": "evt_oil_boost",
                    "event_type": "geopolitics",
                    "event_name": "原油供给扰动升级",
                    "summary": "原油供给扰动显著强化。",
                    "direction": "positive",
                    "confidence": 0.95,
                    "intensity": 0.91,
                    "horizon": "swing_5_20d",
                    "themes": [{
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "signal_count": 5,
                        "target_symbols": ["601857", "600938", "600028"],
                        "supporting_reasons": ["油价中枢抬升", "供给扰动强化", "库存回补预期"],
                        "score_summary": {
                            "avg_final_score": 0.92,
                            "max_final_score": 0.97,
                            "top_symbols": ["601857", "600938", "600028"],
                        },
                    }],
                }],
            },
        })

        boosted_task = report["tasks"][0]

        assert boosted_task["task_source"] == "event_driven"
        assert boosted_task["priority"] >= 100
        assert boosted_task["generation_limit"] > AUTONOMY_CANDIDATES_PER_TASK
        assert boosted_task["generation_limit"] <= EVENT_TASK_GENERATION_LIMIT_MAX

    @pytest.mark.asyncio
    async def test_generate_for_research_task_passes_event_generation_limit_to_autonomy(self):
        from akshare_mcp.services.strategy_factory.constants import EVENT_TASK_GENERATION_LIMIT_MAX

        scheduler = StrategyFactoryScheduler()
        captured = {}

        class _DummyAutonomy:
            async def generate_factory_candidates(self, db, snapshot, *, limit, research_task, source):
                captured.update({
                    "db": db,
                    "snapshot": snapshot,
                    "limit": limit,
                    "research_task": research_task,
                    "source": source,
                })
                return {"generated_count": 0, "candidates": [], "experiments": []}

        db = MagicMock()
        snapshot = {"date": "2026-03-10"}
        task = {
            "task_id": "task_evt_oil",
            "opportunity_type": "sector_breakout",
            "generation_limit": EVENT_TASK_GENERATION_LIMIT_MAX,
        }

        await scheduler._generate_for_research_task(_DummyAutonomy(), db, snapshot, task)

        assert captured["limit"] == EVENT_TASK_GENERATION_LIMIT_MAX
        assert captured["research_task"] == task
        assert captured["source"] == "strategy_factory:sector_breakout"

    @pytest.mark.asyncio
    async def test_generate_for_research_task_respects_task_hard_cap(self, monkeypatch):
        import strategy_factory.application._factory_scheduler_loop as scheduler_loop_mod

        scheduler = StrategyFactoryScheduler()
        captured = {}

        class _DummyAutonomy:
            async def generate_factory_candidates(self, db, snapshot, *, limit, research_task, source):
                captured.update({
                    "db": db,
                    "snapshot": snapshot,
                    "limit": limit,
                    "research_task": research_task,
                    "source": source,
                })
                return {"generated_count": 0, "candidates": [], "experiments": []}

        monkeypatch.setattr(scheduler_loop_mod, "AUTONOMY_TASK_HARD_CAP", 6)
        db = MagicMock()
        snapshot = {"date": "2026-03-10"}
        task = {
            "task_id": "task_high_limit",
            "opportunity_type": "factor_acceleration",
            "generation_limit": 20,
        }

        await scheduler._generate_for_research_task(_DummyAutonomy(), db, snapshot, task)

        assert captured["limit"] == 6
        assert captured["research_task"] == task
        assert captured["source"] == "strategy_factory:factor_acceleration"

    @pytest.mark.asyncio
    async def test_run_once_records_autonomy_task_counts(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_task_run = AsyncMock(side_effect=[{"id": 101}, {"id": 102}])
        db.update_strategy_task_run = AsyncMock()
        db.save_strategy_factory_run = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-08",
                    "fear_greed_index": 62,
                    "fg_level": "greed",
                    "listed_count": 5,
                    "incubating_count": 1,
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
                return {"summary": {"input_count": 2, "passed_count": 2, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 2, "kept_count": 2, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {"submitted": len(candidates), "passed_quality_gate": len(candidates), "strategies": candidates}

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        class _DummyAutonomy:
            async def generate_factory_candidates(self, _db, _snapshot, limit=3, research_task=None, source='strategy_factory'):
                target_symbols = list((research_task or {}).get('target_symbols') or [])
                return {
                    'generated_count': 1,
                    'reviewed_count': 1,
                    'experiments': [{'task_id': (research_task or {}).get('task_id'), 'source': source}],
                    'candidates': [{
                        'name': f"candidate_{(research_task or {}).get('task_id')}",
                        'strategy_type': 'dsl_rule',
                        'params': {'dsl': {'metadata': {'target_symbols': target_symbols}}},
                        'generator_type': 'external_llm',
                        'target_symbols': target_symbols,
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': target_symbols},
                        'tags': ['external_llm', 'ai_generated'],
                    }],
                    'llm_generation': {
                        'external_provider': {
                            'status': 'succeeded' if (research_task or {}).get('task_id') == 'task_hot_chip' else 'fallback_only',
                            'requests': [{'request_limit': limit, 'status': 'succeeded'}],
                            'selected_count': 1,
                            'elapsed_seconds': 0.8,
                        },
                    },
                }

        async def _scan(_self, _db, _snapshot):
            return {
                'summary': {
                    'task_count': 2,
                    'task_types': {'sector_breakout': 1, 'oversold_repair': 1},
                    'themes': ['event_theme_芯片', 'cold_sector_银行'],
                    'task_sources': {'event_driven': 1, 'snapshot': 1},
                    'event_task_count': 1,
                },
                'tasks': [
                    {'task_id': 'task_hot_chip', 'task_key': 'hot:chip', 'task_source': 'event_driven', 'theme': 'event_theme_芯片', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371'], 'generation_limit': 2},
                    {'task_id': 'task_cold_bank', 'task_key': 'cold:bank', 'task_source': 'snapshot', 'theme': 'cold_sector_银行', 'opportunity_type': 'oversold_repair', 'target_symbols': ['600036'], 'generation_limit': 1},
                ],
            }

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _scan)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        result = await StrategyFactoryScheduler().run_once()

        assert result['status'] == 'partial'
        assert result['summary']['autonomy_task_count'] == 2
        assert result['summary']['autonomy_completed_task_count'] == 2
        assert result['summary']['autonomy_failed_task_count'] == 0
        assert result['summary']['autonomy_generated'] == 2
        assert result['summary']['event_task_count'] == 1
        assert result['summary']['snapshot_task_count'] == 1
        assert result['summary']['task_source_counts'] == {'event_driven': 1, 'snapshot': 1}
        assert result['summary']['scanner_task_types'] == {'sector_breakout': 1, 'oversold_repair': 1}
        assert result['summary']['event_snapshot_mixed'] is True
        briefs = result['summary']['autonomy_task_briefs']
        assert len(briefs) == 2
        assert briefs[0]['task_id'] == 'task_hot_chip'
        assert briefs[0]['task_source'] == 'event_driven'
        assert briefs[0]['opportunity_type'] == 'sector_breakout'
        assert briefs[0]['generation_limit'] == 2
        assert briefs[0]['generated_count'] == 1
        assert briefs[1]['task_id'] == 'task_cold_bank'
        assert briefs[1]['task_source'] == 'snapshot'
        assert briefs[1]['opportunity_type'] == 'oversold_repair'
        assert briefs[1]['generation_limit'] == 1
        assert briefs[1]['generated_count'] == 1
        assert result['summary']['external_llm_status'] == 'succeeded'
        assert db.save_strategy_task_run.await_count == 2
        assert db.update_strategy_task_run.await_count == 2
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['summary']['partial_stage_count'] >= 1
        assert saved_run['stages']['autonomy']['task_count'] == 2
        assert saved_run['stages']['autonomy']['completed_task_count'] == 2
        assert saved_run['stages']['autonomy']['failed_task_count'] == 0
        assert saved_run['stages']['autonomy']['status'] == 'completed'
        assert saved_run['stages']['autonomy']['external_llm_status'] == 'succeeded'
        assert saved_run['stages']['autonomy']['external_llm_status_counts']['succeeded'] == 1
        assert saved_run['stages']['autonomy']['external_llm_status_counts']['fallback_only'] == 1

    @pytest.mark.asyncio
    async def test_run_once_aggregates_autonomy_lifecycle_state_and_phase_metrics(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_task_run = AsyncMock(side_effect=[{"id": 401}, {"id": 402}])
        db.update_strategy_task_run = AsyncMock()
        db.save_strategy_factory_run = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-10",
                    "fear_greed_index": 60,
                    "fg_level": "neutral",
                    "listed_count": 3,
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
                return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {"submitted": len(candidates), "passed_quality_gate": len(candidates), "strategies": candidates}

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        class _DummyAutonomy:
            async def generate_factory_candidates(self, _db, _snapshot, limit=3, research_task=None, source='strategy_factory'):
                task_id = (research_task or {}).get('task_id')
                if task_id == 'task_fail':
                    raise RuntimeError('synthetic autonomy failure')
                return {
                    'generated_count': 1,
                    'reviewed_count': 1,
                    'experiments': [{'task_id': task_id, 'source': source}],
                    'candidates': [{
                        'name': f"candidate_{task_id}",
                        'strategy_type': 'dsl_rule',
                        'params': {'dsl': {'metadata': {'target_symbols': ['688981']}}},
                        'generator_type': 'external_llm',
                        'target_symbols': ['688981'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                        'tags': ['external_llm', 'ai_generated'],
                    }],
                    'lifecycle': {
                        'state': 'completed',
                        'current_phase': 'completed',
                        'failed_phase': None,
                        'terminal_phase': 'completed',
                        'phase_order': ['prepared', 'generating', 'reviewing', 'recording', 'submitting', 'completed'],
                        'phase_status_counts': {'completed': 5, 'skipped': 1},
                        'completed_phase_count': 5,
                        'event_count': 6,
                        'events': [],
                    },
                    'llm_generation': {
                        'external_provider': {
                            'status': 'succeeded',
                            'requests': [{'request_limit': limit, 'status': 'succeeded'}],
                            'selected_count': 1,
                            'elapsed_seconds': 0.2,
                        },
                    },
                }

        async def _scan(_self, _db, _snapshot):
            return {
                'summary': {
                    'task_count': 2,
                    'task_sources': {'snapshot': 2},
                    'task_types': {'sector_breakout': 1, 'oversold_repair': 1},
                },
                'tasks': [
                    {'task_id': 'task_ok', 'task_key': 'ok', 'task_source': 'snapshot', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981'], 'generation_limit': 1},
                    {'task_id': 'task_fail', 'task_key': 'fail', 'task_source': 'snapshot', 'opportunity_type': 'oversold_repair', 'target_symbols': ['600036'], 'generation_limit': 1},
                ],
            }

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _scan)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        result = await StrategyFactoryScheduler().run_once()

        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert result['status'] == 'partial'
        assert saved_run['summary']['partial_stage_count'] >= 1
        assert saved_run['stages']['autonomy']['lifecycle_state_counts']['completed'] == 1
        assert saved_run['stages']['autonomy']['lifecycle_state_counts']['failed'] == 1
        assert saved_run['stages']['autonomy']['phase_status_counts']['completed'] >= 5
        assert saved_run['stages']['autonomy']['phase_status_counts']['failed'] >= 1
        assert saved_run['stages']['autonomy']['failed_phase_counts']['generating'] == 1
        assert saved_run['stages']['autonomy']['observable_phases'] == ['prepared', 'generating', 'reviewing', 'recording', 'submitting', 'completed']
        assert result['summary']['autonomy_lifecycle_state_counts']['completed'] == 1
        assert result['summary']['autonomy_lifecycle_state_counts']['failed'] == 1
        assert result['summary']['autonomy_phase_status_counts']['failed'] >= 1

    @pytest.mark.asyncio
    async def test_run_once_treats_skipped_external_llm_as_successful_local_completion(self, monkeypatch):
        db = MagicMock()
        db.save_strategy_task_run = AsyncMock(return_value={"id": 201})
        db.update_strategy_task_run = AsyncMock()
        db.save_strategy_factory_run = AsyncMock()

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-08",
                    "fear_greed_index": 55,
                    "fg_level": "neutral",
                    "listed_count": 0,
                    "incubating_count": 2,
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
                return {"submitted": 0, "passed_quality_gate": 0, "strategies": []}

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        class _DummyAutonomy:
            async def generate_factory_candidates(self, _db, _snapshot, limit=3, research_task=None, source='strategy_factory'):
                return {
                    'generated_count': 0,
                    'reviewed_count': 0,
                    'experiments': [],
                    'candidates': [],
                    'llm_generation': {
                        'external_provider': {
                            'status': 'skipped',
                            'requests': [],
                            'selected_count': 0,
                            'elapsed_seconds': 0.0,
                        },
                    },
                }

        async def _scan(_self, _db, _snapshot):
            return {
                'summary': {'task_count': 1, 'task_types': {'sector_breakout': 1}, 'themes': ['hot_sector_银行']},
                'tasks': [
                    {'task_id': 'task_bank', 'task_key': 'bank', 'theme': 'hot_sector_银行', 'opportunity_type': 'sector_breakout', 'target_symbols': ['600036'], 'generation_limit': 1},
                ],
            }

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _scan)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        result = await StrategyFactoryScheduler().run_once()

        assert result['status'] == 'partial'
        assert result['summary']['external_llm_status'] == 'succeeded'
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['summary']['partial_stage_count'] >= 1
        assert saved_run['stages']['autonomy']['status'] == 'completed'
        assert saved_run['stages']['autonomy']['external_llm_status'] == 'succeeded'
        assert saved_run['stages']['autonomy']['external_llm_status_counts']['skipped'] == 1

    @pytest.mark.asyncio
    async def test_run_once_persists_event_task_evidence_and_summary_counts(self, monkeypatch):
        db = MagicMock()
        saved_evidence = []

        async def _save_evidence(item):
            payload = dict(item)
            payload["id"] = len(saved_evidence) + 1
            saved_evidence.append(payload)
            return payload

        db.save_strategy_task_run = AsyncMock(return_value={"id": 301})
        db.update_strategy_task_run = AsyncMock()
        db.save_strategy_factory_run = AsyncMock()
        db.save_factory_task_evidence = AsyncMock(side_effect=_save_evidence)

        class _DummyCollector:
            async def collect(self, _db):
                return {
                    "date": "2026-03-09",
                    "fear_greed_index": 68,
                    "fg_level": "greed",
                    "listed_count": 6,
                    "incubating_count": 1,
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
                return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

        class _DummyDedup:
            async def deduplicate(self, candidates, _db):
                return candidates

            def get_last_report(self):
                return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}, "kept": [], "dropped": []}

        class _DummySubmitter:
            async def submit(self, candidates, _snapshot, _db):
                return {"submitted": len(candidates), "passed_quality_gate": len(candidates), "strategies": candidates}

        class _DummyEliminator:
            async def check(self, _db, _fg_level):
                return []

        class _DummyAutonomy:
            async def generate_factory_candidates(self, _db, _snapshot, limit=3, research_task=None, source='strategy_factory'):
                task = dict(research_task or {})
                target_symbols = list(task.get('target_symbols') or [])
                return {
                    'generated_count': 1,
                    'reviewed_count': 1,
                    'experiments': [{'task_id': task.get('task_id'), 'source': source, 'event_id': task.get('event_id')}],
                    'candidates': [{
                        'experiment_id': 'exp_event_1',
                        'name': 'candidate_event_task',
                        'strategy_type': 'dsl_rule',
                        'params': {'dsl': {'metadata': {'target_symbols': target_symbols}}},
                        'generator_type': 'external_llm',
                        'target_symbols': target_symbols,
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': target_symbols},
                        'research_task': task,
                        'tags': ['external_llm', 'ai_generated'],
                    }],
                    'llm_generation': {
                        'external_provider': {
                            'status': 'succeeded',
                            'requests': [{'request_limit': limit, 'status': 'succeeded'}],
                            'selected_count': 1,
                            'elapsed_seconds': 0.5,
                        },
                    },
                }

        async def _scan(_self, _db, _snapshot):
            return {
                'summary': {
                    'task_count': 1,
                    'task_sources': {'event_driven': 1},
                    'event_task_count': 1,
                    'task_types': {'sector_breakout': 1},
                    'themes': ['event_theme_upstream_oil_gas'],
                },
                'tasks': [
                    {
                        'task_id': 'task_evt_oil',
                        'task_key': 'event_theme:2026-03-09:evt_oil_1:upstream_oil_gas',
                        'task_source': 'event_driven',
                        'event_id': 'evt_oil_1',
                        'event_type': 'geopolitics',
                        'theme_code': 'upstream_oil_gas',
                        'theme': 'event_theme_upstream_oil_gas',
                        'opportunity_type': 'sector_breakout',
                        'direction': 'positive',
                        'horizon': 'swing_5_20d',
                        'target_symbols': ['601857', '600938'],
                        'generation_limit': 1,
                        'evidence_bundle': {
                            'event_id': 'evt_oil_1',
                            'event_name': '中东战事升级',
                            'event_type': 'geopolitics',
                            'event_summary': '中东局势升级提升原油供给扰动预期。',
                            'theme_code': 'upstream_oil_gas',
                            'theme_name': '上游油气',
                            'direction': 'positive',
                            'horizon': 'swing_5_20d',
                            'signal_count': 2,
                            'supporting_reasons': ['油价中枢抬升', '供给扰动强化'],
                            'score_summary': {'avg_final_score': 0.87, 'max_final_score': 0.93, 'top_symbols': ['601857', '600938']},
                            'symbol_details': [
                                {'code': '601857', 'name': '中国石油', 'industry': '油气开采', 'sector': '石油石化', 'market': 'SH', 'market_cap': 1550000000000},
                                {'code': '600938', 'name': '中国海油', 'industry': '油气开采', 'sector': '石油石化', 'market': 'SH', 'market_cap': 1200000000000},
                            ],
                        },
                    }
                ],
            }

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _scan)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        result = await StrategyFactoryScheduler().run_once()

        assert result['status'] == 'partial'
        assert result['stages']['autonomy']['status'] == 'completed'
        assert result['summary']['partial_stage_count'] >= 1
        assert result['summary']['event_task_count'] == 1
        assert result['summary']['snapshot_task_count'] == 0
        assert result['summary']['task_source_counts'] == {'event_driven': 1}
        assert result['summary']['scanner_task_types'] == {'sector_breakout': 1}
        assert result['summary']['event_snapshot_mixed'] is False
        briefs = result['summary']['autonomy_task_briefs']
        assert len(briefs) == 1
        assert briefs[0]['task_id'] == 'task_evt_oil'
        assert briefs[0]['task_source'] == 'event_driven'
        assert briefs[0]['opportunity_type'] == 'sector_breakout'
        assert briefs[0]['generation_limit'] == 1
        assert briefs[0]['generated_count'] == 1
        assert result['summary']['event_evidence_count'] == len(saved_evidence)
        assert len(saved_evidence) >= 3
        assert any(item['evidence_type'] == 'event_theme_context' for item in saved_evidence)
        assert any(item['evidence_type'] == 'target_symbol' and item['symbol'] == '601857' for item in saved_evidence)
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['stages']['autonomy']['event_task_count'] == 1
        assert saved_run['stages']['autonomy']['event_evidence_count'] == len(saved_evidence)

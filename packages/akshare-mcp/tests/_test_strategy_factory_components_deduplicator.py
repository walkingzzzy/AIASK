from __future__ import annotations

from ._test_strategy_factory_components_support import *

class TestDeduplicator:
    @pytest.mark.asyncio
    async def test_removes_identical_candidates(self):
        dedup = Deduplicator()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[])
        unique = await dedup.deduplicate(candidates, db)
        assert len(unique) == 1
        assert unique[0]["dedup_result"]["duplicate"] is False
        assert dedup.get_last_report()["summary"]["dropped_count"] == 1

    @pytest.mark.asyncio
    async def test_keeps_different_types(self):
        dedup = Deduplicator()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20}},
            {"strategy_type": "rsi", "params": {"rsi_period": 14}},
        ]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[])
        unique = await dedup.deduplicate(candidates, db)
        assert len(unique) == 2

    @pytest.mark.asyncio
    async def test_existing_scan_is_bucketed_by_strategy_type(self):
        dedup = Deduplicator()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        db = MagicMock()
        db.list_strategies = AsyncMock(side_effect=[
            [
                {"id": "m1", "strategy_type": "momentum", "params": {"lookback": 22, "threshold": 0.03}},
                {"id": "r1", "strategy_type": "rsi", "params": {"rsi_period": 14, "oversold": 30}},
            ],
            [],
        ])

        await dedup.deduplicate(candidates, db)

        summary = dedup.get_last_report()["summary"]
        assert summary["existing_count"] == 2
        assert summary["existing_scan_count"] == 1

    @pytest.mark.asyncio
    async def test_removes_similar_to_existing(self):
        dedup = Deduplicator()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        existing = [{"strategy_type": "momentum", "params": {"lookback": 21, "threshold": 0.021}}]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)
        unique = await dedup.deduplicate(candidates, db)
        assert len(unique) == 0  # too similar

    @pytest.mark.asyncio
    async def test_target_pool_reduces_duplicate_score_for_disjoint_universe(self):
        dedup = Deduplicator()
        candidates = [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["688981", "002371"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["688981", "002371"]},
            },
        ]
        existing = [{
            "id": "s1",
            "name": "既有策略",
            "status": "incubating",
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519", "000858"],
        }]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)

        unique = await dedup.deduplicate(candidates, db)

        assert len(unique) == 1
        assert unique[0]["dedup_result"]["duplicate"] is False
        assert unique[0]["dedup_result"]["target_overlap"] == 0.0
        assert unique[0]["dedup_result"]["effective_similarity"] < dedup.THRESHOLD

    @pytest.mark.asyncio
    async def test_vector_check_can_filter_behaviorally_similar_candidate(self, monkeypatch):
        dedup = Deduplicator()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        existing = [{"id": "s1", "name": "既有策略", "strategy_type": "momentum", "params": {"lookback": 18, "threshold": 0.03}}]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)
        monkeypatch.setattr(
            dedup,
            "_vector_check",
            AsyncMock(return_value={
                "similarity": 0.97,
                "backend": "index",
                "matched_strategy_id": "s1",
                "matched_name": "既有策略",
                "matched_status": "incubating",
                "param_similarity": 0.72,
                "target_overlap": 0.5,
                "effective_similarity": 0.61,
            }),
        )
        unique = await dedup.deduplicate(candidates, db)
        assert unique == []
        report = dedup.get_last_report()
        assert report["summary"]["dropped_count"] == 1
        assert report["dropped"][0]["dedup_result"]["match_type"] == "vector"
        assert report["dropped"][0]["dedup_result"]["target_overlap"] == 0.5
        assert report["dropped"][0]["dedup_result"]["effective_similarity"] == 0.61
        assert report["dropped"][0]["dedup_result"]["matched_status"] == "incubating"

    @pytest.mark.asyncio
    async def test_vector_check_keeps_targeted_candidate_when_existing_lacks_universe_context(self, monkeypatch):
        dedup = Deduplicator()
        candidates = [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.01},
                "target_symbols": ["601398", "601857"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601857"]},
            },
        ]
        existing = [{"id": "s1", "name": "历史策略", "status": "incubating", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}}]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)
        monkeypatch.setattr(
            dedup,
            "_vector_check",
            AsyncMock(return_value={
                "similarity": 0.97,
                "backend": "index",
                "matched_strategy_id": "s1",
                "matched_name": "历史策略",
                "matched_status": "incubating",
                "param_similarity": 0.75,
                "target_overlap": None,
                "effective_similarity": 0.75,
            }),
        )
        unique = await dedup.deduplicate(candidates, db)
        assert len(unique) == 1
        assert unique[0]["dedup_result"]["duplicate"] is False
        assert unique[0]["dedup_result"]["vector_checked"] is True
        assert unique[0]["dedup_result"]["vector_similarity"] == 0.97
        assert unique[0]["dedup_result"]["matched_strategy_id"] == "s1"
        assert "缺少目标池信息" in unique[0]["dedup_result"]["reason"]
        assert unique[0]["dedup_result"]["vector_threshold"] == 0.98

    @pytest.mark.asyncio
    async def test_refreshes_existing_event_driven_candidate_instead_of_dropping(self):
        dedup = Deduplicator()
        candidates = [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.008},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "research_task": {"task_source": "event_driven", "event_id": "evt_bank", "theme_code": "high_dividend_banks"},
                "source": "strategy_factory:sector_breakout",
            },
        ]
        existing = [{
            "id": "s_evt_1",
            "name": "银行动量策略",
            "status": "incubating",
            "strategy_type": "momentum",
            "params": {"lookback": 8, "threshold": 0.008},
            "target_symbols": ["601398", "601288", "600036"],
        }]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)

        unique = await dedup.deduplicate(candidates, db)

        assert len(unique) == 1
        assert unique[0]["dedup_result"]["duplicate"] is False
        assert unique[0]["dedup_result"]["refresh_existing"] is True
        assert unique[0]["dedup_result"]["matched_strategy_id"] == "s_evt_1"
        assert dedup.get_last_report()["summary"]["refreshed_existing_count"] == 1

    @pytest.mark.asyncio
    async def test_refresh_existing_candidates_for_same_strategy_keep_best_backtest(self):
        dedup = Deduplicator()
        candidates = [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.008},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "research_task": {"task_source": "event_driven", "event_id": "evt_bank", "theme_code": "high_dividend_banks"},
                "source": "strategy_factory:sector_breakout",
                "backtest_metrics": {"sharpe_ratio": 0.84, "total_return": 0.07, "max_drawdown": 0.06},
            },
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.0076},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "research_task": {"task_source": "event_driven", "event_id": "evt_bank", "theme_code": "high_dividend_banks"},
                "source": "strategy_factory:sector_breakout",
                "backtest_metrics": {"sharpe_ratio": 0.92, "total_return": 0.08, "max_drawdown": 0.05},
            },
        ]
        existing = [{
            "id": "s_evt_1",
            "name": "银行动量策略",
            "status": "incubating",
            "strategy_type": "momentum",
            "params": {"lookback": 8, "threshold": 0.008},
            "target_symbols": ["601398", "601288", "600036"],
        }]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)

        unique = await dedup.deduplicate(candidates, db)

        assert len(unique) == 1
        assert unique[0]["params"]["threshold"] == 0.0076
        assert dedup.get_last_report()["summary"]["refreshed_existing_count"] == 1
        assert dedup.get_last_report()["summary"]["dropped_count"] == 1
        assert dedup.get_last_report()["dropped"][0]["dedup_result"]["duplicate_level"] == "refresh_existing_conflict"

    @pytest.mark.asyncio
    async def test_refreshes_same_parent_bandit_candidate_without_event_context(self):
        dedup = Deduplicator()
        candidates = [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.0076},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "parent_strategy_id": "sid_parent",
                "generator_type": "rl_bandit",
            },
        ]
        existing = [{
            "id": "sid_parent",
            "name": "银行动量母策略",
            "status": "incubating",
            "strategy_type": "momentum",
            "params": {"lookback": 8, "threshold": 0.008},
            "target_symbols": ["601398", "601288", "600036"],
        }]
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=existing)

        unique = await dedup.deduplicate(candidates, db)

        assert len(unique) == 1
        assert unique[0]["dedup_result"]["duplicate"] is False
        assert unique[0]["dedup_result"]["refresh_existing"] is True
        assert unique[0]["dedup_result"]["matched_strategy_id"] == "sid_parent"

    def test_param_sim_identical(self):
        sim = Deduplicator._param_sim({"a": 10, "b": 20}, {"a": 10, "b": 20})
        assert sim == 1.0

    def test_param_sim_different(self):
        sim = Deduplicator._param_sim({"a": 10}, {"a": 100})
        assert sim < 0.5



__all__ = [name for name in globals() if name.startswith("Test")]

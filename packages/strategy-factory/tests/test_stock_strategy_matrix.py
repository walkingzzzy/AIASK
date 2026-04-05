import pytest

import strategy_factory.application.stock_strategy_matrix as matrix_mod
from strategy_factory.application.stock_strategy_matrix import StockStrategyMatrixPlanner
from strategy_factory.domain.strategy_profile import apply_candidate_strategy_profile


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_emits_single_stock_family_tasks(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 4)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 4)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD", 2)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {
                    "code": "300001",
                    "name": "算力成长A",
                    "industry": "算力",
                    "sector": "算力",
                    "market": "CN",
                    "market_cap": 120_000_000_000,
                    "pe_ratio": 48,
                    "pb_ratio": 4.1,
                },
                {
                    "code": "600001",
                    "name": "银行价值A",
                    "industry": "银行",
                    "sector": "银行",
                    "market": "CN",
                    "market_cap": 88_000_000_000,
                    "pe_ratio": 8.5,
                    "pb_ratio": 0.9,
                },
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {"active_factors": ["growth", "value", "quality"]},
        },
    )

    tasks = list(report["tasks"])
    assert report["summary"]["enabled"] is True
    assert report["summary"]["task_count"] == len(tasks)
    assert report["summary"]["task_count"] <= 4
    assert all(task["task_source"] == "bulk_stock_matrix" for task in tasks)
    assert all(len(task["target_symbols"]) == 1 for task in tasks)
    assert all(task["allowed_strategy_types"] == task["preferred_strategy_types"] for task in tasks)
    assert any(task["candidate_family"] == "momentum" for task in tasks)
    assert any(task["candidate_family"] == "value_factor" for task in tasks)
    assert report["summary"]["effective_task_budget"] == 4
    assert report["summary"]["estimated_candidate_count"] == 4
    assert report["summary"]["shard_count"] == 2
    assert [task["matrix_shard_id"] for task in tasks] == [1, 1, 2, 2]
    assert all(task["matrix_budget_slot"] >= 1 for task in tasks)


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_exposes_multiple_families_within_budget_window(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 4)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 4)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD", 10)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {"code": "300001", "name": "算力成长A", "industry": "算力", "sector": "算力", "market_cap": 120_000_000_000, "pe_ratio": 48, "pb_ratio": 4.1},
                {"code": "300002", "name": "算力成长B", "industry": "算力", "sector": "算力", "market_cap": 110_000_000_000, "pe_ratio": 44, "pb_ratio": 3.9},
                {"code": "600001", "name": "银行价值A", "industry": "银行", "sector": "银行", "market_cap": 88_000_000_000, "pe_ratio": 8.5, "pb_ratio": 0.9},
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 65,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {"active_factors": ["growth", "value"]},
        },
    )

    tasks = list(report["tasks"])
    assert len(tasks) == 4
    assert report["summary"]["stock_count"] == 3
    assert report["summary"]["eligible_stock_count"] == 3
    assert report["summary"]["stock_coverage_ratio"] == pytest.approx(1.0)
    assert report["summary"]["allocation_mode"] == "stock_round_robin_by_family_rank"
    assert len({task["candidate_family"] for task in tasks}) >= 3
    assert any(task["matrix_allocation_pass"] > 1 for task in tasks[:4])
    assert len({task["target_symbols"][0] for task in tasks[:3]}) >= 2


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_assigns_batch_metadata(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_BATCH_SIZE", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 6)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 6)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD", 10)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {"code": "300001", "name": "算力成长A", "industry": "算力", "sector": "算力", "market_cap": 120_000_000_000, "pe_ratio": 48, "pb_ratio": 4.1},
                {"code": "300002", "name": "算力成长B", "industry": "算力", "sector": "算力", "market_cap": 110_000_000_000, "pe_ratio": 44, "pb_ratio": 3.9},
                {"code": "600001", "name": "银行价值A", "industry": "银行", "sector": "银行", "market_cap": 88_000_000_000, "pe_ratio": 8.5, "pb_ratio": 0.9},
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 65,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {"active_factors": ["growth", "value"]},
        },
    )

    tasks = list(report["tasks"])
    assert report["summary"]["batch_size"] == 2
    assert report["summary"]["batch_count"] == 2
    assert report["summary"]["selected_batch_count"] == 2
    assert report["summary"]["batch_task_counts"] == {"1": 4, "2": 2}
    assert [task["matrix_batch_id"] for task in tasks].count(1) == 4
    assert [task["matrix_batch_id"] for task in tasks].count(2) == 2
    assert sorted(task["matrix_batch_task_count"] for task in tasks if task["matrix_batch_id"] == 1) == [4, 4, 4, 4]
    assert sorted(task["matrix_batch_task_count"] for task in tasks if task["matrix_batch_id"] == 2) == [2, 2]
    assert sorted(task["matrix_batch_task_index"] for task in tasks if task["matrix_batch_id"] == 1) == [1, 2, 3, 4]
    assert sorted(task["matrix_batch_task_index"] for task in tasks if task["matrix_batch_id"] == 2) == [1, 2]
    assert all(task["matrix_batch_count"] == 2 for task in tasks)
    assert {task["matrix_batch_stock_count"] for task in tasks} == {1, 2}


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_respects_candidate_budget(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 3)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 6)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 5)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 3)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD", 10)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {"code": "300001", "name": "算力成长A", "industry": "算力", "sector": "算力", "market_cap": 120_000_000_000, "pe_ratio": 48, "pb_ratio": 4.1},
                {"code": "600001", "name": "银行价值A", "industry": "银行", "sector": "银行", "market_cap": 88_000_000_000, "pe_ratio": 8.5, "pb_ratio": 0.9},
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 55,
            "fg_level": "neutral",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {"active_factors": ["growth", "value", "quality"]},
        },
    )

    assert report["summary"]["generation_limit_per_task"] == 3
    assert report["summary"]["effective_task_budget"] == 1
    assert report["summary"]["task_count"] == 1
    assert report["summary"]["estimated_candidate_count"] == 3
    assert report["summary"]["overflow_task_count"] >= 1


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_prefers_factor_research_stock_family_allocation(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {
                    "code": "300001",
                    "name": "算力成长A",
                    "industry": "算力",
                    "sector": "算力",
                    "market_cap": 120_000_000_000,
                    "pe_ratio": 48,
                    "pb_ratio": 4.1,
                },
                {
                    "code": "600001",
                    "name": "银行价值A",
                    "industry": "银行",
                    "sector": "银行",
                    "market_cap": 88_000_000_000,
                    "pe_ratio": 8.5,
                    "pb_ratio": 0.9,
                },
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 65,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {
                "active_factors": ["growth", "value"],
                "stock_family_allocation": {
                    "600001": {
                        "families": ["value_factor"],
                        "priority": 0.95,
                        "source_mode": "stock_universe_projection",
                    },
                    "300001": {
                        "families": ["momentum"],
                        "priority": 0.30,
                        "source_mode": "stock_universe_projection",
                    },
                },
            },
        },
    )

    tasks = list(report["tasks"])
    assert [task["target_symbols"][0] for task in tasks] == ["600001", "300001"]
    assert [task["candidate_family"] for task in tasks] == ["value_factor", "momentum"]
    assert report["summary"]["allocation_mode"] == "factor_research_stock_family_allocation"
    assert report["summary"]["stock_family_allocation_count"] == 2
    assert report["summary"]["stock_family_allocation_applied_count"] == 2
    assert report["summary"]["stock_family_allocation_coverage_ratio"] == pytest.approx(1.0)
    assert tasks[0]["stock_family_priority"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_interleaves_passes_when_first_family_is_uniform(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 3)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 6)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 6)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD", 10)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            del limit, offset
            return [
                {"code": "300001", "name": "中盘成长A", "industry": "制造", "sector": "制造", "market_cap": 120_000_000_000, "pe_ratio": 20, "pb_ratio": 2.1},
                {"code": "300002", "name": "中盘成长B", "industry": "制造", "sector": "制造", "market_cap": 110_000_000_000, "pe_ratio": 21, "pb_ratio": 2.2},
                {"code": "300003", "name": "中盘成长C", "industry": "制造", "sector": "制造", "market_cap": 100_000_000_000, "pe_ratio": 22, "pb_ratio": 2.3},
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 55,
            "fg_level": "neutral",
            "hot_sectors": [],
            "cold_sectors": [],
            "factor_research": {"active_factors": []},
        },
    )

    tasks = list(report["tasks"])
    assert len(tasks) == 6
    assert {task["candidate_family"] for task in tasks[:3]} == {"ma_cross", "quality_factor", "multi_factor"}
    assert {task["matrix_allocation_pass"] for task in tasks[:3]} == {1, 2, 3}
    assert report["summary"]["family_counts"] == {
        "ma_cross": 2,
        "multi_factor": 2,
        "quality_factor": 2,
    }


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_prefilters_paginated_universe_before_budget_selection(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT", 1200)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 3)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 3)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)

    calls = []
    rows = [
        {
            "code": f"{idx:06d}",
            "name": f"普通股票{idx}",
            "industry": "银行",
            "sector": "银行",
            "market_cap": 1_000_000_000 + idx,
            "pe_ratio": 12.0,
            "pb_ratio": 1.0,
        }
        for idx in range(1, 1001)
    ] + [
        {
            "code": f"{200000 + idx:06d}",
            "name": f"算力龙头{idx}",
            "industry": "算力",
            "sector": "算力",
            "market_cap": 500_000_000_000 + idx,
            "pe_ratio": 30.0,
            "pb_ratio": 3.5,
        }
        for idx in range(1, 201)
    ]

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            calls.append({"limit": limit, "offset": offset})
            return rows[offset : offset + limit]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {"active_factors": ["growth"]},
        },
    )

    assert calls == [{"limit": 1000, "offset": 0}, {"limit": 200, "offset": 1000}]
    assert report["summary"]["loaded_stock_count"] == 1200
    assert report["summary"]["pages_loaded"] == 2
    assert report["summary"]["analysis_complete"] is False
    assert report["summary"]["planned_task_count"] == 1200
    assert report["summary"]["task_count"] == 3
    assert report["summary"]["overflow_task_count"] == 1197
    assert report["tasks"][0]["target_symbols"][0].startswith("200")


@pytest.mark.asyncio
async def test_stock_strategy_matrix_planner_uses_task_offset_window_and_wraps(monkeypatch):
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_ENABLED", True)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT", 4)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK", 1)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN", 2)
    monkeypatch.setattr(matrix_mod, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK", 1)

    class _DB:
        async def list_stock_universe(self, limit=500, offset=0):
            assert limit == 4
            assert offset == 0
            return [
                {"code": "300004", "name": "算力成长D", "industry": "算力", "sector": "算力", "market_cap": 130_000_000_000, "pe_ratio": 45, "pb_ratio": 4.2},
                {"code": "300003", "name": "算力成长C", "industry": "算力", "sector": "算力", "market_cap": 120_000_000_000, "pe_ratio": 44, "pb_ratio": 4.0},
                {"code": "300002", "name": "算力成长B", "industry": "算力", "sector": "算力", "market_cap": 110_000_000_000, "pe_ratio": 43, "pb_ratio": 3.8},
                {"code": "300001", "name": "算力成长A", "industry": "算力", "sector": "算力", "market_cap": 100_000_000_000, "pe_ratio": 42, "pb_ratio": 3.6},
            ]

    report = await StockStrategyMatrixPlanner().plan(
        _DB(),
        {
            "date": "2026-04-02",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "factor_research": {"active_factors": ["growth"]},
            "bulk_stock_matrix_task_offset": 3,
        },
    )

    assert report["summary"]["requested_task_offset"] == 3
    assert report["summary"]["effective_task_offset"] == 3
    assert report["summary"]["next_task_offset"] == 1
    assert report["summary"]["task_cursor_wrapped"] is True
    assert report["summary"]["requested_universe_offset"] == 3
    assert report["summary"]["next_universe_offset"] == 1
    assert [task["target_symbols"][0] for task in report["tasks"]] == ["300001", "300004"]


def test_apply_candidate_strategy_profile_adds_structured_tags():
    candidate = apply_candidate_strategy_profile(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "generator_type": "external_llm",
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "target_symbols": ["600519"],
                "candidate_family": "momentum",
                "holding_window": {"max_days": 5},
            },
        },
        snapshot={"fear_greed_index": 70},
    )

    profile = dict(candidate["strategy_profile"])
    assert profile["holding_period_bucket"] == "short"
    assert profile["target_symbol_count"] == 1
    assert "generator_external_llm" in candidate["tags"]
    assert "task_bulk_stock_matrix" in candidate["tags"]
    assert candidate["params"]["strategy_profile"]["strategy_family"] == "momentum"

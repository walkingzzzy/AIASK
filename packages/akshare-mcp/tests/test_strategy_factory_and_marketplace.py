"""策略工厂 + 策略超市 全面测试

覆盖:
- 策略注册表 (StrategyRegistry)
- 9种策略的信号生成 + 回测引擎集成
- 策略工厂各组件 (DataCollector, StrategySpawner, BacktestFilter, Deduplicator, EliminationChecker)
- 策略管理器 (strategy_manager) CRUD + 生命周期 + 质检
- RRF 排名引擎
"""

import asyncio
import json
import math
import pytest
import numpy as np
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# ── 策略注册表 & 策略类 ──

from akshare_mcp.services.backtest.strategy_base import IStrategy
from akshare_mcp.services.backtest.strategy_registry import StrategyRegistry
from akshare_mcp.services.backtest.builtin_strategies import (
    MaCrossStrategy, MomentumStrategy, RsiStrategy, BuyAndHoldStrategy,
)
from akshare_mcp.services.backtest.single_factor_strategy import (
    ValueFactorStrategy, QualityFactorStrategy, GrowthFactorStrategy,
)
from akshare_mcp.services.backtest.multi_factor_strategy import MultiFactorStrategy
from akshare_mcp.services.backtest.macro_timing_strategy import MacroTimingStrategy

# ── 策略工厂组件 ──

from akshare_mcp.services.strategy_factory import (
    DataCollector, StrategySpawner, BacktestFilter, Deduplicator,
    StrategySubmitter,
    EliminationChecker, MarketOpportunityScanner, StrategyFactoryScheduler, _auto_name,
    CATEGORY_MINIMUMS, REPRESENTATIVE_STOCKS,
)

# ── 排名引擎 ──

from akshare_mcp.services.ranking import rrf_rank

# ── 回测引擎 ──

from akshare_mcp.services.backtest.engine import BacktestEngine
from akshare_mcp.storage.timescaledb.artifacts import ArtifactMixin
from akshare_mcp.storage.timescaledb.strategy import StrategyMixin
from akshare_mcp.storage.timescaledb.artifacts import ArtifactMixin
from akshare_mcp.storage.timescaledb.strategy import StrategyMixin


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _type_name(value):
    return type(value).__name__


class TestTimestampCoercion:
    def test_strategy_mixin_coerces_iso_timestamp(self):
        value = StrategyMixin._coerce_timestamp("2026-03-08T14:53:01.813821")
        assert isinstance(value, datetime)
        assert value.year == 2026

    def test_artifact_mixin_coerces_zulu_timestamp(self):
        value = ArtifactMixin._coerce_timestamp("2026-03-08T06:54:38.895836Z")
        assert isinstance(value, datetime)
        assert value.tzinfo is not None

    def test_strategy_mixin_coerces_iso_date_string(self):
        value = StrategyMixin._coerce_date("2026-03-09")
        assert isinstance(value, date)
        assert value.isoformat() == "2026-03-09"

    def test_strategy_mixin_coerces_datetime_string_to_date(self):
        value = StrategyMixin._coerce_date("2026-03-09T07:38:25+00:00")
        assert isinstance(value, date)
        assert value.isoformat() == "2026-03-09"

def _make_klines(n=300, base=10.0, trend=0.001, noise=0.02):
    """生成模拟K线数据"""
    klines = []
    price = base
    for i in range(n):
        change = trend + np.random.uniform(-noise, noise)
        price *= (1 + change)
        price = max(price, 0.5)
        vol = int(np.random.uniform(5000, 50000))
        klines.append({
            "time": f"2024-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open": round(price * 0.998, 2),
            "high": round(price * 1.01, 2),
            "low": round(price * 0.99, 2),
            "close": round(price, 2),
            "volume": vol,
        })
    return klines


def _closes_from_klines(klines):
    return np.array([float(k["close"]) for k in klines])


def _volumes_from_klines(klines):
    return np.array([float(k["volume"]) for k in klines])


# ═══════════════════════════════════════════════════════════════
# 1. 策略注册表测试
# ═══════════════════════════════════════════════════════════════

class TestStrategyRegistry:
    def test_all_9_strategies_registered(self):
        names = StrategyRegistry.list_all()
        expected = {
            "ma_cross", "momentum", "rsi", "buy_and_hold",
            "value_factor", "quality_factor", "growth_factor",
            "multi_factor", "macro_timing",
        }
        assert expected.issubset(set(names)), f"Missing: {expected - set(names)}"

    def test_get_returns_class(self):
        for name in StrategyRegistry.list_all():
            klass = StrategyRegistry.get(name)
            assert klass is not None
            assert issubclass(klass, IStrategy)

    def test_create_and_set_params(self):
        inst = StrategyRegistry.create("momentum", {"lookback": 10, "threshold": 0.01})
        params = inst.get_parameters()
        assert params["lookback"] == 10

    def test_unknown_strategy_returns_none(self):
        assert StrategyRegistry.get("nonexistent_strategy") is None


# ═══════════════════════════════════════════════════════════════
# 2. 各策略信号生成测试
# ═══════════════════════════════════════════════════════════════

class TestSignalGeneration:
    """测试所有9种策略的信号生成"""

    @pytest.fixture
    def klines(self):
        np.random.seed(42)
        return _make_klines(300)

    @pytest.fixture
    def closes(self, klines):
        return _closes_from_klines(klines)

    @pytest.fixture
    def volumes(self, klines):
        return _volumes_from_klines(klines)

    @pytest.mark.parametrize("name", [
        "ma_cross", "momentum", "rsi", "buy_and_hold",
        "value_factor", "quality_factor", "growth_factor",
        "multi_factor", "macro_timing",
    ])
    def test_signal_shape_and_values(self, name, closes, volumes):
        klass = StrategyRegistry.get(name)
        inst = klass()
        signals = inst.generate_signals(closes, volumes)
        assert len(signals) == len(closes), f"{name}: signal length mismatch"
        unique = set(signals.tolist())
        assert unique.issubset({-1, 0, 1}), f"{name}: invalid signal values {unique}"

    @pytest.mark.parametrize("name", [
        "ma_cross", "momentum", "rsi",
        "value_factor", "quality_factor", "growth_factor",
        "multi_factor", "macro_timing",
    ])
    def test_signals_not_all_zero(self, name, closes, volumes):
        klass = StrategyRegistry.get(name)
        inst = klass()
        signals = inst.generate_signals(closes, volumes)
        assert np.any(signals != 0), f"{name}: all signals are zero"

    def test_entry_exit_masks(self, closes, volumes):
        inst = MomentumStrategy()
        entry, exit_ = inst.generate_entry_exit_masks(closes, volumes)
        assert entry.dtype == np.bool_
        assert exit_.dtype == np.bool_
        assert len(entry) == len(closes)

    def test_short_data_returns_zeros(self):
        short = np.array([10.0, 11.0, 12.0])
        inst = ValueFactorStrategy()
        signals = inst.generate_signals(short)
        assert np.all(signals == 0)


# ═══════════════════════════════════════════════════════════════
# 3. 回测引擎 + 注册表回退测试
# ═══════════════════════════════════════════════════════════════

class TestBacktestEngineRegistryFallback:
    """测试新策略通过 StrategyRegistry 回退在 BacktestEngine 中运行"""

    @pytest.fixture
    def klines(self):
        np.random.seed(42)
        return _make_klines(300)

    @pytest.mark.parametrize("strategy", [
        "value_factor", "quality_factor", "growth_factor",
        "multi_factor", "macro_timing",
    ])
    def test_new_strategies_run_through_engine(self, strategy, klines):
        result = BacktestEngine.run_backtest("600519", klines, strategy, {
            "initial_capital": 100000, "commission": 0.00025,
        })
        assert result["success"] is True, f"{strategy}: {result.get('error')}"
        data = result["data"]
        assert "sharpe_ratio" in data
        assert "total_return" in data
        assert "max_drawdown" in data
        assert data["trades_count"] >= 0

    def test_unknown_strategy_fails(self):
        klines = _make_klines(100)
        result = BacktestEngine.run_backtest("600519", klines, "totally_fake_strategy", {})
        assert result["success"] is False
        assert "Unknown strategy" in result["error"]


# ═══════════════════════════════════════════════════════════════
# 4. 策略工厂 — StrategySpawner 测试
# ═══════════════════════════════════════════════════════════════

class TestStrategySpawner:
    @pytest.mark.asyncio
    async def test_factor_research_builder_builds_unified_artifact(self):
        from akshare_mcp.services.strategy_factory import FactorResearchBuilder

        artifact = await FactorResearchBuilder.build(
            MagicMock(),
            {
                "factor_ic": {"value": 0.05, "quality": 0.04, "growth": -0.01},
                "factor_ic_trend": {"value": "rising", "quality": "rising", "growth": "falling"},
            },
        )

        assert artifact["active_factors"] == ["value", "quality"]
        assert artifact["positive_rising_factors"] == ["value", "quality"]
        assert artifact["preferred_strategy_types"][:2] == ["value_factor", "multi_factor"]
        assert artifact["summary"]["active_factor_count"] == 2
        assert artifact["degraded"] is False

    def test_fear_market_generates_rsi_and_value(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 20})
        types = [c["strategy_type"] for c in candidates]
        assert "rsi" in types
        assert "value_factor" in types
        assert all(c["generation_reason"]["source"] == "fear_greed" for c in candidates)
        first = candidates[0]
        assert first["generation_reason"]["summary"] == first["spawn_reason"]
        assert first["trigger_signal"] == {"field": "fear_greed_index", "value": 20, "level": "fear"}
        assert first["trigger_thresholds"][0]["field"] == "fear_greed_index"
        assert first["trigger_thresholds"][0]["operator"] == "<"
        assert first["trigger_thresholds"][0]["threshold"] == 30

    def test_greed_market_generates_momentum_and_growth(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 80})
        types = [c["strategy_type"] for c in candidates]
        assert "momentum" in types
        assert "growth_factor" in types

    def test_neutral_market_generates_ma_cross(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 50})
        types = [c["strategy_type"] for c in candidates]
        assert "ma_cross" in types

    def test_fund_flow_north_inflow(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": 8e9, "margin_5d_change_pct": 0})
        types = [c["strategy_type"] for c in candidates]
        assert "growth_factor" in types
        assert "quality_factor" in types
        assert all(c["generation_reason"]["source"] == "fund_flow" for c in candidates)
        assert all(c["trigger_signal"]["field"] == "north_fund_3d_net" for c in candidates)
        assert all(c["trigger_thresholds"][0]["threshold"] == 5_000_000_000 for c in candidates)

    def test_fund_flow_north_outflow(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": -8e9, "margin_5d_change_pct": 0})
        types = [c["strategy_type"] for c in candidates]
        assert "value_factor" in types
        assert "macro_timing" in types

    def test_fund_flow_margin_increase(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": 0, "margin_5d_change_pct": 3.5})
        types = [c["strategy_type"] for c in candidates]
        assert "momentum" in types

    def test_factor_ic_generates_multi_factor(self):
        spawner = StrategySpawner()
        snapshot = {
            "factor_ic": {"value": 0.05, "quality": 0.04, "growth": 0.01},
            "factor_ic_trend": {"value": "rising", "quality": "rising", "growth": "flat"},
        }
        candidates = spawner._from_factor_ic(snapshot)
        types = [c["strategy_type"] for c in candidates]
        assert "multi_factor" in types
        assert "value_factor" in types
        multi_factor = next(c for c in candidates if c["strategy_type"] == "multi_factor")
        assert multi_factor["generation_reason"]["source"] == "factor_ic"
        assert multi_factor["trigger_signal"]["field"] == "factor_ic_weights"
        assert multi_factor["trigger_thresholds"][0]["operator"] == "derived_from"

    def test_factor_ic_prefers_factor_research_artifact_when_present(self):
        spawner = StrategySpawner()
        snapshot = {
            "factor_ic": {},
            "factor_ic_trend": {},
            "factor_research": {
                "ranked_factors": [
                    {
                        "factor_name": "value",
                        "ic_value": 0.06,
                        "trend": "rising",
                        "score": 0.08,
                        "preferred_strategy_types": ["value_factor", "multi_factor"],
                    },
                    {
                        "factor_name": "quality",
                        "ic_value": 0.04,
                        "trend": "rising",
                        "score": 0.06,
                        "preferred_strategy_types": ["quality_factor", "multi_factor"],
                    },
                ],
                "positive_rising_factors": ["value", "quality"],
                "preferred_strategy_types": ["value_factor", "multi_factor", "quality_factor"],
            },
        }

        candidates = spawner._from_factor_ic(snapshot)

        assert {item["strategy_type"] for item in candidates} >= {"value_factor", "quality_factor", "multi_factor"}

    def test_fill_gaps_prefers_market_aligned_types_with_budget(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 50,
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "factor_ic": {},
            "factor_ic_trend": {},
            "event_driven": {"event_count": 0, "tasks_ready_count": 0},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner._fill_gaps(snapshot, current_candidates=[])
        assert 0 < len(candidates) <= SPAWNER_FILL_BUDGET_MAX
        assert {item["strategy_type"] for item in candidates} <= {"ma_cross", "momentum", "quality_factor", "value_factor"}
        first = candidates[0]
        assert first["generation_reason"]["kind"] == "quota_fill"
        assert first["generation_reason"]["source"] == "quota_fill"
        assert first["quota_fill"]["strategy_type"] == first["strategy_type"]
        assert first["quota_fill"]["minimum_required"] == CATEGORY_MINIMUMS[first["strategy_type"]]
        assert first["trigger_thresholds"][0]["field"] == f"generated_type_counts.{first['strategy_type']}"

    def test_fill_gaps_limits_budget_when_event_research_ready(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_EVENT_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 55,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
        current_candidates = [{"strategy_type": "ma_cross"}, {"strategy_type": "momentum"}, {"strategy_type": "multi_factor"}, {"strategy_type": "quality_factor"}, {"strategy_type": "value_factor"}]
        candidates = spawner._fill_gaps(snapshot, current_candidates=current_candidates)
        assert len(candidates) <= SPAWNER_EVENT_FILL_BUDGET_MAX

    def test_fill_gaps_allows_controlled_budget_when_event_ready_and_local_signals_are_strong(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_EVENT_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner._fill_gaps(snapshot, current_candidates=[{"strategy_type": "quality_factor"}])

        assert 0 < len(candidates) <= SPAWNER_EVENT_FILL_BUDGET_MAX
        assert all(candidate.get("quota_fill") for candidate in candidates)

    def test_spawn_returns_nonempty(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 50, "fg_level": "neutral",
            "fg_components": {"volatility": 50},
            "factor_ic": {}, "factor_ic_trend": {},
            "north_fund_3d_net": 0, "margin_5d_change_pct": 0,
            "category_counts": {},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner.spawn(snapshot)
        assert len(candidates) > 0
        for c in candidates:
            assert "strategy_type" in c
            assert "params" in c
            assert "spawn_reason" in c
            assert "generation_reason" in c
            assert "trigger_signal" in c
            assert "trigger_thresholds" in c
        report = spawner.get_last_report()
        assert report["summary"]["candidate_count"] == len(candidates)
        assert 0 < report["summary"]["quota_fill_count"] <= 4
        assert report["summary"]["signal_trigger_count"] > 0
        assert report["summary"]["threshold_hit_count"] >= len(candidates)
        assert report["summary"]["source_counts"]["quota_fill"] > 0
        assert report["summary"]["source_counts"]["fear_greed"] > 0
        assert report["summary"]["source_counts"].get("factor_ic", 0) == 0

    def test_spawn_prefers_event_driven_and_suppresses_broad_neutral_templates(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 55,
            "fg_components": {"volatility": 50},
            "factor_ic": {},
            "factor_ic_trend": {},
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner.spawn(snapshot)
        report = spawner.get_last_report()
        assert report["summary"]["quota_fill_count"] == 0
        assert report["summary"]["source_counts"].get("fear_greed", 0) == 0
        assert report["summary"]["source_counts"].get("volatility", 0) == 0
        assert report["summary"]["source_counts"].get("fund_flow", 0) == 0
        assert all((item.get("generation_reason") or {}).get("source") != "quota_fill" for item in candidates)

    def test_spawn_allows_controlled_event_ready_fill_when_local_signals_are_strong(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner.spawn(snapshot)
        report = spawner.get_last_report()

        assert candidates
        assert report["summary"]["quota_fill_count"] >= 0
        assert report["summary"]["source_counts"].get("volatility", 0) > 0
        assert report["summary"]["source_counts"].get("fund_flow", 0) > 0
        assert report["summary"]["signal_trigger_count"] > 0

    def test_spawn_adds_signal_variants_when_signals_are_strong(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 0, "tasks_ready_count": 0},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner.spawn(snapshot)
        variant_candidates = [
            item for item in candidates
            if (item.get("generation_reason") or {}).get("source") == "signal_variation"
        ]
        report = spawner.get_last_report()

        assert variant_candidates
        assert report["summary"]["source_counts"].get("signal_variation", 0) == len(variant_candidates)
        assert all(item["trigger_thresholds"][0]["label"] == "强信号变体扩容" for item in variant_candidates)


# ═══════════════════════════════════════════════════════════════
# 5. 策略工厂 — Deduplicator 测试
# ═══════════════════════════════════════════════════════════════

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

    def test_param_sim_identical(self):
        sim = Deduplicator._param_sim({"a": 10, "b": 20}, {"a": 10, "b": 20})
        assert sim == 1.0

    def test_param_sim_different(self):
        sim = Deduplicator._param_sim({"a": 10}, {"a": 100})
        assert sim < 0.5


# ═══════════════════════════════════════════════════════════════
# 6. 策略工厂 — EliminationChecker 测试
# ═══════════════════════════════════════════════════════════════

class TestEliminationChecker:
    @pytest.mark.asyncio
    async def test_eliminates_high_drawdown(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s1", "strategy_type": "momentum"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "all", "max_drawdown": -0.40, "sharpe_ratio": 0.5, "win_rate": 0.5},
        ])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()

        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 1
        assert "回撤" in eliminated[0]["reason"]

    @pytest.mark.asyncio
    async def test_eliminates_negative_sharpe(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s2", "strategy_type": "rsi"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "all", "max_drawdown": -0.10, "sharpe_ratio": -0.5, "win_rate": 0.2},
        ])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()

        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 1  # Sharpe<0 + win_rate<30% = 2 red flags

    @pytest.mark.asyncio
    async def test_keeps_healthy_strategy(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s3", "strategy_type": "ma_cross"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "all", "max_drawdown": -0.15, "sharpe_ratio": 1.2, "win_rate": 0.55},
        ])
        db.get_signal_stats = AsyncMock(return_value={
            "hit_rate": {5: 0.55}, "total_signals": 50,
        })
        db.update_strategy_status = AsyncMock()

        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 0

    @pytest.mark.asyncio
    async def test_regime_mismatch_adds_red_flag(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s4", "strategy_type": "momentum"},  # momentum适合greed
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "all", "max_drawdown": -0.10, "sharpe_ratio": 0.1, "win_rate": 0.25},
        ])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()

        # fear环境 + win_rate<30% = 2 red flags → 淘汰
        eliminated = await checker.check(db, "fear")
        assert len(eliminated) == 1
        flags = eliminated[0]["red_flags"]
        assert any("不适合" in f for f in flags)

    @pytest.mark.asyncio
    async def test_signal_hit_rate_check(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s5", "strategy_type": "ma_cross"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "all", "max_drawdown": -0.10, "sharpe_ratio": 0.1, "win_rate": 0.25},
        ])
        db.get_signal_stats = AsyncMock(return_value={
            "hit_rate": {5: 0.15}, "total_signals": 50,
        })
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()

        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 1
        assert any("命中率" in f for f in eliminated[0]["red_flags"])

    @pytest.mark.asyncio
    async def test_validation_and_risk_flags_can_trigger_elimination(self):
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s6", "strategy_type": "multi_factor"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "backtest", "max_drawdown": -0.12, "sharpe_ratio": 0.3, "win_rate": 0.45},
            {"period": "validation", "grade": "D", "total_score": 30.0},
            {"period": "risk", "var_percent": 4.5, "cvar_percent": 6.5, "stress_loss_percent": -28.0},
        ])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()

        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 1
        assert any("验证评级" in flag for flag in eliminated[0]["red_flags"])
        assert any("VaR" in flag for flag in eliminated[0]["red_flags"])


class TestStrategySubmitter:
    @pytest.mark.asyncio
    async def test_submitter_persists_validation_and_risk_metrics(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 58.0, "recommendation": "Strong"}, "walk_forward": {"oos_rank_ic_mean": 0.04}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 2.1, "cvar_percent": 3.2, "stress_loss_percent": -20.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.2, "max_drawdown": 0.12, "win_rate": 0.55, "trades_count": 8},
                "spawn_reason": "测试提交",
            }
        ], {"fg_level": "neutral"}, db)
        periods = [call.args[1] for call in db.save_strategy_metrics.await_args_list]
        assert result["passed_quality_gate"] == 1
        assert "backtest" in periods
        assert "validation" in periods
        assert "risk" in periods
        db.save_strategy_quality_report.assert_awaited_once()
        saved_report = db.save_strategy_quality_report.await_args.args[2]
        assert saved_report["passed"] is True
        assert saved_report["dedup_report"] == {}
        assert saved_report["summary"]["review_source"] == "strategy_factory_submit"
        assert saved_report["quality_gate"]["reason_codes"] == []

    @pytest.mark.asyncio
    async def test_submitter_persists_target_universe_into_strategy_params(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["688981", "002371"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["688981", "002371"]},
                "selection_logic": ["prefer semiconductor leaders"],
                "research_task": {"task_id": "task_chip", "opportunity_type": "sector_breakout"},
                "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.2, "max_drawdown": 0.12, "win_rate": 0.55, "trades_count": 8},
                "spawn_reason": "测试提交",
            }
        ], {"fg_level": "neutral"}, db)

        saved_strategy = db.save_strategy.await_args.args[0]
        assert saved_strategy["params"]["target_symbols"] == ["688981", "002371"]
        assert saved_strategy["params"]["stock_pool"]["symbols"] == ["688981", "002371"]
        assert saved_strategy["params"]["selection_logic"] == ["prefer semiconductor leaders"]
        assert saved_strategy["params"]["research_task"]["task_id"] == "task_chip"

    @pytest.mark.asyncio
    async def test_submitter_preserves_event_context_in_experiment_record(self, monkeypatch):
        submitter = StrategySubmitter()
        db = _StrategyDB()
        await db.save_strategy_generation_experiment({
            "experiment_id": "exp_evt_submit_1",
            "strategy_id": None,
            "parent_strategy_id": "parent_evt_1",
            "source": "strategy_factory:sector_breakout",
            "generator_type": "external_llm",
            "status": "generated",
            "evaluation": {"committee_review": {"final_score": 0.81}},
        })

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": False, "reason": "Insufficient kline data for quality gate"}),
        )

        result = await submitter.submit([
            {
                "experiment_id": "exp_evt_submit_1",
                "source": "strategy_factory:sector_breakout",
                "generator_type": "external_llm",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"metadata": {"target_symbols": ["601857", "600938"]}}},
                "target_symbols": ["601857", "600938"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601857", "600938"]},
                "selection_logic": ["follow geopolitics"],
                "research_scope": {"window": "20d"},
                "research_task": {
                    "task_id": "task_evt_oil",
                    "task_key": "event_theme:2026-03-09:evt_oil_1:upstream_oil_gas",
                    "task_source": "event_driven",
                    "event_id": "evt_oil_1",
                    "event_type": "geopolitics",
                    "theme_code": "upstream_oil_gas",
                    "theme": "event_theme_upstream_oil_gas",
                    "direction": "positive",
                    "horizon": "swing_5_20d",
                    "target_symbols": ["601857", "600938"],
                    "evidence_bundle": {
                        "event_id": "evt_oil_1",
                        "event_name": "中东战事升级",
                        "event_type": "geopolitics",
                        "event_summary": "中东局势升级提升原油供给扰动预期。",
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "horizon": "swing_5_20d",
                        "signal_count": 2,
                        "supporting_reasons": ["油价中枢抬升", "供给扰动强化"],
                        "score_summary": {"avg_final_score": 0.87, "max_final_score": 0.93, "top_symbols": ["601857", "600938"]},
                    },
                },
                "spawn_reason": "事件驱动原型",
            }
        ], {"date": "2026-03-09", "fg_level": "greed", "fear_greed_index": 68}, db)

        saved = await db.get_strategy_generation_experiment("exp_evt_submit_1")

        assert result["created"] == 1
        assert result["passed_quality_gate"] == 0
        assert saved["parent_strategy_id"] == "parent_evt_1"
        assert saved["generated_strategy_id"] == result["strategies"][0]["strategy_id"]
        assert saved["evaluation"]["committee_review"]["final_score"] == 0.81
        assert saved["evaluation"]["research_task"]["event_id"] == "evt_oil_1"
        assert saved["evaluation"]["event_context"]["theme_code"] == "upstream_oil_gas"
        assert saved["strategy_spec"]["research_task"]["theme_code"] == "upstream_oil_gas"

    @pytest.mark.asyncio
    async def test_submitter_allows_provisional_incubation_for_external_llm_prototype(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "D", "total_score": 18.0, "recommendation": "Weak"}, "walk_forward": {"oos_rank_ic_mean": 0.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.8, "cvar_percent": 2.6, "stress_loss_percent": -18.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": True,
                "passed_strict": False,
                "provisional_pass": True,
                "reasons": [],
                "warnings": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
                "warning_codes": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
            }),
        )

        result = await submitter.submit([
            {
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"version": "1.0", "timeframe": "daily", "entry": {"any": [{"op": "gt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}, "exit": {"any": [{"op": "lt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}}},
                "backtest_metrics": {"sharpe_ratio": 0.22, "total_return": 0.08, "max_drawdown": 0.12, "win_rate": 0.51, "trades_count": 2},
                "spawn_reason": "外部 AI 原型提交",
                "tags": ["factory", "external_llm", "ai_generated"],
                "llm_prompt": {"system": "s", "user": "u"},
                "llm_response": {"provider": "openai_compatible", "model": "test-model"},
            }
        ], {"fg_level": "neutral"}, db)

        saved_report = db.save_strategy_quality_report.await_args.args[2]
        assert result["passed_quality_gate"] == 1
        assert result["gate_3_passed"] == 1
        assert result["gate_3_failed"] == 0
        assert result["gate_3_provisional_passed"] == 1
        assert result["gate_report"]["gate_3"]["status"] == "completed_submission_gate"
        assert result["gate_report"]["gate_3"]["provisional_passed_count"] == 1
        assert result["strategies"][0]["provisional_pass"] is True
        assert result["strategies"][0]["gate_3"]["provisional_pass"] is True
        assert saved_report["passed"] is True
        assert saved_report["quality_gate"]["provisional_pass"] is True
        assert "validation_grade_d" in saved_report["quality_gate"]["warning_codes"]


    @pytest.mark.asyncio
    async def test_submitter_aggregates_gate_3_failure_reasons(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "C", "total_score": 42.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.4, "cvar_percent": 2.0, "stress_loss_percent": -11.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": False,
                "reasons": ["Insufficient kline data for quality gate"],
                "reason_codes": ["insufficient_kline_data"],
            }),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 0.31, "total_return": 0.09, "max_drawdown": 0.13, "win_rate": 0.48, "trades_count": 3},
                "spawn_reason": "Gate-3 失败统计测试",
            }
        ], {"fg_level": "neutral"}, db)

        assert result["passed_quality_gate"] == 0
        assert result["gate_3_passed"] == 0
        assert result["gate_3_failed"] == 1
        assert result["gate_3_provisional_passed"] == 0
        assert result["gate_3_failure_reason_topn"] == [{"reason_code": "insufficient_kline_data", "count": 1}]
        assert result["gate_report"]["final_decision"]["stage"] == "gate_3"
        assert result["strategies"][0]["gate_3"]["reason_codes"] == ["insufficient_kline_data"]
        assert result["strategies"][0]["status"] == "rejected"
        assert result["strategies"][0]["passed"] is False
        assert result["strategies"][0]["provisional_pass"] is False
        assert result["strategies"][0]["reason_codes"] == ["insufficient_kline_data"]
        assert result["strategies"][0]["warning_codes"] == []
        db.update_strategy_status.assert_awaited()
        status_call = db.update_strategy_status.await_args_list[-1]
        assert status_call.args[1] == "rejected"
        assert status_call.kwargs["reason"] == "quality_gate_failed"
        assert status_call.kwargs["metadata"]["quality_gate"]["reason_codes"] == ["insufficient_kline_data"]

    @pytest.mark.asyncio
    async def test_shared_submission_gate_grants_provisional_incubation_for_factory_ai_strategy(self, monkeypatch):
        from types import SimpleNamespace
        from akshare_mcp.services.strategy_factory import submission_gate as submission_gate_mod

        class _DummyStrategy:
            def set_parameters(self, _params):
                return None

            def generate_signals(self, closes):
                return np.linspace(0.0, 1.0, len(closes))

        class _WalkForwardValidator:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_ir=0.0)

        class _PurgedKFoldCV:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_mean=0.03)

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(n=160, base=10.0, trend=0.01, noise=0.001))

        monkeypatch.setattr(
            "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
            lambda *_args, **_kwargs: _DummyStrategy,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.WalkForwardValidator",
            _WalkForwardValidator,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.PurgedKFoldCV",
            _PurgedKFoldCV,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.bootstrap_ic_ci",
            lambda *_args, **_kwargs: {"ci_lower": 0.01},
        )

        gate = await submission_gate_mod.run_submission_quality_gate(
            db,
            {
                "id": "factory_gate_1",
                "strategy_type": "dsl_rule",
                "params": {"lookback": 20},
                "tags": ["factory", "external_llm", "ai_generated"],
            },
            validation_report={"rating": {"grade": "D", "total_score": 18.0}},
            risk_report={"var_percent": 1.8, "cvar_percent": 2.6, "stress_loss_percent": -18.0},
            backtest_metrics={"sharpe_ratio": 0.22, "max_drawdown": 0.12, "trade_count": 2},
        )

        assert gate["passed"] is True
        assert gate["passed_strict"] is False
        assert gate["provisional_pass"] is True
        assert "validation_grade_d" in gate["warning_codes"]
        assert "walk_forward_ic_ir" in gate["statistical_checks_failed_names"]

    @pytest.mark.asyncio
    async def test_submitter_passes_review_context_to_shared_submission_gate(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 82.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.2, "cvar_percent": 1.8, "stress_loss_percent": -12.0}),
        )
        gate_mock = AsyncMock(return_value={"passed": True, "reasons": []})
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            gate_mock,
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 0.61, "total_return": 0.19, "max_drawdown": 0.08, "trade_count": 3},
                "spawn_reason": "factory_context_test",
            }
        ], {"fg_level": "neutral"}, db)

        assert result["submitted"] == 1
        assert gate_mock.await_count == 1
        gate_kwargs = gate_mock.await_args.kwargs
        assert gate_kwargs["validation_report"]["rating"]["grade"] == "B"
        assert gate_kwargs["risk_report"]["var_percent"] == 1.2
        assert gate_kwargs["backtest_metrics"]["trade_count"] == 3
        assert gate_kwargs["backtest_metrics"]["trades_count"] is None

    @pytest.mark.asyncio
    async def test_submitter_reuses_existing_strategy_for_refresh_existing_candidate(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.get_strategy = AsyncMock(return_value={
            "id": "sid_existing_1",
            "name": "银行动量策略",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "incubating",
            "params": {"lookback": 8, "threshold": 0.008, "target_symbols": ["601398", "601288", "600036"]},
            "factor_weights": {},
            "tags": ["factory", "momentum"],
        })
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()
        db.save_strategy_generation_experiment = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.008},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "research_task": {"task_source": "event_driven", "event_id": "evt_bank", "theme_code": "high_dividend_banks"},
                "source": "strategy_factory:sector_breakout",
                "spawn_reason": "银行事件刷新",
                "backtest_metrics": {"sharpe_ratio": 0.85, "total_return": 0.07, "max_drawdown": 0.06, "win_rate": 0.55, "trades_count": 14},
                "dedup_result": {"refresh_existing": True, "matched_strategy_id": "sid_existing_1", "matched_status": "incubating"},
            }
        ], {"date": "2026-03-08", "fg_level": "neutral", "fear_greed_index": 55}, db)

        assert result["created"] == 0
        assert result["refreshed"] == 1
        assert result["submitted"] == 1
        assert result["passed_quality_gate"] == 1
        saved_strategy = db.save_strategy.await_args.args[0]
        assert saved_strategy["id"] == "sid_existing_1"
        db.update_strategy_status.assert_not_awaited()
        db.save_strategy_lineage.assert_not_awaited()
        assert result["strategies"][0]["strategy_id"] == "sid_existing_1"
        assert result["strategies"][0]["refreshed_existing"] is True

    @pytest.mark.asyncio
    async def test_submitter_runs_initial_incubation_pipeline(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()
        db.save_strategy_generation_experiment = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 66.0, "recommendation": "Strong"}, "walk_forward": {"oos_rank_ic_mean": 0.05}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.5, "cvar_percent": 2.1, "stress_loss_percent": -12.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        class _DummyIncubationService:
            async def ensure_account(self, *_args, **_kwargs):
                return {'account': {'id': 'paper_acc_1'}}

        class _DummyIncubationPipeline:
            async def run_strategy(self, *_args, **_kwargs):
                return {
                    'task_run_id': 88,
                    'snapshot': {
                        'pipeline_stage': 'warmup',
                        'pipeline_status': 'collecting',
                        'readiness_score': 0.42,
                    },
                }

        class _DummyVectorPlatform:
            async def build_strategy_profile(self, *_args, **_kwargs):
                return {'id': 7}

        monkeypatch.setattr('akshare_mcp.services.incubation.get_strategy_incubation_service', lambda: _DummyIncubationService())
        monkeypatch.setattr('akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service', lambda: _DummyIncubationPipeline())
        monkeypatch.setattr('akshare_mcp.services.vector_platform.get_strategy_vector_platform', lambda: _DummyVectorPlatform())

        result = await submitter.submit([
            {
                'strategy_type': 'momentum',
                'params': {'lookback': 20, 'threshold': 0.02},
                'backtest_metrics': {'sharpe_ratio': 1.1, 'total_return': 0.2, 'max_drawdown': 0.12, 'win_rate': 0.55, 'trades_count': 8},
                'spawn_reason': '测试提交',
                'experiment_id': 'exp_1',
                'generator_type': 'external_llm',
                'llm_response': {'provider': 'openai_compatible', 'model': 'test-model'},
            }
        ], {'date': '2026-03-08', 'fg_level': 'neutral'}, db)

        assert result['passed_quality_gate'] == 1
        assert result['strategies'][0]['incubation_pipeline_stage'] == 'warmup'
        assert result['strategies'][0]['incubation_pipeline_status'] == 'collecting'
        assert result['strategies'][0]['incubation_task_run_id'] == 88



# ═══════════════════════════════════════════════════════════════
# 7. RRF 排名引擎测试
# ═══════════════════════════════════════════════════════════════

class TestRRFRanking:
    def test_basic_ranking(self):
        strategies = [
            {"id": "a", "sharpe_ratio": 2.0, "total_return": 0.3, "win_rate": 0.6,
             "calmar_ratio": 1.5, "max_drawdown": -0.10},
            {"id": "b", "sharpe_ratio": 0.5, "total_return": 0.1, "win_rate": 0.4,
             "calmar_ratio": 0.3, "max_drawdown": -0.30},
            {"id": "c", "sharpe_ratio": 1.0, "total_return": 0.2, "win_rate": 0.5,
             "calmar_ratio": 0.8, "max_drawdown": -0.20},
        ]
        ranked = rrf_rank(strategies)
        assert ranked[0]["id"] == "a"  # best across all dimensions
        assert ranked[-1]["id"] == "b"  # worst across all dimensions
        for s in ranked:
            assert "rrf_score" in s

    def test_empty_list(self):
        assert rrf_rank([]) == []

    def test_single_strategy(self):
        strategies = [{"id": "x", "sharpe_ratio": 1.0, "total_return": 0.1,
                       "win_rate": 0.5, "calmar_ratio": 0.5, "max_drawdown": -0.15}]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 1
        assert ranked[0]["rrf_score"] > 0


# ═══════════════════════════════════════════════════════════════
# 8. 策略管理器 (strategy_manager) 测试
# ═══════════════════════════════════════════════════════════════

import akshare_mcp.tools.managers.strategy_manager as sm_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


class _StrategyConn:
    """模拟策略管理器所需的DB连接"""
    def __init__(self):
        self.strategies = {}
        self.metrics = {}
        self.reviews = []
        self.subscriptions = set()

    async def fetchrow(self, query, *args):
        if 'FROM strategies WHERE id' in query:
            return self.strategies.get(args[0])
        return None

    async def fetch(self, query, *args):
        if 'FROM strategies' in query and 'status' in query:
            return [s for s in self.strategies.values()
                    if s.get("status") == args[0]]
        if 'FROM strategy_metrics' in query:
            sid = args[0]
            return self.metrics.get(sid, [])
        if 'FROM strategy_reviews' in query:
            return self.reviews
        return []

    async def fetchval(self, query, *args):
        return 0

    async def execute(self, query, *args):
        if 'INSERT INTO strategies' in query or 'UPSERT' in query.upper():
            pass
        elif 'UPDATE strategies SET status' in query:
            sid = args[1] if len(args) > 1 else args[0]
            if sid in self.strategies:
                self.strategies[sid]["status"] = args[0]


class _StrategyDB:
    def __init__(self):
        self._pgvector_enabled = False
        self._strategies = {}
        self._metrics = {}
        self._reviews = []
        self._subs = set()
        self._quality_reports = {}
        self._events = {}
        self._signal_stats = {}
        self._factory_runs = []
        self._daily_snapshots = []
        self._factory_event_clusters = []
        self._factory_theme_definitions = []
        self._factory_company_theme_exposures = []
        self._factory_event_signals = []
        self._factory_task_evidence = []
        self._factory_market_internals = []
        self._north_fund_summary = None
        self._paper_accounts = {}
        self._paper_orders = []
        self._paper_positions = {}
        self._paper_trades = []
        self._paper_nav = {}
        self._incubation_accounts = []
        self._incubation_metrics = []
        self._incubation_pipeline_snapshots = []
        self._risk_events = []
        self._runtime_risk_snapshots = []
        self._vector_profiles = []
        self._vector_profile_store = []
        self._vector_indexes = []
        self._vector_index_snapshots = []
        self._vector_index_items = []
        self._vector_index_item_store = []
        self._vector_hnsw_indexes = []
        self._experiments = {}
        self._task_runs = []
        self._domain_events = []
        self._runtime_controls = {}
        self._runtime_alerts = []
        self._promotion_reviews = []
        self._projection_snapshots = []

    def supports_pgvector(self):
        return bool(self._pgvector_enabled)

    def get_vector_backend(self):
        return 'pgvector' if self.supports_pgvector() else 'index'

    @staticmethod
    def _sanitize_index_part(value):
        text = ''.join(ch if str(ch).isalnum() else '_' for ch in str(value or 'na'))
        text = text.strip('_')
        return text or 'na'

    @staticmethod
    def _timestamp_key(value):
        if value is None:
            return ''
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return ''
            try:
                dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError:
                return text
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    @classmethod
    def _best_timestamp(cls, row):
        for key in ('activated_at', 'built_at', 'updated_at', 'created_at', 'last_seen'):
            value = row.get(key)
            if value is not None:
                return cls._timestamp_key(value)
        return ''

    def acquire(self):
        class _Acq:
            def __init__(self, conn):
                self.conn = conn
            async def __aenter__(self):
                return self.conn
            async def __aexit__(self, *a):
                return False
        return _Acq(_StrategyConn())

    @staticmethod
    def _normalize_strategy_status(status):
        normalized = str(status or "").strip().lower()
        return "listed" if normalized == "published" else normalized

    @classmethod
    def _expand_strategy_status_filter(cls, status):
        normalized = cls._normalize_strategy_status(status)
        if normalized == "listed":
            return {"listed", "published"}
        return {normalized}

    async def save_strategy(self, data):
        item = dict(data)
        item["status"] = self._normalize_strategy_status(item.get("status", "draft"))
        self._strategies[data["id"]] = item
        return item

    async def get_strategy(self, sid):
        strategy = self._strategies.get(sid)
        if not strategy:
            return None
        item = dict(strategy)
        item["status"] = self._normalize_strategy_status(item.get("status"))
        return item

    async def update_strategy_status(self, sid, status, actor_id="system", reason=None, metadata=None):
        if sid in self._strategies:
            previous = self._normalize_strategy_status(self._strategies[sid].get("status"))
            normalized = self._normalize_strategy_status(status)
            self._strategies[sid]["status"] = normalized
            if previous != normalized:
                created_at = datetime.now(timezone.utc).isoformat()
                self._events.setdefault(sid, []).append({
                    "from_status": previous,
                    "to_status": normalized,
                    "event_type": "status_change",
                    "actor_id": actor_id,
                    "reason": reason,
                    "metadata": metadata or {},
                    "created_at": created_at,
                })
                self._domain_events.append({
                    'id': len(self._domain_events) + 1,
                    'strategy_id': sid,
                    'aggregate_type': 'strategy',
                    'aggregate_id': sid,
                    'event_type': 'strategy.status_changed',
                    'source': actor_id,
                    'severity': 'info',
                    'correlation_id': (metadata or {}).get('task_run_id') if isinstance(metadata, dict) else None,
                    'payload': {'from_status': previous, 'to_status': normalized, 'reason': reason, 'metadata': metadata or {}},
                    'created_at': created_at,
                })

    @staticmethod
    def _parse_event_time(value):
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def list_strategies(self, status, strategy_type=None, limit=20, offset=0):
        allowed_statuses = self._expand_strategy_status_filter(status)
        return [
            dict(s, status=self._normalize_strategy_status(s.get("status")))
            for s in self._strategies.values()
            if self._normalize_strategy_status(s.get("status")) in allowed_statuses
        ]

    async def get_strategy_metrics(self, sid):
        return self._metrics.get(sid, [])

    async def save_strategy_metrics(self, sid, period, metrics):
        self._metrics.setdefault(sid, []).append({"period": period, **metrics})

    async def get_reviews(self, sid, limit=10):
        return self._reviews

    async def save_review(self, sid, user_id, rating, comment):
        self._reviews.append({"strategy_id": sid, "user_id": user_id, "rating": rating})

    async def subscribe_strategy(self, sid, user_id):
        self._subs.add((sid, user_id))

    async def unsubscribe_strategy(self, sid, user_id):
        self._subs.discard((sid, user_id))

    async def is_subscribed(self, sid, user_id):
        return (sid, user_id) in self._subs

    async def list_user_subscriptions(self, user_id):
        return [{"strategy_id": s} for s, u in self._subs if u == user_id]

    async def get_signal_stats(self, sid):
        return self._signal_stats.get(sid, {"hit_rate": {}, "forward_ic": {}, "forward_sharpe": {}, "total_signals": 0})

    async def get_signals(self, sid, start_date=None, end_date=None, limit=100):
        return []

    async def get_signals_public(self, sid, start_date=None, end_date=None, limit=100):
        return []

    async def get_klines(self, code, limit=200):
        return [
            {"date": f"2026-01-{(idx % 28) + 1:02d}", "open": 10 + idx * 0.1, "high": 10.2 + idx * 0.1, "low": 9.8 + idx * 0.1, "close": 10 + idx * 0.1, "volume": 1000 + idx}
            for idx in range(limit)
        ]

    async def list_stock_universe(self, limit=200, offset=0, min_market_cap=None, industry=None, market=None):
        rows = [
            {"code": "600519", "name": "贵州茅台", "industry": "白酒", "sector": "消费", "market": "SH", "market_cap": 2.1e12, "pe_ratio": 24.0, "pb_ratio": 9.2},
            {"code": "000858", "name": "五粮液", "industry": "白酒", "sector": "消费", "market": "SZ", "market_cap": 8.5e11, "pe_ratio": 18.5, "pb_ratio": 5.1},
            {"code": "300750", "name": "宁德时代", "industry": "电池", "sector": "新能源", "market": "SZ", "market_cap": 9.8e11, "pe_ratio": 21.0, "pb_ratio": 4.2},
            {"code": "601318", "name": "中国平安", "industry": "保险", "sector": "金融", "market": "SH", "market_cap": 7.0e11, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.0e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
            {"code": "000333", "name": "美的集团", "industry": "家电", "sector": "消费", "market": "SZ", "market_cap": 5.4e11, "pe_ratio": 12.0, "pb_ratio": 2.8},
        ]
        filtered = rows
        if industry:
            filtered = [row for row in filtered if industry in str(row.get("industry") or "")]
        if min_market_cap is not None:
            filtered = [row for row in filtered if float(row.get("market_cap") or 0.0) >= float(min_market_cap)]
        return filtered[offset: offset + limit]

    async def count_stock_universe(self, min_market_cap=None, industry=None, market=None):
        rows = await self.list_stock_universe(limit=1000, offset=0, min_market_cap=min_market_cap, industry=industry, market=market)
        return len(rows)

    async def get_financials(self, code, limit=4):
        return [{"code": code, "report_date": "2025-12-31", "revenue_growth": 0.12, "profit_growth": 0.15, "roe": 0.18}]

    async def get_factor_values(self, stock_codes, factor_name, start_date=None, end_date=None):
        rows = []
        for idx, code in enumerate(list(stock_codes or []), 1):
            rows.append({"stock_code": code, "factor_date": "2026-03-07", "factor_name": factor_name, "factor_value": 0.1 * idx})
        return rows

    async def count_strategies_by_type(self, status):
        counts = {}
        allowed_statuses = self._expand_strategy_status_filter(status)
        for s in self._strategies.values():
            if self._normalize_strategy_status(s.get("status")) in allowed_statuses:
                t = s.get("strategy_type", "unknown")
                counts[t] = counts.get(t, 0) + 1
        return counts

    async def save_strategy_quality_report(self, sid, report_type, report):
        now = datetime.now().isoformat()
        existing = self._quality_reports.get((sid, report_type)) or {}
        self._quality_reports[(sid, report_type)] = {
            **dict(report),
            "report_type": report_type,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }

    async def get_strategy_quality_report(self, sid, report_type="submission"):
        return self._quality_reports.get((sid, report_type))

    async def get_latest_strategy_quality_report(self, sid):
        rows = await self.list_strategy_quality_reports(sid, limit=1)
        return rows[0] if rows else None

    async def list_strategy_quality_reports(self, sid, limit=10):
        rows = [
            dict(report)
            for (strategy_id, _report_type), report in self._quality_reports.items()
            if strategy_id == sid
        ]
        rows.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return rows[:limit]

    async def list_strategy_status_events(
        self,
        sid,
        event_type=None,
        from_status=None,
        to_status=None,
        actor_id=None,
        start_time=None,
        end_time=None,
        limit=50,
    ):
        rows = list(reversed(self._events.get(sid, [])))
        start_dt = self._parse_event_time(start_time)
        end_dt = self._parse_event_time(end_time)
        filtered = []
        for item in rows:
            if event_type and item.get("event_type") != event_type:
                continue
            if from_status and item.get("from_status") != from_status:
                continue
            if to_status and item.get("to_status") != to_status:
                continue
            if actor_id and item.get("actor_id") != actor_id:
                continue
            created_at = self._parse_event_time(item.get("created_at"))
            if start_dt and (created_at is None or created_at < start_dt):
                continue
            if end_dt and (created_at is None or created_at > end_dt):
                continue
            filtered.append(dict(item))
        return filtered[: max(1, min(int(limit or 50), 200))]

    async def save_strategy_domain_event(self, event):
        item = {'id': len(self._domain_events) + 1, 'created_at': datetime.now(timezone.utc).isoformat(), **dict(event)}
        self._domain_events.append(item)
        return dict(item)

    async def list_strategy_domain_events(self, strategy_id=None, aggregate_type=None, event_type=None, source=None, correlation_id=None, limit=50):
        rows = list(reversed(self._domain_events))
        filtered = []
        for item in rows:
            if strategy_id is not None and item.get('strategy_id') != strategy_id:
                continue
            if aggregate_type and item.get('aggregate_type') != aggregate_type:
                continue
            if event_type and item.get('event_type') != event_type:
                continue
            if source and item.get('source') != source:
                continue
            if correlation_id and item.get('correlation_id') != correlation_id:
                continue
            filtered.append(dict(item))
        return filtered[: max(1, min(int(limit or 50), 500))]

    async def save_strategy_factory_run(self, run):
        self._factory_runs = [item for item in self._factory_runs if item.get("run_id") != run.get("run_id")]
        self._factory_runs.append(dict(run))
        self._factory_runs.sort(key=lambda item: item.get("started_at") or "", reverse=True)

    async def list_strategy_factory_runs(self, limit=20):
        return self._factory_runs[:limit]

    async def get_latest_strategy_factory_run(self):
        rows = await self.list_strategy_factory_runs(limit=1)
        return rows[0] if rows else None

    async def get_strategy_factory_run(self, run_id):
        for item in self._factory_runs:
            if item.get("run_id") == run_id:
                return item
        return None

    @staticmethod
    def _normalize_snapshot_date(snapshot_date):
        return str(snapshot_date)

    async def save_daily_snapshot(self, snapshot_date, data):
        normalized = self._normalize_snapshot_date(snapshot_date)
        item = {"snapshot_date": normalized, **dict(data)}
        self._daily_snapshots = [row for row in self._daily_snapshots if row.get("snapshot_date") != normalized]
        self._daily_snapshots.append(item)
        self._daily_snapshots.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)

    async def save_factory_market_internal_snapshot(self, item):
        payload = {"snapshot_date": self._normalize_snapshot_date((item or {}).get("snapshot_date") or (item or {}).get("date")), **dict(item or {})}
        self._factory_market_internals = [row for row in self._factory_market_internals if row.get("snapshot_date") != payload.get("snapshot_date")]
        self._factory_market_internals.append(payload)
        self._factory_market_internals.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)
        return dict(payload)

    async def get_factory_market_internal_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return dict(self._factory_market_internals[0]) if self._factory_market_internals else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._factory_market_internals:
            if item.get("snapshot_date") == normalized:
                return dict(item)
        return None

    async def list_factory_market_internal_snapshots(self, limit=20):
        return [dict(item) for item in self._factory_market_internals[: max(1, min(int(limit or 20), 200))]]

    async def get_recent_north_fund_summary(self, days=3, sample_limit=5):
        if self._north_fund_summary is not None:
            return dict(self._north_fund_summary)
        return None

    async def get_daily_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return self._daily_snapshots[0] if self._daily_snapshots else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._daily_snapshots:
            if item.get("snapshot_date") == normalized:
                return item
        return None

    async def list_daily_snapshots(self, limit=20, start_date=None, end_date=None):
        rows = list(self._daily_snapshots)
        if start_date:
            rows = [row for row in rows if row.get("snapshot_date") >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get("snapshot_date") <= str(end_date)]
        return rows[:limit]

    async def save_factory_event_cluster(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        self._factory_event_clusters = [row for row in self._factory_event_clusters if str(row.get('event_id') or '').strip() != event_id]
        saved = dict(item or {})
        saved.setdefault('event_id', event_id)
        self._factory_event_clusters.append(saved)
        self._factory_event_clusters.sort(key=lambda row: row.get('last_seen_at') or row.get('occurred_at') or '', reverse=True)
        return saved

    async def list_factory_event_clusters(self, status=None, event_type=None, limit=20):
        rows = [dict(item) for item in self._factory_event_clusters]
        if status:
            rows = [row for row in rows if str(row.get('status') or 'active') == str(status)]
        if event_type:
            rows = [row for row in rows if str(row.get('event_type') or '') == str(event_type)]
        rows.sort(key=lambda row: (row.get('last_seen_at') or row.get('occurred_at') or '', float(row.get('confidence') or 0.0)), reverse=True)
        return rows[: max(1, min(int(limit or 20), 200))]

    async def save_factory_theme_definition(self, item):
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_theme_definitions = [row for row in self._factory_theme_definitions if str(row.get('theme_code') or '').strip() != theme_code]
        saved = dict(item or {})
        saved.setdefault('theme_code', theme_code)
        self._factory_theme_definitions.append(saved)
        self._factory_theme_definitions.sort(key=lambda row: str(row.get('theme_code') or ''))
        return saved

    async def list_factory_theme_definitions(self, active_only=True, limit=200):
        rows = [dict(item) for item in self._factory_theme_definitions]
        if active_only:
            rows = [row for row in rows if bool(row.get('active', True))]
        rows.sort(key=lambda row: str(row.get('theme_code') or ''))
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_company_theme_exposure(self, item):
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        exposure_type = str((item or {}).get('exposure_type') or 'revenue')
        self._factory_company_theme_exposures = [
            row for row in self._factory_company_theme_exposures
            if not (
                str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
                and str(row.get('exposure_type') or 'revenue') == exposure_type
            )
        ]
        saved = dict(item or {})
        self._factory_company_theme_exposures.append(saved)
        self._factory_company_theme_exposures.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return saved

    async def list_factory_company_theme_exposures(self, theme_codes=None, symbols=None, limit=200):
        rows = [dict(item) for item in self._factory_company_theme_exposures]
        normalized_theme_codes = {str(item).strip() for item in list(theme_codes or []) if str(item).strip()}
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_theme_codes:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() in normalized_theme_codes]
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        rows.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_event_signal(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_event_signals = [
            row for row in self._factory_event_signals
            if not (
                str(row.get('event_id') or '').strip() == event_id
                and str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
            )
        ]
        saved = dict(item or {})
        self._factory_event_signals.append(saved)
        self._factory_event_signals.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return saved

    async def list_factory_event_signals(self, event_id=None, theme_code=None, symbols=None, min_final_score=None, limit=200):
        rows = [dict(item) for item in self._factory_event_signals]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '').strip() == str(event_id)]
        if theme_code is not None:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() == str(theme_code)]
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        if min_final_score is not None:
            rows = [row for row in rows if float(row.get('final_score') or 0.0) >= float(min_final_score)]
        rows.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_task_evidence(self, item):
        saved = dict(item or {})
        self._factory_task_evidence.append(saved)
        self._factory_task_evidence.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return saved

    async def list_factory_task_evidence(self, task_key=None, event_id=None, limit=200):
        rows = [dict(item) for item in self._factory_task_evidence]
        if task_key:
            rows = [row for row in rows if str(row.get('task_key') or '') == str(task_key)]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '') == str(event_id)]
        rows.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def get_paper_account_by_strategy(self, strategy_id):
        for item in self._paper_accounts.values():
            if item.get('strategy_id') == strategy_id:
                return dict(item)
        return None

    async def get_paper_account(self, account_id):
        item = self._paper_accounts.get(account_id)
        return dict(item) if item else None

    async def save_paper_account(self, account):
        item = dict(account)
        existing = self._paper_accounts.get(item['id']) or {}
        merged = {**existing, **item}
        self._paper_accounts[item['id']] = merged
        return dict(merged)

    async def update_paper_account_status(self, account_id, status, stage=None, promotion_candidate=None):
        account = self._paper_accounts.get(account_id)
        if not account:
            return None
        account['status'] = status
        if stage is not None:
            account['incubation_stage'] = stage
        if promotion_candidate is not None:
            account['promotion_candidate'] = promotion_candidate
        return dict(account)

    async def list_strategy_paper_orders(self, strategy_id, signal_date=None, status=None, limit=200):
        rows = [dict(item) for item in self._paper_orders if item.get('strategy_id') == strategy_id]
        if signal_date is not None:
            rows = [item for item in rows if str(item.get('signal_date')) == str(signal_date)]
        if status is not None:
            rows = [item for item in rows if str(item.get('status')) == str(status)]
        rows.sort(key=lambda item: int(item.get('id') or 0), reverse=True)
        return rows[:limit]

    async def save_paper_order(self, order):
        item = dict(order)
        item.setdefault('id', len(self._paper_orders) + 1)
        self._paper_orders.append(item)
        return dict(item)

    async def update_paper_order(self, order_id, updates):
        for item in self._paper_orders:
            if int(item.get('id')) == int(order_id):
                item.update(dict(updates or {}))
                return dict(item)
        return None

    async def list_paper_positions(self, account_id):
        rows = [dict(item) for item in self._paper_positions.values() if item.get('account_id') == account_id]
        rows.sort(key=lambda item: str(item.get('stock_code') or ''))
        return rows

    async def save_paper_position(self, position):
        item = dict(position)
        key = (item.get('account_id'), item.get('stock_code'))
        existing = self._paper_positions.get(key) or {}
        merged = {**existing, **item}
        self._paper_positions[key] = merged
        return dict(merged)

    async def save_paper_trade(self, trade):
        item = dict(trade)
        self._paper_trades.append(item)
        return dict(item)

    async def save_paper_nav(self, nav):
        item = dict(nav)
        rows = [row for row in self._paper_nav.get(item['account_id'], []) if str(row.get('nav_date')) != str(item.get('nav_date'))]
        rows.append(item)
        self._paper_nav[item['account_id']] = rows
        return dict(item)

    async def get_paper_nav_rows(self, account_id, limit=60):
        rows = list(self._paper_nav.get(account_id, []))
        rows.sort(key=lambda row: row.get('nav_date') or '', reverse=True)
        return rows[:limit]

    async def get_paper_order_summary(self, account_id):
        orders = [item for item in self._paper_orders if item.get('account_id') == account_id]
        return {
            'total_orders': len(orders),
            'total_trades': len([item for item in orders if item.get('status') == 'filled']),
            'trade_amount': float(sum((item.get('price') or 0) * (item.get('shares') or 0) for item in orders if item.get('status') == 'filled')),
        }

    async def save_strategy_incubation_account(self, strategy_id, account_id, stage='warmup', status='active', source_run_id=None, metadata=None):
        item = {
            'id': len(self._incubation_accounts) + 1,
            'strategy_id': strategy_id,
            'account_id': account_id,
            'stage': stage,
            'status': status,
            'source_run_id': source_run_id,
            'metadata': metadata or {},
        }
        self._incubation_accounts = [row for row in self._incubation_accounts if not (row.get('strategy_id') == strategy_id and row.get('account_id') == account_id)]
        self._incubation_accounts.append(item)
        return dict(item)

    async def get_strategy_incubation_account(self, strategy_id, account_id=None):
        rows = [row for row in self._incubation_accounts if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_incubation_accounts(self, strategy_id=None, status=None, limit=20):
        rows = list(self._incubation_accounts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_metric(self, strategy_id, metric_date, metric):
        item = {'strategy_id': strategy_id, 'metric_date': str(metric_date), **dict(metric)}
        self._incubation_metrics = [row for row in self._incubation_metrics if not (row.get('strategy_id') == strategy_id and row.get('metric_date') == str(metric_date))]
        self._incubation_metrics.append(item)
        self._incubation_metrics.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return dict(item)

    async def get_latest_strategy_incubation_metric(self, strategy_id):
        rows = await self.list_strategy_incubation_metrics(strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_metrics(self, strategy_id, limit=30, start_date=None, end_date=None):
        rows = [row for row in self._incubation_metrics if row.get('strategy_id') == strategy_id]
        if start_date:
            rows = [row for row in rows if row.get('metric_date') >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get('metric_date') <= str(end_date)]
        rows.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_pipeline_snapshot(self, snapshot):
        item = {'id': len(self._incubation_pipeline_snapshots) + 1, **dict(snapshot)}
        self._incubation_pipeline_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id):
        rows = await self.list_strategy_incubation_pipeline_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_pipeline_snapshots(self, strategy_id=None, pipeline_stage=None, pipeline_status=None, limit=20):
        rows = list(self._incubation_pipeline_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if pipeline_stage:
            rows = [row for row in rows if row.get('pipeline_stage') == pipeline_stage]
        if pipeline_status:
            rows = [row for row in rows if row.get('pipeline_status') == pipeline_status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_event(self, event):
        item = {'id': len(self._risk_events) + 1, **dict(event)}
        self._risk_events.append(item)
        return dict(item)

    async def list_strategy_runtime_risk_events(self, strategy_id=None, account_id=None, status=None, severity=None, limit=50):
        rows = list(self._risk_events)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if status:
            rows = [row for row in rows if row.get('status', 'open') == status]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_snapshot(self, snapshot):
        item = {'id': len(self._runtime_risk_snapshots) + 1, **dict(snapshot)}
        self._runtime_risk_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_risk_snapshot(self, strategy_id):
        rows = await self.list_strategy_runtime_risk_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_risk_snapshots(self, strategy_id=None, posture_level=None, control_mode=None, limit=20):
        rows = list(self._runtime_risk_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if posture_level:
            rows = [row for row in rows if row.get('posture_level') == posture_level]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_alert(self, alert):
        existing = None
        alert_id = alert.get('alert_id')
        if alert_id is not None:
            for item in self._runtime_alerts:
                if int(item.get('alert_id')) == int(alert_id):
                    existing = item
                    break
        now = datetime.now(timezone.utc).isoformat()
        if existing is not None:
            existing.update(dict(alert))
            existing['updated_at'] = now
            if existing.get('status') == 'resolved' and not existing.get('resolved_at'):
                existing['resolved_at'] = now
            return dict(existing)
        item = {
            'status': 'open',
            'channels': [],
            'related_event_ids': [],
            'metadata': {},
            'created_at': now,
            'updated_at': now,
            **{k: v for k, v in dict(alert).items() if not (k == 'alert_id' and v is None)},
            'alert_id': len(self._runtime_alerts) + 1,
        }
        self._runtime_alerts.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_alert(self, strategy_id, alert_key=None, category=None, status='open_or_ack'):
        rows = await self.list_strategy_runtime_alerts(strategy_id=strategy_id, alert_key=alert_key, category=category, status=status, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_alerts(self, strategy_id=None, account_id=None, category=None, severity=None, status=None, alert_key=None, limit=50):
        rows = list(self._runtime_alerts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if category:
            rows = [row for row in rows if row.get('category') == category]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        if alert_key:
            rows = [row for row in rows if row.get('alert_key') == alert_key]
        if status:
            if status == 'open_or_ack':
                rows = [row for row in rows if row.get('status', 'open') in {'open', 'acknowledged'}]
            else:
                rows = [row for row in rows if row.get('status', 'open') == status]
        rows = sorted(rows, key=lambda row: row.get('updated_at') or row.get('created_at') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def acknowledge_strategy_runtime_alert(self, alert_id, acknowledged_by=None, source='runtime_alerts'):
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if int(item.get('alert_id')) == int(alert_id):
                if item.get('status') != 'resolved':
                    item['status'] = 'acknowledged'
                item['acknowledged_by'] = acknowledged_by
                item['acknowledged_at'] = item.get('acknowledged_at') or now
                item['updated_at'] = now
                item['metadata'] = {**dict(item.get('metadata') or {}), 'ack_source': source}
                return dict(item)
        return None

    async def resolve_strategy_runtime_alerts(self, strategy_id=None, alert_id=None, alert_key=None, category=None, resolution=None, source='runtime_alerts'):
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if item.get('status', 'open') == 'resolved':
                continue
            if strategy_id and item.get('strategy_id') != strategy_id:
                continue
            if alert_id is not None and int(item.get('alert_id')) != int(alert_id):
                continue
            if alert_key and item.get('alert_key') != alert_key:
                continue
            if category and item.get('category') != category:
                continue
            item['status'] = 'resolved'
            item['resolved_at'] = item.get('resolved_at') or now
            item['updated_at'] = now
            item['metadata'] = {**dict(item.get('metadata') or {}), 'resolution': resolution or {}, 'resolution_source': source}
            rows.append(dict(item))
        return rows

    async def save_strategy_runtime_control(self, control):
        existing = self._runtime_controls.get(control['strategy_id'])
        item = {
            'id': (existing or {}).get('id', len(self._runtime_controls) + 1),
            **dict(existing or {}),
            **dict(control),
        }
        self._runtime_controls[item['strategy_id']] = item
        return dict(item)

    async def get_strategy_runtime_control(self, strategy_id):
        item = self._runtime_controls.get(strategy_id)
        return dict(item) if item else None

    async def list_strategy_runtime_controls(self, strategy_id=None, control_mode=None, status=None, limit=50):
        rows = list(self._runtime_controls.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_promotion_review(self, review):
        item = {'id': len(self._promotion_reviews) + 1, **dict(review)}
        self._promotion_reviews.append(item)
        return dict(item)

    async def get_latest_strategy_promotion_review(self, strategy_id):
        rows = [row for row in self._promotion_reviews if row.get('strategy_id') == strategy_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_promotion_reviews(self, strategy_id=None, status=None, limit=50):
        rows = list(self._promotion_reviews)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_projection_snapshot(self, snapshot):
        item = {'id': len(self._projection_snapshots) + 1, **dict(snapshot)}
        self._projection_snapshots.append(item)
        return dict(item)

    async def get_latest_strategy_projection_snapshot(self, strategy_id, projection_type='strategy_state'):
        rows = [row for row in self._projection_snapshots if row.get('strategy_id') == strategy_id and row.get('projection_type', 'strategy_state') == projection_type]
        return dict(rows[-1]) if rows else None

    async def list_strategy_projection_snapshots(self, strategy_id=None, projection_type=None, limit=50):
        rows = list(self._projection_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if projection_type:
            rows = [row for row in rows if row.get('projection_type') == projection_type]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def resolve_strategy_runtime_risk_event(self, event_id, resolution=None):
        for item in self._risk_events:
            if int(item.get('id')) == int(event_id):
                item['status'] = 'resolved'
                item['resolution'] = resolution or {}
                return dict(item)
        return None

    async def save_strategy_vector_profile(self, profile):
        payload = dict(profile)
        payload['index_name'] = payload.get('index_name') or dict(payload.get('metadata') or {}).get('index_name') or 'strategy_behavior'
        item = {'id': len(self._vector_profiles) + 1, **payload}
        self._vector_profiles.append(item)
        if self.supports_pgvector() and int(item.get('vector_dim') or len(item.get('embedding') or [])) > 0:
            store_row = {
                'profile_id': item['id'],
                'strategy_id': item.get('strategy_id'),
                'index_name': item.get('index_name') or 'strategy_behavior',
                'index_version': item.get('index_version'),
                'profile_type': item.get('profile_type'),
                'vector_method': item.get('vector_method'),
                'metric': item.get('metric') or 'cosine',
                'vector_dim': int(item.get('vector_dim') or len(item.get('embedding') or [])),
                'embedding': list(item.get('embedding') or []),
                'metadata': dict(item.get('metadata') or {}),
                'updated_at': item.get('updated_at') or item.get('created_at'),
            }
            self._vector_profile_store = [row for row in self._vector_profile_store if row.get('profile_id') != item['id']]
            self._vector_profile_store.append(store_row)
        return dict(item)

    async def list_strategy_vector_profiles(self, strategy_id=None, profile_type=None, index_name=None, index_version=None, limit=20):
        rows = list(self._vector_profiles)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if index_name:
            rows = [row for row in rows if (row.get('index_name') or dict(row.get('metadata') or {}).get('index_name') or 'strategy_behavior') == index_name]
        if profile_type:
            rows = [row for row in rows if row.get('profile_type') == profile_type]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        rows.sort(key=lambda row: (str(row.get('updated_at') or ''), str(row.get('created_at') or '')), reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def save_vector_index_registry(self, entry):
        item = dict(entry)
        self._vector_indexes = [row for row in self._vector_indexes if not (row.get('index_name') == item.get('index_name') and row.get('index_version') == item.get('index_version'))]
        self._vector_indexes.append(item)
        return dict(item)

    async def list_vector_index_registry(self, index_name=None, status=None, limit=20):
        rows = list(self._vector_indexes)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_vector_index_snapshot(self, snapshot):
        item = {'id': len(self._vector_index_snapshots) + 1, **dict(snapshot)}
        self._vector_index_snapshots = [
            row for row in self._vector_index_snapshots
            if not (row.get('index_name') == item.get('index_name') and row.get('index_version') == item.get('index_version'))
        ]
        self._vector_index_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_vector_index_snapshot(self, index_name='strategy_behavior'):
        rows = await self.list_strategy_vector_index_snapshots(index_name=index_name, limit=1)
        return rows[0] if rows else None

    async def list_strategy_vector_index_snapshots(self, index_name=None, index_version=None, status=None, limit=20):
        rows = list(self._vector_index_snapshots)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def replace_strategy_vector_index_items(self, index_name, index_version, items):
        self._vector_index_items = [
            row for row in self._vector_index_items
            if not (row.get('index_name') == index_name and row.get('index_version') == index_version)
        ]
        if self.supports_pgvector():
            self._vector_index_item_store = [
                row for row in self._vector_index_item_store
                if not (row.get('index_name') == index_name and row.get('index_version') == index_version)
            ]
        for item in items:
            stored = {'id': len(self._vector_index_items) + 1, 'index_name': index_name, 'index_version': index_version, **dict(item)}
            self._vector_index_items.append(stored)
            if self.supports_pgvector() and int(stored.get('vector_dim') or len(stored.get('embedding') or [])) > 0:
                self._vector_index_item_store.append({
                    'item_id': stored['id'],
                    'index_name': index_name,
                    'index_version': index_version,
                    'strategy_id': stored.get('strategy_id'),
                    'profile_id': stored.get('profile_id'),
                    'profile_type': stored.get('profile_type'),
                    'vector_method': stored.get('vector_method'),
                    'metric': stored.get('metric') or 'cosine',
                    'vector_dim': int(stored.get('vector_dim') or len(stored.get('embedding') or [])),
                    'embedding': list(stored.get('embedding') or []),
                    'metadata': dict(stored.get('metadata') or {}),
                    'updated_at': stored.get('updated_at') or stored.get('created_at'),
                })
        return {'index_name': index_name, 'index_version': index_version, 'count': len(items)}

    async def list_strategy_vector_index_items(self, index_name=None, index_version=None, bucket_ids=None, strategy_id=None, limit=200):
        rows = list(self._vector_index_items)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        if bucket_ids:
            rows = [row for row in rows if row.get('bucket_id') in set(bucket_ids)]
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        rows.sort(key=lambda row: float(row.get('coarse_score') or 0.0), reverse=True)
        return [dict(row) for row in rows[:limit]]

    @staticmethod
    def _vector_similarity(left, right, metric='cosine'):
        a = [float(item) for item in list(left or [])]
        b = [float(item) for item in list(right or [])]
        if not a or len(a) != len(b):
            return 0.0
        if metric == 'euclidean':
            distance = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
            return 1.0 / (1.0 + distance)
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a <= 1e-12 or norm_b <= 1e-12:
            return 0.0
        return dot / (norm_a * norm_b)

    async def search_strategy_vector_profiles_by_embedding(self, query_embedding, profile_type=None, index_name=None, index_version=None, exclude_strategy_id=None, limit=20, metric='cosine'):
        if not self.supports_pgvector():
            return []
        rows = await self.list_strategy_vector_profiles(profile_type=profile_type, index_name=index_name, index_version=index_version, limit=5000)
        results = []
        for row in rows:
            if exclude_strategy_id and row.get('strategy_id') == exclude_strategy_id:
                continue
            similarity = self._vector_similarity(query_embedding, row.get('embedding') or [], metric=metric)
            results.append({**dict(row), 'similarity': round(float(similarity), 6)})
        results.sort(key=lambda row: row.get('similarity', 0.0), reverse=True)
        return results[:limit]

    async def search_strategy_vector_index_items_by_embedding(self, query_embedding, index_name, index_version, profile_type=None, exclude_strategy_id=None, limit=80, metric='cosine'):
        if not self.supports_pgvector():
            return []
        rows = await self.list_strategy_vector_index_items(index_name=index_name, index_version=index_version, limit=5000)
        if profile_type:
            rows = [row for row in rows if row.get('profile_type') == profile_type]
        if exclude_strategy_id:
            rows = [row for row in rows if row.get('strategy_id') != exclude_strategy_id]
        results = []
        for row in rows:
            similarity = self._vector_similarity(query_embedding, row.get('embedding') or [], metric=metric)
            results.append({**dict(row), 'similarity': round(float(similarity), 6)})
        results.sort(key=lambda row: row.get('similarity', 0.0), reverse=True)
        return results[:limit]

    async def ensure_strategy_vector_index_item_pgvector_index(self, index_name, index_version, vector_dim, metric='cosine'):
        if not self.supports_pgvector() or int(vector_dim or 0) <= 0:
            return None
        idx_name = f"idx_svi_pg_hnsw_{self._sanitize_index_part(index_name)}_{self._sanitize_index_part(index_version)}_{int(vector_dim)}_{self._sanitize_index_part(metric)}"
        row = {
            'schemaname': 'public',
            'tablename': 'strategy_vector_index_item_store',
            'indexname': idx_name,
            'indexdef': f"CREATE INDEX {idx_name} ON strategy_vector_index_item_store USING hnsw ((embedding::vector({int(vector_dim)}) vector_cosine_ops)) WHERE index_name = '{index_name}' AND index_version = '{index_version}' AND vector_dim = {int(vector_dim)}",
            'index_name': index_name,
            'index_version': index_version,
        }
        self._vector_hnsw_indexes = [item for item in self._vector_hnsw_indexes if item.get('indexname') != idx_name]
        self._vector_hnsw_indexes.append(row)
        return idx_name

    async def ensure_strategy_vector_profile_pgvector_index(self, index_name, index_version, vector_dim, profile_type=None, metric='cosine'):
        if not self.supports_pgvector() or int(vector_dim or 0) <= 0:
            return None
        suffix = profile_type or 'all'
        idx_name = f"idx_svp_pg_hnsw_{self._sanitize_index_part(index_name)}_{self._sanitize_index_part(index_version)}_{int(vector_dim)}_{self._sanitize_index_part(suffix)}_{self._sanitize_index_part(metric)}"
        where_parts = [
            f"index_name = '{index_name}'",
            f"index_version = '{index_version}'",
            f"vector_dim = {int(vector_dim)}",
        ]
        if profile_type:
            where_parts.append(f"profile_type = '{profile_type}'")
        row = {
            'schemaname': 'public',
            'tablename': 'strategy_vector_profile_store',
            'indexname': idx_name,
            'indexdef': f"CREATE INDEX {idx_name} ON strategy_vector_profile_store USING hnsw ((embedding::vector({int(vector_dim)}) vector_cosine_ops)) WHERE {' AND '.join(where_parts)}",
            'index_name': index_name,
            'index_version': index_version,
        }
        self._vector_hnsw_indexes = [item for item in self._vector_hnsw_indexes if item.get('indexname') != idx_name]
        self._vector_hnsw_indexes.append(row)
        return idx_name

    async def list_strategy_vector_hnsw_indexes(self, index_name=None, index_version=None, limit=200):
        rows = list(self._vector_hnsw_indexes)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name or f"'{index_name}'" in str(row.get('indexdef') or '')]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version or f"'{index_version}'" in str(row.get('indexdef') or '')]
        rows.sort(key=lambda row: (str(row.get('tablename') or ''), str(row.get('indexname') or '')))
        return [dict(row) for row in rows[:limit]]

    async def get_strategy_vector_health(self, index_name='strategy_behavior', limit_versions=20, include_hnsw_indexes=False):
        table_flags = {
            'strategy_vector_profiles': True,
            'strategy_vector_profile_store': self.supports_pgvector(),
            'strategy_vector_index_snapshots': True,
            'strategy_vector_index_items': True,
            'strategy_vector_index_item_store': self.supports_pgvector(),
        }
        counts = {
            'profiles': sum(1 for row in self._vector_profiles if (row.get('index_name') or 'strategy_behavior') == index_name),
            'profile_store': sum(1 for row in self._vector_profile_store if row.get('index_name') == index_name),
            'index_snapshots': sum(1 for row in self._vector_index_snapshots if row.get('index_name') == index_name),
            'index_items': sum(1 for row in self._vector_index_items if row.get('index_name') == index_name),
            'index_item_store': sum(1 for row in self._vector_index_item_store if row.get('index_name') == index_name),
        }
        versions = {}
        for row in self._vector_indexes:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['registry_status'] = row.get('status')
            item['registry_backend'] = row.get('backend')
            item['sample_count'] = int(row.get('sample_count') or item['sample_count'] or 0)
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_snapshots:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['snapshot_status'] = row.get('status')
            item['snapshot_backend'] = row.get('backend')
            item['profile_count'] = int(row.get('profile_count') or item['profile_count'] or 0)
            item['bucket_count'] = int(row.get('bucket_count') or item['bucket_count'] or 0)
            item['vector_dim'] = int(row.get('vector_dim') or item['vector_dim'] or 0)
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_profiles:
            if (row.get('index_name') or 'strategy_behavior') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['profile_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_profile_store:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['profile_store_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_items:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['index_item_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_item_store:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['index_item_store_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        latest_snapshot = next((dict(row) for row in sorted(
            [row for row in self._vector_index_snapshots if row.get('index_name') == index_name],
            key=lambda row: (self._best_timestamp(row), str(row.get('index_version') or '')),
            reverse=True,
        )), None)
        latest_snapshot_version = str((latest_snapshot or {}).get('index_version') or '')
        version_rows = [dict(row) for row in versions.values()]

        def _version_sort_key(row):
            priority = 3
            version = str(row.get('index_version') or '')
            if latest_snapshot_version and version == latest_snapshot_version:
                priority = 0
            elif str(row.get('snapshot_status') or '').lower() == 'active':
                priority = 1
            elif str(row.get('registry_status') or '').lower() == 'active':
                priority = 2
            return (priority, -(datetime.fromisoformat(str(row.get('last_seen')).replace('Z', '+00:00')).timestamp() if row.get('last_seen') else 0.0), version)

        version_rows.sort(key=_version_sort_key)
        hnsw_indexes = await self.list_strategy_vector_hnsw_indexes(index_name=index_name, limit=500) if include_hnsw_indexes else []
        return {
            'index_name': index_name,
            'backend': self.get_vector_backend(),
            'pgvector_enabled': self.supports_pgvector(),
            'pgvector_extension': {'extname': 'vector', 'extversion': '0.8.1'} if self.supports_pgvector() else None,
            'tables': table_flags,
            'counts': counts,
            'latest_snapshot': latest_snapshot,
            'versions': [dict(row) for row in version_rows[:limit_versions]],
            'hnsw_indexes': hnsw_indexes,
            'hnsw_index_count': len(hnsw_indexes),
            'recommended_cleanup_versions': [row.get('index_version') for row in version_rows[1:] if row.get('index_version')],
        }

    async def cleanup_strategy_vector_history(self, index_name='strategy_behavior', keep_versions=1, dry_run=True, cleanup_hnsw=True, limit_versions=200, protect_versions=None):
        health = await self.get_strategy_vector_health(index_name=index_name, limit_versions=limit_versions, include_hnsw_indexes=cleanup_hnsw)
        versions = [row for row in list(health.get('versions') or []) if row.get('index_version')]
        latest_snapshot_version = str((health.get('latest_snapshot') or {}).get('index_version') or '').strip()
        keep_total = max(0, int(keep_versions or 0))
        protected = []
        if latest_snapshot_version:
            protected.append(latest_snapshot_version)
        protected_limit = max(keep_total, 1 if latest_snapshot_version else 0)
        for row in versions:
            version = str(row.get('index_version') or '').strip()
            if not version or version in protected:
                continue
            if len(protected) >= protected_limit:
                break
            protected.append(version)
        protected.extend(str(item) for item in list(protect_versions or []) if str(item).strip())
        protected_set = {item for item in protected if item}
        target_versions = [row for row in versions if str(row.get('index_version')) not in protected_set]
        target_set = {str(row.get('index_version')) for row in target_versions if row.get('index_version')}
        hnsw_indexes = list(health.get('hnsw_indexes') or []) if cleanup_hnsw else []
        indexes_to_drop = [row for row in hnsw_indexes if row.get('index_version') in target_set or any(f"'{version}'" in str(row.get('indexdef') or '') for version in target_set)]
        summary = {
            'index_name': index_name,
            'dry_run': bool(dry_run),
            'keep_versions': max(0, int(keep_versions or 0)),
            'protected_versions': sorted(protected_set),
            'target_versions': [row.get('index_version') for row in target_versions],
            'hnsw_indexes_to_drop': [row.get('indexname') for row in indexes_to_drop],
            'deleted': {
                'vector_index_registry': 0,
                'vector_index_snapshots': 0,
                'vector_profiles': 0,
                'vector_profile_store': 0,
                'vector_index_items': 0,
                'vector_index_item_store': 0,
                'hnsw_indexes': 0,
            },
            'version_details': [dict(row) for row in target_versions],
        }
        if dry_run or not target_set:
            return summary

        def _delete_rows(rows, *, key):
            kept = [row for row in rows if not (row.get('index_name') == index_name and row.get('index_version') in target_set)]
            return kept, len(rows) - len(kept)

        self._vector_indexes, summary['deleted']['vector_index_registry'] = _delete_rows(self._vector_indexes, key='index_version')
        self._vector_index_snapshots, summary['deleted']['vector_index_snapshots'] = _delete_rows(self._vector_index_snapshots, key='index_version')
        self._vector_profiles, summary['deleted']['vector_profiles'] = _delete_rows(self._vector_profiles, key='index_version')
        self._vector_profile_store, summary['deleted']['vector_profile_store'] = _delete_rows(self._vector_profile_store, key='index_version')
        self._vector_index_items, summary['deleted']['vector_index_items'] = _delete_rows(self._vector_index_items, key='index_version')
        self._vector_index_item_store, summary['deleted']['vector_index_item_store'] = _delete_rows(self._vector_index_item_store, key='index_version')
        if cleanup_hnsw:
            kept_indexes = [
                row for row in self._vector_hnsw_indexes
                if not (row.get('index_name') == index_name and (row.get('index_version') in target_set or any(f"'{version}'" in str(row.get('indexdef') or '') for version in target_set)))
            ]
            summary['deleted']['hnsw_indexes'] = len(self._vector_hnsw_indexes) - len(kept_indexes)
            self._vector_hnsw_indexes = kept_indexes
        return summary

    async def save_strategy_generation_experiment(self, experiment):
        payload = dict(experiment)
        existing = self._experiments.get(payload['experiment_id']) or {}
        item = {**existing, **payload}
        self._experiments[item['experiment_id']] = item
        return dict(item)

    async def get_strategy_generation_experiment(self, experiment_id):
        item = self._experiments.get(experiment_id)
        return dict(item) if item else None

    async def list_strategy_generation_experiments(self, strategy_id=None, parent_strategy_id=None, generated_strategy_id=None, task_run_id=None, status=None, source=None, limit=20):
        rows = list(self._experiments.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id or row.get('parent_strategy_id') == strategy_id or row.get('generated_strategy_id') == strategy_id]
        if parent_strategy_id:
            rows = [row for row in rows if row.get('parent_strategy_id') == parent_strategy_id]
        if generated_strategy_id:
            rows = [row for row in rows if row.get('generated_strategy_id') == generated_strategy_id]
        if task_run_id is not None:
            rows = [row for row in rows if int(row.get('task_run_id') or 0) == int(task_run_id)]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        if source:
            rows = [row for row in rows if row.get('source') == source]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_task_run(self, run):
        item = {'id': len(self._task_runs) + 1, **dict(run)}
        self._task_runs.append(item)
        return dict(item)

    async def update_strategy_task_run(self, run_id, status=None, result=None, error=None, completed_at=None):
        for item in self._task_runs:
            if int(item.get('id')) == int(run_id):
                if status is not None:
                    item['status'] = status
                if result is not None:
                    item['result'] = result
                if error is not None:
                    item['error'] = error
                if completed_at is not None:
                    item['completed_at'] = completed_at
                return dict(item)
        return None

    async def list_strategy_task_runs(self, strategy_id=None, task_name=None, task_scope=None, status=None, limit=20):
        rows = list(self._task_runs)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if task_name:
            rows = [row for row in rows if row.get('task_name') == task_name]
        if task_scope:
            rows = [row for row in rows if row.get('task_scope') == task_scope]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]


class TestStrategyManager:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_help_action(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="help")
        assert r["success"] is True
        assert "create" in r["data"]["actions"]
        assert "review_report_recheck" in r["data"]["actions"]

    @pytest.mark.asyncio
    async def test_create_strategy(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "测试动量", "strategy_type": "momentum",
            "params": {"lookback": 20}, "author_id": "user1",
        }))
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert sid.startswith("strat_")
        assert db._strategies[sid]["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_strategy_accepts_structured_params(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", params={
            "name": "结构化参数策略",
            "strategy_type": "momentum",
            "params": {"lookback": 10},
            "author_id": "user2",
        })
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert db._strategies[sid]["author_id"] == "user2"

    @pytest.mark.asyncio
    async def test_create_strategy_accepts_dict_kwargs(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs={
            "name": "字典 kwargs 策略",
            "strategy_type": "momentum",
            "author_id": "user3",
        })
        assert r["success"] is True
        sid = r["data"]["strategy_id"]
        assert db._strategies[sid]["author_id"] == "user3"

    @pytest.mark.asyncio
    async def test_create_requires_name(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="create", kwargs="{}")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_publish_and_archive(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        pub = await mcp.strategy_manager(action="publish", kwargs=json.dumps({"strategy_id": sid}))
        assert pub["success"] is True
        assert pub["data"]["status"] == "listed"
        assert db._strategies[sid]["status"] == "listed"

        arc = await mcp.strategy_manager(action="archive", kwargs=json.dumps({"strategy_id": sid}))
        assert arc["success"] is True
        assert db._strategies[sid]["status"] == "archived"

    @pytest.mark.asyncio
    async def test_list_and_rank_keep_published_alias_compatible(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "alias-test",
            "strategy_type": "momentum",
        }))
        sid = cr["data"]["strategy_id"]

        await mcp.strategy_manager(action="publish", kwargs=json.dumps({"strategy_id": sid}))
        await db.save_strategy_metrics(sid, "all", {
            "total_return": 0.12,
            "annual_return": 0.10,
            "sharpe_ratio": 1.1,
            "max_drawdown": 0.08,
            "win_rate": 0.6,
            "calmar_ratio": 1.2,
        })

        listed_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({}))
        published_resp = await mcp.strategy_manager(action="list", kwargs=json.dumps({"status": "published"}))
        rank_resp = await mcp.strategy_manager(action="rank", kwargs=json.dumps({"status": "published"}))

        assert listed_resp["success"] is True
        assert listed_resp["data"]["count"] == 1
        assert listed_resp["data"]["strategies"][0]["status"] == "listed"
        assert published_resp["data"]["count"] == 1
        assert published_resp["data"]["strategies"][0]["id"] == sid
        assert rank_resp["data"]["count"] == 1
        assert rank_resp["data"]["strategies"][0]["id"] == sid

    @pytest.mark.asyncio
    async def test_review_rating_validation(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        r = await mcp.strategy_manager(action="review", kwargs=json.dumps({
            "strategy_id": sid, "rating": 6,
        }))
        assert r["success"] is False

        r = await mcp.strategy_manager(action="review", kwargs=json.dumps({
            "strategy_id": sid, "rating": 4, "comment": "不错",
        }))
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({"name": "test"}))
        sid = cr["data"]["strategy_id"]

        sub = await mcp.strategy_manager(action="subscribe", kwargs=json.dumps({
            "strategy_id": sid, "user_id": "u1",
        }))
        assert sub["success"] is True

        subs = await mcp.strategy_manager(action="my_subscriptions", kwargs=json.dumps({
            "user_id": "u1",
        }))
        assert subs["data"]["count"] == 1

        unsub = await mcp.strategy_manager(action="unsubscribe", kwargs=json.dumps({
            "strategy_id": sid, "user_id": "u1",
        }))
        assert unsub["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_action(self, setup):
        mcp, db = setup
        r = await mcp.strategy_manager(action="nonexistent_action")
        assert r["success"] is False
        assert "Unknown action" in r["error"]

    @pytest.mark.asyncio
    async def test_review_report_events_and_incubation_overview(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "孵化策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {"validation_grade": "B", "status_after_review": "incubating"},
            "quality_gate": {"passed": True, "wf_ic_ir": 0.41, "reasons": []},
            "validation_report": {},
            "risk_report": {},
            "dedup_report": {"match_type": None},
            "backtest_metrics": {},
            "snapshot": {},
        })
        await db.update_strategy_status(
            sid,
            "incubating",
            actor_id="seed-bot",
            reason="seed",
            metadata={"source": "submission", "batch": "A1"},
        )
        await db.update_strategy_status(
            sid,
            "listed",
            actor_id="reviewer",
            reason="promote",
            metadata={"source": "review", "score": 91},
        )
        now = datetime.now(timezone.utc)
        db._events[sid][0]["created_at"] = (now - timedelta(days=2)).isoformat()
        db._events[sid][1]["created_at"] = now.isoformat()
        await db.save_strategy_metrics(sid, "all", {"sharpe_ratio": 0.8, "max_drawdown": 0.12})
        db._signal_stats[sid] = {
            "hit_rate": {1: 0.51, 5: 0.52, 10: 0.50, 20: 0.49},
            "forward_ic": {1: 0.01, 5: 0.08, 10: 0.04, 20: 0.02},
            "forward_sharpe": {1: 0.12, 5: 0.66, 10: 0.41, 20: 0.20},
            "total_signals": 18,
        }

        review = await mcp.strategy_manager(action="review_report", kwargs=json.dumps({"strategy_id": sid}))
        events = await mcp.strategy_manager(action="events", kwargs=json.dumps({"strategy_id": sid}))
        filtered_events = await mcp.strategy_manager(action="events", kwargs=json.dumps({
            "strategy_id": sid,
            "event_type": "status_change",
            "from_status": "incubating",
            "to_status": "listed",
            "actor_id": "reviewer",
            "start_time": now.date().isoformat(),
            "end_time": now.date().isoformat(),
            "limit": 10,
        }))
        incubation = await mcp.strategy_manager(action="incubation_overview", kwargs=json.dumps({"strategy_id": sid}))

        assert review["success"] is True
        assert review["data"]["passed"] is True
        assert review["data"]["reports"][0]["report_type"] == "submission"
        assert events["data"]["count"] == 2
        assert events["data"]["events"][0]["event_type"] == "status_change"
        assert events["data"]["events"][0]["metadata"]["source"] == "review"
        assert filtered_events["success"] is True
        assert filtered_events["data"]["count"] == 1
        assert filtered_events["data"]["events"][0]["from_status"] == "incubating"
        assert filtered_events["data"]["events"][0]["to_status"] == "listed"
        assert filtered_events["data"]["events"][0]["actor_id"] == "reviewer"
        assert filtered_events["data"]["events"][0]["metadata"]["score"] == 91
        assert incubation["data"]["promotion_ready"] is True
        assert incubation["data"]["observed_forward_days"] == [1, 5, 10, 20]
        assert incubation["data"]["missing_forward_days"] == []
        assert len(incubation["data"]["forward_returns"]) == 4
        assert incubation["data"]["blockers_by_period"] == {}
        assert incubation["data"]["risk_flags_by_period"] == {}

    @pytest.mark.asyncio
    async def test_incubation_overview_surfaces_multi_period_blockers(self, setup):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期阻塞策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.update_strategy_status(sid, "incubating", actor_id="test", reason="seed")
        await db.save_strategy_metrics(sid, "all", {"sharpe_ratio": 0.9, "max_drawdown": 0.10})
        db._signal_stats[sid] = {
            "hit_rate": {1: 0.51, 5: 0.50, 10: 0.47, 20: 0.40},
            "forward_ic": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
            "forward_sharpe": {1: 0.10, 5: 0.55, 10: 0.21, 20: 0.05},
            "total_signals": 14,
        }

        incubation = await mcp.strategy_manager(action="incubation_overview", kwargs=json.dumps({"strategy_id": sid}))

        assert incubation["success"] is True
        assert incubation["data"]["promotion_ready"] is False
        assert incubation["data"]["deprecation_risk"] is False
        assert "20D" in incubation["data"]["blockers_by_period"]
        assert any("20D命中率" in item for item in incubation["data"]["blockers_by_period"]["20D"])
        assert incubation["data"]["risk_flags_by_period"] == {}

    @pytest.mark.asyncio
    async def test_lifecycle_scan_uses_multi_period_forward_returns(self, setup):
        mcp, db = setup

        good = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期晋级策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        good_id = good["data"]["strategy_id"]
        await db.update_strategy_status(good_id, "incubating", actor_id="test", reason="seed")
        await db.save_strategy_metrics(good_id, "all", {"sharpe_ratio": 0.85, "max_drawdown": 0.11})
        db._signal_stats[good_id] = {
            "hit_rate": {1: 0.52, 5: 0.54, 10: 0.51, 20: 0.47},
            "forward_ic": {1: 0.01, 5: 0.07, 10: 0.05, 20: 0.03},
            "forward_sharpe": {1: 0.08, 5: 0.61, 10: 0.33, 20: 0.12},
            "total_signals": 18,
        }

        bad = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "多周期淘汰策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        bad_id = bad["data"]["strategy_id"]
        await db.update_strategy_status(bad_id, "listed", actor_id="test", reason="seed")
        await db.save_strategy_metrics(bad_id, "all", {"sharpe_ratio": 0.72, "max_drawdown": 0.14})
        db._signal_stats[bad_id] = {
            "hit_rate": {1: 0.48, 5: 0.41, 10: 0.38, 20: 0.22},
            "forward_ic": {1: 0.01, 5: 0.02, 10: -0.01, 20: -0.08},
            "forward_sharpe": {1: 0.05, 5: 0.12, 10: -0.05, 20: -0.31},
            "total_signals": 16,
        }
        await db.save_strategy_incubation_metric(bad_id, '2026-03-08', {
            'account_id': 'acct_bad', 'stage': 'candidate', 'decision': 'halt', 'nav': 0.97,
            'total_orders': 3, 'total_trades': 2,
        })
        await db.save_strategy_incubation_metric(bad_id, '2026-03-07', {
            'account_id': 'acct_bad', 'stage': 'candidate', 'decision': 'halt', 'nav': 0.96,
            'total_orders': 2, 'total_trades': 1,
        })

        result = await sm_mod._lifecycle_scan(db)

        assert result["scanned"] >= 2
        assert db._strategies[good_id]["status"] == "listed"
        assert db._strategies[bad_id]["status"] == "deprecated"
        assert any(item["id"] == good_id and item["reason"] == "incubation_promoted" for item in result["transitions"])
        assert any(item["id"] == bad_id and item["reason"] == "listed_degraded" for item in result["transitions"])

    @pytest.mark.asyncio
    async def test_review_report_recheck_persists_latest_report(self, setup, monkeypatch):
        mcp, db = setup
        cr = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "复检策略", "strategy_type": "momentum", "params": {"lookback": 20},
        }))
        sid = cr["data"]["strategy_id"]
        await db.save_strategy_quality_report(sid, "submission", {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "status_after_review": "incubating",
                "review_source": "strategy_factory_submit",
            },
            "quality_gate": {"passed": True, "reasons": []},
            "validation_report": {"rating": {"grade": "B"}},
            "risk_report": {},
            "dedup_report": {},
            "backtest_metrics": {"sharpe_ratio": 1.1},
            "snapshot": {"date": "2026-03-06"},
        })

        monkeypatch.setattr(
            "akshare_mcp.tools.managers.strategy_mgr_lifecycle.run_quality_gate",
            AsyncMock(return_value={"passed": False, "reason": "Insufficient kline data for quality gate"}),
        )

        recheck = await mcp.strategy_manager(action="review_report_recheck", kwargs=json.dumps({"strategy_id": sid}))
        review = await mcp.strategy_manager(action="review_report", kwargs=json.dumps({"strategy_id": sid}))

        assert recheck["success"] is True
        assert recheck["data"]["summary"]["review_source"] == "review_report_recheck"
        assert recheck["data"]["quality_gate"]["reason_codes"] == ["insufficient_kline_data"]
        assert review["data"]["summary"]["review_source"] == "review_report_recheck"
        assert review["data"]["reports"][0]["report_type"].startswith("recheck:")
        assert review["data"]["reports"][1]["report_type"] == "submission"

    @pytest.mark.asyncio
    async def test_factory_status_and_run_once_actions(self, setup, monkeypatch):
        mcp, db = setup
        await db.save_strategy_factory_run({
            "run_id": "run_hist_1",
            "status": "success",
            "started_at": "2026-03-06T10:00:00",
            "completed_at": "2026-03-06T10:00:05",
            "elapsed_seconds": 5.0,
            "summary": {
                "candidates_spawned": 2,
                "submitted": 1,
                "event_task_count": 1,
                "snapshot_task_count": 1,
                "task_source_counts": {"event_driven": 1, "snapshot": 1},
                "scanner_task_types": {"sector_breakout": 1, "rotation_balanced": 1},
                "event_snapshot_mixed": True,
                "autonomy_task_briefs": [
                    {
                        "task_id": "event_demo_1",
                        "task_source": "event_driven",
                        "opportunity_type": "sector_breakout",
                        "generation_limit": 6,
                        "generated_count": 6,
                    }
                ],
            },
            "stages": {},
            "snapshot_summary": {},
            "error": None,
        })
        await db.save_daily_snapshot("2026-03-06", {
            "date": "2026-03-06",
            "summary": {"listed_count": 12, "degraded": True},
            "completeness": {"completion_ratio": 0.67, "missing_sources": ["north_fund"]},
            "sources": {"north_fund": {"status": "fallback"}},
            "failure_reasons": [{"source": "north_fund", "reason": "network error"}],
            "missing_fields": ["north_fund_3d_net"],
            "degraded": True,
        })

        class _DummyScheduler:
            def status(self):
                return {"running": True, "last_run": None, "last_result": None, "last_summary": None}

            async def run_once(self):
                return {"run_id": "run_live_1", "status": "success", "summary": {"candidates_spawned": 3}}

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.get_strategy_factory_scheduler",
            lambda: _DummyScheduler(),
        )

        status_resp = await mcp.strategy_manager(action="factory_status")
        run_resp = await mcp.strategy_manager(action="factory_run_once")
        runs_resp = await mcp.strategy_manager(action="factory_runs", kwargs=json.dumps({"limit": 1}))
        detail_resp = await mcp.strategy_manager(action="factory_run_detail", kwargs=json.dumps({"run_id": "run_hist_1"}))
        snapshots_resp = await mcp.strategy_manager(action="daily_snapshots", kwargs=json.dumps({"limit": 1}))
        snapshot_resp = await mcp.strategy_manager(action="daily_snapshot", kwargs=json.dumps({"snapshot_date": "2026-03-06"}))
        assert status_resp["data"]["running"] is True
        assert status_resp["data"]["last_summary"]["candidates_spawned"] == 2
        assert status_resp["data"]["last_summary"]["snapshot_task_count"] == 1
        assert status_resp["data"]["last_summary"]["task_source_counts"]["snapshot"] == 1
        assert status_resp["data"]["last_summary"]["event_snapshot_mixed"] is True
        assert status_resp["data"]["last_summary"]["autonomy_task_briefs"][0]["task_id"] == "event_demo_1"
        assert run_resp["data"]["status"] == "success"
        assert runs_resp["data"]["count"] == 1
        assert runs_resp["data"]["items"][0]["run_id"] == "run_hist_1"
        assert runs_resp["data"]["items"][0]["summary"]["event_task_count"] == 1
        assert runs_resp["data"]["items"][0]["summary"]["event_snapshot_mixed"] is True
        assert detail_resp["data"]["run_id"] == "run_hist_1"
        assert detail_resp["data"]["summary"]["snapshot_task_count"] == 1
        assert detail_resp["data"]["summary"]["autonomy_task_briefs"][0]["task_source"] == "event_driven"
        assert snapshots_resp["data"]["count"] == 1
        assert snapshots_resp["data"]["items"][0]["snapshot_date"] == "2026-03-06"
        assert snapshot_resp["data"]["degraded"] is True
        assert snapshot_resp["data"]["completeness"]["completion_ratio"] == 0.67


    @pytest.mark.asyncio
    async def test_submit_allows_provisional_incubation_for_factory_ai_strategy(self, setup, monkeypatch):
        mcp, db = setup
        sid = 'sid_provisional_submit'
        await db.save_strategy({
            'id': sid,
            'name': 'AI原型策略',
            'strategy_type': 'dsl_rule',
            'params': {
                'dsl': {
                    'version': '1.0',
                    'timeframe': 'daily',
                    'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 20}}]},
                    'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 20}}]},
                },
            },
            'status': 'draft',
            'tags': ['factory', 'auto_generated', 'external_llm'],
        })
        await db.save_strategy_metrics(sid, 'backtest', {'sharpe_ratio': 0.21, 'max_drawdown': 0.12, 'trade_count': 2})
        await db.save_strategy_quality_report(sid, 'submission', {
            'passed': False,
            'summary': {
                'validation_grade': 'D',
                'status_after_review': 'submitted',
                'review_source': 'seed_report',
            },
            'quality_gate': {'passed': False, 'reasons': []},
            'validation_report': {'rating': {'grade': 'D'}},
            'risk_report': {'var_percent': 1.8, 'cvar_percent': 2.6, 'stress_loss_percent': -18.0},
            'dedup_report': {},
            'backtest_metrics': {'sharpe_ratio': 0.21, 'max_drawdown': 0.12, 'trade_count': 2},
            'snapshot': {'date': '2026-03-08'},
        })

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": True,
                "passed_strict": False,
                "provisional_pass": True,
                "reasons": [],
                "warnings": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
                "warning_codes": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
            }),
        )

        resp = await mcp.strategy_manager(action='submit', kwargs=json.dumps({'strategy_id': sid}))

        assert resp['success'] is True
        assert resp['data']['status'] == 'incubating'
        assert resp['data']['details']['provisional_pass'] is True

    @pytest.mark.asyncio
    async def test_run_quality_gate_forwards_context_to_shared_submission_gate(self, monkeypatch):
        from akshare_mcp.tools.managers import strategy_mgr_lifecycle as lifecycle_mod

        gate_mock = AsyncMock(return_value={"passed": True, "reasons": []})
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            gate_mock,
        )

        result = await lifecycle_mod.run_quality_gate(
            MagicMock(),
            {"id": "sid_ctx_gate", "strategy_type": "momentum", "params": {}},
            validation_report={"rating": {"grade": "A"}},
            risk_report={"var_percent": 0.9},
            backtest_metrics={"sharpe_ratio": 0.42},
        )

        assert result["passed"] is True
        assert gate_mock.await_count == 1
        gate_kwargs = gate_mock.await_args.kwargs
        assert gate_kwargs["validation_report"]["rating"]["grade"] == "A"
        assert gate_kwargs["risk_report"]["var_percent"] == 0.9
        assert gate_kwargs["backtest_metrics"]["sharpe_ratio"] == 0.42

    @pytest.mark.asyncio
    async def test_submit_binds_incubation_account(self, setup, monkeypatch):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "AI提交策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]

        monkeypatch.setattr(
            "akshare_mcp.tools.managers.strategy_mgr_lifecycle.run_quality_gate",
            AsyncMock(return_value={"passed": True, "reasons": []}),
        )

        resp = await mcp.strategy_manager(action="submit", kwargs=json.dumps({"strategy_id": sid}))
        assert resp["success"] is True
        assert resp["data"]["status"] == "incubating"
        assert resp["data"]["incubation_account_id"] is not None

        accounts = await db.list_strategy_incubation_accounts(strategy_id=sid, limit=10)
        assert len(accounts) == 1
        assert accounts[0]["strategy_id"] == sid

    @pytest.mark.asyncio
    async def test_new_capability_and_query_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "扩展动作策略", "strategy_type": "momentum",
        }))
        sid = created["data"]["strategy_id"]

        await db.save_strategy_incubation_account(sid, "acct_1", metadata={"owner": "factory"})
        await db.save_strategy_incubation_metric(sid, "2026-03-06", {
            "account_id": "acct_1",
            "stage": "warmup",
            "decision": "observe",
            "total_value": 101000,
            "max_drawdown": 0.08,
        })
        await db.save_strategy_runtime_risk_event({
            "strategy_id": sid,
            "account_id": "acct_1",
            "severity": "medium",
            "event_type": "alpha_decay",
            "status": "open",
        })
        await db.save_strategy_vector_profile({
            "strategy_id": sid,
            "profile_type": "behavior",
            "vector_method": "price_volume",
            "embedding": [0.1, 0.2, 0.3],
        })
        await db.save_vector_index_registry({
            "index_name": "strategy_behavior",
            "index_version": "v1",
            "status": "active",
        })
        await db.save_strategy_generation_experiment({
            "experiment_id": "exp_test_1",
            "strategy_id": sid,
            "source": "strategy_manager",
            "generator_type": "llm_proxy",
            "status": "generated",
        })
        await db.save_strategy_task_run({
            "task_name": "strategy_ai_cycle",
            "task_scope": "strategy_manager",
            "status": "completed",
        })

        capabilities = await mcp.strategy_manager(action="capabilities")
        incubation_accounts = await mcp.strategy_manager(action="incubation_accounts", kwargs=json.dumps({"strategy_id": sid}))
        incubation_metrics = await mcp.strategy_manager(action="incubation_metrics", kwargs=json.dumps({"strategy_id": sid}))
        risk_events = await mcp.strategy_manager(action="risk_events", kwargs=json.dumps({"strategy_id": sid}))
        vector_profiles = await mcp.strategy_manager(action="vector_profiles", kwargs=json.dumps({"strategy_id": sid}))
        vector_indexes = await mcp.strategy_manager(action="vector_indexes")
        ai_experiments = await mcp.strategy_manager(action="ai_experiments", kwargs=json.dumps({"strategy_id": sid}))
        task_runs = await mcp.strategy_manager(action="task_runs")
        resolve_risk = await mcp.strategy_manager(action="resolve_risk_event", kwargs=json.dumps({"event_id": 1, "resolution": "manual"}))

        assert capabilities["success"] is True
        assert capabilities["data"]["ai_generation"] is True
        assert incubation_accounts["data"]["count"] == 1
        assert incubation_metrics["data"]["latest"]["decision"] == "observe"
        assert risk_events["data"]["count"] == 1
        assert vector_profiles["data"]["count"] == 1
        assert vector_indexes["data"]["count"] == 1
        assert ai_experiments["data"]["count"] == 1
        assert task_runs["data"]["count"] == 1
        assert resolve_risk["data"]["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_ai_generate_action(self, setup, monkeypatch):
        mcp, db = setup

        class _DummyAutonomy:
            async def run_cycle(self, *_args, **_kwargs):
                return {
                    "task_run": {"id": 1, "status": "completed"},
                    "generation": {
                        "count": 2,
                        "stats": {"rule_count": 1},
                        "llm_generation": {},
                        "candidates": [{"strategy_type": "momentum"}],
                    },
                    "review": {
                        "reviewed_count": 2,
                        "rejected_count": 0,
                        "committee_reviews": [],
                        "champion": None,
                    },
                    "experiments": {
                        "count": 1,
                        "items": [{"experiment_id": "exp_dummy_1"}],
                        "status_counts": {"generated": 1},
                    },
                    "submission": {
                        "auto_submit": False,
                        "attempted": False,
                        "submitted_count": 0,
                        "passed_count": 0,
                        "failed_count": 0,
                        "provisional_passed_count": 0,
                        "failure_reason_topn": [],
                        "items": [],
                        "result": None,
                    },
                    "task_run_id": 1,
                    "generated_count": 2,
                    "candidates": [{"strategy_type": "momentum"}],
                    "experiment_records": [{"experiment_id": "exp_dummy_1"}],
                    "submitted": None,
                }

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
            lambda: _DummyAutonomy(),
        )

        resp = await mcp.strategy_manager(action="ai_generate", kwargs=json.dumps({"limit": 2}))
        assert resp["success"] is True
        assert resp["data"]["generated_count"] == 2
        assert resp["data"]["generation"]["count"] == 2
        assert resp["data"]["experiments"]["items"][0]["experiment_id"] == "exp_dummy_1"
        assert resp["data"]["submission"]["result"] is None

    @pytest.mark.asyncio
    async def test_incubation_sync_run_creates_paper_orders_and_nav(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "模拟盘闭环策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.0, 'max_drawdown': -0.08})
        db._signal_stats[sid] = {
            'total_signals': 20,
            'hit_rate': {1: 0.53, 5: 0.58, 10: 0.55, 20: 0.54},
            'forward_ic': {1: 0.01, 5: 0.02, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.08, 5: 0.55, 10: 0.42, 20: 0.35},
        }

        async def _signals(_sid, start_date=None, end_date=None, limit=100):
            return [
                {'code': '600519', 'signal': 1, 'signal_date': str(start_date or '2026-03-08')}
            ]

        db.get_signals = _signals

        sync = await mcp.strategy_manager(action='incubation_sync_run', kwargs=json.dumps({'strategy_id': sid, 'signal_date': '2026-03-08'}))
        paper_account = await mcp.strategy_manager(action='paper_account', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        paper_orders = await mcp.strategy_manager(action='paper_orders', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        paper_nav = await mcp.strategy_manager(action='paper_nav', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        latest_metric = await db.get_latest_strategy_incubation_metric(sid)
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert sync['success'] is True
        assert sync['data']['orders_created'] == 1
        assert sync['data']['orders_filled'] == 1
        assert sync['data']['nav_snapshots'] == 1
        assert paper_account['data']['account']['strategy_id'] == sid
        assert paper_account['data']['order_summary']['total_orders'] == 1
        assert paper_account['data']['order_summary']['total_trades'] == 1
        assert len(paper_account['data']['positions']) == 1
        assert paper_orders['data']['items'][0]['status'] == 'filled'
        assert paper_nav['data']['latest']['total_value'] > 0
        assert latest_metric['total_orders'] == 1
        assert latest_metric['total_trades'] == 1
        assert len(detail['data']['nav_series']) >= 1
        assert capabilities['data']['paper_trading'] is True

    @pytest.mark.asyncio
    async def test_domain_events_vector_governance_and_runtime_cycle_actions(self, setup, monkeypatch):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "治理策略", "strategy_type": "momentum",
        }))
        sid = created["data"]["strategy_id"]
        await db.save_strategy_domain_event({
            "strategy_id": sid,
            "aggregate_type": "strategy",
            "aggregate_id": sid,
            "event_type": "incubation.metric_recorded",
            "source": "incubation",
            "payload": {"decision": "observe"},
        })

        class _DummyVectorGovernance:
            async def reconcile_registry(self, *_args, **_kwargs):
                return {"registry_updated": 1, "stale_marked": 0, "active_indexes": 1, "items": [{"index_name": "strategy_behavior"}]}

            async def rebuild_index(self, *_args, **_kwargs):
                return {"task_run_id": 99, "index_name": "strategy_behavior", "built_profiles": 2}

        class _DummyTracker:
            def status(self):
                return {"running": False, "last_result": {"risk_actions": 1}}

            async def run_once(self):
                return {"task_run_id": 11, "signals_generated": 3, "risk_actions": 1, "vector_registry_updates": 1}

        monkeypatch.setattr(
            "akshare_mcp.services.vector_governance.get_strategy_vector_governance_service",
            lambda: _DummyVectorGovernance(),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.signal_tracker.get_signal_tracker",
            lambda: _DummyTracker(),
        )

        capabilities = await mcp.strategy_manager(action="capabilities")
        domain_events = await mcp.strategy_manager(action="domain_events", kwargs=json.dumps({"strategy_id": sid}))
        reconcile = await mcp.strategy_manager(action="vector_reconcile")
        rebuild = await mcp.strategy_manager(action="vector_rebuild", kwargs=json.dumps({"statuses": ["draft"], "limit": 5}))
        runtime_status = await mcp.strategy_manager(action="runtime_cycle_status")
        runtime_run = await mcp.strategy_manager(action="runtime_cycle_run")
        detail = await mcp.strategy_manager(action="detail", kwargs=json.dumps({"strategy_id": sid}))

        assert capabilities["data"]["domain_events"] is True
        assert capabilities["data"]["vector_governance"] is True
        assert capabilities["data"]["runtime_cycle"] is True
        assert domain_events["data"]["count"] == 1
        assert reconcile["data"]["registry_updated"] == 1
        assert rebuild["data"]["built_profiles"] == 2
        assert runtime_status["data"]["last_result"]["risk_actions"] == 1
        assert runtime_run["data"]["vector_registry_updates"] == 1
        assert detail["data"]["domain_events"][0]["event_type"] == "incubation.metric_recorded"


    @pytest.mark.asyncio
    async def test_runtime_control_promotion_and_projection_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "晋级策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.2, 'max_drawdown': -0.12})
        db._signal_stats[sid] = {
            'total_signals': 18,
            'hit_rate': {1: 0.55, 5: 0.62, 10: 0.58, 20: 0.56},
            'forward_ic': {1: 0.01, 5: 0.03, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.12, 5: 0.8, 10: 0.5, 20: 0.3},
        }
        await db.save_strategy_incubation_account(sid, 'acct_promote', stage='candidate', status='active')
        await db.save_strategy_incubation_metric(sid, '2026-03-08', {
            'account_id': 'acct_promote',
            'stage': 'candidate',
            'decision': 'promote',
            'nav': 1.08,
            'sharpe_ratio': 1.2,
            'max_drawdown': 0.12,
            'hit_rate_5d': 0.62,
            'forward_sharpe_5d': 0.8,
            'total_signals': 18,
        })

        review = await mcp.strategy_manager(action='promotion_review_run', kwargs=json.dumps({'strategy_id': sid, 'auto_apply': True}))
        control = await mcp.strategy_manager(action='runtime_control_set', kwargs=json.dumps({'strategy_id': sid, 'control_mode': 'manual_stop', 'reason': 'operator_halt'}))
        projection = await mcp.strategy_manager(action='domain_projection', kwargs=json.dumps({'strategy_id': sid}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert review['success'] is True
        assert review['data']['review']['status'] == 'approved'
        assert review['data']['applied_transition']['to'] == 'listed'
        assert control['data']['control_mode'] == 'manual_stop'
        assert projection['data']['runtime_control_mode'] == 'manual_stop'
        assert projection['data']['latest_promotion_status'] == 'approved'
        assert detail['data']['runtime_control']['control_mode'] == 'manual_stop'
        assert detail['data']['latest_promotion_review']['status'] == 'approved'
        assert capabilities['data']['runtime_controls'] is True
        assert capabilities['data']['promotion_pipeline'] is True
        assert capabilities['data']['domain_projection'] is True


    @pytest.mark.asyncio
    async def test_domain_projection_rebuild_snapshot_actions(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "投影策略", "strategy_type": "momentum", "params": {"lookback": 10},
        }))
        sid = created["data"]["strategy_id"]
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_domain_event({
            'strategy_id': sid,
            'aggregate_type': 'strategy',
            'aggregate_id': sid,
            'event_type': 'custom.domain_marker',
            'source': 'test',
            'payload': {'step': 'marker'},
        })

        rebuilt = await mcp.strategy_manager(action='domain_projection_rebuild', kwargs=json.dumps({'strategy_id': sid}))
        snapshot = await mcp.strategy_manager(action='domain_projection_snapshot', kwargs=json.dumps({'strategy_id': sid}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))

        assert rebuilt['success'] is True
        assert rebuilt['data']['snapshot']['strategy_id'] == sid
        assert snapshot['data']['latest']['strategy_id'] == sid
        assert snapshot['data']['count'] >= 1
        assert detail['data']['latest_projection_snapshot']['strategy_id'] == sid



class TestAutonomyEnhancements:
    @pytest.mark.asyncio
    async def test_run_cycle_records_committee_reviews(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 20, 'threshold': 0.02}, name='ok', tags=['rule']),
            StrategySpec(strategy_type='unknown_type', params={'lookback': 1}, name='reject', tags=['rule']),
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        result = await service.run_cycle(db, snapshot={'date': '2026-03-07', 'fear_greed_index': 68}, limit=3, source='test')

        assert result['generated_count'] == 1
        assert result['generation']['count'] == result['generated_count']
        assert result['review']['reviewed_count'] == result['reviewed_count']
        assert result['review']['rejected_count'] == result['rejected_count']
        assert result['task_run']['id'] == result['task_run_id']
        assert result['experiments']['count'] == 1
        assert result['experiments']['items'] == result['experiment_records']
        assert result['artifacts']['experiments'] == result['experiment_records']
        assert result['submission']['result'] is None
        assert result['reviewed_count'] == 1
        assert result['rejected_count'] == 1
        assert any(item['decision'] in {'accept', 'reject', 'revise'} for item in result['committee_reviews'])
        experiments = await db.list_strategy_generation_experiments(limit=10)
        assert experiments[0]['evaluation']['committee_review']['decision'] in {'accept', 'revise'}
        assert result['champion']['experiment_id'] == experiments[0]['experiment_id']


    @pytest.mark.asyncio
    async def test_run_cycle_exposes_factor_research_across_result_and_event_payload(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='value_factor', params={'lookback': 30}, name='factor-aware', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        factor_research = {
            'active_factors': ['value', 'quality'],
            'summary': {'top_factor_names': ['value', 'quality']},
            'preferred_strategy_types': ['value_factor', 'quality_factor'],
            'degraded': False,
        }
        research_task = {
            'task_id': 'task_factor_ctx',
            'theme': 'factor_rotation_value',
            'strategy_preferences': ['value_factor'],
        }

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 63, 'factor_research': factor_research},
            limit=3,
            source='test',
            research_task=research_task,
        )

        assert result['factor_research'] == factor_research
        assert result['generation_stats']['factor_research'] == factor_research
        assert result['research_task']['metadata']['factor_research'] == factor_research

        task_runs = await db.list_strategy_task_runs(limit=10)
        assert task_runs[0]['result']['factor_research'] == factor_research
        assert task_runs[0]['result']['research_task']['metadata']['factor_research'] == factor_research

        domain_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.completed', limit=10)
        assert domain_events[0]['payload']['factor_research'] == factor_research
        assert domain_events[0]['payload']['research_task']['metadata']['factor_research'] == factor_research

    @pytest.mark.asyncio
    async def test_run_cycle_exposes_lifecycle_across_result_task_run_and_event(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 15}, name='lifecycle-ok', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test',
        )

        lifecycle = result['lifecycle']
        phases = {item['name']: item for item in lifecycle['phases']}

        assert lifecycle['state'] == 'completed'
        assert lifecycle['current_phase'] == 'completed'
        assert lifecycle['terminal_phase'] == 'completed'
        assert lifecycle['phase_order'] == ['prepared', 'generating', 'reviewing', 'recording', 'submitting', 'completed']
        assert phases['prepared']['status'] == 'completed'
        assert phases['generating']['status'] == 'completed'
        assert phases['reviewing']['status'] == 'completed'
        assert phases['recording']['status'] == 'completed'
        assert phases['submitting']['status'] == 'skipped'
        assert phases['submitting']['reason'] == 'auto_submit_disabled'
        assert phases['completed']['status'] == 'completed'
        assert result['task_run']['lifecycle']['state'] == 'completed'

        task_runs = await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=10)
        assert task_runs[0]['result']['lifecycle']['state'] == 'completed'
        assert task_runs[0]['result']['lifecycle']['phase_status_counts']['completed'] >= 4

        domain_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.completed', limit=10)
        assert domain_events[0]['payload']['lifecycle']['state'] == 'completed'
        assert domain_events[0]['payload']['lifecycle']['phase_status_counts']['skipped'] == 1


    @pytest.mark.asyncio
    async def test_run_cycle_auto_submit_preserves_parent_lineage(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_parent_cycle',
            'name': 'ParentCycle',
            'strategy_type': 'momentum',
            'params': {'lookback': 20, 'threshold': 0.02},
            'author_id': 'u1',
            'status': 'listed',
        })

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 18, 'threshold': 0.018}, name='child-from-parent', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        async def _fake_submit(self, candidates, snapshot, db_):
            return {
                'items': [{
                    'experiment_id': candidates[0]['experiment_id'],
                    'strategy_id': 'sid_generated_child',
                    'passed': True,
                    'duplicate': False,
                }]
            }

        monkeypatch.setattr('akshare_mcp.services.strategy_factory.StrategySubmitter.submit', _fake_submit)

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 72},
            limit=1,
            source='test',
            parent_strategy_id='sid_parent_cycle',
            auto_submit=True,
        )

        experiments = await db.list_strategy_generation_experiments(parent_strategy_id='sid_parent_cycle', limit=10)
        child_lookup = await db.list_strategy_generation_experiments(strategy_id='sid_generated_child', limit=10)
        task_run = (await db.list_strategy_task_runs(strategy_id='sid_parent_cycle', task_name='strategy_ai_cycle', limit=5))[0]

        assert result['generated_count'] == 1
        assert result['generation']['count'] == 1
        assert result['submission']['auto_submit'] is True
        assert result['submission']['submitted_count'] == 1
        assert result['submission']['passed_count'] == 1
        assert result['submission']['result'] == result['submitted']
        assert result['champion']['generated_strategy_id'] == 'sid_generated_child'
        assert result['experiments']['status_counts']['accepted'] == 1
        assert len(experiments) == 1
        assert experiments[0]['strategy_id'] == 'sid_parent_cycle'
        assert experiments[0]['parent_strategy_id'] == 'sid_parent_cycle'
        assert experiments[0]['generated_strategy_id'] == 'sid_generated_child'
        assert experiments[0]['task_run_id'] == result['task_run_id']
        assert experiments[0]['status'] == 'accepted'
        assert experiments[0]['evaluation']['committee_review']['is_champion'] is True
        assert child_lookup[0]['generated_strategy_id'] == 'sid_generated_child'
        assert task_run['result']['champion']['experiment_id'] == experiments[0]['experiment_id']

    @pytest.mark.asyncio
    async def test_run_cycle_submission_failure_keeps_experiments_and_task_run_sections(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 16, 'threshold': 0.015}, name='reject-at-submit', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        async def _fake_submit(self, candidates, snapshot, db_):
            return {
                'submitted': len(candidates),
                'gate_3_passed': 0,
                'gate_3_failed': len(candidates),
                'gate_3_failure_reason_topn': [{'reason_code': 'risk_guard', 'count': len(candidates)}],
                'items': [{
                    'experiment_id': candidates[0]['experiment_id'],
                    'passed': False,
                    'duplicate': False,
                    'reason_code': 'risk_guard',
                }],
            }

        monkeypatch.setattr('akshare_mcp.services.strategy_factory.StrategySubmitter.submit', _fake_submit)

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-09', 'fear_greed_index': 49},
            limit=1,
            source='test',
            auto_submit=True,
        )

        experiments = await db.list_strategy_generation_experiments(limit=10)
        task_run = (await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=5))[0]

        assert result['submission']['auto_submit'] is True
        assert result['submission']['attempted'] is True
        assert result['submission']['submitted_count'] == 1
        assert result['submission']['failed_count'] == 1
        assert result['submission']['failure_reason_topn'][0]['reason_code'] == 'risk_guard'
        assert result['submission']['result'] == result['submitted']
        assert result['experiments']['count'] == 1
        assert result['experiments']['items'] == result['experiment_records']
        assert result['experiments']['status_counts']['rejected'] == 1
        assert experiments[0]['status'] == 'rejected'
        assert task_run['result']['submission']['failed_count'] == 1
        assert task_run['result']['experiments']['status_counts']['rejected'] == 1

    @pytest.mark.asyncio
    async def test_run_cycle_failure_persists_failed_lifecycle_and_domain_event(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 18}, name='broken-recording', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.experiment_recorder.record_candidates = AsyncMock(side_effect=RuntimeError('recorder down'))

        with pytest.raises(RuntimeError, match='recorder down'):
            await service.run_cycle(
                db,
                snapshot={'date': '2026-03-09', 'fear_greed_index': 47},
                limit=1,
                source='test',
            )

        task_run = (await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=5))[0]
        lifecycle = task_run['result']['lifecycle']

        assert task_run['status'] == 'failed'
        assert lifecycle['state'] == 'failed'
        assert lifecycle['failed_phase'] == 'recording'
        assert lifecycle['terminal_phase'] == 'failed'
        assert lifecycle['phase_status_counts']['failed'] == 1

        failed_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.failed', limit=10)
        assert failed_events[0]['payload']['error'] == 'recorder down'
        assert failed_events[0]['payload']['lifecycle']['state'] == 'failed'
        assert failed_events[0]['payload']['lifecycle']['failed_phase'] == 'recording'


    @pytest.mark.asyncio
    async def test_bandit_optimizer_uses_experiment_feedback(self):
        from akshare_mcp.services.strategy_autonomy import BanditParameterOptimizer

        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_parent',
            'name': 'Parent',
            'strategy_type': 'momentum',
            'params': {'lookback': 20, 'threshold': 0.02},
            'author_id': 'u1',
            'status': 'listed',
        })
        await db.save_strategy_metrics('sid_parent', 'all', {'sharpe_ratio': 1.1, 'max_drawdown': -0.12})
        db._signal_stats['sid_parent'] = {'total_signals': 48, 'hit_rate': {5: 0.61}}
        await db.save_strategy_generation_experiment({
            'experiment_id': 'exp_good',
            'strategy_id': None,
            'parent_strategy_id': 'sid_parent',
            'generated_strategy_id': 'sid_child_good',
            'source': 'manual',
            'generator_type': 'rl_bandit',
            'optimizer_type': 'epsilon_greedy_feedback',
            'status': 'accepted',
            'evaluation': {'generation_reason': {'scale': 1.1}, 'committee_review': {'final_score': 0.82}},
            'result': {'passed': True},
        })
        await db.save_strategy_generation_experiment({
            'experiment_id': 'exp_bad',
            'strategy_id': None,
            'parent_strategy_id': 'sid_parent',
            'generated_strategy_id': 'sid_child_bad',
            'source': 'manual',
            'generator_type': 'rl_bandit',
            'optimizer_type': 'epsilon_greedy_feedback',
            'status': 'rejected',
            'evaluation': {'generation_reason': {'scale': 0.8}, 'committee_review': {'final_score': 0.31}},
            'result': {'passed': False},
        })

        optimizer = BanditParameterOptimizer()
        parent = await db.get_strategy('sid_parent')
        specs = await optimizer.evolve(db, parent, limit=2)

        assert len(specs) == 2
        feedback = specs[0].metadata['generation_reason']['bandit_feedback']
        assert specs[0].metadata['generation_reason']['scale'] == 1.1
        assert feedback['historical_reward_avg'] > 0
        assert '1.10' in feedback['known_scales']

    def test_dsl_rule_strategy_can_run_backtest(self):
        from akshare_mcp.services.backtest.engine import BacktestEngine
        prices = [10 - i * 0.04 for i in range(30)] + [8.8 + i * 0.08 for i in range(45)] + [12.4 - i * 0.07 for i in range(45)]
        klines = [
            {
                'date': f'2026-02-{(idx % 28) + 1:02d}',
                'open': round(price * 0.998, 4),
                'high': round(price * 1.01, 4),
                'low': round(price * 0.99, 4),
                'close': round(price, 4),
                'volume': 1000 + idx * 10,
            }
            for idx, price in enumerate(prices)
        ]
        dsl = {
            'version': '1.0',
            'timeframe': 'daily',
            'entry': {
                'all': [
                    {
                        'op': 'cross_above',
                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                    },
                    {
                        'op': 'gt',
                        'left': {'indicator': 'roc', 'field': 'close', 'window': 10},
                        'right': {'value': 0.01},
                    },
                ],
            },
            'exit': {
                'any': [
                    {
                        'op': 'cross_below',
                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                    },
                    {
                        'op': 'lt',
                        'left': {'indicator': 'roc', 'field': 'close', 'window': 5},
                        'right': {'value': -0.02},
                    },
                ],
            },
        }

        result = BacktestEngine.run_backtest('000001', klines, 'dsl_rule', {'dsl': dsl})

        assert result['success'] is True
        assert result['data']['strategy'] == 'dsl_rule'
        assert 'total_return' in result['data']

    def test_strategy_llm_config_can_load_from_mcp_env_file(self, tmp_path, monkeypatch):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        env_file = tmp_path / '.env'
        env_file.write_text(
            '\n'.join([
                'STRATEGY_LLM_ENABLED=1',
                'STRATEGY_LLM_PROVIDER=openai_compatible',
                'STRATEGY_LLM_BASE_URL=https://example.com/v1',
                'STRATEGY_LLM_API_KEY=test-key',
                'STRATEGY_LLM_MODEL=test-model',
                'STRATEGY_LLM_INITIAL_COMPACT_LEVEL=1',
                'STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK=2',
                'STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC=123',
                'STRATEGY_LLM_STRICT_MODE=1',
            ]),
            encoding='utf-8',
        )
        for key in [
            'STRATEGY_LLM_ENABLED', 'STRATEGY_LLM_PROVIDER', 'STRATEGY_LLM_BASE_URL',
            'STRATEGY_LLM_API_KEY', 'STRATEGY_LLM_MODEL', 'STRATEGY_LLM_INITIAL_COMPACT_LEVEL',
            'STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK', 'STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC',
            'STRATEGY_LLM_STRICT_MODE',
        ]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv('AKSHARE_MCP_ENV', str(env_file))

        config = StrategyLLMConfig.from_env()

        assert config.enabled is True
        assert config.base_url == 'https://example.com/v1'
        assert config.api_key == 'test-key'
        assert config.model == 'test-model'
        assert config.initial_compact_level == 1
        assert config.recent_timeout_minimal_streak == 2
        assert config.recent_timeout_cooldown_sec == 123.0
        assert config.strict is True

    @pytest.mark.asyncio
    async def test_register_experiment_uses_storage_get_db_injection(self, monkeypatch):
        import akshare_mcp.storage as storage_mod
        from akshare_mcp.services import artifact_registry as artifact_mod

        class _ArtifactDB:
            def __init__(self):
                self.saved = []

            async def save_artifact(self, artifact):
                self.saved.append(dict(artifact))
                return dict(artifact)

        db = _ArtifactDB()
        monkeypatch.setattr(storage_mod, 'get_db', lambda: db)

        artifact_mod.register_experiment({
            'experiment_id': 'exp_injected',
            'hypothesis': 'verify injected db getter',
            'method': 'unit_test',
            'parameters': {'alpha': 1},
            'status': 'running',
        })
        await asyncio.sleep(0)

        assert db.saved
        assert db.saved[0]['artifact_id'] == 'exp_injected'
        assert db.saved[0]['artifact_type'] == 'experiment'

    def test_compile_strategy_blueprint_can_tune_sparse_dsl(self):
        import pandas as pd
        from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

        prices = [10 + math.sin(idx / 4) * 0.8 + idx * 0.015 for idx in range(160)]
        volumes = [1000 + (idx % 12) * 120 for idx in range(160)]
        frame = pd.DataFrame({
            'open': prices,
            'high': [price * 1.01 for price in prices],
            'low': [price * 0.99 for price in prices],
            'close': prices,
            'volume': volumes,
        })
        blueprint = {
            'name': '稀疏 DSL',
            'dsl': {
                'version': '1.0',
                'timeframe': 'daily',
                'entry': {
                    'all': [
                        {
                            'op': 'cross_above',
                            'left': {'indicator': 'sma', 'field': 'close', 'window': 30},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 80},
                        },
                        {
                            'op': 'gt',
                            'left': {'indicator': 'volume_ratio', 'window': 20},
                            'right': {'value': 1.18},
                        },
                    ],
                },
                'exit': {
                    'any': [
                        {
                            'op': 'cross_below',
                            'left': {'indicator': 'sma', 'field': 'close', 'window': 30},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 80},
                        },
                    ],
                },
            },
        }

        compiled = compile_strategy_blueprint(blueprint, market_frame=frame, tune_for_factory=True)
        tuning = compiled['metadata']['dsl_tuning']
        activity = compiled['metadata']['dsl_activity']

        assert tuning['variants_evaluated'] > 1
        assert activity['score'] >= tuning['before']['score']
        assert activity['entry_count'] >= tuning['before']['entry_count']

    def test_compile_strategy_blueprint_supports_shorthand_llm_dsl(self):
        import pandas as pd
        from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

        prices = [10 + math.sin(i / 4) * 0.8 + i * 0.015 for i in range(160)]
        frame = pd.DataFrame({
            'open': prices,
            'high': [price * 1.01 for price in prices],
            'low': [price * 0.99 for price in prices],
            'close': prices,
            'volume': [1000 + (i % 12) * 120 for i in range(160)],
        })
        blueprint = {
            'name': '简写 DSL',
            'dsl': {
                'version': '1.0',
                'timeframe': 'daily',
                'entry': {
                    'all': [
                        {'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 20}}]},
                        {'gte': [{'volume_ratio': {'field': 'volume', 'window': 10}}, 0.98]},
                    ]
                },
                'exit': {
                    'any': [
                        {'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 10}}]},
                        {'lt': [{'rsi': {'field': 'close', 'window': 6}}, 45]},
                    ]
                },
            },
        }

        compiled = compile_strategy_blueprint(blueprint, market_frame=frame, tune_for_factory=True)
        dsl = compiled['params']['dsl']
        activity = compiled['metadata']['dsl_activity']

        entry_branch = dsl['entry'].get('all') or dsl['entry'].get('any') or []
        exit_branch = dsl['exit'].get('all') or dsl['exit'].get('any') or []

        assert entry_branch
        assert exit_branch
        assert activity['entry_count'] > 0
        assert activity['exit_count'] > 0
        assert activity['score'] > 0

    def test_backtest_filter_relaxes_thresholds_for_external_llm_prototype(self):
        flt = BacktestFilter()

        thresholds = flt._get_thresholds('dsl_rule', {'generator_type': 'external_llm', 'tags': ['external_llm']})
        fallback_thresholds = flt._get_thresholds('momentum', {'generator_type': 'local_rule_v1', 'tags': ['llm_proxy_fallback']})

        assert thresholds['sharpe_min'] == 0.10
        assert thresholds['mdd_max'] == 0.45
        assert thresholds['trades_min'] == 1
        assert fallback_thresholds['sharpe_min'] == 0.10
        assert fallback_thresholds['mdd_max'] == 0.45
        assert fallback_thresholds['trades_min'] == 1

    def test_strategy_llm_prompt_profiles_shrink_context_and_contract(self):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

        normal_system, normal_user = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-08', 'fear_greed_index': 61},
            market_summary={'rows': 120},
            research_context={
                'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61, 'hot_sectors': ['AI', '芯片']},
                'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                'symbol_insights': [
                    {'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'close': 88.1, 'return_5d': 0.02, 'return_20d': 0.12, 'volatility_20d': 0.03, 'trend_state': 'uptrend', 'price_vs_sma20': 'above', 'volume_ratio_20': 1.2},
                    {'code': '002371', 'name': '北方华创', 'industry': '芯片', 'close': 120.5, 'return_5d': 0.01, 'return_20d': 0.08, 'volatility_20d': 0.02, 'trend_state': 'uptrend', 'price_vs_sma20': 'above', 'volume_ratio_20': 1.1},
                ],
                'candidate_universe': [
                    {'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'market_cap': 100, 'pe_ratio': 20, 'pb_ratio': 3, 'return_20d': 0.12, 'trend_state': 'uptrend', 'volume_ratio_20': 1.2, 'screen_score': 0.9, 'factor_snapshot': {'momentum': 0.9, 'quality': 0.6}, 'financial_snapshot': {'revenue_growth': 0.2, 'profit_growth': 0.3, 'roe': 0.1}},
                    {'code': '002371', 'name': '北方华创', 'industry': '芯片', 'market_cap': 90, 'pe_ratio': 18, 'pb_ratio': 2.8, 'return_20d': 0.08, 'trend_state': 'uptrend', 'volume_ratio_20': 1.1, 'screen_score': 0.8, 'factor_snapshot': {'momentum': 0.7, 'quality': 0.5}, 'financial_snapshot': {'revenue_growth': 0.18, 'profit_growth': 0.24, 'roe': 0.11}},
                    {'code': '300750', 'name': '宁德时代', 'industry': '电池', 'market_cap': 80, 'pe_ratio': 16, 'pb_ratio': 2.1, 'return_20d': 0.03, 'trend_state': 'sideways', 'volume_ratio_20': 0.9, 'screen_score': 0.6, 'factor_snapshot': {'momentum': 0.4}, 'financial_snapshot': {'revenue_growth': 0.1, 'profit_growth': 0.09, 'roe': 0.08}},
                ],
                'population_state': {'listed_count': 12, 'incubating_count': 3, 'top_categories': {'momentum': 5}},
            },
            parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
            history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
            limit=2,
            research_task={'theme': 'chip_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']},
            compact_level=0,
        )
        minimal_system, minimal_user = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-08', 'fear_greed_index': 61},
            market_summary={'rows': 120},
            research_context={
                'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61, 'hot_sectors': ['AI', '芯片']},
                'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                'symbol_insights': [{'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'close': 88.1, 'return_20d': 0.12, 'trend_state': 'uptrend'}],
                'candidate_universe': [{'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'return_20d': 0.12, 'trend_state': 'uptrend', 'volume_ratio_20': 1.2, 'screen_score': 0.9}],
            },
            parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
            history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
            limit=1,
            research_task={'theme': 'chip_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']},
            compact_level=2,
        )

        normal_payload = json.loads(normal_user)
        minimal_payload = json.loads(minimal_user)

        assert len(minimal_system) + len(minimal_user) < len(normal_system) + len(normal_user)
        assert len(minimal_system) < len(normal_system)
        assert minimal_payload['output_contract']['target_symbol_rule'] == 'prefer_intersection_with_research_task'
        assert minimal_payload['output_contract']['prefer_single_high_confidence_candidate'] is True
        assert minimal_payload['output_contract']['required'] == ['candidates']
        assert minimal_payload['output_contract']['analysis_fields'] == []
        assert len(minimal_payload['output_contract']['candidate_fields']) < len(normal_payload['output_contract']['candidate_fields'])
        assert set(minimal_payload['research_task'].keys()) <= {'task_id', 'opportunity_type', 'target_symbols'}
        assert 'output_example' in minimal_payload
        assert minimal_payload['output_example']['candidates'][0]['dsl']['metadata']['target_symbols']

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_accepts_candidate_only_minimal_response(self):
        import pandas as pd
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'candidates': [
                                    {
                                        'name': 'candidate_ok',
                                        'target_symbols': ['688981'],
                                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                                        'dsl': {
                                            'version': '1.0',
                                            'timeframe': 'daily',
                                            'entry': {'any': [{'op': 'cross_above', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                            'exit': {'any': [{'op': 'cross_below', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        },
                                        'tags': ['external_llm'],
                                    },
                                    {
                                        'name': 'candidate_bad',
                                        'target_symbols': ['688981'],
                                        'dsl': 'not_a_dict',
                                    },
                                ],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                assert user_payload.get('prompt_profile') == 'minimal'
                assert user_payload.get('output_contract', {}).get('required') == ['candidates']
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
                initial_compact_level=2,
            ))
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}, 'candidate_universe': [{'code': '688981'}]},
                research_task={'task_id': 't1', 'target_symbols': ['688981']},
                limit=2,
            )

        assert result['analysis'] == {}
        assert len(result['candidates']) == 1
        assert result['candidates'][0]['target_symbols'] == ['688981']
        assert result['candidates'][0]['dsl']['metadata']['target_symbols'] == ['688981']
        assert result['request_metrics']['raw_candidate_count'] == 2
        assert result['request_metrics']['returned_candidate_count'] == 1
        assert result['request_metrics']['analysis_present'] is False

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_retries_after_timeout(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        calls = {'count': 0, 'prompt_chars': [], 'timeout_reads': [], 'max_tokens': []}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {
                                    'market_regime': 'trend_up',
                                    'style_bias': 'momentum',
                                    'hypothesis': '顺势回踩',
                                    'evidence': ['close_above_sma20'],
                                    'risk_focus': ['watch_drawdown'],
                                    'selection_notes': ['prefer_medium_frequency'],
                                },
                                'candidates': [{
                                    'name': 'retry_candidate',
                                    'dsl': {
                                        'version': '1.0',
                                        'timeframe': 'daily',
                                        'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                    },
                                }],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                calls['count'] += 1
                calls['prompt_chars'].append(len(kwargs['json']['messages'][1]['content']))
                calls['timeout_reads'].append(float(kwargs['timeout'].read))
                calls['max_tokens'].append(int(kwargs['json'].get('max_tokens') or 0))
                if calls['count'] == 1:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
            ))
            result = await provider.generate_candidates(
                snapshot={
                    'date': '2026-03-08',
                    'fear_greed_index': 61,
                    'hot_sectors': ['AI', '芯片', '机器人', '算力'],
                    'cold_sectors': ['银行', '煤炭', '地产'],
                    'category_counts': {'momentum': 5, 'value': 3, 'quality': 2},
                    'completeness': {'completion_ratio': 0.86, 'missing_sources': ['north_fund', 'margin']},
                    'failure_reasons': [{'source': 'north_fund', 'reason': 'timeout'}],
                },
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={
                    'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61},
                    'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                    'symbol_insights': [{'code': '000300', 'return_20d': 0.05, 'trend_state': 'uptrend'}],
                    'population_state': {'listed_count': 12, 'incubating_count': 3, 'top_categories': {'momentum': 5}},
                },
                parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
                history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
                limit=3,
            )

        assert calls['count'] == 2
        assert calls['prompt_chars'][1] <= calls['prompt_chars'][0]
        assert calls['timeout_reads'][0] <= calls['timeout_reads'][1]
        assert calls['max_tokens'][1] <= calls['max_tokens'][0]
        assert result['analysis']['market_regime'] == 'trend_up'
        assert result['research_context']['market_regime']['fg_level'] is not None
        assert result['candidates'][0]['name'] == 'retry_candidate'
        assert result['request_metrics']['attempt_count'] == 2
        assert result['request_metrics']['analysis_present'] is True
        assert result['request_metrics']['attempts'][0]['error_type'] == 'ReadTimeout'
        assert result['request_metrics']['attempts'][1]['prompt_profile'] == 'minimal'

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_starts_minimal_after_recent_timeout_failure(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider, StrategyLLMRequestError

        calls = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {'market_regime': 'trend_up'},
                                'candidates': [{
                                    'name': 'minimal_candidate',
                                    'dsl': {
                                        'version': '1.0',
                                        'timeframe': 'daily',
                                        'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                    },
                                }],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                calls.append({
                    'prompt_profile': user_payload.get('prompt_profile'),
                    'max_tokens': int(kwargs['json'].get('max_tokens') or 0),
                    'timeout_read': float(kwargs['timeout'].read),
                })
                if len(calls) == 1:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=0,
                retry_backoff_sec=0,
                recent_timeout_minimal_streak=1,
                recent_timeout_cooldown_sec=600,
            ))
            with pytest.raises(StrategyLLMRequestError):
                await provider.generate_candidates(
                    snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                    market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                    research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                    limit=2,
                )
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                limit=2,
            )

        assert calls[0]['prompt_profile'] == 'normal'
        assert calls[1]['prompt_profile'] == 'minimal'
        assert calls[1]['max_tokens'] <= calls[0]['max_tokens']
        assert calls[1]['timeout_read'] >= calls[0]['timeout_read']
        assert result['request_metrics']['prompt_profile'] == 'minimal'
        assert result['request_metrics']['initial_prompt_profile'] == 'minimal'
        assert result['request_metrics']['degrade_reason'] == 'recent_timeout'

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_recent_timeout_uses_single_minimal_attempt(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider, StrategyLLMRequestError

        calls = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {'market_regime': 'trend_up'},
                                'candidates': [{'name': 'minimal_candidate', 'dsl': {'version': '1.0', 'timeframe': 'daily', 'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]}, 'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]}}}],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                calls.append(user_payload.get('prompt_profile'))
                if len(calls) <= 2:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
                recent_timeout_minimal_streak=1,
                recent_timeout_cooldown_sec=600,
            ))
            with pytest.raises(StrategyLLMRequestError):
                await provider.generate_candidates(
                    snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                    market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                    research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                    limit=2,
                )
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                limit=2,
            )

        assert calls == ['normal', 'minimal', 'minimal']
        assert result['request_metrics']['attempt_count'] == 1
        assert len(result['request_metrics']['attempts']) == 1
        assert result['request_metrics']['initial_prompt_profile'] == 'minimal'

    def test_strategy_llm_provider_build_prompt_includes_event_driven_research_task(self):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

        _system_prompt, user_prompt = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-09', 'fear_greed_index': 57, 'fg_level': 'neutral'},
            market_summary={'rows': 10, 'close': {'latest': 101.2}},
            research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 57}},
            parent_strategies=[],
            history_summary=[],
            limit=2,
            research_task={
                'task_id': 'task_evt_oil',
                'task_source': 'event_driven',
                'event_id': 'evt_oil_1',
                'event_type': 'geopolitics',
                'theme': 'event_theme_upstream_oil_gas',
                'theme_code': 'upstream_oil_gas',
                'direction': 'positive',
                'horizon': 'swing_5_20d',
                'opportunity_type': 'sector_breakout',
                'target_symbols': ['601857', '600938'],
                'evidence_bundle': {
                    'event_summary': '中东战事升级抬升原油供给风险。',
                    'theme_name': '上游油气',
                    'direction': 'positive',
                    'signal_count': 2,
                    'score_summary': {'avg_final_score': 0.87, 'top_symbols': ['601857', '600938']},
                    'supporting_reasons': ['油价中枢抬升', '供给扰动强化'],
                },
            },
            compact_level=0,
        )

        user_payload = json.loads(user_prompt)
        compact_task = user_payload['research_task']

        assert compact_task['event_id'] == 'evt_oil_1'
        assert compact_task['theme_code'] == 'upstream_oil_gas'
        assert compact_task['direction'] == 'positive'
        assert compact_task['task_source'] == 'event_driven'
        assert compact_task['evidence_summary']['event_summary'].startswith('中东战事升级')
        assert compact_task['evidence_summary']['top_symbols'] == ['601857', '600938']

    @pytest.mark.asyncio
    async def test_run_cycle_uses_external_llm_dsl_blueprint(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService

        captured = {}

        class _FakeProvider:
            class config:
                strict = True
                provider = 'openai_compatible'
                model = 'test-model'

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                captured['research_context'] = _kwargs.get('research_context')
                return {
                    'provider': 'openai_compatible',
                    'model': 'test-model',
                    'prompt': {'system': 's', 'user': 'u'},
                    'analysis': {
                        'market_regime': 'neutral_to_up',
                        'style_bias': 'trend',
                        'hypothesis': '顺势回踩后放量确认',
                        'evidence': ['trend_up_count>0'],
                        'risk_focus': ['avoid_chasing'],
                        'selection_notes': ['prefer_pullback_entry'],
                        'universe_view': 'candidate_universe 中消费与新能源趋势较强',
                        'selection_plan': ['优先 trend_state=uptrend', '再筛 volume_ratio_20>1.0'],
                        'trade_plan': ['回踩确认买入', '跌破中期均线退出'],
                    },
                    'research_context': _kwargs.get('research_context') or {},
                    'content': '{"analysis": {...}, "candidates": [...] }',
                    'candidates': [{
                        'name': '外部 AI 趋势策略',
                        'description': '外部模型生成的 DSL 规则。',
                        'rationale': '使用短中期均线趋势与量能确认。',
                        'tags': ['swing'],
                        'target_symbols': ['600519', '000858', '300750'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['600519', '000858', '300750']},
                        'selection_logic': ['消费龙头与新能源龙头共振', '保留量能确认的强趋势股'],
                        'dsl': {
                            'version': '1.0',
                            'timeframe': 'daily',
                            'entry': {
                                'all': [
                                    {
                                        'op': 'cross_above',
                                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                                    },
                                    {
                                        'op': 'gt',
                                        'left': {'indicator': 'volume_ratio', 'window': 10},
                                        'right': {'value': 1.05},
                                    },
                                ],
                            },
                            'exit': {
                                'any': [
                                    {
                                        'op': 'cross_below',
                                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                                    },
                                ],
                            },
                            'risk_rules': {'stop_loss': 0.06, 'take_profit': 0.15},
                            'metadata': {'target_symbols': ['600519', '000858', '300750']},
                        },
                    }],
                }

        service = StrategyAutonomyService()
        db = _StrategyDB()
        service.rule_generator.generate = lambda *_args, **_kwargs: []
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.llm_generator.external_provider = _FakeProvider()
        monkeypatch.setattr('akshare_mcp.services.strategy_generators.PIPELINE_MODE', 'monolithic')

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test_external',
        )
        experiments = await db.list_strategy_generation_experiments(limit=10)

        assert result['generated_count'] == 1
        assert captured['research_context']['symbol_insights']
        assert captured['research_context']['candidate_universe']
        assert result['llm_generation']['research_context_summary']['symbol_count'] >= 1
        assert result['llm_generation']['research_context_summary']['candidate_universe_count'] >= 1
        assert result['llm_generation']['external_provider']['analysis']['style_bias'] == 'trend'
        assert result['candidates'][0]['strategy_type'] == 'dsl_rule'
        assert result['candidates'][0]['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['generator_type'] == 'external_llm'
        assert experiments[0]['strategy_spec']['params']['dsl']['entry']
        assert experiments[0]['strategy_spec']['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['evaluation']['llm_analysis']['style_bias'] == 'trend'
        assert experiments[0]['evaluation']['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['evaluation']['llm_response']['provider'] == 'openai_compatible'
        assert result['llm_generation']['external_provider']['status'] in {'succeeded', 'fallback_only'}

    @pytest.mark.asyncio
    async def test_run_cycle_records_external_llm_failure_metrics(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMRequestError

        class _FailProvider:
            class config:
                strict = False
                provider = 'openai_compatible'
                model = 'test-model'

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError(
                    'external llm timeout',
                    metrics={
                        'status': 'failed',
                        'attempt_count': 2,
                        'elapsed_seconds': 18.5,
                        'last_error_type': 'ReadTimeout',
                        'last_error': 'timeout',
                        'attempts': [
                            {'attempt': 1, 'status': 'failed', 'error_type': 'ReadTimeout'},
                            {'attempt': 2, 'status': 'failed', 'error_type': 'ReadTimeout'},
                        ],
                    },
                )

        service = StrategyAutonomyService()
        db = _StrategyDB()
        service.rule_generator.generate = lambda *_args, **_kwargs: []
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.llm_generator.external_provider = _FailProvider()
        monkeypatch.setattr('akshare_mcp.services.strategy_generators.PIPELINE_MODE', 'monolithic')

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test_external_failure',
        )

        assert result['generated_count'] >= 1
        assert result['llm_generation']['external_provider']['status'] == 'failed'
        assert result['llm_generation']['external_provider']['last_error_type'] == 'ReadTimeout'
        assert result['llm_generation']['external_provider']['requests'][0]['request_metrics']['attempt_count'] == 2

    @pytest.mark.asyncio
    async def test_task_runs_can_filter_by_strategy_id(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)
        await db.save_strategy_task_run({'strategy_id': 'sid_keep', 'task_name': 'strategy_ai_cycle', 'task_scope': 'manual', 'status': 'completed'})
        await db.save_strategy_task_run({'strategy_id': 'sid_other', 'task_name': 'strategy_ai_cycle', 'task_scope': 'manual', 'status': 'completed'})

        result = await mcp.strategy_manager(action='task_runs', kwargs=json.dumps({'strategy_id': 'sid_keep'}))

        assert result['success'] is True
        assert result['data']['count'] == 1
        assert result['data']['items'][0]['strategy_id'] == 'sid_keep'


class TestRuntimeRiskEnhancements:
    @pytest.mark.asyncio
    async def test_runtime_risk_scan_executes_risk_actions(self, monkeypatch):
        from akshare_mcp.services.runtime_risk import StrategyRuntimeRiskService

        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_risk',
            'name': '风险策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        db._paper_accounts['acct_risk'] = {'id': 'acct_risk', 'strategy_id': 'sid_risk', 'status': 'active', 'initial_capital': 100000, 'total_value': 70000}
        await db.save_strategy_incubation_account('sid_risk', 'acct_risk', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_risk', '2026-03-07', {
            'account_id': 'acct_risk',
            'max_drawdown': 0.35,
            'daily_return': -0.02,
            'exposure_rate': 0.98,
            'alpha_decay': 0.1,
            'drift_score': 0.1,
            'decision': 'halt',
        })

        class _DummyAction:
            def to_dict(self):
                return {'action_type': 'force_liquidate', 'code': '600519', 'shares': 100, 'price': 10.0, 'reason': 'test'}

        class _DummyExecutor:
            async def enforce(self, account_id):
                assert account_id == 'acct_risk'
                return [_DummyAction()]

        monkeypatch.setattr('akshare_mcp.services.risk_executor.get_risk_executor', lambda: _DummyExecutor())

        service = StrategyRuntimeRiskService()
        result = await service.scan(db, [{'id': 'sid_risk', 'status': 'listed'}], enforce_actions=True)

        assert result['event_count'] >= 1
        assert result['action_count'] == 1
        assert result['snapshot_count'] >= 1
        latest_snapshot = await db.get_latest_strategy_runtime_risk_snapshot('sid_risk')
        assert latest_snapshot is not None
        assert latest_snapshot['posture_level'] == 'critical'
        assert latest_snapshot['control_mode'] == 'halted'
        control = await db.get_strategy_runtime_control('sid_risk')
        assert control['control_mode'] == 'halted'
        domain_events = await db.list_strategy_domain_events(strategy_id='sid_risk', event_type='runtime_risk.actions_executed', limit=10)
        assert len(domain_events) == 1

    @pytest.mark.asyncio
    async def test_runtime_risk_recovery_restores_strategy_and_snapshot(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_recover',
            'name': '恢复策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        await db.update_strategy_status('sid_recover', 'suspended', actor_id='runtime_risk', reason='runtime_circuit_breaker')
        db._paper_accounts['acct_recover'] = {
            'id': 'acct_recover',
            'strategy_id': 'sid_recover',
            'status': 'frozen',
            'promotion_candidate': False,
            'initial_capital': 100000,
            'total_value': 98000,
        }
        await db.save_strategy_incubation_account('sid_recover', 'acct_recover', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_recover', '2026-03-08', {
            'account_id': 'acct_recover',
            'max_drawdown': 0.08,
            'daily_return': 0.01,
            'exposure_rate': 0.42,
            'alpha_decay': 0.06,
            'drift_score': 0.08,
            'decision': 'promote',
        })
        await db.save_strategy_runtime_risk_event({
            'strategy_id': 'sid_recover',
            'account_id': 'acct_recover',
            'severity': 'critical',
            'event_type': 'liquidity_stress',
            'action': 'halt_and_liquidate',
            'title': '损失与暴露复合熔断',
            'reason': 'test',
            'status': 'open',
            'payload': {},
        })
        await db.save_strategy_runtime_control({
            'strategy_id': 'sid_recover',
            'control_mode': 'halted',
            'status': 'active',
            'reason': 'test',
            'source': 'runtime_risk',
        })

        recovery = await mcp.strategy_manager(action='risk_recovery', kwargs=json.dumps({'strategy_id': 'sid_recover', 'source': 'pytest'}))
        snapshots = await mcp.strategy_manager(action='risk_snapshots', kwargs=json.dumps({'strategy_id': 'sid_recover', 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': 'sid_recover'}))
        strategy = await db.get_strategy('sid_recover')
        control = await db.get_strategy_runtime_control('sid_recover')
        latest_snapshot = await db.get_latest_strategy_runtime_risk_snapshot('sid_recover')
        open_events = await db.list_strategy_runtime_risk_events(strategy_id='sid_recover', status='open', limit=10)

        assert recovery['success'] is True
        assert recovery['data']['eligible'] is True
        assert recovery['data']['recovered'] is True
        assert recovery['data']['recovery']['to_status'] == 'listed'
        assert strategy['status'] == 'listed'
        assert control['control_mode'] == 'active'
        assert db._paper_accounts['acct_recover']['status'] == 'active'
        assert db._paper_accounts['acct_recover']['promotion_candidate'] is True
        assert open_events == []
        assert latest_snapshot is not None
        assert latest_snapshot['posture_level'] == 'safe'
        assert latest_snapshot['control_mode'] == 'active'
        assert snapshots['data']['count'] >= 1
        assert snapshots['data']['latest']['posture_level'] == 'safe'
        assert detail['data']['latest_runtime_risk_snapshot']['posture_level'] == 'safe'


class TestRuntimeAlertEnhancements:
    @pytest.mark.asyncio
    async def test_runtime_risk_scan_generates_runtime_alerts_and_ack(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_alert',
            'name': '告警策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 10},
            'factor_weights': {},
        })
        await db.save_strategy_incubation_account('sid_alert', 'acct_alert', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_alert', '2026-03-08', {
            'account_id': 'acct_alert',
            'max_drawdown': 0.31,
            'daily_return': -0.09,
            'exposure_rate': 0.98,
            'alpha_decay': 0.12,
            'drift_score': 0.18,
        })

        scan = await mcp.strategy_manager(action='risk_scan_run', kwargs=json.dumps({'strategy_id': 'sid_alert', 'enforce_actions': False}))
        alerts = await mcp.strategy_manager(action='runtime_alerts', kwargs=json.dumps({'strategy_id': 'sid_alert', 'limit': 20}))

        assert scan['success'] is True
        assert scan['data']['alert_count'] >= 1
        assert alerts['data']['count'] >= 1
        first_alert = alerts['data']['items'][0]
        ack = await mcp.strategy_manager(action='runtime_alert_ack', kwargs=json.dumps({'alert_id': first_alert['alert_id'], 'acknowledged_by': 'pytest'}))
        latest = await db.get_latest_strategy_runtime_alert('sid_alert')

        assert ack['success'] is True
        assert ack['data']['status'] == 'acknowledged'
        assert latest is not None
        assert latest['status'] in {'open', 'acknowledged'}

    @pytest.mark.asyncio
    async def test_runtime_risk_recovery_resolves_runtime_alerts(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_alert_recover',
            'name': '恢复告警策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        await db.update_strategy_status('sid_alert_recover', 'suspended', actor_id='runtime_risk', reason='runtime_circuit_breaker')
        await db.save_strategy_incubation_account('sid_alert_recover', 'acct_alert_recover', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_alert_recover', '2026-03-08', {
            'account_id': 'acct_alert_recover',
            'max_drawdown': 0.08,
            'daily_return': 0.02,
            'exposure_rate': 0.35,
            'alpha_decay': 0.05,
            'drift_score': 0.05,
            'decision': 'promote',
        })
        await db.save_strategy_runtime_control({
            'strategy_id': 'sid_alert_recover',
            'account_id': 'acct_alert_recover',
            'control_mode': 'halted',
            'status': 'engaged',
            'source': 'runtime_risk',
            'reason': 'test',
        })
        await db.save_strategy_runtime_alert({
            'strategy_id': 'sid_alert_recover',
            'account_id': 'acct_alert_recover',
            'alert_key': 'control:sid_alert_recover:halted',
            'category': 'halted_control',
            'severity': 'critical',
            'status': 'open',
            'title': '运行控制已熔断',
            'message': 'test',
            'escalation_level': 3,
        })

        recovery = await mcp.strategy_manager(action='risk_recovery', kwargs=json.dumps({'strategy_id': 'sid_alert_recover', 'source': 'pytest'}))
        resolved = await mcp.strategy_manager(action='runtime_alerts', kwargs=json.dumps({'strategy_id': 'sid_alert_recover', 'status': 'resolved', 'limit': 20}))

        assert recovery['success'] is True
        assert recovery['data']['recovered'] is True
        assert resolved['data']['count'] >= 1
        assert any(item.get('category') == 'halted_control' for item in resolved['data']['items'])

class TestVectorGovernanceEnhancements:
    @pytest.mark.asyncio
    async def test_vector_rebuild_creates_task_run_and_registry(self, monkeypatch):
        from akshare_mcp.services.vector_governance import StrategyVectorGovernanceService

        db = _StrategyDB()
        await db.save_strategy({'id': 'sid_vec_1', 'name': '向量1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_vec_2', 'name': '向量2', 'strategy_type': 'momentum', 'status': 'incubating', 'params': {'lookback': 10}, 'factor_weights': {}})
        await db.save_vector_index_registry({'index_name': 'strategy_behavior', 'index_version': 'old_v1', 'status': 'active', 'metadata': {}})

        class _DummyVectorPlatform:
            class engine:
                backend = 'index'

            async def build_profiles_for_strategies(self, db, strategies, profile_type='behavior', vector_method='price_volume', index_name='strategy_behavior', index_version='v1'):
                built = []
                for idx, strategy in enumerate(strategies, 1):
                    built.append(await db.save_strategy_vector_profile({
                        'strategy_id': strategy['id'],
                        'profile_type': profile_type,
                        'vector_method': vector_method,
                        'metric': 'cosine',
                        'vector_dim': 3,
                        'embedding': [0.1 * idx, 0.2 * idx, 0.3 * idx],
                        'signature': f'sig_{idx}',
                        'backend': 'index',
                        'index_version': index_version,
                        'metadata': {'index_name': index_name, 'index_version': index_version},
                    }))
                return {'count': len(strategies), 'items': built}

            async def build_persisted_ann_index(self, db, index_name='strategy_behavior', index_version='v1', profile_type='behavior', task_run_id=None, source='vector_governance', limit_profiles=5000):
                snapshot = await db.save_strategy_vector_index_snapshot({
                    'index_name': index_name,
                    'index_version': index_version,
                    'status': 'active',
                    'profile_type': profile_type,
                    'vector_method': 'price_volume',
                    'metric': 'cosine',
                    'backend': 'index',
                    'profile_count': 2,
                    'bucket_count': 1,
                    'vector_dim': 3,
                    'centroids': [{'bucket_id': 'bucket_01', 'size': 2, 'neighbors': []}],
                    'metadata': {'task_run_id': task_run_id, 'source': source},
                    'task_run_id': task_run_id,
                    'source': source,
                })
                await db.replace_strategy_vector_index_items(index_name, index_version, [
                    {'profile_id': 1, 'strategy_id': 'sid_vec_1', 'profile_type': profile_type, 'vector_method': 'price_volume', 'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_01', 'coarse_score': 0.99, 'embedding': [0.1, 0.2, 0.3], 'metadata': {'signature': 'sig_1'}},
                    {'profile_id': 2, 'strategy_id': 'sid_vec_2', 'profile_type': profile_type, 'vector_method': 'price_volume', 'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_01', 'coarse_score': 0.98, 'embedding': [0.2, 0.4, 0.6], 'metadata': {'signature': 'sig_2'}},
                ])
                return {'snapshot': snapshot, 'items_count': 2, 'bucket_count': 1, 'profile_count': 2}

        monkeypatch.setattr('akshare_mcp.services.vector_platform.get_strategy_vector_platform', lambda: _DummyVectorPlatform())

        service = StrategyVectorGovernanceService()
        result = await service.rebuild_index(db, index_name='strategy_behavior', index_version='v2', statuses=['listed', 'incubating'], limit=10)

        assert result['task_run_id'] is not None
        assert result['built_profiles'] == 2
        assert result['persisted_snapshot_id'] is not None
        assert result['persisted_items'] == 2
        indexes = await db.list_vector_index_registry(index_name='strategy_behavior', limit=10)
        assert any(item.get('index_version') == 'v2' for item in indexes)
        assert any(item.get('index_version') == 'old_v1' and item.get('status') == 'stale' for item in indexes)
        snapshots = await db.list_strategy_vector_index_snapshots(index_name='strategy_behavior', limit=10)
        assert any(item.get('index_version') == 'v2' and item.get('status') == 'active' for item in snapshots)
        items = await db.list_strategy_vector_index_items(index_name='strategy_behavior', index_version='v2', limit=10)
        assert len(items) == 2

class TestVectorAnnSearchActions:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_vector_ann_search_and_snapshot_actions(self, setup):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        mcp, db = setup
        await db.save_strategy({'id': 'sid_ann_1', 'name': 'ANN1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_ann_2', 'name': 'ANN2', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 22}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_ann_3', 'name': 'ANN3', 'strategy_type': 'mean_reversion', 'status': 'listed', 'params': {'lookback': 5}, 'factor_weights': {}})
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'ann_sig_1', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.98, 0.05, 0.0], 'signature': 'ann_sig_2', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_3', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [-1.0, 0.0, 0.0], 'signature': 'ann_sig_3', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })

        platform = StrategyVectorPlatform()
        persisted = await platform.build_persisted_ann_index(db, index_name='strategy_behavior', index_version='ann_v1', profile_type='behavior', task_run_id=11, source='test_case')

        snapshots = await mcp.strategy_manager(action='vector_index_snapshots', kwargs=json.dumps({'index_name': 'strategy_behavior', 'limit': 10}))
        search = await mcp.strategy_manager(action='vector_ann_search', kwargs=json.dumps({'strategy_id': 'sid_ann_1', 'index_version': 'ann_v1', 'limit': 5}))

        assert persisted['items_count'] == 3
        assert snapshots['success'] is True
        assert snapshots['data']['count'] >= 1
        assert snapshots['data']['latest']['index_version'] == 'ann_v1'
        assert search['success'] is True
        assert search['data']['count'] >= 1
        assert search['data']['backend_requested'] == 'pgvector'
        assert search['data']['backend_used'] == 'index'
        assert search['data']['fallback_used'] is True
        assert search['data']['fallback_reason'] == 'preferred_backend_unavailable'
        assert search['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert search['data']['fallback_allowed'] is True
        assert search['data']['index_name'] == 'strategy_behavior'
        assert search['data']['index_version'] == 'ann_v1'
        assert search['data']['active_index']['index_version'] == 'ann_v1'
        assert search['data']['active_index']['backend'] == 'index'
        assert search['data']['items'][0]['strategy_id'] == 'sid_ann_2'
        assert search['data']['items'][0]['retrieval_mode'] == 'persisted_ann'
        assert search['data']['items'][0]['candidate_count'] >= 1

    @pytest.mark.asyncio
    async def test_vector_ann_search_uses_pgvector_backend_when_available(self, setup):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        mcp, db = setup
        db._pgvector_enabled = True
        await db.save_strategy({'id': 'sid_pg_1', 'name': 'PG1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_pg_2', 'name': 'PG2', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 21}, 'factor_weights': {}})
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_pg_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'pg_sig_1', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'pg_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'pg_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_pg_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.99, 0.01, 0.0], 'signature': 'pg_sig_2', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'pg_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'pg_v1'},
        })

        platform = StrategyVectorPlatform()
        await platform.build_persisted_ann_index(db, index_name='strategy_behavior', index_version='pg_v1', profile_type='behavior', task_run_id=21, source='test_case')

        search = await mcp.strategy_manager(action='vector_ann_search', kwargs=json.dumps({'strategy_id': 'sid_pg_1', 'index_version': 'pg_v1', 'limit': 5}))

        assert search['success'] is True
        assert search['data']['count'] >= 1
        assert search['data']['backend_requested'] == 'pgvector'
        assert search['data']['backend_used'] == 'pgvector'
        assert search['data']['fallback_used'] is False
        assert search['data']['fallback_reason'] is None
        assert search['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert search['data']['fallback_allowed'] is True
        assert search['data']['index_name'] == 'strategy_behavior'
        assert search['data']['index_version'] == 'pg_v1'
        assert search['data']['active_index']['index_version'] == 'pg_v1'
        assert search['data']['active_index']['backend'] == 'pgvector'
        assert search['data']['items'][0]['strategy_id'] == 'sid_pg_2'
        assert search['data']['items'][0]['retrieval_mode'] == 'pgvector_ann'
        assert search['data']['items'][0]['backend'] == 'pgvector'

    @pytest.mark.asyncio
    async def test_vector_health_action_reports_counts_and_hnsw_indexes(self, setup):
        mcp, db = setup
        db._pgvector_enabled = True
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_vh_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'vh_sig_1', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'created_at': '2026-03-08T00:00:00+00:00',
            'metadata': {'index_name': 'strategy_behavior', 'index_version': 'vh_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_vh_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.9, 0.1, 0.0], 'signature': 'vh_sig_2', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'created_at': '2026-03-08T00:01:00+00:00',
            'metadata': {'index_name': 'strategy_behavior', 'index_version': 'vh_v1'},
        })
        await db.save_vector_index_registry({
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'status': 'active', 'backend': 'pgvector',
            'sample_count': 2, 'created_at': '2026-03-08T00:02:00+00:00',
        })
        await db.save_strategy_vector_index_snapshot({
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'status': 'active', 'backend': 'pgvector',
            'profile_count': 2, 'bucket_count': 1, 'vector_dim': 3,
            'built_at': '2026-03-08T00:03:00+00:00', 'activated_at': '2026-03-08T00:03:00+00:00',
        })
        await db.replace_strategy_vector_index_items('strategy_behavior', 'vh_v1', [
            {
                'profile_id': 1, 'strategy_id': 'sid_vh_1', 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 1.0,
                'embedding': [1.0, 0.0, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': '2026-03-08T00:04:00+00:00',
            },
            {
                'profile_id': 2, 'strategy_id': 'sid_vh_2', 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 0.9,
                'embedding': [0.9, 0.1, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': '2026-03-08T00:04:30+00:00',
            },
        ])
        await db.ensure_strategy_vector_profile_pgvector_index('strategy_behavior', 'vh_v1', 3, profile_type='behavior')
        await db.ensure_strategy_vector_index_item_pgvector_index('strategy_behavior', 'vh_v1', 3)

        health = await mcp.strategy_manager(action='vector_health', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'limit_versions': 5,
            'include_hnsw_indexes': True,
        }))

        assert health['success'] is True
        assert health['data']['backend'] == 'pgvector'
        assert health['data']['backend_requested'] == 'pgvector'
        assert health['data']['backend_used'] == 'pgvector'
        assert health['data']['fallback_used'] is False
        assert health['data']['fallback_reason'] is None
        assert health['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert health['data']['fallback_allowed'] is True
        assert health['data']['active_index']['index_name'] == 'strategy_behavior'
        assert health['data']['active_index']['index_version'] == 'vh_v1'
        assert health['data']['active_index']['backend'] == 'pgvector'
        assert health['data']['active_index']['source'] == 'snapshot'
        assert health['data']['counts']['profiles'] == 2
        assert health['data']['counts']['profile_store'] == 2
        assert health['data']['counts']['index_items'] == 2
        assert health['data']['counts']['index_item_store'] == 2
        assert health['data']['hnsw_index_count'] == 2
        assert health['data']['versions'][0]['index_version'] == 'vh_v1'
        assert health['data']['versions'][0]['profile_store_rows'] == 2
        assert health['data']['versions'][0]['index_item_store_rows'] == 2

    @pytest.mark.asyncio
    async def test_build_profiles_for_strategies_builds_profiles_concurrently(self, monkeypatch):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        platform = StrategyVectorPlatform()
        db = MagicMock()
        db.save_vector_index_registry = AsyncMock()
        db.supports_pgvector = lambda: False

        active = 0
        max_active = 0

        async def _build_profile(_db, strategy, profile_type='behavior', vector_method='price_volume', index_name='strategy_behavior', index_version='v1'):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                'id': f"profile_{strategy['id']}",
                'strategy_id': strategy['id'],
                'profile_type': profile_type,
                'vector_method': vector_method,
                'metric': 'cosine',
                'vector_dim': 3,
                'embedding': [1.0, 0.0, 0.0],
            }

        monkeypatch.setattr(platform, 'build_strategy_profile', _build_profile)

        result = await platform.build_profiles_for_strategies(
            db,
            strategies=[{'id': f's{i}'} for i in range(6)],
            profile_type='behavior',
            vector_method='price_volume',
            index_name='strategy_behavior',
            index_version='pytest_v1',
        )

        assert result['count'] == 6
        assert max_active > 1
        db.save_vector_index_registry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vector_cleanup_action_prunes_old_versions_and_hnsw_indexes(self, setup):
        mcp, db = setup
        db._pgvector_enabled = True

        async def seed(version: str, ts: str, strategy_id: str):
            await db.save_strategy_vector_profile({
                'strategy_id': strategy_id, 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
                'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': f'{version}_sig', 'backend': 'pgvector',
                'index_name': 'strategy_behavior', 'index_version': version, 'created_at': ts,
                'metadata': {'index_name': 'strategy_behavior', 'index_version': version},
            })
            await db.save_vector_index_registry({
                'index_name': 'strategy_behavior', 'index_version': version, 'status': 'active', 'backend': 'pgvector',
                'sample_count': 1, 'created_at': ts,
            })
            await db.save_strategy_vector_index_snapshot({
                'index_name': 'strategy_behavior', 'index_version': version, 'status': 'active', 'backend': 'pgvector',
                'profile_count': 1, 'bucket_count': 1, 'vector_dim': 3, 'built_at': ts, 'activated_at': ts,
            })
            await db.replace_strategy_vector_index_items('strategy_behavior', version, [{
                'profile_id': len(db._vector_profiles), 'strategy_id': strategy_id, 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 1.0,
                'embedding': [1.0, 0.0, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': ts,
            }])
            await db.ensure_strategy_vector_profile_pgvector_index('strategy_behavior', version, 3, profile_type='behavior')
            await db.ensure_strategy_vector_index_item_pgvector_index('strategy_behavior', version, 3)

        await seed('cleanup_v1', '2026-03-07T00:00:00+00:00', 'sid_cleanup_1')
        await seed('cleanup_v2', '2026-03-08T00:00:00+00:00', 'sid_cleanup_2')
        await seed('cleanup_v3', '2026-03-09T00:00:00+00:00', 'sid_cleanup_3')

        preview = await mcp.strategy_manager(action='vector_cleanup', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'keep_versions': 1,
            'dry_run': True,
            'cleanup_hnsw': True,
        }))
        cleaned = await mcp.strategy_manager(action='vector_cleanup', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'keep_versions': 1,
            'dry_run': False,
            'cleanup_hnsw': True,
        }))
        health = await mcp.strategy_manager(action='vector_health', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'limit_versions': 10,
            'include_hnsw_indexes': True,
        }))

        assert preview['success'] is True
        assert set(preview['data']['target_versions']) == {'cleanup_v1', 'cleanup_v2'}
        assert cleaned['success'] is True
        assert cleaned['data']['deleted']['vector_index_registry'] == 2
        assert cleaned['data']['deleted']['vector_index_snapshots'] == 2
        assert cleaned['data']['deleted']['vector_profiles'] == 2
        assert cleaned['data']['deleted']['vector_profile_store'] == 2
        assert cleaned['data']['deleted']['vector_index_items'] == 2
        assert cleaned['data']['deleted']['vector_index_item_store'] == 2
        assert cleaned['data']['deleted']['hnsw_indexes'] == 4
        assert health['success'] is True
        assert [item['index_version'] for item in health['data']['versions']] == ['cleanup_v3']
        assert health['data']['hnsw_index_count'] == 2


class TestIncubationPipelineActions:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_incubation_pipeline_auto_promotes_strategy(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action='create', kwargs=json.dumps({
            'name': '孵化晋级策略', 'strategy_type': 'momentum', 'params': {'lookback': 20},
        }))
        sid = created['data']['strategy_id']
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.3, 'max_drawdown': -0.08})
        db._signal_stats[sid] = {
            'total_signals': 24,
            'hit_rate': {1: 0.54, 5: 0.62, 10: 0.58, 20: 0.57},
            'forward_ic': {1: 0.01, 5: 0.03, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.10, 5: 0.9, 10: 0.7, 20: 0.5},
        }
        await db.save_strategy_incubation_account(sid, 'acct_pipe', stage='candidate', status='active')
        metric_dates = [f'2026-02-{day:02d}' for day in range(17, 29)] + [f'2026-03-{day:02d}' for day in range(1, 9)]
        for offset, metric_date in enumerate(metric_dates):
            await db.save_strategy_incubation_metric(sid, metric_date, {
                'account_id': 'acct_pipe',
                'stage': 'candidate',
                'decision': 'promote',
                'nav': 1.05 + offset * 0.002,
                'sharpe_ratio': 1.2,
                'max_drawdown': 0.08,
                'hit_rate_5d': 0.62,
                'forward_sharpe_5d': 0.85,
                'total_signals': 24,
                'total_orders': 6,
                'total_trades': 4,
            })

        run = await mcp.strategy_manager(action='incubation_pipeline_run', kwargs=json.dumps({'strategy_id': sid, 'auto_apply_review': True}))
        snapshots = await mcp.strategy_manager(action='incubation_pipeline', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert run['success'] is True
        assert run['data']['snapshot']['pipeline_stage'] in {'graduation_ready', 'promoted'}
        assert run['data']['auto_promoted'] is True
        assert snapshots['data']['count'] >= 1
        assert detail['data']['latest_incubation_pipeline_snapshot']['pipeline_stage'] == 'promoted'
        assert detail['data']['strategy']['status'] == 'listed'
        assert capabilities['data']['incubation_pipeline'] is True

    @pytest.mark.asyncio
    async def test_incubation_pipeline_batch_records_failed_stage(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action='create', kwargs=json.dumps({
            'name': '孵化阻塞策略', 'strategy_type': 'mean_reversion', 'params': {'lookback': 5},
        }))
        sid = created['data']['strategy_id']
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': -0.2, 'max_drawdown': -0.35})
        db._signal_stats[sid] = {
            'total_signals': 12,
            'hit_rate': {1: 0.42, 5: 0.28, 10: 0.25, 20: 0.24},
            'forward_ic': {1: 0.0, 5: -0.01, 10: -0.03, 20: -0.02},
            'forward_sharpe': {1: -0.1, 5: -0.4, 10: -0.5, 20: -0.6},
        }
        await db.save_strategy_incubation_account(sid, 'acct_fail', stage='observe', status='active')
        await db.save_strategy_incubation_metric(sid, '2026-03-08', {
            'account_id': 'acct_fail', 'stage': 'observe', 'decision': 'halt', 'nav': 0.91, 'sharpe_ratio': -0.3,
            'max_drawdown': 0.35, 'hit_rate_5d': 0.28, 'forward_sharpe_5d': -0.4, 'total_signals': 12, 'total_orders': 2, 'total_trades': 1,
        })
        await db.save_strategy_incubation_metric(sid, '2026-03-07', {
            'account_id': 'acct_fail', 'stage': 'observe', 'decision': 'halt', 'nav': 0.92, 'sharpe_ratio': -0.25,
            'max_drawdown': 0.32, 'hit_rate_5d': 0.29, 'forward_sharpe_5d': -0.3, 'total_signals': 12, 'total_orders': 1, 'total_trades': 1,
        })

        batch = await mcp.strategy_manager(action='incubation_pipeline_run', kwargs=json.dumps({'statuses': ['incubating'], 'auto_apply_review': False}))
        snapshots = await mcp.strategy_manager(action='incubation_pipeline', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))

        assert batch['success'] is True
        assert batch['data']['count'] >= 1
        assert batch['data']['stage_counts'].get('failed', 0) >= 1
        assert snapshots['data']['latest']['pipeline_stage'] == 'failed'
        assert snapshots['data']['latest']['pipeline_status'] == 'blocked'


class TestBacktestFilterReport:
    def test_report_entry_preserves_generation_metadata(self):
        entry = BacktestFilter._build_report_entry({
            'strategy_type': 'momentum',
            'generator_type': 'local_rule_v1',
            'params': {'lookback': 8, 'threshold': 0.01},
            'spawn_reason': 'test',
            'generation_reason': {'source': 'event_driven_local_fallback'},
            'target_symbols': ['601398'],
            'stock_pool': {'selection_mode': 'explicit', 'symbols': ['601398']},
            'selection_logic': ['follow trend'],
            'research_task': {'task_id': 'task_evt'},
            'event_context': {'event_id': 'evt_1'},
            'tags': ['ai_generated', 'llm_proxy_fallback'],
            'backtest_result': {'passed': True},
            'backtest_metrics': {'sharpe_ratio': 0.8},
        })

        assert entry['generator_type'] == 'local_rule_v1'
        assert entry['generation_reason']['source'] == 'event_driven_local_fallback'
        assert entry['research_task']['task_id'] == 'task_evt'
        assert entry['event_context']['event_id'] == 'evt_1'
        assert 'llm_proxy_fallback' in entry['tags']


class TestStrategyFactoryScheduler:
    @pytest.mark.asyncio
    async def test_market_frame_prefers_research_task_targets(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        calls = []

        async def _get_klines(code, limit=180):
            calls.append(code)
            if code == '688981':
                return _make_klines(150)
            return []

        db = MagicMock()
        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.list_stock_universe = AsyncMock(return_value=[{'code': '601398'}])

        frame = await generator._build_market_frame(db, research_task={'target_symbols': ['688981', '002371']})

        assert frame is not None
        assert calls[0] == '688981'

    @pytest.mark.asyncio
    async def test_generate_uses_research_context_frame_cache_when_primary_frame_missing(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _no_frame(_db, research_task=None):
            return None

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        async def _frame_cache(_db, research_context=None, research_task=None):
            return {'688981': sample_frame}

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{
                        'name': 'cache_frame_candidate',
                        'description': 'uses cached frame',
                        'rationale': 'test',
                        'target_symbols': ['688981'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                        'selection_logic': ['test'],
                        'dsl': {
                            'version': '1.0',
                            'timeframe': 'daily',
                            'entry': {'all': [{'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 12}}]}]},
                            'exit': {'any': [{'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 8}}]}]},
                            'metadata': {'target_symbols': ['688981']},
                        },
                        'tags': ['external_llm'],
                    }],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _no_frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        generator._build_symbol_frame_cache = _frame_cache

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981']})
        report = generator.get_last_report()

        assert len(specs) == 1
        assert report['market_frame_source'] == 'research_context_frame_cache'
        assert report['market_frame_ready'] is True
        assert report['external_provider']['status'] in {'succeeded', 'fallback_only'}

    @pytest.mark.asyncio
    async def test_generate_local_fallback_preserves_research_task_targets(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMRequestError

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError('timeout', metrics={'last_error_type': 'ReadTimeout', 'last_error': 'ReadTimeout'})

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981'], 'task_id': 'task_chip'})
        report = generator.get_last_report()
        candidate = specs[0].to_candidate('strategy_factory', 'exp_local_fallback')

        assert len(specs) == 1
        assert specs[0].metadata['generator_type'] == 'local_rule_v1'
        assert 'llm_proxy_fallback' in specs[0].tags
        assert specs[0].metadata['target_symbols'] == ['688981']
        assert specs[0].metadata['stock_pool']['symbols'] == ['688981']
        assert report['external_provider']['status'] == 'failed'
        assert candidate['target_symbols'] == ['688981']
        assert candidate['stock_pool']['symbols'] == ['688981']
        assert candidate['generator_type'] == 'local_rule_v1'

    @pytest.mark.asyncio
    async def test_generate_targeted_research_avoids_mixing_local_specs_when_external_fallback_exists(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{
                        'name': 'event_fallback_candidate',
                        'description': '消息驱动后的延续性。',
                        'rationale': 'test',
                        'target_symbols': ['688981'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                        'selection_logic': ['test'],
                        'dsl': {
                            'version': '1.0',
                            'timeframe': 'daily',
                            'entry': {'all': [{'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 12}}]}]},
                            'exit': {'any': [{'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 8}}]}]},
                            'metadata': {'target_symbols': ['688981']},
                        },
                        'tags': ['external_llm'],
                    }],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(MagicMock(), limit=2, snapshot={'date': '2026-03-08'}, research_task={'task_id': 'task_evt', 'target_symbols': ['688981']})

        assert len(specs) == 1
        assert specs[0].metadata['generator_type'] == 'external_llm'

    @pytest.mark.asyncio
    async def test_generate_fans_out_external_requests_and_dedupes_aggregated_specs(self, monkeypatch):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig
        from akshare_mcp.services.strategy_spec import StrategySpec
        from akshare_mcp.services.strategy_factory.constants import LLM_FAN_OUT_COUNT

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

        spec_a = StrategySpec(
            strategy_type='momentum',
            params={'lookback': 20, 'threshold': 0.02},
            name='fanout_a',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )
        spec_a_dup = StrategySpec(
            strategy_type='momentum',
            params={'lookback': 20, 'threshold': 0.02},
            name='fanout_a_dup',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )
        spec_b = StrategySpec(
            strategy_type='rsi',
            params={'rsi_period': 14, 'oversold': 30, 'overbought': 70},
            name='fanout_b',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )

        async def _fanout_request(**kwargs):
            request_index = int(kwargs.get('request_index') or 0)
            specs = [spec_a] if request_index == 1 else [spec_a_dup, spec_b]
            return {
                'status': 'succeeded',
                'request_index': request_index,
                'analysis': {'request_index': request_index},
                'request_report': {
                    'request_index': request_index,
                    'request_limit': kwargs.get('request_limit'),
                    'status': 'succeeded',
                    'viable_candidate_count': len(specs),
                },
                'successful_without_specs': False,
                'all_specs': list(specs),
                'viable_specs': list(specs),
                'exception': None,
            }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        monkeypatch.setattr(generator, '_run_external_provider_request', AsyncMock(side_effect=_fanout_request))

        specs = await generator.generate(
            MagicMock(),
            limit=2,
            snapshot={'date': '2026-03-08'},
            research_task={'task_id': 'task_evt', 'target_symbols': ['688981']},
        )
        report = generator.get_last_report()
        expected_requests = max(1, min(int(LLM_FAN_OUT_COUNT or 1), 4))

        assert len(specs) == 2
        assert {spec.strategy_type for spec in specs} == {'momentum', 'rsi'}
        assert generator._run_external_provider_request.await_count == expected_requests
        assert len(report['external_provider']['requests']) == expected_requests
        assert report['external_provider']['viable_selected_count'] == 2
        assert report['external_provider']['status'] == 'succeeded'

    @pytest.mark.asyncio
    async def test_build_research_context_includes_factor_research_artifact(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[])
        db.count_stock_universe = AsyncMock(return_value=0)
        db.get_klines = AsyncMock(return_value=[])

        context = await generator._build_research_context(
            db,
            {
                'date': '2026-03-08',
                'fg_level': 'greed',
                'fear_greed_index': 63,
                'factor_research': {
                    'active_factors': ['value', 'quality'],
                    'summary': {'top_factor_names': ['value', 'quality']},
                    'preferred_strategy_types': ['value_factor', 'quality_factor'],
                    'degraded': False,
                },
            },
            research_task={'task_id': 'task_factor_ctx'},
        )

        assert context['market_regime']['factor_research']['active_factors'] == ['value', 'quality']
        assert context['selection_framework']['factor_names'] == ['value', 'quality']

    @pytest.mark.asyncio
    async def test_generate_event_task_local_fallback_prioritizes_breakout_categories(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMRequestError

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '601398'}],
                'symbol_insights': [{'code': '601398'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError('timeout', metrics={'last_error_type': 'ReadTimeout', 'last_error': 'ReadTimeout'})

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(
            MagicMock(),
            limit=2,
            snapshot={'date': '2026-03-08'},
            research_task={
                'task_id': 'task_evt',
                'task_source': 'event_driven',
                'opportunity_type': 'sector_breakout',
                'target_symbols': ['601398', '601288'],
                'event_id': 'evt_bank',
                'theme_code': 'high_dividend_banks',
                'strategy_preferences': ['quality_factor', 'value_factor', 'ma_cross'],
            },
        )

        assert len(specs) == 1
        assert specs[0].strategy_type in {'momentum', 'ma_cross'}
        assert all(spec.strategy_type != 'quality_factor' for spec in specs)
        candidate = specs[0].to_candidate('strategy_factory:sector_breakout', 'exp_evt_local_fallback')
        assert candidate['generation_reason']['source'] == 'event_driven_local_fallback'
        assert candidate['research_task']['task_id'] == 'task_evt'
        assert candidate['event_context']['event_id'] == 'evt_bank'

    def test_local_fallback_varies_params_by_research_task(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        candidate = {
            'name': 'Momentum_20_60_Spread',
            'description': '中期与短期动量差，捕捉趋势加速。',
            'formula': '(close.pct_change(60) - close.pct_change(20))',
            'category': 'momentum',
            'rationale': '趋势行情中更稳健地识别加速段。',
            'engine': 'local_rule_v1',
        }

        spec_a = LLMProxyStrategyGenerator._local_candidate_to_spec(candidate, research_task={'task_id': 'task_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']})
        spec_b = LLMProxyStrategyGenerator._local_candidate_to_spec(candidate, research_task={'task_id': 'task_rotation', 'opportunity_type': 'rotation_balanced', 'target_symbols': ['600519', '000858']})

        assert spec_a is not None
        assert spec_b is not None
        assert spec_a.params != spec_b.params
        assert spec_a.metadata['fallback_profile']['task_opportunity_type'] == 'sector_breakout'
        assert spec_b.metadata['fallback_profile']['task_opportunity_type'] == 'rotation_balanced'

    @pytest.mark.asyncio
    async def test_generate_marks_non_executable_when_external_candidates_do_not_compile(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {'selection_notes': ['test']},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{'name': 'bad_blueprint', 'dsl': {'entry': {'all': []}, 'exit': {'any': []}}}],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        generator._build_external_candidate_spec = lambda *args, **kwargs: None

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981'], 'task_id': 'task_non_exec'})
        report = generator.get_last_report()

        assert len(specs) == 1
        assert report['external_provider']['status'] == 'non_executable'
        assert report['external_provider']['last_error_type'] == 'NoExecutableCandidates'
        assert report['external_provider']['requests'][0]['status'] == 'succeeded'
        assert report['external_provider']['requests'][0]['compiled_candidate_count'] == 0
        assert report['external_provider']['requests'][0]['non_executable_candidate_count'] == 1

    @pytest.mark.asyncio
    async def test_bandit_optimizer_accepts_stringified_parent_params(self):
        from akshare_mcp.services.strategy_autonomy import BanditParameterOptimizer

        optimizer = BanditParameterOptimizer()
        db = MagicMock()
        db.get_strategy_metrics = AsyncMock(return_value=[])
        db.get_signal_stats = AsyncMock(return_value={'total_signals': 12, 'hit_rate': {'5': 0.56}})
        db.list_strategy_generation_experiments = AsyncMock(return_value=[])

        specs = await optimizer.evolve(db, {
            'id': 'parent_1',
            'name': 'parent',
            'strategy_type': 'momentum',
            'params': '{"lookback": 20, "threshold": 0.02}',
        }, limit=1)

        assert len(specs) == 1
        assert specs[0].strategy_type == 'momentum'
        assert isinstance(specs[0].params, dict)
        assert 'lookback' in specs[0].params

    @pytest.mark.asyncio
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

        assert result['status'] == 'success'
        assert result['summary']['autonomy_task_count'] == 2
        assert result['summary']['autonomy_completed_task_count'] == 2
        assert result['summary']['autonomy_failed_task_count'] == 0
        assert result['summary']['autonomy_generated'] == 2
        assert result['summary']['event_task_count'] == 1
        assert result['summary']['snapshot_task_count'] == 1
        assert result['summary']['task_source_counts'] == {'event_driven': 1, 'snapshot': 1}
        assert result['summary']['scanner_task_types'] == {'sector_breakout': 1, 'oversold_repair': 1}
        assert result['summary']['event_snapshot_mixed'] is True
        assert result['summary']['autonomy_task_briefs'] == [
            {
                'task_id': 'task_hot_chip',
                'task_source': 'event_driven',
                'opportunity_type': 'sector_breakout',
                'generation_limit': 2,
                'generated_count': 1,
            },
            {
                'task_id': 'task_cold_bank',
                'task_source': 'snapshot',
                'opportunity_type': 'oversold_repair',
                'generation_limit': 1,
                'generated_count': 1,
            },
        ]
        assert result['summary']['external_llm_status'] == 'succeeded'
        assert db.save_strategy_task_run.await_count == 2
        assert db.update_strategy_task_run.await_count == 2
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['stages']['autonomy']['task_count'] == 2
        assert saved_run['stages']['autonomy']['completed_task_count'] == 2
        assert saved_run['stages']['autonomy']['failed_task_count'] == 0
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
        assert result['status'] == 'success'
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

        assert result['status'] == 'success'
        assert result['summary']['external_llm_status'] == 'succeeded'
        saved_run = db.save_strategy_factory_run.await_args.args[0]
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

        assert result['status'] == 'success'
        assert result['summary']['event_task_count'] == 1
        assert result['summary']['snapshot_task_count'] == 0
        assert result['summary']['task_source_counts'] == {'event_driven': 1}
        assert result['summary']['scanner_task_types'] == {'sector_breakout': 1}
        assert result['summary']['event_snapshot_mixed'] is False
        assert result['summary']['autonomy_task_briefs'] == [
            {
                'task_id': 'task_evt_oil',
                'task_source': 'event_driven',
                'opportunity_type': 'sector_breakout',
                'generation_limit': 1,
                'generated_count': 1,
            }
        ]
        assert result['summary']['event_evidence_count'] == len(saved_evidence)
        assert len(saved_evidence) >= 3
        assert any(item['evidence_type'] == 'event_theme_context' for item in saved_evidence)
        assert any(item['evidence_type'] == 'target_symbol' and item['symbol'] == '601857' for item in saved_evidence)
        saved_run = db.save_strategy_factory_run.await_args.args[0]
        assert saved_run['stages']['autonomy']['event_task_count'] == 1
        assert saved_run['stages']['autonomy']['event_evidence_count'] == len(saved_evidence)

    @pytest.mark.asyncio
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

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)

        scheduler = StrategyFactoryScheduler()
        result = await scheduler.run_once()

        assert result["status"] == "success"
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

        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
        monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
        monkeypatch.setattr("akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service", lambda: _DummyAutonomy())

        result = await StrategyFactoryScheduler().run_once()

        assert result['status'] == 'success'
        saved_run = db.save_strategy_factory_run.await_args.args[0]
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


# ═══════════════════════════════════════════════════════════════
# 9. 自动命名测试
# ═══════════════════════════════════════════════════════════════

class TestAutoName:
    def test_ma_cross_name(self):
        name = _auto_name("ma_cross", {"short_period": 5, "long_period": 20})
        assert "均线" in name
        assert "5" in name

    def test_momentum_name(self):
        name = _auto_name("momentum", {"lookback": 20, "threshold": 0.02})
        assert "动量" in name

    def test_multi_factor_name(self):
        name = _auto_name("multi_factor", {"factor_weights": {"value": 0.5, "quality": 0.3, "growth": 0.2}})
        assert "多因子" in name
        assert "value" in name

    def test_unknown_type(self):
        name = _auto_name("custom_xyz", {})
        assert "策略" in name


# ═══════════════════════════════════════════════════════════════
# 10. BacktestFilter 测试
# ═══════════════════════════════════════════════════════════════

class TestBacktestFilter:
    @staticmethod
    def _make_backtest_result(sharpe: float, mdd: float, trades: float, total_return: float = 0.12, win_rate: float = 0.55) -> dict:
        return {
            "success": True,
            "data": {
                "sharpe_ratio": sharpe,
                "total_return": total_return,
                "max_drawdown": mdd,
                "win_rate": win_rate,
                "trades_count": trades,
            },
        }

    @pytest.mark.asyncio
    async def test_filter_records_insufficient_samples_reason_when_no_klines(self):
        """没有足够样本时应记录标准化失败原因"""
        bt_filter = BacktestFilter()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 1, "threshold": 0.5}},
        ]
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=[])

        passed = await bt_filter.filter(candidates, db)
        assert passed == []
        assert candidates[0]["backtest_result"]["reason_code"] == "insufficient_samples"
        assert candidates[0]["backtest_result"]["failed_metric"]["field"] == "sample_count"
        assert bt_filter.get_last_report()["summary"]["failed_reason_counts"]["insufficient_samples"] == 1

    @pytest.mark.asyncio
    async def test_filter_records_sharpe_failure_reason(self):
        """Sharpe 不达标时应记录标准化失败原因和指标"""
        bt_filter = BacktestFilter()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(200))

        with patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            new=AsyncMock(return_value=self._make_backtest_result(0.18, 0.12, 8)),
        ):
            passed = await bt_filter.filter(candidates, db)

        assert passed == []
        assert candidates[0]["backtest_result"]["reason_code"] == "sharpe_below_threshold"
        assert candidates[0]["backtest_result"]["failed_metric"]["field"] == "sharpe_ratio"
        assert candidates[0]["backtest_result"]["metrics"]["sharpe_ratio"] == 0.18
        assert bt_filter.get_last_report()["summary"]["failed_reason_counts"]["sharpe_below_threshold"] == 1

    @pytest.mark.asyncio
    async def test_filter_uses_strategy_type_specific_thresholds(self):
        """不同策略类型应使用分层初筛阈值"""
        bt_filter = BacktestFilter()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
            {"strategy_type": "value_factor", "params": {"lookback": 60, "buy_quantile": 0.8, "sell_quantile": 0.2}},
        ]
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(200))

        with patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            new=AsyncMock(return_value=self._make_backtest_result(0.28, 0.12, 5)),
        ):
            passed = await bt_filter.filter(candidates, db)

        assert len(passed) == 1
        assert passed[0]["strategy_type"] == "value_factor"
        assert candidates[0]["backtest_result"]["passed"] is False
        assert candidates[0]["backtest_result"]["reason_code"] == "sharpe_below_threshold"
        assert candidates[1]["backtest_result"]["passed"] is True
        assert candidates[0]["backtest_result"]["thresholds"]["sharpe_min"] > candidates[1]["backtest_result"]["thresholds"]["sharpe_min"]
        assert bt_filter.get_last_report()["summary"]["thresholds_by_type"]["momentum"]["sharpe_min"] == 0.35
        assert bt_filter.get_last_report()["summary"]["thresholds_by_type"]["value_factor"]["sharpe_min"] == 0.25

    @pytest.mark.asyncio
    async def test_filter_prefers_candidate_target_symbols_for_external_llm(self):
        bt_filter = BacktestFilter()
        target_symbols = ["300750", "600519", "000858"]
        candidates = [{
            "strategy_type": "dsl_rule",
            "params": {"dsl": {"metadata": {"target_symbols": target_symbols}}},
            "generator_type": "external_llm",
            "target_symbols": target_symbols,
            "stock_pool": {"selection_mode": "explicit", "symbols": target_symbols},
            "tags": ["external_llm", "ai_generated"],
        }]
        calls = []

        async def _get_klines(code, limit=500):
            calls.append(code)
            if code in target_symbols:
                return _make_klines(200)
            return []

        db = MagicMock()
        db.get_klines = AsyncMock(side_effect=_get_klines)

        with patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            new=AsyncMock(return_value=self._make_backtest_result(0.32, 0.12, 4)),
        ):
            passed = await bt_filter.filter(candidates, db)

        assert len(passed) == 1
        result = candidates[0]["backtest_result"]
        assert result["passed"] is True
        assert result["target_codes"] == target_symbols
        assert result["code_source"] == "candidate_target_symbols"
        assert result["primary_layer"] == "target"
        assert result["layers"]["target"]["sample_count"] == 3
        assert calls[:3] == target_symbols


# ═══════════════════════════════════════════════════════════════
# 11. DataCollector 测试（mock外部依赖）
# ═══════════════════════════════════════════════════════════════

class TestDataCollector:
    @pytest.mark.asyncio
    async def test_collect_returns_structured_snapshot_when_partially_degraded(self):
        """部分数据源失败时应返回结构化完整性摘要"""
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 12})

        async def _factor_ic_side_effect(fname, *_args):
            if fname == "quality":
                raise Exception("quality unavailable")
            return [{"ic_value": 0.12}] * 10

        async def _count_by_type(status):
            if status == "listed":
                return {"momentum": 2, "value_factor": 1}
            return {"momentum": 1}

        db.get_factor_ic_history = AsyncMock(side_effect=_factor_ic_side_effect)
        db.count_strategies_by_type = AsyncMock(side_effect=_count_by_type)
        db.save_daily_snapshot = AsyncMock()

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 61, "level": "greed", "components": {"breadth": 70}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 20}, {"total": 30}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["summary"]["listed_count"] == 3
        assert snapshot["summary"]["degraded"] is True
        assert snapshot["completeness"]["completion_ratio"] < 1.0
        assert snapshot["source"] == "strategy_factory.collector"
        assert snapshot["asof_time"]
        assert snapshot["freshness_sec"] >= 0
        assert "degraded" in snapshot["quality_flags"]
        assert "incomplete" in snapshot["quality_flags"]
        assert snapshot["sources"]["factor_ic"]["status"] == "partial"
        assert snapshot["sources"]["factor_ic"]["source"] == "factor_ic"
        assert snapshot["sources"]["factor_ic"]["asof_time"] == snapshot["asof_time"]
        assert snapshot["sources"]["factor_ic"]["freshness_sec"] >= 0
        assert "partial" in snapshot["sources"]["factor_ic"]["quality_flags"]
        assert snapshot["degraded"] is True
        assert any(item["source"] == "factor_ic" for item in snapshot["failure_reasons"])
        db.save_daily_snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collect_marks_empty_factor_history_as_fallback(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 12})
        db.get_factor_ic_history = AsyncMock(return_value=[])
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 61, "level": "greed", "components": {"breadth": 70}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 20}, {"total": 30}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["factor_ic"] == {}
        assert snapshot["factor_ic_trend"] == {}
        assert snapshot["sources"]["factor_ic"]["status"] == "fallback"
        assert snapshot["degraded"] is True
        assert snapshot["completeness"]["is_complete"] is False
        assert "factor_ic" in snapshot["completeness"]["missing_sources"]
        assert any(item["source"] == "factor_ic" and item["fallback_used"] for item in snapshot["failure_reasons"])
        db.save_daily_snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collect_with_all_failures_still_returns_snapshot(self):
        """所有外部数据源失败时仍应返回有效快照"""
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=[])
        db.get_limit_up_stats = AsyncMock(side_effect=Exception("no data"))
        db.get_factor_ic_history = AsyncMock(side_effect=Exception("no data"))
        db.count_strategies_by_type = AsyncMock(return_value={})
        db.save_daily_snapshot = AsyncMock()
        # north_fund DB 路径也需要失败
        db.acquire = MagicMock(side_effect=Exception("db unavailable"))

        with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread",
                   side_effect=Exception("network error")), \
             patch("akshare_mcp.tools.market.kline.get_index_kline",
                   new_callable=AsyncMock,
                   return_value={"success": False, "data": []}):
            snapshot = await collector.collect(db)

        assert "date" in snapshot
        assert "fear_greed_index" in snapshot
        assert snapshot["fear_greed_index"] == 50  # fallback
        assert snapshot["north_fund_3d_net"] == 0.0
        assert isinstance(snapshot["category_counts"], dict)
        assert snapshot["degraded"] is True
        assert snapshot["completeness"]["is_complete"] is False
        assert "north_fund_3d_net" in snapshot["missing_fields"]
        assert snapshot["sources"]["fear_greed"]["status"] == "fallback"
        assert len(snapshot["failure_reasons"]) >= 4
        db.save_daily_snapshot.assert_awaited_once()


class TestFactorSchedulerAndBatchFactors:
    def test_factor_scheduler_defaults_align_with_strategy_factory_consumption(self):
        from akshare_mcp.services.factor_scheduler import DEFAULT_FACTORS

        assert "reversal" in DEFAULT_FACTORS
        assert "liquidity" not in DEFAULT_FACTORS

    @pytest.mark.asyncio
    async def test_batch_compute_factors_supports_reversal(self, monkeypatch):
        from akshare_mcp.tools.managers.quant_manager import quant_manager

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(80, base=20.0, trend=-0.01, noise=0.001))
        db.get_financials = AsyncMock(return_value=[])
        db.save_factor_values = AsyncMock()
        monkeypatch.setattr("akshare_mcp.tools.managers.quant_manager.get_db", lambda: db)

        result = await quant_manager(
            action="batch_compute_factors",
            kwargs=json.dumps({
                "codes": ["000001"],
                "factors": ["reversal"],
                "persist": True,
                "compute_ic": False,
            }),
        )

        assert result["success"] is True
        assert result["data"]["computed_count"] == 1
        assert result["data"]["factors"] == ["reversal"]
        saved_values = db.save_factor_values.await_args.args[2]
        assert "reversal" in saved_values
        assert "liquidity" not in saved_values

    @pytest.mark.asyncio
    async def test_factor_scheduler_run_once_can_import_quant_manager(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        calls = []

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            calls.append({"action": action, "code": code, "kwargs": kwargs})
            payload = json.loads(kwargs["kwargs"])
            assert payload["factors"] == ["reversal"]
            assert payload["persist"] is True
            assert payload["compute_ic"] is True
            return {"success": True, "data": {"computed_count": 1, "error_count": 0}}

        monkeypatch.setattr(
            quant_manager_module,
            "quant_manager",
            _fake_quant_manager,
        )

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()

        assert result["computed"] == 2
        assert result["errors"] == 0
        assert result["universe_size"] == 2
        assert result["source"] == "factor_scheduler"
        assert result["asof_time"]
        assert result["freshness_sec"] >= 0
        assert result["quality_flags"] == []
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_factor_scheduler_run_once_counts_failed_manager_batches(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setattr(
            quant_manager_module,
            "quant_manager",
            AsyncMock(return_value={"success": False, "data": None, "error": "bad json"}),
        )

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()

        assert result["computed"] == 0
        assert result["errors"] == 2
        assert result["universe_size"] == 2
        assert result["source"] == "factor_scheduler"
        assert "degraded" in result["quality_flags"]
        assert "failed" in result["quality_flags"]

    def test_factor_scheduler_status_marks_stale_result(self):
        from akshare_mcp.services.factor_scheduler import FactorScheduler

        scheduler = FactorScheduler(universe=["000001"], factors=["reversal"], batch_size=1)
        scheduler.last_run = datetime.now(timezone.utc) - timedelta(days=2)
        scheduler.last_result = {
            "computed": 1,
            "errors": 0,
            "elapsed_seconds": 1.2,
            "universe_size": 1,
            "source": "factor_scheduler",
            "asof_time": scheduler.last_run.isoformat(),
            "freshness_sec": 0.0,
            "quality_flags": [],
        }

        status = scheduler.status()

        assert status["source"] == "factor_scheduler"
        assert status["asof_time"] == scheduler.last_run.isoformat()
        assert status["freshness_sec"] >= 2 * 24 * 60 * 60
        assert "stale" in status["quality_flags"]

    @pytest.mark.asyncio
    async def test_collect_prefers_db_index_klines_before_external_fetch(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60, base=3000, trend=0.002, noise=0.001))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 9})
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.08}] * 10)
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()
        db.acquire = MagicMock(side_effect=Exception("db unavailable"))
        db.list_stock_universe = AsyncMock(return_value=[])
        db.save_factory_event_cluster = None
        db.save_factory_event_signal = None

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 63, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ), patch(
            "akshare_mcp.tools.market.kline.get_index_kline",
            new_callable=AsyncMock,
            return_value={"success": True, "data": _make_klines(60, base=3000, trend=0.003, noise=0.001)},
        ) as index_mock:
            snapshot = await collector.collect(db)

        assert snapshot["fear_greed_index"] == 63
        assert snapshot["sources"]["fear_greed"]["status"] == "success"
        assert index_mock.await_count == 0

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_collect_uses_db_native_paths_without_external_threads(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.55e12, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.20e12, "pe_ratio": 8.8, "pb_ratio": 1.2},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.00e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601857", "600938"}:
                return _make_klines(size, base=10.0, trend=0.012, noise=0.002)
            return _make_klines(size, base=30.0, trend=-0.002, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 67, "level": "greed", "components": {"breadth": 74}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["fear_greed"]["status"] == "success"
        assert snapshot["sources"]["north_fund"]["status"] == "fallback"
        assert snapshot["sources"]["margin_data"]["status"] == "success"
        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert snapshot["sources"]["sector_fund_flow"]["details"]["mode"] == "local_rotation"
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert internal_snapshot["engine"] == "local_db_rule_v1"
        assert "石油石化" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_uses_industry_as_rotation_fallback_when_sector_missing(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601398", "name": "工商银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 2.52e11, "pe_ratio": 6.9, "pb_ratio": 0.66},
            {"code": "601288", "name": "农业银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 2.33e11, "pe_ratio": 8.2, "pb_ratio": 0.86},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 9.73e10, "pe_ratio": 6.5, "pb_ratio": 0.91},
            {"code": "600048", "name": "保利发展", "industry": "房地产开发", "sector": None, "market": "SH", "market_cap": 1.10e11, "pe_ratio": 10.8, "pb_ratio": 0.88},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601398", "601288", "600036"}:
                return _make_klines(size, base=8.0, trend=0.011, noise=0.0015)
            return _make_klines(size, base=12.0, trend=-0.006, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 64, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "银行" in list(snapshot.get("hot_sectors") or [])
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert "银行" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_uses_theme_alias_as_rotation_fallback_when_industry_missing(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601398", "name": "工商银行", "industry": None, "sector": None, "market": "SH", "market_cap": 2.52e11, "pe_ratio": 6.9, "pb_ratio": 0.66},
            {"code": "601288", "name": "农业银行", "industry": None, "sector": None, "market": "SH", "market_cap": 2.33e11, "pe_ratio": 8.2, "pb_ratio": 0.86},
            {"code": "600036", "name": "招商银行", "industry": None, "sector": None, "market": "SH", "market_cap": 9.73e10, "pe_ratio": 6.5, "pb_ratio": 0.91},
            {"code": "600048", "name": "保利发展", "industry": None, "sector": None, "market": "SH", "market_cap": 1.10e11, "pe_ratio": 10.8, "pb_ratio": 0.88},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601398", "601288", "600036"}:
                return _make_klines(size, base=8.0, trend=0.011, noise=0.0015)
            return _make_klines(size, base=12.0, trend=-0.006, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 64, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "高股息金融" in list(snapshot.get("hot_sectors") or [])
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert "高股息金融" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_local_event_engine_generates_oil_event_without_external_sector_flow(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.55e12, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.20e12, "pe_ratio": 8.8, "pb_ratio": 1.2},
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 7.20e11, "pe_ratio": 10.1, "pb_ratio": 0.9},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.00e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601857", "600938", "600028"}:
                return _make_klines(size, base=10.0, trend=0.012, noise=0.002)
            return _make_klines(size, base=30.0, trend=-0.004, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 67, "level": "greed", "components": {"breadth": 74}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                Exception("sector flow unavailable"),
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "石油石化" in list(snapshot.get("hot_sectors") or [])
        assert snapshot["event_driven"]["enabled"] is True
        assert snapshot["event_driven"]["event_count"] >= 1
        assert any(str(item.get("event_id") or "") == "local_theme_upstream_oil_gas_positive" for item in snapshot["event_driven"]["events"])
        oil_event = next(item for item in snapshot["event_driven"]["events"] if item.get("event_id") == "local_theme_upstream_oil_gas_positive")
        assert oil_event["themes"][0]["theme_code"] == "upstream_oil_gas"
        assert oil_event["themes"][0]["target_symbols"][:2] == ["601857", "600938"]

    @pytest.mark.asyncio
    async def test_collect_builds_event_driven_snapshot_from_factory_tables(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 8})
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.08}] * 10)
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()
        db.list_factory_event_clusters = AsyncMock(return_value=[{
            "event_id": "evt_oil_1",
            "event_type": "geopolitics",
            "event_name": "中东战事升级",
            "summary": "中东战事升级推动原油供给担忧升温。",
            "direction": "positive",
            "intensity": 0.85,
            "confidence": 0.91,
            "horizon": "swing_5_20d",
            "themes": ["upstream_oil_gas"],
            "status": "active",
            "last_seen_at": "2026-03-09T09:00:00+08:00",
        }])
        db.list_factory_theme_definitions = AsyncMock(return_value=[{
            "theme_code": "upstream_oil_gas",
            "theme_name": "上游油气",
            "active": True,
        }])
        db.list_factory_event_signals = AsyncMock(return_value=[
            {
                "event_id": "evt_oil_1",
                "symbol": "601857",
                "theme_code": "upstream_oil_gas",
                "final_score": 0.92,
                "theme_score": 0.88,
                "exposure_score": 0.91,
                "price_confirm_score": 0.84,
                "flow_confirm_score": 0.73,
                "rationale": "上游油气对油价上行弹性更高。",
            },
            {
                "event_id": "evt_oil_1",
                "symbol": "600938",
                "theme_code": "upstream_oil_gas",
                "final_score": 0.87,
                "theme_score": 0.82,
                "exposure_score": 0.85,
                "price_confirm_score": 0.79,
                "flow_confirm_score": 0.68,
                "rationale": "供给扰动叠加板块相对强势。",
            },
        ])

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 58, "level": "neutral", "components": {"breadth": 60}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "石油石化", "mainNetInflow": 2},
                    {"name": "航运", "mainNetInflow": 1},
                    {"name": "航空", "mainNetInflow": -1},
                    {"name": "化工", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["event_driven"]["enabled"] is True
        assert snapshot["event_driven"]["event_count"] == 1
        assert snapshot["event_driven"]["tasks_ready_count"] == 1
        assert snapshot["event_driven"]["events"][0]["event_id"] == "evt_oil_1"
        assert snapshot["event_driven"]["events"][0]["themes"][0]["target_symbols"] == ["601857", "600938"]
        assert snapshot["summary"]["event_count"] == 1
        assert snapshot["sources"]["event_driven"]["status"] == "success"
        db.save_daily_snapshot.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# 12. 生命周期状态转换测试
# ═══════════════════════════════════════════════════════════════

class TestLifecycleTransitions:
    def test_valid_transitions(self):
        from akshare_mcp.tools.managers.strategy_manager import (
            LIFECYCLE_TRANSITIONS, _validate_transition,
        )
        assert _validate_transition("draft", "submitted") is True
        assert _validate_transition("submitted", "incubating") is True
        assert _validate_transition("incubating", "listed") is True
        assert _validate_transition("incubating", "deprecated") is True
        assert _validate_transition("listed", "deprecated") is True
        assert _validate_transition("listed", "suspended") is True
        assert _validate_transition("suspended", "listed") is True

    def test_invalid_transitions(self):
        from akshare_mcp.tools.managers.strategy_manager import _validate_transition
        assert _validate_transition("draft", "listed") is False
        assert _validate_transition("incubating", "rejected") is False
        assert _validate_transition("deprecated", "listed") is False
        assert _validate_transition("archived", "draft") is False
        assert _validate_transition("draft", "deprecated") is False


# ═══════════════════════════════════════════════════════════════
# 13. 质量门 4 阶段验证单元测试
# ═══════════════════════════════════════════════════════════════

from akshare_mcp.services.strategy_factory import (
    QUALITY_GATE_THRESHOLDS,
    RISK_REPORT_THRESHOLDS,
    PROMOTION_THRESHOLDS,
    DEPRECATION_THRESHOLDS,
)


class TestQualityGateThresholdConstants:
    """验证阈值常量已定义且值合理"""

    def test_quality_gate_keys_present(self):
        for key in ["walk_forward_ic_ir_min", "purged_kfold_ic_min",
                     "bootstrap_ci_lower_min", "param_sensitivity_max"]:
            assert key in QUALITY_GATE_THRESHOLDS

    def test_risk_report_keys_present(self):
        for key in ["var_percent_max", "cvar_percent_max", "stress_loss_percent_min"]:
            assert key in RISK_REPORT_THRESHOLDS

    def test_promotion_keys_present(self):
        for key in ["sharpe_min", "mdd_max", "hit_rate_blocker", "hit_rate_risk_flag"]:
            assert key in PROMOTION_THRESHOLDS

    def test_deprecation_keys_present(self):
        for key in ["sharpe_negative", "mdd_critical"]:
            assert key in DEPRECATION_THRESHOLDS

    def test_values_reasonable(self):
        assert 0 < QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"] < 2
        assert 0 < QUALITY_GATE_THRESHOLDS["param_sensitivity_max"] < 1
        assert RISK_REPORT_THRESHOLDS["stress_loss_percent_min"] < 0
        assert PROMOTION_THRESHOLDS["sharpe_min"] > DEPRECATION_THRESHOLDS["sharpe_negative"]


class TestQualityGateFunction:
    """_run_quality_gate 4-stage 验证"""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        # 返回足够的K线数据
        klines = _make_klines(n=500, trend=0.002, noise=0.01)
        db.get_klines = AsyncMock(return_value=klines)
        return db

    @pytest.mark.asyncio
    async def test_unknown_strategy_type_fails(self, mock_db):
        from akshare_mcp.tools.managers.strategy_manager import _run_quality_gate
        result = await _run_quality_gate(mock_db, {
            "strategy_type": "nonexistent_type_xyz",
            "params": {},
        })
        assert result["passed"] is False
        assert any("registry" in r.lower() for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_insufficient_kline_fails(self):
        from akshare_mcp.tools.managers.strategy_manager import _run_quality_gate
        db = MagicMock()
        # 只返回少量K线
        db.get_klines = AsyncMock(return_value=_make_klines(n=30))
        result = await _run_quality_gate(db, {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
        })
        assert result["passed"] is False
        assert any("insufficient" in r.lower() or "kline" in r.lower() for r in result["reasons"])

    @pytest.mark.asyncio
    async def test_result_has_normalized_structure(self, mock_db):
        from akshare_mcp.tools.managers.strategy_manager import _run_quality_gate
        result = await _run_quality_gate(mock_db, {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
        })
        # 无论 passed 与否，结构都应规范
        assert "passed" in result
        assert "reasons" in result
        assert "reason_codes" in result
        assert isinstance(result["reasons"], list)
        assert isinstance(result["reason_codes"], list)
        assert len(result["reasons"]) == len(result["reason_codes"])


# ═══════════════════════════════════════════════════════════════
# 14. Deduplicator 行为向量边界测试
# ═══════════════════════════════════════════════════════════════

class TestDeduplicatorBehaviorVector:
    """测试 _build_behavior_klines 的边界条件"""

    @pytest.mark.asyncio
    async def test_all_zero_series_returns_none(self, monkeypatch):
        """全零序列（低活跃策略）应被跳过，避免余弦相似度恒为1"""
        dedup = Deduplicator()
        # mock _build_strategy_panels 返回全零序列
        zero_series = np.zeros(60)
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._build_strategy_panels",
            AsyncMock(return_value={"strategy_returns": zero_series}),
        )
        result = await dedup._build_behavior_klines("momentum", {"lookback": 20}, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_short_series_returns_none(self, monkeypatch):
        """长度不足30的序列应返回None"""
        dedup = Deduplicator()
        short_series = np.random.randn(15)
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._build_strategy_panels",
            AsyncMock(return_value={"strategy_returns": short_series}),
        )
        result = await dedup._build_behavior_klines("rsi", {"rsi_period": 14}, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_near_zero_series_returns_none(self, monkeypatch):
        """非零比例<10%的序列应返回None"""
        dedup = Deduplicator()
        series = np.zeros(100)
        series[50] = 0.01  # 只有1%非零
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._build_strategy_panels",
            AsyncMock(return_value={"strategy_returns": series}),
        )
        result = await dedup._build_behavior_klines("ma_cross", {"short_period": 5}, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_active_series_returns_klines(self, monkeypatch):
        """正常活跃序列应返回伪K线列表"""
        dedup = Deduplicator()
        series = np.random.randn(100) * 0.01  # 大部分非零
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._build_strategy_panels",
            AsyncMock(return_value={"strategy_returns": series}),
        )
        result = await dedup._build_behavior_klines("momentum", {"lookback": 20}, MagicMock())
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 60  # 取最后60条
        for k in result:
            assert "open" in k and "close" in k and "high" in k and "low" in k

    @pytest.mark.asyncio
    async def test_behavior_cache_prevents_recompute(self, monkeypatch):
        """缓存应防止重复计算"""
        dedup = Deduplicator()
        call_count = 0
        original_series = np.random.randn(100) * 0.01

        async def mock_panels(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"strategy_returns": original_series}

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._build_strategy_panels",
            mock_panels,
        )
        db = MagicMock()
        r1 = await dedup._build_behavior_klines("momentum", {"lookback": 20}, db)
        r2 = await dedup._build_behavior_klines("momentum", {"lookback": 20}, db)
        assert r1 == r2
        assert call_count == 1  # 只调用一次

    def test_param_sim_all_same_scores(self):
        """完全相同参数相似度为1.0"""
        params = {"lookback": 20, "threshold": 0.05, "period": 14}
        assert Deduplicator._param_sim(params, params) == 1.0

    def test_param_sim_empty_keys(self):
        """无共同键时相似度为0.0"""
        assert Deduplicator._param_sim({"a": 1}, {"b": 2}) == 0.0


# ═══════════════════════════════════════════════════════════════
# 15. EliminationChecker 市场环境测试
# ═══════════════════════════════════════════════════════════════

class TestEliminationCheckerRegime:
    """测试不同市场环境下的淘汰决策"""

    def _make_db(self, *, strategy_type="momentum", mdd=-0.10, sharpe=0.3,
                 win_rate=0.40, hit_rate_5d=None, total_signals=0,
                 validation_grade=None, var_percent=0, cvar_percent=0,
                 stress_loss_percent=0):
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s_test", "strategy_type": strategy_type},
        ])
        metrics = [{"period": "all", "max_drawdown": mdd,
                     "sharpe_ratio": sharpe, "win_rate": win_rate}]
        if validation_grade:
            metrics.append({"period": "validation", "grade": validation_grade})
        if var_percent or cvar_percent or stress_loss_percent:
            metrics.append({"period": "risk", "var_percent": var_percent,
                            "cvar_percent": cvar_percent,
                            "stress_loss_percent": stress_loss_percent})
        db.get_strategy_metrics = AsyncMock(return_value=metrics)
        hr = {}
        if hit_rate_5d is not None:
            hr = {5: hit_rate_5d}
        db.get_signal_stats = AsyncMock(return_value={
            "hit_rate": hr, "total_signals": total_signals,
        })
        db.update_strategy_status = AsyncMock()
        db.save_elimination_log = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_momentum_survives_in_greed(self):
        """动量策略在greed环境中，指标健康时不应被淘汰"""
        checker = EliminationChecker()
        db = self._make_db(strategy_type="momentum", sharpe=0.5, win_rate=0.50)
        eliminated = await checker.check(db, "greed")
        assert len(eliminated) == 0

    @pytest.mark.asyncio
    async def test_momentum_flagged_in_fear(self):
        """动量策略在fear环境中，加上边缘指标，应因regime+win_rate被淘汰"""
        checker = EliminationChecker()
        db = self._make_db(strategy_type="momentum", sharpe=0.1, win_rate=0.25)
        eliminated = await checker.check(db, "fear")
        assert len(eliminated) == 1
        flags = eliminated[0]["red_flags"]
        assert any("不适合" in f for f in flags)
        assert any("胜率" in f for f in flags)

    @pytest.mark.asyncio
    async def test_value_factor_survives_in_fear(self):
        """价值因子策略在fear环境中适宜，健康指标不应被淘汰"""
        checker = EliminationChecker()
        db = self._make_db(strategy_type="value_factor", sharpe=0.8, win_rate=0.55)
        eliminated = await checker.check(db, "fear")
        assert len(eliminated) == 0

    @pytest.mark.asyncio
    async def test_fatal_drawdown_eliminates_regardless_of_regime(self):
        """致命回撤（>30%）无论环境如何都应被淘汰"""
        checker = EliminationChecker()
        for regime in ["neutral", "greed", "fear", "extreme_greed", "extreme_fear"]:
            db = self._make_db(strategy_type="multi_factor", mdd=-0.40, sharpe=1.0, win_rate=0.60)
            eliminated = await checker.check(db, regime)
            assert len(eliminated) == 1, f"Should eliminate in {regime}"

    @pytest.mark.asyncio
    async def test_metrics_period_priority(self):
        """验证 all > backtest 优先级排序：即使 backtest 排在前面也应选取 all"""
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s_prio", "strategy_type": "ma_cross"},
        ])
        # backtest 排在前面，all 排在后面；应选取 all
        db.get_strategy_metrics = AsyncMock(return_value=[
            {"period": "backtest", "max_drawdown": -0.40, "sharpe_ratio": -1.0, "win_rate": 0.1},
            {"period": "all", "max_drawdown": -0.10, "sharpe_ratio": 1.0, "win_rate": 0.55},
        ])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        eliminated = await checker.check(db, "neutral")
        # 使用 all 的健康指标，不应被淘汰
        assert len(eliminated) == 0

    @pytest.mark.asyncio
    async def test_no_metrics_does_not_crash(self):
        """没有指标数据时不应崩溃"""
        checker = EliminationChecker()
        db = MagicMock()
        db.list_strategies = AsyncMock(return_value=[
            {"id": "s_empty", "strategy_type": "rsi"},
        ])
        db.get_strategy_metrics = AsyncMock(return_value=[])
        db.get_signal_stats = AsyncMock(return_value={"hit_rate": {}, "total_signals": 0})
        db.update_strategy_status = AsyncMock()
        eliminated = await checker.check(db, "neutral")
        # 没有指标数据，所有值默认0，不应崩溃
        assert isinstance(eliminated, list)

    @pytest.mark.asyncio
    async def test_var_cvar_stress_flags(self):
        """VaR/CVaR/压力测试应触发红旗"""
        checker = EliminationChecker()
        db = self._make_db(
            strategy_type="rsi", sharpe=0.1, win_rate=0.25,
            var_percent=5.0, cvar_percent=7.0, stress_loss_percent=-30.0,
        )
        eliminated = await checker.check(db, "neutral")
        assert len(eliminated) == 1
        flags = eliminated[0]["red_flags"]
        assert any("VaR" in f for f in flags)
        assert any("CVaR" in f for f in flags)
        assert any("压力测试" in f for f in flags)


# ═══════════════════════════════════════════════════════════════
# 16. RRF 排名边界测试
# ═══════════════════════════════════════════════════════════════

class TestRRFRankingEdgeCases:
    """RRF 排名极端情况"""

    def test_all_same_scores(self):
        """所有策略指标完全相同时，每个都应有相同的 rrf_score"""
        strategies = [
            {"id": f"s{i}", "sharpe_ratio": 1.0, "total_return": 0.2,
             "win_rate": 0.5, "calmar_ratio": 0.8, "max_drawdown": -0.15}
            for i in range(5)
        ]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 5
        scores = [s["rrf_score"] for s in ranked]
        # 所有score总和应相同（排名并列，每个位置score叠加后分布均匀）
        # 实际上由于排序稳定性，分数不会完全相同，但差异应很小
        assert max(scores) - min(scores) < 0.01

    def test_single_strategy_has_positive_score(self):
        """单个策略也应有正分"""
        ranked = rrf_rank([
            {"id": "solo", "sharpe_ratio": 0.5, "total_return": 0.1,
             "win_rate": 0.45, "calmar_ratio": 0.3, "max_drawdown": -0.20}
        ])
        assert len(ranked) == 1
        assert ranked[0]["rrf_score"] > 0

    def test_missing_metric_fields(self):
        """缺失指标字段不应崩溃"""
        strategies = [
            {"id": "a", "sharpe_ratio": 1.0},  # 缺少其他字段
            {"id": "b", "win_rate": 0.6},  # 缺少其他字段
        ]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 2
        for s in ranked:
            assert "rrf_score" in s

    def test_nan_and_none_metrics(self):
        """NaN和None指标不应崩溃"""
        strategies = [
            {"id": "a", "sharpe_ratio": float("nan"), "total_return": None,
             "win_rate": 0.5, "calmar_ratio": 0.8, "max_drawdown": -0.15},
            {"id": "b", "sharpe_ratio": 1.0, "total_return": 0.2,
             "win_rate": None, "calmar_ratio": float("nan"), "max_drawdown": None},
        ]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 2
        for s in ranked:
            assert not math.isnan(s["rrf_score"])

    def test_large_number_of_strategies(self):
        """大量策略排名稳定性"""
        strategies = [
            {"id": f"s{i}", "sharpe_ratio": i * 0.1, "total_return": i * 0.01,
             "win_rate": 0.3 + i * 0.01, "calmar_ratio": i * 0.05,
             "max_drawdown": -0.05 - i * 0.01}
            for i in range(50)
        ]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 50
        # 最佳策略应排在前面（指标单调递增）
        assert ranked[0]["id"] == "s49"
        # score 应单调递减
        for i in range(len(ranked) - 1):
            assert ranked[i]["rrf_score"] >= ranked[i + 1]["rrf_score"]

    def test_custom_rank_keys(self):
        """自定义排名键"""
        strategies = [
            {"id": "a", "sharpe_ratio": 2.0, "custom_metric": 0.1},
            {"id": "b", "sharpe_ratio": 0.5, "custom_metric": 0.9},
        ]
        ranked = rrf_rank(strategies, rank_keys=["custom_metric"])
        assert ranked[0]["id"] == "b"  # custom_metric 高的排前面

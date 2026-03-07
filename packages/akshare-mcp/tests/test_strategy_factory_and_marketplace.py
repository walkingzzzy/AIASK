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
    EliminationChecker, StrategyFactoryScheduler, _auto_name,
    CATEGORY_MINIMUMS, REPRESENTATIVE_STOCKS,
)

# ── 排名引擎 ──

from akshare_mcp.services.ranking import rrf_rank

# ── 回测引擎 ──

from akshare_mcp.services.backtest.engine import BacktestEngine


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

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

    def test_fill_gaps_generates_varied_params(self):
        spawner = StrategySpawner()
        candidates = spawner._fill_gaps({"category_counts": {}})
        # 每个分类至少3个
        assert len(candidates) == sum(CATEGORY_MINIMUMS.values())
        first = candidates[0]
        assert first["generation_reason"]["kind"] == "quota_fill"
        assert first["generation_reason"]["source"] == "quota_fill"
        assert first["quota_fill"]["strategy_type"] == first["strategy_type"]
        assert first["quota_fill"]["minimum_required"] == CATEGORY_MINIMUMS[first["strategy_type"]]
        assert first["trigger_thresholds"][0]["field"] == f"category_counts.{first['strategy_type']}"
        # 同类型的参数不应完全相同
        momentum_params = [c["params"] for c in candidates if c["strategy_type"] == "momentum"]
        if len(momentum_params) >= 2:
            assert momentum_params[0] != momentum_params[1], "补位策略参数应有差异"

    def test_spawn_returns_nonempty(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 50, "fg_level": "neutral",
            "fg_components": {"volatility": 50},
            "factor_ic": {}, "factor_ic_trend": {},
            "north_fund_3d_net": 0, "margin_5d_change_pct": 0,
            "category_counts": {},
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
        assert report["summary"]["quota_fill_count"] > 0
        assert report["summary"]["signal_trigger_count"] > 0
        assert report["summary"]["threshold_hit_count"] >= len(candidates)
        assert report["summary"]["source_counts"]["quota_fill"] > 0
        assert report["summary"]["source_counts"]["fear_greed"] > 0
        assert report["summary"]["source_counts"]["factor_ic"] > 0


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
            AsyncMock(return_value={"similarity": 0.97, "backend": "index", "matched_strategy_id": "s1", "matched_name": "既有策略", "param_similarity": 0.72}),
        )
        unique = await dedup.deduplicate(candidates, db)
        assert unique == []
        report = dedup.get_last_report()
        assert report["summary"]["dropped_count"] == 1
        assert report["dropped"][0]["dedup_result"]["match_type"] == "vector"

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
            sm_mod,
            "_run_quality_gate",
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
        self._strategies = {}
        self._metrics = {}
        self._reviews = []
        self._subs = set()
        self._quality_reports = {}
        self._events = {}
        self._signal_stats = {}
        self._factory_runs = []
        self._daily_snapshots = []
        self._paper_accounts = {}
        self._paper_orders = []
        self._paper_nav = {}
        self._incubation_accounts = []
        self._incubation_metrics = []
        self._risk_events = []
        self._vector_profiles = []
        self._vector_indexes = []
        self._experiments = {}
        self._task_runs = []
        self._domain_events = []

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

    async def get_paper_account_by_strategy(self, strategy_id):
        for item in self._paper_accounts.values():
            if item.get('strategy_id') == strategy_id:
                return dict(item)
        return None

    async def save_paper_account(self, account):
        item = dict(account)
        self._paper_accounts[item['id']] = item
        return dict(item)

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

    async def list_strategy_paper_orders(self, strategy_id, signal_date=None):
        rows = [dict(item) for item in self._paper_orders if item.get('strategy_id') == strategy_id]
        if signal_date is not None:
            rows = [item for item in rows if str(item.get('signal_date')) == str(signal_date)]
        return rows

    async def save_paper_order(self, order):
        item = dict(order)
        item.setdefault('id', len(self._paper_orders) + 1)
        self._paper_orders.append(item)
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

    async def resolve_strategy_runtime_risk_event(self, event_id, resolution=None):
        for item in self._risk_events:
            if int(item.get('id')) == int(event_id):
                item['status'] = 'resolved'
                item['resolution'] = resolution or {}
                return dict(item)
        return None

    async def save_strategy_vector_profile(self, profile):
        item = {'id': len(self._vector_profiles) + 1, **dict(profile)}
        self._vector_profiles.append(item)
        return dict(item)

    async def list_strategy_vector_profiles(self, strategy_id=None, profile_type=None, limit=20):
        rows = list(self._vector_profiles)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if profile_type:
            rows = [row for row in rows if row.get('profile_type') == profile_type]
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

    async def save_strategy_generation_experiment(self, experiment):
        item = dict(experiment)
        self._experiments[item['experiment_id']] = item
        return dict(item)

    async def get_strategy_generation_experiment(self, experiment_id):
        item = self._experiments.get(experiment_id)
        return dict(item) if item else None

    async def list_strategy_generation_experiments(self, strategy_id=None, status=None, source=None, limit=20):
        rows = list(self._experiments.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
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

    async def list_strategy_task_runs(self, task_name=None, task_scope=None, status=None, limit=20):
        rows = list(self._task_runs)
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
            sm_mod,
            "_run_quality_gate",
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
            "summary": {"candidates_spawned": 2, "submitted": 1},
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
        assert run_resp["data"]["status"] == "success"
        assert runs_resp["data"]["count"] == 1
        assert runs_resp["data"]["items"][0]["run_id"] == "run_hist_1"
        assert detail_resp["data"]["run_id"] == "run_hist_1"
        assert snapshots_resp["data"]["count"] == 1
        assert snapshots_resp["data"]["items"][0]["snapshot_date"] == "2026-03-06"
        assert snapshot_resp["data"]["degraded"] is True
        assert snapshot_resp["data"]["completeness"]["completion_ratio"] == 0.67


    @pytest.mark.asyncio
    async def test_submit_binds_incubation_account(self, setup, monkeypatch):
        mcp, db = setup
        created = await mcp.strategy_manager(action="create", kwargs=json.dumps({
            "name": "AI提交策略", "strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02},
        }))
        sid = created["data"]["strategy_id"]

        monkeypatch.setattr(
            sm_mod,
            "_run_quality_gate",
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
                    "task_run_id": 1,
                    "generated_count": 2,
                    "candidates": [{"strategy_type": "momentum"}],
                    "experiments": [{"experiment_id": "exp_dummy_1"}],
                    "submitted": None,
                }

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
            lambda: _DummyAutonomy(),
        )

        resp = await mcp.strategy_manager(action="ai_generate", kwargs=json.dumps({"limit": 2}))
        assert resp["success"] is True
        assert resp["data"]["generated_count"] == 2
        assert resp["data"]["experiments"][0]["experiment_id"] == "exp_dummy_1"

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
        assert result['reviewed_count'] == 1
        assert result['rejected_count'] == 1
        assert any(item['decision'] in {'accept', 'reject', 'revise'} for item in result['committee_reviews'])
        experiments = await db.list_strategy_generation_experiments(limit=10)
        assert experiments[0]['evaluation']['committee_review']['decision'] in {'accept', 'revise'}


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
        domain_events = await db.list_strategy_domain_events(strategy_id='sid_risk', event_type='runtime_risk.actions_executed', limit=10)
        assert len(domain_events) == 1


class TestVectorGovernanceEnhancements:
    @pytest.mark.asyncio
    async def test_vector_rebuild_creates_task_run_and_registry(self, monkeypatch):
        from akshare_mcp.services.vector_governance import StrategyVectorGovernanceService

        db = _StrategyDB()
        await db.save_strategy({'id': 'sid_vec_1', 'name': '向量1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_vec_2', 'name': '向量2', 'strategy_type': 'momentum', 'status': 'incubating', 'params': {'lookback': 10}, 'factor_weights': {}})
        await db.save_vector_index_registry({'index_name': 'strategy_behavior', 'index_version': 'old_v1', 'status': 'active', 'metadata': {}})

        class _DummyVectorPlatform:
            async def build_profiles_for_strategies(self, db, strategies, profile_type='behavior', vector_method='price_volume', index_name='strategy_behavior', index_version='v1'):
                for idx, strategy in enumerate(strategies, 1):
                    await db.save_strategy_vector_profile({
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
                    })
                return {'count': len(strategies), 'items': strategies}

        monkeypatch.setattr('akshare_mcp.services.vector_platform.get_strategy_vector_platform', lambda: _DummyVectorPlatform())

        service = StrategyVectorGovernanceService()
        result = await service.rebuild_index(db, index_name='strategy_behavior', index_version='v2', statuses=['listed', 'incubating'], limit=10)

        assert result['task_run_id'] is not None
        assert result['built_profiles'] == 2
        indexes = await db.list_vector_index_registry(index_name='strategy_behavior', limit=10)
        assert any(item.get('index_version') == 'v2' for item in indexes)
        assert any(item.get('index_version') == 'old_v1' and item.get('status') == 'stale' for item in indexes)

class TestStrategyFactoryScheduler:
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
                return {"submitted": len(candidates), "passed_quality_gate": len(candidates), "strategies": []}

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
        assert saved_run["snapshot_summary"]["degraded"] is True
        assert saved_run["snapshot_summary"]["completion_ratio"] == 0.83
        assert saved_run["stages"]["spawn"]["count"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["candidate_count"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["source_counts"]["fear_greed"] == 2
        assert saved_run["stages"]["spawn"]["summary"]["threshold_hit_count"] == 2
        assert saved_run["stages"]["backtest"]["input_count"] == 2
        assert saved_run["stages"]["backtest"]["summary"]["failed_reason_counts"]["sharpe_below_threshold"] == 1
        assert saved_run["stages"]["backtest"]["summary"]["thresholds_by_type"]["momentum"]["sharpe_min"] == 0.35


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
        assert snapshot["sources"]["factor_ic"]["status"] == "partial"
        assert snapshot["degraded"] is True
        assert any(item["source"] == "factor_ic" for item in snapshot["failure_reasons"])
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

        with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread",
                   side_effect=Exception("network error")):
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

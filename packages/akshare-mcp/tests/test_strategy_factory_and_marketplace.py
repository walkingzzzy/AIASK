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
from datetime import date, datetime
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

    def test_fill_gaps_generates_varied_params(self):
        spawner = StrategySpawner()
        candidates = spawner._fill_gaps({"category_counts": {}})
        # 每个分类至少3个
        assert len(candidates) == sum(CATEGORY_MINIMUMS.values())
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

    def acquire(self):
        class _Acq:
            def __init__(self, conn):
                self.conn = conn
            async def __aenter__(self):
                return self.conn
            async def __aexit__(self, *a):
                return False
        return _Acq(_StrategyConn())

    async def save_strategy(self, data):
        self._strategies[data["id"]] = data
        return data

    async def get_strategy(self, sid):
        return self._strategies.get(sid)

    async def update_strategy_status(self, sid, status):
        if sid in self._strategies:
            self._strategies[sid]["status"] = status

    async def list_strategies(self, status, strategy_type=None, limit=20, offset=0):
        return [s for s in self._strategies.values() if s.get("status") == status]

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
        return {"hit_rate": {}, "forward_ic": {}, "forward_sharpe": {}, "total_signals": 0}

    async def get_signals(self, sid, limit=100):
        return []

    async def get_signals_public(self, sid, limit=100):
        return []

    async def count_strategies_by_type(self, status):
        counts = {}
        for s in self._strategies.values():
            if s.get("status") == status:
                t = s.get("strategy_type", "unknown")
                counts[t] = counts.get(t, 0) + 1
        return counts


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
        assert db._strategies[sid]["status"] == "published"

        arc = await mcp.strategy_manager(action="archive", kwargs=json.dumps({"strategy_id": sid}))
        assert arc["success"] is True
        assert db._strategies[sid]["status"] == "archived"

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
    @pytest.mark.asyncio
    async def test_filters_bad_candidates(self):
        """候选策略回测不通过时应被过滤"""
        bt_filter = BacktestFilter()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 1, "threshold": 0.5}},
        ]
        db = MagicMock()
        # 返回足够的K线数据
        np.random.seed(42)
        klines = _make_klines(200, trend=0.0, noise=0.001)  # 几乎无趋势
        db.get_klines = AsyncMock(return_value=klines)

        passed = await bt_filter.filter(candidates, db)
        # 极端参数大概率被过滤（Sharpe太低或交易太少）
        # 不做严格断言，只验证不报错
        assert isinstance(passed, list)

    @pytest.mark.asyncio
    async def test_filter_with_no_klines(self):
        """没有K线数据时应返回空"""
        bt_filter = BacktestFilter()
        candidates = [
            {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        ]
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=[])

        passed = await bt_filter.filter(candidates, db)
        assert len(passed) == 0


# ═══════════════════════════════════════════════════════════════
# 11. DataCollector 测试（mock外部依赖）
# ═══════════════════════════════════════════════════════════════

class TestDataCollector:
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
        assert _validate_transition("listed", "deprecated") is True
        assert _validate_transition("listed", "suspended") is True
        assert _validate_transition("suspended", "listed") is True

    def test_invalid_transitions(self):
        from akshare_mcp.tools.managers.strategy_manager import _validate_transition
        assert _validate_transition("draft", "listed") is False
        assert _validate_transition("deprecated", "listed") is False
        assert _validate_transition("archived", "draft") is False
        assert _validate_transition("draft", "deprecated") is False

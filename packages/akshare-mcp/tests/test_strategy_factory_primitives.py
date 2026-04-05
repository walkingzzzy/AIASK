"""拆分自 test_strategy_factory_and_marketplace 的基础策略工厂测试。"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from akshare_mcp.services.backtest.builtin_strategies import (
    BuyAndHoldStrategy,
    MaCrossStrategy,
    MomentumStrategy,
    RsiStrategy,
)
from akshare_mcp.services.backtest.engine import BacktestEngine
from akshare_mcp.services.backtest.macro_timing_strategy import MacroTimingStrategy
from akshare_mcp.services.backtest.multi_factor_strategy import MultiFactorStrategy
from akshare_mcp.services.backtest.single_factor_strategy import (
    GrowthFactorStrategy,
    QualityFactorStrategy,
    ValueFactorStrategy,
)
from akshare_mcp.services.backtest.strategy_base import IStrategy
from akshare_mcp.services.backtest.strategy_registry import StrategyRegistry
from akshare_mcp.services.ranking import rrf_rank
from akshare_mcp.storage.timescaledb.artifacts import ArtifactMixin
from akshare_mcp.storage.timescaledb.strategy import StrategyMixin

from ._strategy_factory_marketplace_helpers import _closes_from_klines, _make_klines, _volumes_from_klines


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


class TestStrategyRegistry:
    def test_all_factory_strategies_registered(self):
        names = StrategyRegistry.list_all()
        expected = {
            "ma_cross",
            "momentum",
            "rsi",
            "buy_and_hold",
            "value_factor",
            "quality_factor",
            "growth_factor",
            "multi_factor",
            "macro_timing",
            "volatility_breakout",
            "gap_fill",
            "mean_reversion_short",
            "sector_rotation",
            "north_capital_track",
            "margin_divergence",
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


class TestSignalGeneration:
    """测试所有扩展策略的信号生成"""

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

    @pytest.mark.parametrize(
        "name",
        [
            "ma_cross",
            "momentum",
            "rsi",
            "buy_and_hold",
            "value_factor",
            "quality_factor",
            "growth_factor",
            "multi_factor",
            "macro_timing",
            "volatility_breakout",
            "gap_fill",
            "mean_reversion_short",
            "sector_rotation",
            "north_capital_track",
            "margin_divergence",
        ],
    )
    def test_signal_shape_and_values(self, name, closes, volumes):
        klass = StrategyRegistry.get(name)
        inst = klass()
        signals = inst.generate_signals(closes, volumes)
        assert len(signals) == len(closes), f"{name}: signal length mismatch"
        unique = set(signals.tolist())
        assert unique.issubset({-1, 0, 1}), f"{name}: invalid signal values {unique}"

    @pytest.mark.parametrize(
        "name",
        [
            "ma_cross",
            "momentum",
            "rsi",
            "value_factor",
            "quality_factor",
            "growth_factor",
            "multi_factor",
            "macro_timing",
            "volatility_breakout",
            "gap_fill",
            "mean_reversion_short",
            "sector_rotation",
            "north_capital_track",
            "margin_divergence",
        ],
    )
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


class TestBacktestEngineRegistryFallback:
    """测试新策略通过 StrategyRegistry 回退在 BacktestEngine 中运行"""

    @pytest.fixture
    def klines(self):
        np.random.seed(42)
        return _make_klines(300)

    @pytest.mark.parametrize(
        "strategy",
        [
            "value_factor",
            "quality_factor",
            "growth_factor",
            "multi_factor",
            "macro_timing",
            "volatility_breakout",
            "gap_fill",
            "mean_reversion_short",
            "sector_rotation",
            "north_capital_track",
            "margin_divergence",
        ],
    )
    def test_new_strategies_run_through_engine(self, strategy, klines):
        result = BacktestEngine.run_backtest(
            "600519",
            klines,
            strategy,
            {
                "initial_capital": 100000,
                "commission": 0.00025,
            },
        )
        assert result["success"] is True, f"{strategy}: {result.get('error')}"
        data = result["data"]
        assert "sharpe_ratio" in data
        assert "total_return" in data
        assert "max_drawdown" in data
        assert data["trades_count"] >= 0

    def test_unknown_strategy_fails(self):
        klines = _make_klines(100)
        result = BacktestEngine.run_backtest(
            "600519",
            klines,
            "totally_fake_strategy",
            {},
        )
        assert result["success"] is False
        assert "Unknown strategy" in result["error"]


class TestRRFRanking:
    def test_basic_ranking(self):
        strategies = [
            {"id": "a", "sharpe_ratio": 2.0, "total_return": 0.3, "win_rate": 0.6, "calmar_ratio": 1.5, "max_drawdown": -0.10},
            {"id": "b", "sharpe_ratio": 0.5, "total_return": 0.1, "win_rate": 0.4, "calmar_ratio": 0.3, "max_drawdown": -0.30},
            {"id": "c", "sharpe_ratio": 1.0, "total_return": 0.2, "win_rate": 0.5, "calmar_ratio": 0.8, "max_drawdown": -0.20},
        ]
        ranked = rrf_rank(strategies)
        assert ranked[0]["id"] == "a"
        assert ranked[-1]["id"] == "b"
        for strategy in ranked:
            assert "rrf_score" in strategy

    def test_empty_list(self):
        assert rrf_rank([]) == []

    def test_single_strategy(self):
        strategies = [
            {"id": "x", "sharpe_ratio": 1.0, "total_return": 0.1, "win_rate": 0.5, "calmar_ratio": 0.5, "max_drawdown": -0.15}
        ]
        ranked = rrf_rank(strategies)
        assert len(ranked) == 1
        assert ranked[0]["rrf_score"] > 0

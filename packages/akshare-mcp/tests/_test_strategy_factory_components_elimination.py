from __future__ import annotations

from ._test_strategy_factory_components_support import *

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

__all__ = [name for name in globals() if name.startswith("Test")]

from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

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

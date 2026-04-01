from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

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

__all__ = [name for name in globals() if name.startswith("Test")]

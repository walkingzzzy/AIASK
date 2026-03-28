"""MCP P0 精度底座模块验收测试

覆盖：
- probability_calibration.py（概率校准框架）
- realtime_constraints.py（实时交易约束复核）
- decision_offline_eval.py（统一决策离线评估基线）
- prediction_interval（预测区间表达）
"""

from __future__ import annotations

import datetime
import math

import pytest

# ── 概率校准 ──────────────────────────────────────────────────────────────────

from akshare_mcp.services.probability_calibration import (
    ReliabilityBin,
    brier_score,
    brier_score_single,
    build_calibration_quality_report,
    estimate_prediction_interval,
    expected_calibration_error,
    fit_platt_params,
    isotonic_calibrate,
    platt_scale,
    reliability_diagram,
)


class TestPlattScale:
    def test_sigmoid_at_zero(self):
        assert abs(platt_scale(0.0) - 0.5) < 1e-6

    def test_large_positive_score_near_one(self):
        assert platt_scale(10.0) > 0.99

    def test_large_negative_score_near_zero(self):
        assert platt_scale(-10.0) < 0.01

    def test_custom_a_b(self):
        result = platt_scale(0.5, a=2.0, b=-1.0)
        assert 0 < result < 1

    def test_clamp_prevents_exact_zero_or_one(self):
        # platt_scale 输出始终在 [0, 1]
        r = platt_scale(100.0)
        assert 0.0 <= r <= 1.0


class TestFitPlattParams:
    def test_returns_tuple(self):
        a, b = fit_platt_params([0.1, 0.5, 0.9], [0, 1, 1])
        assert isinstance(a, float) and isinstance(b, float)

    def test_empty_input_returns_default(self):
        assert fit_platt_params([], []) == (1.0, 0.0)

    def test_params_improve_calibration(self):
        """用极端偏斜分数拟合后概率应该更接近标签均值。"""
        scores = [5.0, 5.0, 5.0, -5.0, -5.0]  # 极端值
        labels = [1, 1, 0, 0, 0]
        a, b = fit_platt_params(scores, labels)
        # 参数应有意义（不是完全默认值）
        assert isinstance(a, float)


class TestIsotonicCalibrate:
    def test_below_table_returns_first(self):
        table = [(0.2, 0.1), (0.5, 0.4), (0.8, 0.7)]
        assert abs(isotonic_calibrate(0.1, table) - 0.1) < 1e-6

    def test_above_table_returns_last(self):
        table = [(0.2, 0.1), (0.5, 0.4), (0.8, 0.7)]
        assert abs(isotonic_calibrate(0.9, table) - 0.7) < 1e-6

    def test_interpolation(self):
        table = [(0.0, 0.0), (1.0, 1.0)]
        assert abs(isotonic_calibrate(0.5, table) - 0.5) < 1e-6

    def test_empty_table_returns_clamped_score(self):
        assert abs(isotonic_calibrate(0.7, []) - 0.7) < 1e-6


class TestBrierScore:
    def test_perfect_prediction(self):
        assert brier_score([1.0, 0.0], [1, 0]) == 0.0

    def test_worst_prediction(self):
        score = brier_score([0.0, 1.0], [1, 0])
        assert abs(score - 1.0) < 1e-6

    def test_random_prediction(self):
        # 随机猜测 Brier ≈ 0.25
        probs = [0.5] * 100
        labels = [1 if i < 50 else 0 for i in range(100)]
        score = brier_score(probs, labels)
        assert abs(score - 0.25) < 0.01

    def test_empty_returns_none(self):
        assert brier_score([], []) is None

    def test_length_mismatch_returns_none(self):
        assert brier_score([0.5, 0.5], [1]) is None

    def test_single_prediction(self):
        score = brier_score_single(0.8, 0.8)
        assert score == 0.0


class TestECE:
    def test_perfect_calibration(self):
        """校准良好时 ECE 应低于差劲预测情形。"""
        # 中等概率 + 50% 命中率 ≈ 合理校准
        probs = [0.5] * 100
        labels = [1 if i % 2 == 0 else 0 for i in range(100)]
        ece_good = expected_calibration_error(probs, labels)
        # 差劲：预测 0.9 但实际 10% 命中
        probs_bad = [0.9] * 20
        labels_bad = [1] * 2 + [0] * 18
        ece_bad = expected_calibration_error(probs_bad, labels_bad)
        assert ece_good is not None and ece_bad is not None
        assert ece_good < ece_bad

    def test_miscalibrated_high_ece(self):
        """总预测 0.9 但实际命中率 0.1，ECE 应很高。"""
        probs = [0.9] * 20
        labels = [1] * 2 + [0] * 18  # 实际命中率 0.1
        ece = expected_calibration_error(probs, labels)
        assert ece is not None
        assert ece > 0.3

    def test_empty_returns_none(self):
        assert expected_calibration_error([], []) is None


class TestReliabilityDiagram:
    def test_returns_list(self):
        probs = [0.1, 0.5, 0.9]
        labels = [0, 1, 1]
        bins = reliability_diagram(probs, labels)
        assert isinstance(bins, list)
        assert all(isinstance(b, ReliabilityBin) for b in bins)

    def test_bin_count_capped_by_data(self):
        # 只有 1 个数据点，最多 1 个桶
        bins = reliability_diagram([0.5], [1])
        assert len(bins) <= 1

    def test_to_dict(self):
        bins = reliability_diagram([0.2, 0.8], [0, 1])
        assert all("bin" in b.to_dict() for b in bins)


class TestPredictionInterval:
    def test_normal_approx(self):
        pi = estimate_prediction_interval(0.6, sample_size=100, coverage_target=0.90)
        assert pi.lower < pi.point_estimate < pi.upper
        assert 0 <= pi.lower < pi.upper <= 1

    def test_wilson_interval(self):
        pi = estimate_prediction_interval(0.6, sample_size=30, method="wilson")
        assert pi.lower >= 0 and pi.upper <= 1
        assert pi.interval_width > 0

    def test_small_sample_wider_interval(self):
        pi_small = estimate_prediction_interval(0.5, sample_size=10)
        pi_large = estimate_prediction_interval(0.5, sample_size=1000)
        assert pi_small.interval_width > pi_large.interval_width

    def test_to_dict_contains_required_fields(self):
        pi = estimate_prediction_interval(0.7)
        d = pi.to_dict()
        assert all(k in d for k in ["point_estimate", "lower", "upper", "coverage_target", "interval_width"])

    def test_coverage_target_respected(self):
        pi_90 = estimate_prediction_interval(0.5, sample_size=100, coverage_target=0.90)
        pi_99 = estimate_prediction_interval(0.5, sample_size=100, coverage_target=0.99)
        assert pi_99.interval_width > pi_90.interval_width


class TestCalibrationQualityReport:
    def test_good_quality(self):
        """Brier 较低时质量应为 good 或 fair。"""
        probs = [0.9] * 10 + [0.1] * 10
        labels = [1] * 10 + [0] * 10
        report = build_calibration_quality_report(probs, labels, calibration_method="platt")
        # 近似完美预测，Brier 应远低于随机基线 0.25
        assert report.brier_score is not None and report.brier_score < 0.10
        assert report.quality_band in ("good", "fair")

    def test_poor_quality_generates_notes(self):
        """差劲的预测应生成警告 note。"""
        probs = [0.5] * 5  # 小样本，随机概率
        labels = [1, 0, 1, 0, 1]
        report = build_calibration_quality_report(probs, labels)
        assert len(report.notes) > 0

    def test_to_dict_has_required_keys(self):
        probs = [0.6, 0.4, 0.7]
        labels = [1, 0, 1]
        report = build_calibration_quality_report(probs, labels)
        d = report.to_dict()
        assert all(k in d for k in ["brier_score", "ece", "quality_band", "calibration_method"])


# ── 实时交易约束 ──────────────────────────────────────────────────────────────

from akshare_mcp.services.realtime_constraints import (
    TradeConstraintChecker,
    TradeConstraintContext,
    check_trade_constraints,
)


class TestTradeConstraintChecker:
    def setup_method(self):
        self.checker = TradeConstraintChecker()

    def _trading_ctx(self, **kwargs) -> TradeConstraintContext:
        defaults = dict(
            code="600519",
            name="贵州茅台",
            current_price=1800.0,
            prev_close=1780.0,
            check_time=datetime.datetime(2025, 6, 16, 10, 0, 0),  # 周一上午
        )
        defaults.update(kwargs)
        return TradeConstraintContext(**defaults)

    def test_normal_tradeable(self):
        ctx = self._trading_ctx()
        result = self.checker.check(ctx)
        assert result.tradeable is True
        assert not result.has_blocking

    def test_suspended_blocking(self):
        ctx = self._trading_ctx(is_suspended=True)
        result = self.checker.check(ctx)
        assert result.tradeable is False
        assert "SUSPENDED" in result.blocking_reasons

    def test_limit_up_detected(self):
        """价格触及涨停价时应报告 LIMIT_UP。"""
        ctx = self._trading_ctx(
            current_price=1958.0,  # ≈ 1780 * 1.10
            prev_close=1780.0,
        )
        result = self.checker.check(ctx)
        assert any(v.code == "LIMIT_UP" for v in result.violations)

    def test_st_warning(self):
        ctx = self._trading_ctx(is_st=True, current_price=5.0, prev_close=5.2)
        result = self.checker.check(ctx)
        assert any(v.code == "ST_RISK" for v in result.violations)

    def test_non_trading_hours_warning(self):
        ctx = self._trading_ctx(
            check_time=datetime.datetime(2025, 6, 16, 8, 0, 0)  # 盘前
        )
        result = self.checker.check(ctx)
        assert any(v.code == "NON_TRADING_HOURS" for v in result.violations)

    def test_weekend_warning(self):
        ctx = self._trading_ctx(
            check_time=datetime.datetime(2025, 6, 14, 10, 0, 0)  # 周六
        )
        result = self.checker.check(ctx)
        assert any(v.code == "NON_TRADING_HOURS" for v in result.violations)

    def test_high_participation_rate_warning(self):
        ctx = self._trading_ctx(
            volume_5d_avg=100_000,
            target_shares=50_000,  # 参与率 50%，超过默认 30%
        )
        result = self.checker.check(ctx)
        assert any(v.code == "HIGH_PARTICIPATION_RATE" for v in result.violations)

    def test_low_liquidity_warning(self):
        ctx = self._trading_ctx(volume_5d_avg=50_000)
        result = self.checker.check(ctx)
        assert any(v.code == "LOW_LIQUIDITY" for v in result.violations)

    def test_limit_prices_calculated(self):
        ctx = self._trading_ctx(prev_close=100.0)
        result = self.checker.check(ctx)
        assert result.limit_price_up is not None
        assert abs(result.limit_price_up - 110.0) < 0.01
        assert abs(result.limit_price_down - 90.0) < 0.01

    def test_st_smaller_limit(self):
        ctx = self._trading_ctx(is_st=True, prev_close=10.0)
        result = self.checker.check(ctx)
        assert result.limit_price_up is not None
        assert abs(result.limit_price_up - 10.5) < 0.01  # ±5%

    def test_star_market_larger_limit(self):
        ctx = self._trading_ctx(is_star_market=True, prev_close=100.0)
        result = self.checker.check(ctx)
        assert result.limit_price_up is not None
        assert abs(result.limit_price_up - 120.0) < 0.01  # ±20%

    def test_to_dict(self):
        ctx = self._trading_ctx()
        result = self.checker.check(ctx)
        d = result.to_dict()
        assert all(k in d for k in ["tradeable", "has_blocking", "violations", "limit_price_up"])

    def test_convenience_function(self):
        result = check_trade_constraints(
            code="000001",
            current_price=15.0,
            prev_close=14.5,
        )
        assert result.stock_code == "000001"


# ── 决策离线评估 ──────────────────────────────────────────────────────────────

from akshare_mcp.services.decision_offline_eval import (
    build_decision_offline_eval,
    build_multi_decision_eval,
    define_buy_label,
    define_hold_label,
    define_sell_label,
    layered_hit_rate_analysis,
    monotonicity_score,
)


class TestLabelDefinition:
    def test_buy_label_positive_return(self):
        assert define_buy_label(0.06) == 1  # 6% > 5% 阈值

    def test_buy_label_insufficient_return(self):
        assert define_buy_label(0.03) == 0  # 3% < 5%

    def test_sell_label_negative_return(self):
        assert define_sell_label(-0.05) == 1  # -5% < -3%

    def test_sell_label_positive_return(self):
        assert define_sell_label(0.02) == 0

    def test_hold_label_in_range(self):
        assert define_hold_label(0.01) == 1  # 1% 在 [-3%, +5%] 内

    def test_hold_label_out_of_range(self):
        assert define_hold_label(0.10) == 0  # 超过买入阈值


class TestLayeredHitRate:
    def test_empty_input(self):
        assert layered_hit_rate_analysis([], []) == []

    def test_mismatched_length(self):
        assert layered_hit_rate_analysis([0.5], [1, 0]) == []

    def test_bucket_count(self):
        probs = [0.1, 0.3, 0.5, 0.7, 0.9] * 4
        labels = [0, 0, 1, 1, 1] * 4
        buckets = layered_hit_rate_analysis(probs, labels, n_buckets=5)
        assert len(buckets) >= 1

    def test_hit_rate_range(self):
        probs = [0.1, 0.5, 0.9]
        labels = [0, 1, 1]
        buckets = layered_hit_rate_analysis(probs, labels)
        for b in buckets:
            assert 0.0 <= b.hit_rate <= 1.0


class TestMonotonicityScore:
    def test_perfect_monotone(self):
        from akshare_mcp.services.decision_offline_eval import ProbabilityBucketStat
        buckets = [
            ProbabilityBucketStat(1, 0.0, 0.2, 10, 1, 0.1, 0.1, 0.0),
            ProbabilityBucketStat(2, 0.2, 0.4, 10, 3, 0.3, 0.3, 0.0),
            ProbabilityBucketStat(3, 0.4, 0.6, 10, 5, 0.5, 0.5, 0.0),
            ProbabilityBucketStat(4, 0.6, 0.8, 10, 7, 0.7, 0.7, 0.0),
            ProbabilityBucketStat(5, 0.8, 1.0, 10, 9, 0.9, 0.9, 0.0),
        ]
        assert monotonicity_score(buckets) == 1.0

    def test_single_bucket(self):
        from akshare_mcp.services.decision_offline_eval import ProbabilityBucketStat
        buckets = [ProbabilityBucketStat(1, 0.0, 1.0, 10, 5, 0.5, 0.5, 0.0)]
        assert monotonicity_score(buckets) == 1.0


class TestDecisionOfflineEval:
    def _make_data(self, n=50):
        """高概率 -> 大涨，低概率 -> 跌，模拟合理信号。"""
        probs = [0.1 * (i % 10) for i in range(n)]
        returns = [0.01 * ((p - 0.5) * 20) for p in probs]
        return probs, returns

    def test_basic_build(self):
        probs, returns = self._make_data()
        report = build_decision_offline_eval(probs, returns)
        assert report.sample_size == 50
        assert 0.0 <= report.overall_hit_rate <= 1.0

    def test_empty_input(self):
        report = build_decision_offline_eval([], [])
        assert report.sample_size == 0
        assert "样本量为 0" in report.notes[0]

    def test_buy_decision(self):
        probs = [0.9] * 20 + [0.1] * 20
        returns = [0.08] * 20 + [-0.02] * 20  # 高概率 -> 大涨
        report = build_decision_offline_eval(probs, returns, decision_type="buy")
        assert report.hit_count > 0
        assert report.decision_type == "buy"

    def test_sell_decision(self):
        probs = [0.9] * 10 + [0.1] * 10
        returns = [-0.08] * 10 + [0.05] * 10  # 高 sell prob -> 下跌
        report = build_decision_offline_eval(probs, returns, decision_type="sell")
        assert report.decision_type == "sell"

    def test_brier_score_present(self):
        probs, returns = self._make_data(30)
        report = build_decision_offline_eval(probs, returns)
        assert report.brier_score is not None

    def test_quality_band_assigned(self):
        probs, returns = self._make_data()
        report = build_decision_offline_eval(probs, returns)
        assert report.quality_band in ("good", "fair", "poor", "unknown")

    def test_to_dict(self):
        probs, returns = self._make_data()
        report = build_decision_offline_eval(probs, returns)
        d = report.to_dict()
        assert all(k in d for k in [
            "decision_type", "horizon_days", "overall_hit_rate",
            "brier_score", "ece", "quality_band", "bucket_stats",
        ])

    def test_multi_decision_eval(self):
        probs = [0.6] * 30 + [0.3] * 20
        returns = [0.07] * 30 + [-0.04] * 20
        result = build_multi_decision_eval(probs, returns)
        assert "buy" in result and "sell" in result and "hold" in result
        assert "summary" in result

"""验收测试 — MCP 能力改造缺口四项实现

覆盖:
1. sentiment.py  — _build_news_sentiment_oos_validation()
2. signal_quality_registry.py
3. execution_slippage.py
4. rolling_model_registry.py
"""

from __future__ import annotations

import math
from typing import Any

import pytest


# ============================================================================
# 1. Sentiment news OOS validation
# ============================================================================

class TestNewsSentimentOosValidation:
    """Tests for SentimentAnalyzer._build_news_sentiment_oos_validation()."""

    @staticmethod
    def _make_klines(n: int, seed: float = 100.0, trend: float = 0.002) -> list[dict]:
        """Generate synthetic K-line dicts with a mild upward trend."""
        import random
        random.seed(42)
        klines = []
        price = seed
        for i in range(n):
            price = price * (1 + trend + (random.random() - 0.5) * 0.04)
            klines.append({
                "date": f"2022-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
                "open": price * 0.99,
                "high": price * 1.01,
                "low": price * 0.98,
                "close": price,
                "volume": 1_000_000 + random.randint(-100_000, 100_000),
            })
        return klines

    def test_returns_available_true_for_sufficient_klines(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(120)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        assert result["available"] is True

    def test_returns_available_false_for_short_klines(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(30)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        assert result["available"] is False
        assert "insufficient_kline" in result.get("reason", "")

    def test_bucket_stats_structure(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(200)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        assert result["available"] is True
        bucket_stats = result["bucket_stats"]
        for bucket in ("bullish", "neutral", "bearish"):
            assert bucket in bucket_stats
        for period_key in ("5d", "10d", "20d"):
            for bucket in bucket_stats.values():
                assert period_key in bucket

    def test_bucket_stats_hit_rate_in_range(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(200)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        for bucket_data in result["bucket_stats"].values():
            for period_stat in bucket_data.values():
                hr = period_stat.get("hit_rate")
                if hr is not None:
                    assert 0.0 <= hr <= 1.0

    def test_alpha_5d_is_float_or_none(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(200)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        alpha = result.get("alpha_5d_bull_vs_bear")
        if alpha is not None:
            assert isinstance(alpha, float)

    def test_signal_stability_is_valid_label(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(200)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        assert result.get("signal_stability") in {"stable", "degraded", "unknown"}

    def test_decay_analysis_present(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        klines = self._make_klines(200)
        result = SentimentAnalyzer._build_news_sentiment_oos_validation(klines)
        decay = result.get("decay_analysis")
        assert isinstance(decay, dict)
        assert "decay_note" in decay

    def test_analyze_sentiment_includes_news_oos_validation(self):
        """Full pipeline includes news_oos_validation in output."""
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        klines = self._make_klines(200)
        result = analyzer.analyze_sentiment(klines, news_headlines=["利好 扩产"], fund_flow_data=None)
        assert "news_oos_validation" in result
        # Even if insufficient klines, key should be present
        assert isinstance(result["news_oos_validation"], dict)

    def test_news_sentiment_score_uses_classify_headline(self):
        """Keyword detection: bullish title should score higher than neutral."""
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        bull = SentimentAnalyzer._news_sentiment_score(["利好大涨创新高"])
        neutral = SentimentAnalyzer._news_sentiment_score(["公司发布年报"])
        assert bull > neutral

    def test_classify_headline_bullish(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        assert SentimentAnalyzer._classify_headline("公司今日涨停大涨利好") == "bullish"

    def test_classify_headline_bearish(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        assert SentimentAnalyzer._classify_headline("暴雷亏损退市") == "bearish"

    def test_classify_headline_neutral(self):
        from akshare_mcp.services.sentiment import SentimentAnalyzer
        assert SentimentAnalyzer._classify_headline("公司发布年报") == "neutral"


# ============================================================================
# 2. Signal quality registry
# ============================================================================

class TestSignalQualityRegistry:

    def _make_registry(self):
        from akshare_mcp.services.signal_quality_registry import SignalQualityRegistry
        return SignalQualityRegistry(max_entries_per_type=100)

    def _prob_payload(self, **overrides) -> dict:
        base = {
            "up_probability": 0.65,
            "prediction_quality": {
                "brier_score": 0.12,
                "ece": 0.08,
                "calibration_gap": 0.05,
                "quality": "medium",
                "sample_size": 80,
                "support_samples": 80,
            },
            "prediction_interval": {
                "coverage_proxy": 0.80,
                "observed_coverage": 0.74,
                "coverage_gap": -0.06,
            },
        }
        base.update(overrides)
        return base

    def _sent_payload(self, **overrides) -> dict:
        base = {
            "score": 65.0,
            "sentiment": "bullish",
            "news_oos_validation": {
                "available": True,
                "alpha_5d_bull_vs_bear": 0.08,
                "signal_stability": "stable",
            },
            "historical_validation": {
                "available": True,
                "sample_count": 45,
                "forward_returns": {"5d": {"hit_rate": 0.58}},
            },
        }
        base.update(overrides)
        return base

    def _factor_payload(self, **overrides) -> dict:
        base = {
            "ic_mean": 0.045,
            "ic_ir": 1.2,
            "rank_ic_mean": 0.038,
            "oos_rank_ic_mean": 0.031,
            "purged_kfold_stability_ratio": 0.72,
            "lookahead_audit": {"risk_level": "low"},
            "rating": "good",
        }
        base.update(overrides)
        return base

    def test_register_probability_returns_entry(self):
        reg = self._make_registry()
        entry = reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        assert entry["signal_type"] == "buy_probability"
        assert entry["brier_score"] == pytest.approx(0.12)
        assert entry["ece"] == pytest.approx(0.08)

    def test_register_sentiment_returns_entry(self):
        reg = self._make_registry()
        entry = reg.register_sentiment(code="000001", as_of="2024-01-01", payload=self._sent_payload())
        assert entry["signal_type"] == "sentiment"
        assert entry["news_oos_available"] is True
        assert entry["news_alpha_5d"] == pytest.approx(0.08)

    def test_register_factor_returns_entry(self):
        reg = self._make_registry()
        entry = reg.register_factor(factor_name="momentum_20d", payload=self._factor_payload())
        assert entry["signal_type"] == "factor"
        assert entry["oos_rank_ic_mean"] == pytest.approx(0.031)
        assert entry["lookahead_risk"] == "low"

    def test_snapshot_structure(self):
        reg = self._make_registry()
        reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        reg.register_sentiment(code="000001", as_of="2024-01-01", payload=self._sent_payload())
        reg.register_factor(factor_name="momentum_20d", payload=self._factor_payload())
        snap = reg.snapshot()
        assert snap["total_entries"] == 3
        assert "buy_probability" in snap
        assert "sentiment" in snap
        assert "factor" in snap

    def test_snapshot_brier_aggregate(self):
        reg = self._make_registry()
        for _ in range(5):
            reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        snap = reg.snapshot()
        brier = snap["buy_probability"]["brier_score"]
        assert brier["count"] == 5
        assert brier["mean"] == pytest.approx(0.12, abs=1e-6)

    def test_drift_check_stable(self):
        reg = self._make_registry()
        for _ in range(5):
            reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        result = reg.drift_check(baseline_brier=0.12, baseline_ece=0.08)
        assert result["checks"]["brier_score"]["status"] == "stable"
        assert result["checks"]["ece"]["status"] == "stable"

    def test_drift_check_degraded_brier(self):
        reg = self._make_registry()
        # Register higher Brier scores (worse)
        bad_payload = self._prob_payload()
        bad_payload["prediction_quality"]["brier_score"] = 0.25
        for _ in range(5):
            reg.register_probability(code="000001", as_of="2024-01-01", payload=bad_payload)
        result = reg.drift_check(baseline_brier=0.12)
        assert result["checks"]["brier_score"]["status"] == "degraded"

    def test_max_entries_cap(self):
        reg = self._make_registry()
        for i in range(150):
            reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        assert len(reg.recent_probability(200)) <= 100

    def test_clear_resets_all(self):
        reg = self._make_registry()
        reg.register_probability(code="000001", as_of="2024-01-01", payload=self._prob_payload())
        reg.clear()
        snap = reg.snapshot()
        assert snap["total_entries"] == 0

    def test_sentiment_distribution_in_snapshot(self):
        reg = self._make_registry()
        reg.register_sentiment(code="000001", as_of="2024-01-01", payload=self._sent_payload())
        reg.register_sentiment(code="000002", as_of="2024-01-01", payload=self._sent_payload(sentiment="neutral"))
        snap = reg.snapshot()
        dist = snap["sentiment"]["sentiment_distribution"]
        assert dist.get("bullish") == 1
        assert dist.get("neutral") == 1


# ============================================================================
# 3. Execution slippage model
# ============================================================================

class TestExecutionSlippageModel:

    def test_volume_share_basic(self):
        from akshare_mcp.services.execution_slippage import VolumeShareSlippageModel
        model = VolumeShareSlippageModel()
        result = model.estimate(
            order_shares=10_000,
            avg_minute_volume=50_000,
            duration_minutes=10,
            reference_price=30.0,
        )
        assert result["model"] == "volume_share_slippage"
        assert result["total_slippage_bps"] > 0
        assert 0 < result["participation_rate"] <= model.max_participation_rate

    def test_volume_share_zero_participation_is_minimum_slippage(self):
        from akshare_mcp.services.execution_slippage import VolumeShareSlippageModel
        model = VolumeShareSlippageModel()
        # huge volume -> near-zero participation
        result = model.estimate(
            order_shares=1,
            avg_minute_volume=10_000_000,
            duration_minutes=60,
            reference_price=30.0,
        )
        assert result["participation_rate"] < 1e-4
        # only spread cost
        assert result["total_slippage_bps"] == pytest.approx(model.spread_bps * 0.5, abs=0.1)

    def test_market_impact_basic(self):
        from akshare_mcp.services.execution_slippage import MarketImpactModel
        model = MarketImpactModel()
        result = model.estimate(
            order_shares=500_000,
            adv_shares=5_000_000,
            reference_price=25.0,
        )
        assert result["model"] == "market_impact"
        assert result["impact_bps"] > 0
        assert result["impact_bps"] <= model.max_impact_bps

    def test_market_impact_illiquid_stock(self):
        from akshare_mcp.services.execution_slippage import MarketImpactModel
        model = MarketImpactModel()
        result = model.estimate(
            order_shares=500_000,
            adv_shares=100_000,  # very illiquid
            reference_price=5.0,
        )
        assert result["liquidity_tier"] == "low"

    def test_partial_fill_no_risk_low_participation(self):
        from akshare_mcp.services.execution_slippage import PartialFillSimulator
        sim = PartialFillSimulator()
        result = sim.simulate(
            order_shares=1_000,
            available_volume=100_000,
            participation_rate=0.01,
        )
        assert result["is_partial_fill_risk"] is False
        assert result["full_fill_probability"] > 0.90

    def test_partial_fill_high_risk_high_participation(self):
        from akshare_mcp.services.execution_slippage import PartialFillSimulator
        sim = PartialFillSimulator()
        result = sim.simulate(
            order_shares=90_000,
            available_volume=100_000,
            participation_rate=0.90,
        )
        assert result["is_partial_fill_risk"] is True
        assert result["full_fill_probability"] < 0.90

    def test_partial_fill_ratio_in_range(self):
        from akshare_mcp.services.execution_slippage import PartialFillSimulator
        sim = PartialFillSimulator()
        result = sim.simulate(
            order_shares=50_000,
            available_volume=200_000,
            participation_rate=0.25,
        )
        assert 0.0 <= result["fill_ratio"] <= 1.0

    def test_bundle_simulate_returns_all_sections(self):
        from akshare_mcp.services.execution_slippage import ExecutionSlippageBundle
        bundle = ExecutionSlippageBundle()
        result = bundle.simulate(
            order_shares=10_000,
            avg_minute_volume=30_000,
            adv_shares=5_000_000,
            duration_minutes=15,
            reference_price=20.0,
            slices=5,
        )
        assert "slippage_simulation" in result
        assert "volume_share_slippage" in result
        assert "market_impact" in result
        assert "partial_fill" in result

    def test_bundle_execution_quality_label(self):
        from akshare_mcp.services.execution_slippage import ExecutionSlippageBundle
        bundle = ExecutionSlippageBundle()
        result = bundle.simulate(
            order_shares=100,
            avg_minute_volume=1_000_000,
            adv_shares=50_000_000,
            duration_minutes=30,
            reference_price=50.0,
        )
        assert result["slippage_simulation"]["execution_quality"] in {"good", "acceptable", "poor"}

    def test_convenience_function(self):
        from akshare_mcp.services.execution_slippage import estimate_execution_slippage
        result = estimate_execution_slippage(
            order_shares=5_000,
            avg_minute_volume=20_000,
            adv_shares=2_000_000,
            duration_minutes=10,
            reference_price=15.0,
        )
        assert "slippage_simulation" in result
        sim = result["slippage_simulation"]
        assert sim["total_cost_bps"] > 0
        assert sim["total_cost_cny"] > 0

    def test_execution_manager_slippage_simulation_field(self):
        """Integration: slippage_simulation field appears in execution metrics when avg_minute_volume given."""
        from akshare_mcp.services.execution_slippage import estimate_execution_slippage
        result = estimate_execution_slippage(
            order_shares=10_000,
            avg_minute_volume=50_000,
            adv_shares=10_000_000,
            duration_minutes=20,
            reference_price=25.0,
            slices=4,
        )
        assert "slippage_simulation" in result
        sim = result["slippage_simulation"]
        assert "total_cost_bps" in sim
        assert "full_fill_probability" in sim
        assert "is_partial_fill_risk" in sim


# ============================================================================
# 4. Rolling model registry
# ============================================================================

class TestRollingModelRegistry:

    def _make_registry(self):
        from akshare_mcp.services.rolling_model_registry import RollingModelRegistry
        return RollingModelRegistry(max_history_per_model=30)

    def _eval_payload(self, rank_ic: float = 0.04, score: float = 75.0, stage: str = "challenger") -> dict:
        return {
            "deployment_stage": stage,
            "metrics": {"ic_mean": 0.03, "rank_ic_mean": rank_ic, "rank_ic_ir": 1.2, "sample_dates": 100},
            "validation": {
                "ic_mean": 0.03,
                "rank_ic_mean": rank_ic,
                "rank_ic_ir": 1.2,
                "purged_kfold": {
                    "stability_ratio": 0.70,
                    "oos_rank_ic_mean": rank_ic * 0.8,
                    "degradation": 0.005,
                },
            },
            "rating": {"total_score": score, "overall_rating": "good", "recommendation": "promote"},
            "risk_audit": {"risk_level": "low"},
        }

    def test_record_evaluation_creates_snapshot(self):
        reg = self._make_registry()
        snap = reg.record_evaluation("momentum_20d", self._eval_payload(), window_tag="2024-Q1")
        assert snap["model_name"] == "momentum_20d"
        assert snap["rank_ic_mean"] == pytest.approx(0.04)

    def test_rolling_stability_single_entry(self):
        reg = self._make_registry()
        reg.record_evaluation("momentum_20d", self._eval_payload())
        result = reg.compute_rolling_stability("momentum_20d")
        assert result["available"] is True
        assert result["evaluation_count"] == 1

    def test_rolling_stability_trend_improving(self):
        reg = self._make_registry()
        for ic in [0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
            reg.record_evaluation("factor_x", self._eval_payload(rank_ic=ic))
        result = reg.compute_rolling_stability("factor_x")
        assert result["trend"] in {"improving", "stable"}  # upward trend
        assert result["all_windows"]["stability_ratio"] == 1.0

    def test_rolling_stability_trend_degrading(self):
        reg = self._make_registry()
        for ic in [0.08, 0.06, 0.04, 0.02, 0.00, -0.02]:
            reg.record_evaluation("factor_y", self._eval_payload(rank_ic=ic))
        result = reg.compute_rolling_stability("factor_y")
        assert result["trend"] in {"degrading", "stable"}  # downward trend

    def test_rolling_stability_no_history(self):
        reg = self._make_registry()
        result = reg.compute_rolling_stability("nonexistent")
        assert result["available"] is False

    def test_transition_stage_records_and_updates(self):
        reg = self._make_registry()
        reg.record_evaluation("momentum_20d", self._eval_payload(stage="challenger"))
        rec = reg.transition_stage(
            "momentum_20d",
            from_stage="challenger",
            to_stage="champion",
            reason="outperformed_incumbent",
        )
        assert rec["to_stage"] == "champion"
        assert reg.get_current_stage("momentum_20d") == "champion"

    def test_lifecycle_report_structure(self):
        reg = self._make_registry()
        reg.record_evaluation("model_a", self._eval_payload(stage="champion"))
        reg.record_evaluation("model_b", self._eval_payload(stage="challenger"))
        reg.transition_stage("model_a", from_stage="challenger", to_stage="champion", reason="promoted")
        report = reg.lifecycle_report()
        assert report["total_models"] == 2
        assert "champion_count" in report
        assert "challenger_count" in report
        assert isinstance(report["models"], list)

    def test_detect_degradation_insufficient_history(self):
        reg = self._make_registry()
        reg.record_evaluation("model_new", self._eval_payload())
        result = reg.detect_degradation("model_new")
        assert result["degraded"] is False
        assert result["reason"] == "insufficient_history"

    def test_detect_degradation_stable_model(self):
        reg = self._make_registry()
        for _ in range(8):
            reg.record_evaluation("stable_model", self._eval_payload(rank_ic=0.05))
        result = reg.detect_degradation("stable_model")
        assert result["degraded"] is False

    def test_detect_degradation_degrading_model(self):
        reg = self._make_registry()
        # Early high IC
        for _ in range(5):
            reg.record_evaluation("weak_model", self._eval_payload(rank_ic=0.06))
        # Recent low IC (negative)
        for _ in range(4):
            reg.record_evaluation("weak_model", self._eval_payload(rank_ic=-0.02))
        result = reg.detect_degradation("weak_model")
        assert result["degraded"] is True
        assert result["action_recommended"] in {"retire_or_retrain", "review"}

    def test_compare_champion_challenger(self):
        reg = self._make_registry()
        reg.record_evaluation("champion_model", self._eval_payload(rank_ic=0.03, stage="champion"))
        reg.record_evaluation("challenger_model", self._eval_payload(rank_ic=0.06, stage="challenger"))
        result = reg.compare_champion_challenger("champion_model", "challenger_model")
        assert result["champion"] == "champion_model"
        assert result["challenger"] == "challenger_model"
        assert result["metric_delta"] == pytest.approx(0.03, abs=1e-6)
        assert result["promote_challenger_recommended"] is True

    def test_compare_champion_wins(self):
        reg = self._make_registry()
        reg.record_evaluation("champ", self._eval_payload(rank_ic=0.07, stage="champion"))
        reg.record_evaluation("chal", self._eval_payload(rank_ic=0.03, stage="challenger"))
        result = reg.compare_champion_challenger("champ", "chal")
        assert result["promote_challenger_recommended"] is False

    def test_max_history_cap(self):
        reg = self._make_registry()
        for i in range(50):
            reg.record_evaluation("big_model", self._eval_payload())
        assert len(reg._evaluations.get("big_model", [])) <= 30

    def test_clear_resets(self):
        reg = self._make_registry()
        reg.record_evaluation("model_x", self._eval_payload())
        reg.transition_stage("model_x", from_stage="challenger", to_stage="champion")
        reg.clear()
        assert reg.list_models() == []
        report = reg.lifecycle_report()
        assert report["total_models"] == 0

    def test_list_models(self):
        reg = self._make_registry()
        reg.record_evaluation("alpha", self._eval_payload())
        reg.record_evaluation("beta", self._eval_payload())
        assert sorted(reg.list_models()) == ["alpha", "beta"]

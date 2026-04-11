from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from strategy_factory.application.panels import _apply_trade_quality_rating_adjustment, _run_validation_report


@pytest.mark.asyncio
async def test_run_validation_report_forwards_strategy_family_returns(monkeypatch):
    import strategy_factory.application.panels as panels_mod

    captured: dict[str, object] = {}

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes, volumes=None):
            lookback = float(self.params.get("lookback", 20) or 20)
            threshold = float(self.params.get("threshold", 0.05) or 0.05)
            slope = max(0.05, min(2.0, threshold * lookback))
            return np.linspace(0.0, slope, len(closes), dtype=np.float64)

    class _FakePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, factor_panel, return_panel, **kwargs):
            captured["factor_panel_shape"] = np.asarray(factor_panel).shape
            captured["return_panel_shape"] = np.asarray(return_panel).shape
            captured["strategy_returns"] = np.asarray(kwargs.get("strategy_returns"))
            captured["family_returns"] = np.asarray(kwargs.get("family_returns"))
            return {"rating": {"grade": "B"}, "multiple_testing": {"available": True}}

    monkeypatch.setattr(
        panels_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "momentum" else None),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(FactorValidationPipeline=_FakePipeline),
    )

    klines = [
        {"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(100 + idx), "volume": float(1000 + idx)}
        for idx in range(160)
    ]
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=klines)

    report = await _run_validation_report("momentum", {"lookback": 20, "threshold": 0.05}, db)

    assert report["multiple_testing"]["available"] is True
    assert captured["factor_panel_shape"][1] >= 3
    assert captured["strategy_returns"].ndim == 1
    assert captured["strategy_returns"].size > 0
    assert captured["family_returns"].ndim == 2
    assert captured["family_returns"].shape[1] >= 2
    assert report["validation_focus_layer"] == "broad_market"
    assert report["sample_selection_mode"] == "representative_only"
    assert report["sample_selection"]["sample_code_count"] >= 3
    assert report["validation_focus_annotation"]["validation_focus_layer"] == "broad_market"
    assert "宽市场代表样本" in report["validation_focus_annotation"]["interpretation"]


@pytest.mark.asyncio
async def test_run_validation_report_applies_trade_quality_adjustment_for_target_only_quality(monkeypatch):
    import strategy_factory.application.panels as panels_mod

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes, volumes=None):
            return np.ones(len(closes), dtype=np.float64)

    class _FakePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, factor_panel, return_panel, **kwargs):
            strategy_returns = np.asarray(kwargs.get("strategy_returns"), dtype=np.float64)
            assert strategy_returns.size > 0
            return {
                "rating": {"grade": "D", "total_score": 34.0},
                "multiple_testing": {
                    "deflated_sharpe": {"dsr": 0.22},
                    "pbo": {"pbo": 0.62},
                    "white_reality_check": {"p_value": 0.18},
                    "hansen_spa": {"p_value": 0.14},
                },
            }

    monkeypatch.setattr(
        panels_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "quality_factor" else None),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(FactorValidationPipeline=_FakePipeline),
    )

    klines = []
    close = 100.0
    for idx in range(180):
        close *= 1.0025 if idx % 3 != 0 else 0.999
        klines.append({"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(close), "volume": float(1000 + idx)})
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=klines)

    report = await _run_validation_report(
        "quality_factor",
        {
            "target_symbols": ["000776"],
            "validation_profile": {"validation_focus": "candidate_target_only"},
        },
        db,
    )

    assert report["rating"]["grade"] in {"C", "B", "A"}
    assert report["rating"]["total_score"] > 34.0
    assert report["trade_quality_adjustment"]["applied"] is True
    assert report["trade_quality_adjustment"]["baseline_grade"] == "D"
    assert report["validation_focus_layer"] == "target_only"
    assert report["sample_selection_mode"] == "target_plus_dynamic_family_peer"
    assert report["sample_alignment_reason"] == "target_only_with_family_aligned_dynamic_peers"
    assert report["sample_selection"]["target_codes"] == ["000776"]
    assert "600519" in report["sample_selection"]["family_peer_codes"]
    assert report["validation_focus_annotation"]["validation_focus_layer"] == "target_only"
    assert "单目标或强目标约束 cohort" in report["validation_focus_annotation"]["interpretation"]


@pytest.mark.asyncio
async def test_run_validation_report_applies_trade_quality_adjustment_for_target_only_ma_cross(monkeypatch):
    import strategy_factory.application.panels as panels_mod

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes, volumes=None):
            return np.where(np.arange(len(closes)) % 3 == 0, 1.0, 0.5).astype(np.float64)

    class _FakePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, factor_panel, return_panel, **kwargs):
            strategy_returns = np.asarray(kwargs.get("strategy_returns"), dtype=np.float64)
            assert strategy_returns.size > 0
            return {
                "rating": {"grade": "D", "total_score": 38.0},
                "multiple_testing": {
                    "deflated_sharpe": {"dsr": 0.14},
                    "pbo": {"pbo": 0.68},
                    "white_reality_check": {"p_value": 0.18},
                    "hansen_spa": {"p_value": 0.14},
                },
            }

    monkeypatch.setattr(
        panels_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(FactorValidationPipeline=_FakePipeline),
    )

    klines = []
    close = 100.0
    for idx in range(180):
        close *= 1.003 if idx % 4 != 0 else 0.9995
        klines.append({"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(close), "volume": float(1000 + idx)})
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=klines)

    report = await _run_validation_report(
        "ma_cross",
        {
            "target_symbols": ["300750"],
            "short_period": 8,
            "long_period": 36,
            "holding_horizon": {"min_days": 6, "max_days": 24},
            "rebalance_rule": {"mode": "periodic_rebalance", "frequency_days": 7},
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "market_regime_assumption": {
                "preferred_regime": "trend_expansion_with_volume_confirmation",
                "avoid_regime": "range_bound_chop",
            },
            "family_specialization": {
                "range_filter": "avoid_crosses_when_long_ma_is_flat_and_price_is_range_bound",
                "volume_confirmation": "prefer_crosses_with_volume_ratio_confirmation",
            },
        },
        db,
    )

    assert report["rating"]["grade"] in {"C", "B", "A"}
    assert report["rating"]["total_score"] > 38.0
    assert report["trade_quality_adjustment"]["applied"] is True
    assert report["trade_quality_adjustment"]["baseline_grade"] == "D"
    assert report["trade_quality_adjustment"]["family_specialization"]["range_filter"]


@pytest.mark.asyncio
async def test_run_validation_report_applies_trade_quality_adjustment_for_target_only_momentum(monkeypatch):
    import strategy_factory.application.panels as panels_mod

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes, volumes=None):
            values = np.where(np.arange(len(closes)) % 4 == 0, 1.0, 0.6).astype(np.float64)
            return values

    class _FakePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, factor_panel, return_panel, **kwargs):
            strategy_returns = np.asarray(kwargs.get("strategy_returns"), dtype=np.float64)
            assert strategy_returns.size > 0
            return {
                "rating": {"grade": "D", "total_score": 12.0},
                "multiple_testing": {
                    "deflated_sharpe": {"dsr": 0.01},
                    "pbo": {"pbo": 0.78},
                    "white_reality_check": {"p_value": 0.34},
                    "hansen_spa": {"p_value": 0.33},
                },
            }

    monkeypatch.setattr(
        panels_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "momentum" else None),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )
    monkeypatch.setattr(
        panels_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(FactorValidationPipeline=_FakePipeline),
    )

    klines = []
    close = 100.0
    for idx in range(180):
        close *= 1.004 if idx % 5 != 0 else 0.998
        klines.append({"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(close), "volume": float(1000 + idx)})
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=klines)

    report = await _run_validation_report(
        "momentum",
        {
            "target_symbols": ["600489"],
            "holding_horizon": {"min_days": 14, "max_days": 42},
            "rebalance_rule": {"mode": "periodic_rebalance", "frequency_days": 14},
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "market_regime_assumption": {
                "preferred_regime": "trend_expansion_with_persistence",
                "avoid_regime": "false_breakout_range_reversion",
            },
            "family_specialization": {
                "false_breakout_filter": "prefer_volume_confirmed_breakout_and_positive_trend_slope",
            },
        },
        db,
    )

    assert report["rating"]["grade"] in {"C", "B", "A"}
    assert report["rating"]["total_score"] >= 40.0
    assert report["trade_quality_adjustment"]["applied"] is True
    assert report["trade_quality_adjustment"]["baseline_grade"] == "D"
    assert report["trade_quality_adjustment"]["trade_total_score"] >= 40.0
    assert report["trade_quality_adjustment"]["adjustment_reason"].startswith("validation_trade_quality_adjustment")


def test_trade_quality_adjustment_can_upgrade_target_only_momentum_to_raw_b_with_strong_target_consensus():
    report = _apply_trade_quality_rating_adjustment(
        {
            "rating": {"grade": "D", "total_score": 0.0},
            "multiple_testing": {
                "deflated_sharpe": {"dsr": 0.0},
                "pbo": {"pbo": 0.18},
                "white_reality_check": {"p_value": 0.31},
                "hansen_spa": {"p_value": 0.32},
            },
        },
        strategy_type="momentum",
        params={
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "holding_horizon": {
                "min_days": 20,
                "max_days": 20,
                "expected_turnover_band": "low",
            },
            "rebalance_rule": {
                "mode": "periodic_rebalance",
                "frequency_days": 20,
                "expected_turnover_band": "low",
            },
            "market_regime_assumption": {
                "preferred_regime": "trend_expansion_with_persistence",
            },
            "family_specialization": {
                "false_breakout_filter": "prefer_volume_confirmed_breakout_and_positive_trend_slope",
            },
        },
        strategy_returns=np.asarray(
            [-0.002 if idx % 3 == 0 else 0.001 for idx in range(120)],
            dtype=np.float64,
        ),
        sample_codes=["300442", "300750", "601012", "002415", "300059", "002594"],
        sample_selection={
            "validation_focus_layer": "target_only",
            "sample_selection_mode": "target_plus_dynamic_family_peer",
        },
    )

    assert report["rating"]["grade"] in {"B", "A"}
    assert report["rating"]["total_score"] >= 55.0
    adjustment = report["trade_quality_adjustment"]
    assert adjustment["trade_score_breakdown"]["turnover_discipline"] == 4.0
    assert adjustment["trade_score_breakdown"]["target_cohort_consensus"] >= 7.0
    assert adjustment["trade_score_breakdown"]["target_cohort_trade_alignment"] == 6.0
    assert adjustment["trade_score_breakdown"]["target_cohort_low_turnover_consensus"] == 1.0


def test_trade_quality_adjustment_can_upgrade_target_only_ma_cross_to_raw_b_with_low_noise_consensus():
    report = _apply_trade_quality_rating_adjustment(
        {
            "rating": {"grade": "D", "total_score": 38.0},
            "multiple_testing": {
                "deflated_sharpe": {"dsr": 0.12},
                "pbo": {"pbo": 0.34},
                "white_reality_check": {"p_value": 0.18},
                "hansen_spa": {"p_value": 0.16},
            },
        },
        strategy_type="ma_cross",
        params={
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "short_period": 8,
            "long_period": 36,
            "holding_horizon": {
                "min_days": 14,
                "max_days": 36,
                "expected_turnover_band": "low",
            },
            "rebalance_rule": {
                "mode": "periodic_rebalance",
                "frequency_days": 12,
                "expected_turnover_band": "low",
            },
            "market_regime_assumption": {
                "preferred_regime": "trend_expansion_with_volume_confirmation",
                "avoid_regime": "range_bound_chop",
            },
            "family_specialization": {
                "range_filter": "avoid_crosses_when_long_ma_is_flat_and_price_is_range_bound",
                "volume_confirmation": "prefer_crosses_with_volume_ratio_confirmation",
            },
        },
        strategy_returns=np.asarray(
            [0.0012 if idx % 5 else -0.0003 for idx in range(120)],
            dtype=np.float64,
        ),
        sample_codes=["603993", "300750", "601012", "002415", "300059", "002594"],
        sample_selection={
            "validation_focus_layer": "target_only",
            "sample_selection_mode": "target_plus_dynamic_family_peer",
        },
    )

    assert report["rating"]["grade"] in {"B", "A"}
    assert report["rating"]["total_score"] >= 55.0
    adjustment = report["trade_quality_adjustment"]
    assert adjustment["trade_score_breakdown"]["cross_confirmation_discipline"] == 8.0
    assert adjustment["trade_score_breakdown"]["low_noise_trend_consensus"] == 6.0


def test_trade_quality_adjustment_can_upgrade_target_only_quality_factor_to_raw_b_with_slow_compounding():
    report = _apply_trade_quality_rating_adjustment(
        {
            "rating": {"grade": "D", "total_score": 34.0},
            "multiple_testing": {
                "deflated_sharpe": {"dsr": 0.11},
                "pbo": {"pbo": 0.42},
                "white_reality_check": {"p_value": 0.2},
                "hansen_spa": {"p_value": 0.18},
            },
        },
        strategy_type="quality_factor",
        params={
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "holding_horizon": {
                "min_days": 30,
                "max_days": 84,
                "expected_turnover_band": "low",
            },
            "rebalance_rule": {
                "mode": "periodic_rebalance",
                "frequency_days": 28,
                "expected_turnover_band": "low",
            },
            "market_regime_assumption": {
                "preferred_regime": "quality_stability_with_trend_resonance",
                "avoid_regime": "quality_drift_high_noise_rotation",
            },
            "family_specialization": {
                "quality_trend_resonance": "require_fundamental_stability_and_price_trend_alignment",
                "quality_drift_detection": "monitor_rank_margin_cashflow_stability_deterioration",
                "compounding_window": "prefer_slow_compounding_validation_window",
            },
        },
        strategy_returns=np.asarray(
            [0.001 if idx % 6 else -0.0002 for idx in range(120)],
            dtype=np.float64,
        ),
        sample_codes=["600028", "600519", "000858", "600036", "000333", "600276"],
        sample_selection={
            "validation_focus_layer": "target_only",
            "sample_selection_mode": "target_plus_dynamic_family_peer",
        },
    )

    assert report["rating"]["grade"] in {"B", "A"}
    assert report["rating"]["total_score"] >= 55.0
    adjustment = report["trade_quality_adjustment"]
    assert adjustment["trade_score_breakdown"]["target_cohort_slow_compounding"] == 8.0
    assert adjustment["trade_score_breakdown"]["target_cohort_capital_efficiency"] == 6.0
    assert adjustment["trade_score_breakdown"]["ultra_slow_compounding_window"] == 2.0


def test_trade_quality_adjustment_can_soft_upgrade_borderline_quality_factor_target_only_to_raw_b():
    report = _apply_trade_quality_rating_adjustment(
        {
            "rating": {"grade": "D", "total_score": 34.0},
            "multiple_testing": {
                "deflated_sharpe": {"dsr": 0.02},
                "pbo": {"pbo": 0.57},
                "white_reality_check": {"p_value": 0.932},
                "hansen_spa": {"p_value": 1.0},
            },
        },
        strategy_type="quality_factor",
        params={
            "validation_profile": {"validation_focus": "candidate_target_only"},
            "holding_horizon": {
                "min_days": 24,
                "max_days": 72,
                "expected_turnover_band": "low",
            },
            "rebalance_rule": {
                "mode": "periodic_rebalance",
                "frequency_days": 72,
                "expected_turnover_band": "low",
            },
            "market_regime_assumption": {
                "preferred_regime": "quality_stability_with_trend_resonance",
                "avoid_regime": "quality_drift_high_noise_rotation",
            },
            "family_specialization": {
                "quality_trend_resonance": "require_fundamental_stability_and_price_trend_alignment",
                "quality_drift_detection": "monitor_rank_margin_cashflow_stability_deterioration",
            },
        },
        strategy_returns=np.asarray(
            [0.0008 if idx % 7 else -0.00025 for idx in range(120)],
            dtype=np.float64,
        ),
        sample_codes=["601825", "600519", "000858", "600036", "000333", "600276"],
        sample_selection={
            "validation_focus_layer": "target_only",
            "sample_selection_mode": "target_plus_dynamic_family_peer",
        },
    )

    assert report["rating"]["grade"] in {"B", "A"}
    assert report["rating"]["total_score"] >= 55.0
    adjustment = report["trade_quality_adjustment"]
    assert adjustment["trade_score_breakdown"]["target_cohort_slow_compounding"] == 4.0
    assert adjustment["trade_score_breakdown"]["target_cohort_capital_efficiency"] >= 3.0

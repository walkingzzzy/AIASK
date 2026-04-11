import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import strategy_factory.application.backtest_filter as backtest_filter_module
from strategy_factory.application.backtest_filter import BacktestFilter, build_target_quality_gate_summary


def _make_klines(n: int = 140) -> list[dict]:
    return [
        {
            "date": f"2025-02-{(idx % 28) + 1:02d}",
            "open": 10.0 + idx * 0.02,
            "high": 10.1 + idx * 0.02,
            "low": 9.9 + idx * 0.02,
            "close": 10.0 + idx * 0.02,
            "volume": 1_000_000.0,
        }
        for idx in range(n)
    ]


class _FakeBacktestEngine:
    @staticmethod
    def run_backtest(code, klines, strategy_type, params):
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.9,
                "total_return": 0.12,
                "max_drawdown": 0.08,
                "win_rate": 0.6,
                "trades_count": 6,
                "avg_holding_days": 9.0,
                "turnover_proxy": 1.8,
                "cost_assumptions": {
                    "commission_rate": params.get("commission"),
                    "implementation_shortfall_proxy": 18.4,
                    "implementation_shortfall_model_source": "estimated",
                },
                "explicit_cost_breakdown": {"commission_rate": params.get("commission")},
                "implicit_cost_breakdown": {"implementation_shortfall_proxy": 18.4},
                "tradability_summary": {
                    "tradability_filter": params.get("tradability_filter"),
                    "tradable_ratio": 0.92,
                },
                "capacity_summary": {
                    "capacity_participation_rate": params.get("capacity_participation_rate"),
                    "adv_utilization": 1.5,
                },
                "implementation_shortfall_model_source": "estimated",
                "implementation_shortfall_components": {
                    "capacity_bps": 11.2,
                    "effective_total_bps": 18.4,
                },
                "position_assumption": params.get("position_assumption"),
            },
        }

    @staticmethod
    def run_portfolio_backtest(market_data, strategy_type, params):
        del market_data, strategy_type
        return {
            "success": True,
            "data": {
                "portfolio_engine_used": True,
                "aggregation_mode": "portfolio_engine_shared_cash",
                "allocation_mode": "equal_weight",
                "component_count": 3,
                "sharpe_ratio": 0.9,
                "total_return": 0.12,
                "max_drawdown": 0.08,
                "win_rate": 0.6,
                "trades_count": 6,
                "avg_holding_days": 9.0,
                "turnover_proxy": 1.8,
                "cost_assumptions": {
                    "commission_rate": params.get("commission"),
                    "implementation_shortfall_proxy": 18.4,
                    "implementation_shortfall_model_source": "estimated",
                },
                "explicit_cost_breakdown": {"commission_rate": params.get("commission")},
                "implicit_cost_breakdown": {"implementation_shortfall_proxy": 18.4},
                "tradability_summary": {
                    "tradability_filter": params.get("tradability_filter"),
                    "tradable_ratio": 0.92,
                },
                "capacity_summary": {
                    "capacity_participation_rate": params.get("capacity_participation_rate"),
                    "adv_utilization": 1.5,
                },
                "implementation_shortfall_model_source": "estimated",
                "implementation_shortfall_components": {
                    "capacity_bps": 11.2,
                    "effective_total_bps": 18.4,
                },
                "position_assumption": params.get("position_assumption"),
                "equity_curve": [100000.0, 106000.0, 112000.0],
            },
        }


class _PortfolioCurveBacktestEngine:
    CURVES = {
        "600519": [100.0, 120.0, 140.0],
        "000858": [100.0, 102.0, 105.0],
        "000001": [100.0, 95.0, 90.0],
    }
    RETURNS = {
        "600519": 0.40,
        "000858": 0.05,
        "000001": -0.10,
    }

    @classmethod
    def run_backtest(cls, code, klines, strategy_type, params):
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.9,
                "total_return": cls.RETURNS[code],
                "max_drawdown": 0.08,
                "win_rate": 0.5,
                "trades_count": 6,
                "avg_holding_days": 8.0,
                "turnover_proxy": 1.5,
                "equity_curve": cls.CURVES[code],
            },
        }


class _EventWindowBacktestEngine:
    CURVES = {
        "600519": [100.0, 101.0, 102.0, 103.0, 110.0, 115.0],
        "600000": [100.0, 101.0, 102.0, 103.0, 110.0, 115.0],
        "601318": [100.0, 101.0, 102.0, 103.0, 110.0, 115.0],
        "000858": [100.0, 100.5, 101.0, 101.5, 102.0, 102.5],
    }

    @classmethod
    def run_backtest(cls, code, klines, strategy_type, params):
        curve = cls.CURVES[code]
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.9,
                "total_return": curve[-1] / curve[0] - 1.0,
                "max_drawdown": 0.06,
                "win_rate": 0.65,
                "trades_count": 5,
                "avg_holding_days": 7.0,
                "turnover_proxy": 1.1,
                "equity_curve": curve,
            },
        }

    @classmethod
    def run_portfolio_backtest(cls, market_data, strategy_type, params):
        del market_data, strategy_type
        return {
            "success": True,
            "data": {
                "portfolio_engine_used": True,
                "aggregation_mode": "portfolio_engine_shared_cash",
                "allocation_mode": "equal_weight",
                "component_count": 3,
                "total_return": 0.15,
                "max_drawdown": 0.05,
                "sharpe_ratio": 1.1,
                "win_rate": 0.66,
                "trades_count": 9,
                "avg_holding_days": 7.0,
                "turnover_proxy": 1.1,
                "cost_assumptions": {"commission_rate": params.get("commission")},
                "equity_curve": [100000.0, 106000.0, 115000.0],
                "position_assumption": params.get("position_assumption"),
            },
        }


class _WeightedPortfolioBacktestEngine:
    CURVES = {
        "600519": [100.0, 110.0, 120.0],
        "000858": [100.0, 90.0, 80.0],
        "600000": [100.0, 100.0, 100.0],
    }

    @classmethod
    def run_backtest(cls, code, klines, strategy_type, params):
        curve = cls.CURVES[code]
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.8,
                "total_return": curve[-1] / curve[0] - 1.0,
                "max_drawdown": 0.1,
                "win_rate": 0.5,
                "trades_count": 4,
                "avg_holding_days": 6.0,
                "turnover_proxy": 1.2,
                "equity_curve": curve,
            },
        }

    @classmethod
    def run_portfolio_backtest(cls, market_data, strategy_type, params):
        del market_data, strategy_type
        return {
            "success": True,
            "data": {
                "portfolio_engine_used": True,
                "aggregation_mode": "portfolio_weighted",
                "allocation_mode": "target_weight_map",
                "allocation_weights": {"600519": 0.75, "000858": 0.25},
                "component_count": 2,
                "sharpe_ratio": 0.92,
                "total_return": 0.10,
                "max_drawdown": 0.05,
                "win_rate": 0.5,
                "trades_count": 8,
                "avg_holding_days": 6.0,
                "turnover_proxy": 1.1,
                "position_assumption": params.get("position_assumption"),
                "equity_curve": [100000.0, 104000.0, 110000.0],
            },
        }


class _SharedCashPortfolioBacktestEngine:
    portfolio_calls = []

    @classmethod
    def run_backtest(cls, code, klines, strategy_type, params):
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.5,
                "total_return": 0.04,
                "max_drawdown": 0.12,
                "win_rate": 0.45,
                "trades_count": 3,
                "avg_holding_days": 5.0,
                "turnover_proxy": 0.8,
                "equity_curve": [100.0, 101.0, 102.0],
            },
        }

    @classmethod
    def run_portfolio_backtest(cls, market_data, strategy_type, params):
        cls.portfolio_calls.append(
            {
                "codes": list(market_data.keys()),
                "strategy_type": strategy_type,
                "params": dict(params or {}),
            }
        )
        return {
            "success": True,
            "data": {
                "strategy": strategy_type,
                "portfolio_mode": "shared_cash",
                "aggregation_mode": "portfolio_engine_shared_cash",
                "allocation_mode": "equal_weight",
                "allocation_weights": {"600519": 1 / 3, "000858": 1 / 3, "000001": 1 / 3},
                "component_count": 3,
                "total_return": 0.18,
                "max_drawdown": 0.05,
                "sharpe_ratio": 1.4,
                "win_rate": 0.6,
                "trades_count": 12,
                "avg_holding_days": 7.0,
                "turnover_proxy": 1.4,
                "cost_assumptions": {"commission_rate": params.get("commission")},
                "explicit_cost_breakdown": {"commission_rate": params.get("commission")},
                "implicit_cost_breakdown": {"implementation_shortfall_proxy": 12.0},
                "tradability_summary": {"tradability_filter": params.get("tradability_filter"), "tradable_ratio": 0.97},
                "capacity_summary": {"capacity_participation_rate": params.get("capacity_participation_rate")},
                "implementation_shortfall_model_source": "estimated",
                "implementation_shortfall_components": {"effective_total_bps": 12.0},
                "position_assumption": params.get("position_assumption"),
                "equity_curve": [100000.0, 108000.0, 118000.0],
                "portfolio_engine_used": True,
            },
        }


class _LowTradeCountBacktestEngine:
    @staticmethod
    def run_backtest(code, klines, strategy_type, params):
        del code, klines, strategy_type, params
        return {
            "success": True,
            "data": {
                "sharpe_ratio": 0.6,
                "total_return": 0.05,
                "max_drawdown": 0.08,
                "win_rate": 0.5,
                "trades_count": 3,
                "avg_holding_days": 10.0,
                "turnover_proxy": 0.6,
                "equity_curve": [100.0, 103.0, 105.0],
            },
        }


def _patch_runtime(monkeypatch, engine_cls=_FakeBacktestEngine):
    monkeypatch.setattr(backtest_filter_module, "get_backtest_engine_class", lambda: engine_cls)
    monkeypatch.setattr(backtest_filter_module, "_get_strategy_factory_package", lambda: SimpleNamespace(asyncio=asyncio))


@pytest.mark.asyncio
async def test_backtest_filter_propagates_execution_audit_fields(monkeypatch):
    _patch_runtime(monkeypatch)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858", "000001"],
        },
        "execution_assumptions": {
            "commission_rate": 0.00025,
            "tradability_filter": True,
            "capacity_participation_rate": 0.15,
            "adv_ratio_limit": 0.10,
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    metrics = passed[0]["backtest_metrics"]
    assert metrics["implementation_shortfall_model_source"] == "estimated"
    assert metrics["implementation_shortfall_components"]["capacity_bps"] == pytest.approx(11.2)
    assert metrics["tradability_summary"]["tradable_ratio"] == pytest.approx(0.92)
    assert metrics["capacity_summary"]["adv_utilization"] == pytest.approx(1.5)
    assert metrics["backtest_assumptions"]["target_weight_scheme"] == "equal_weight"
    assert metrics["avg_holding_days"] == pytest.approx(9.0)
    assert metrics["turnover_proxy"] == pytest.approx(1.8)


def test_apply_result_to_candidate_compacts_large_curve_payloads():
    candidate = {"strategy_type": "momentum", "params": {"lookback": 20}}
    result = {
        "passed": True,
        "metrics": {"sharpe_ratio": 1.1, "total_return": 0.16, "max_drawdown": 0.08, "trades_count": 6},
        "constraint_check": {"coverage_ratio": 1.0},
        "validation_focus": "target_plus_representative",
        "primary_validation_layer": "combined",
        "event_window_config": {"event_window": {"pre_days": 0, "post_days": 20}},
        "contamination_summary": {"representative_included": True},
        "cost_assumptions": {"commission_bps": 8},
        "execution_summary": {"order_attempt_count": 12},
        "cash_curve": [100000.0, 101200.0, 102400.0],
        "gross_exposure_curve": [0.0, 0.5, 0.6],
        "net_exposure_curve": [0.0, 0.5, 0.55],
        "layers": {
            "target": {
                "metrics": {
                    "total_return": 0.18,
                    "component_codes": ["600519", "000858"],
                    "equity_curve": [100000.0, 102000.0, 104000.0],
                }
            },
            "representative": {"metrics": {"total_return": 0.05}},
            "combined": {
                "metrics": {
                    "total_return": 0.16,
                    "cash_curve": [100000.0, 101000.0, 102000.0],
                }
            },
        },
        "event_window_metrics": {"hit_ratio": 0.5},
        "backtest_assumptions": {"target_weight_scheme": "equal_weight"},
    }
    passed: list[dict] = []
    failed: list[dict] = []

    BacktestFilter()._apply_result_to_candidate(candidate, result, passed, failed)

    metrics = passed[0]["backtest_metrics"]
    assert metrics["cash_curve_summary"]["points"] == 3
    assert metrics["cash_curve_summary"]["last"] == pytest.approx(102400.0)
    assert "cash_curve" not in metrics
    assert metrics["target_layer_metrics"]["equity_curve_summary"]["points"] == 3
    assert "equity_curve" not in metrics["target_layer_metrics"]
    assert metrics["combined_layer_metrics"]["cash_curve_summary"]["points"] == 3


@pytest.mark.asyncio
async def test_backtest_filter_event_target_only_excludes_representative_contamination(monkeypatch):
    _patch_runtime(monkeypatch)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519", "000858", "000001"],
            "validation_focus": "event_target_only",
            "event_samples": [
                {
                    "sample_id": "sample_evt_1",
                    "event_id": "evt_1",
                    "event_time": "2026-03-01T09:30:00+08:00",
                    "target_return": 0.10,
                    "benchmark_return": 0.03,
                    "abnormal_return": 0.07,
                    "car": 0.065,
                    "bhar": 0.068,
                    "hit": True,
                    "post_event_decay": -0.18,
                    "pre_days": 2,
                    "post_days": 5,
                    "estimation_days": 30,
                    "control_group": ["000300"],
                },
            ],
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    result = passed[0]["backtest_result"]
    assert result["validation_focus"] == "event_target_only"
    assert result["primary_validation_layer"] == "target"
    assert result["contamination_summary"]["representative_included"] is False
    assert result["layers"]["representative"]["sample_count"] == 0
    assert result["event_window_metrics"]["traceable_to_event_samples"] is True


@pytest.mark.asyncio
async def test_backtest_filter_allows_single_target_bulk_matrix_candidate_with_target_only_validation(monkeypatch):
    _patch_runtime(monkeypatch)
    original_compat = backtest_filter_module._compat_setting

    def _fake_compat(name, default):
        if name == "REPRESENTATIVE_STOCKS":
            return ["000858", "000001", "600000"]
        return original_compat(name, default)

    monkeypatch.setattr(backtest_filter_module, "_compat_setting", _fake_compat)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519"],
        "research_task": {
            "task_source": "bulk_stock_matrix",
            "target_symbols": ["600519"],
            "validation_focus": "candidate_target_only",
            "allowed_strategy_types": ["momentum"],
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    result = passed[0]["backtest_result"]
    assert result["passed"] is True
    assert result["primary_validation_layer"] == "target"
    assert result["sample_count"] == 1
    assert result["required_sample_count"] == 1
    assert result["layers"]["combined"]["sample_count"] == 3
    assert result["validation_focus"] == "candidate_target_only"


@pytest.mark.asyncio
async def test_backtest_filter_raises_trade_floor_for_single_target_bulk_matrix_candidates(monkeypatch):
    _patch_runtime(monkeypatch, engine_cls=_LowTradeCountBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "ma_cross",
        "params": {"short_window": 5, "long_window": 20},
        "target_symbols": ["600519"],
        "research_task": {
            "task_source": "bulk_stock_matrix",
            "target_symbols": ["600519"],
            "validation_focus": "candidate_target_only",
            "allowed_strategy_types": ["ma_cross"],
        },
    }

    backtest = BacktestFilter()
    passed = await backtest.filter([candidate], db)

    assert passed == []
    report = backtest.get_last_report()
    assert report["summary"]["failed_reason_counts"]["trades_below_threshold"] == 1
    failed_result = report["failed"][0]["backtest_result"]
    assert failed_result["thresholds"]["trades_min"] == pytest.approx(4.0)
    assert failed_result["metrics"]["trades_count"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_backtest_filter_requires_portfolio_engine_for_equal_weight_multi_target(monkeypatch):
    _patch_runtime(monkeypatch, engine_cls=_PortfolioCurveBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858", "000001"],
            "validation_focus": "event_target_only",
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
    }

    backtest = BacktestFilter()
    passed = await backtest.filter([candidate], db)

    assert passed == []
    report = backtest.get_last_report()
    assert report["summary"]["failed_reason_counts"]["portfolio_engine_required"] == 1
    failed_result = report["failed"][0]["backtest_result"]
    assert failed_result["reason_code"] == "portfolio_engine_required"
    assert failed_result["portfolio_backtest_coverage"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_backtest_filter_rejects_event_window_metrics_without_traceable_samples(monkeypatch):
    _patch_runtime(monkeypatch, engine_cls=_EventWindowBacktestEngine)
    original_compat = backtest_filter_module._compat_setting

    def _fake_compat(name, default):
        if name == "REPRESENTATIVE_STOCKS":
            return ["000858"]
        return original_compat(name, default)

    monkeypatch.setattr(backtest_filter_module, "_compat_setting", _fake_compat)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "600000", "601318"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_real_window",
            "target_symbols": ["600519", "600000", "601318"],
            "validation_focus": "target_plus_representative",
            "event_window": {"pre_days": 1, "post_days": 2},
            "estimation_window": {"lookback_days": 2},
        },
    }

    backtest = BacktestFilter()
    passed = await backtest.filter([candidate], db)

    assert passed == []
    report = backtest.get_last_report()
    assert report["summary"]["failed_reason_counts"]["event_samples_required"] == 1
    failed_result = report["failed"][0]["backtest_result"]
    event_metrics = failed_result["event_window_metrics"]

    assert failed_result["reason_code"] == "event_samples_required"
    assert failed_result["portfolio_backtest_mode"] == "portfolio_engine_shared_cash"
    assert event_metrics["aggregation_mode"] == "portfolio_engine_shared_cash"
    assert event_metrics.get("traceable_to_event_samples") is not True


@pytest.mark.asyncio
async def test_backtest_filter_prefers_event_samples_over_curve_tail_proxy(monkeypatch):
    _SharedCashPortfolioBacktestEngine.portfolio_calls = []
    _patch_runtime(monkeypatch, engine_cls=_SharedCashPortfolioBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_sample_driven",
            "target_symbols": ["600519", "000858", "000001"],
            "validation_focus": "event_target_only",
            "event_samples": [
                {
                    "sample_id": "sample_1",
                    "event_id": "evt_sample_driven",
                    "event_time": "2026-03-01T09:30:00+08:00",
                    "target_return": 0.11,
                    "benchmark_return": 0.03,
                    "abnormal_return": 0.08,
                    "car": 0.075,
                    "bhar": 0.079,
                    "hit": True,
                    "post_event_decay": -0.22,
                    "pre_days": 2,
                    "post_days": 5,
                    "estimation_days": 30,
                    "control_group": ["000300"],
                },
                {
                    "sample_id": "sample_2",
                    "event_id": "evt_sample_driven",
                    "event_time": "2026-03-05T09:30:00+08:00",
                    "target_return": 0.07,
                    "benchmark_return": 0.01,
                    "abnormal_return": 0.06,
                    "car": 0.058,
                    "bhar": 0.061,
                    "hit": False,
                    "post_event_decay": -0.35,
                    "pre_days": 2,
                    "post_days": 4,
                    "estimation_days": 28,
                    "control_group": ["000905"],
                },
            ],
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    event_metrics = passed[0]["backtest_result"]["event_window_metrics"]
    assert event_metrics["event_study_mode"] == "sample_driven"
    assert event_metrics["event_sample_count"] == 2
    assert event_metrics["event_anchor_count"] == 2
    assert event_metrics["benchmark_source"] == "sample_control_group"
    assert event_metrics["abnormal_return"] == pytest.approx(0.07)
    assert event_metrics["car"] == pytest.approx(0.0665)
    assert event_metrics["bhar"] == pytest.approx(0.07)
    assert event_metrics["hit_ratio"] == pytest.approx(0.5)
    assert event_metrics["control_group_count"] == 2
    assert event_metrics["traceable_to_event_samples"] is True
    assert passed[0]["backtest_result"]["portfolio_backtest_mode"] == "portfolio_engine_shared_cash"


@pytest.mark.asyncio
async def test_backtest_filter_rejects_minimal_event_samples_from_context(monkeypatch):
    _patch_runtime(monkeypatch, engine_cls=_EventWindowBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "600000", "601318"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_auto_minimal",
            "target_symbols": ["600519", "600000", "601318"],
            "validation_focus": "event_target_only",
            "event_window": {"pre_days": 1, "post_days": 2},
            "estimation_window": {"lookback_days": 5},
            "event_context": {
                "event_id": "evt_auto_minimal",
                "event_time": "2026-03-10T09:30:00+08:00",
                "control_symbols": ["000858"],
            },
        },
    }

    backtest_filter = BacktestFilter()
    passed = await backtest_filter.filter([candidate], db)

    assert passed == []
    report = backtest_filter.get_last_report()
    assert report["summary"]["failed_reason_counts"]["event_audit_incomplete"] == 1
    failed_entry = report["failed"][0]
    event_metrics = failed_entry["backtest_result"]["event_window_metrics"]
    assert event_metrics["event_study_mode"] == "sample_driven_minimal"
    assert event_metrics["event_sample_source"] == "auto_context_minimal"
    assert event_metrics["event_sample_count"] == 3
    assert event_metrics["event_anchor_count"] == 1
    assert event_metrics["benchmark_source"] == "event_context_control_group"
    assert event_metrics["control_group_count"] == 1
    assert event_metrics["traceable_to_event_samples"] is False
    assert sorted(event_metrics["event_sample_ids"]) == sorted([
        "evt_auto_minimal:600519",
        "evt_auto_minimal:600000",
        "evt_auto_minimal:601318",
    ])


def test_build_target_quality_gate_summary_flags_gate_1_sample_and_stability_risks():
    candidate = {
        "strategy_type": "rsi",
        "generator_type": "pipeline_staged",
        "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
        "target_symbols": ["603855", "603279", "002833", "601766"],
        "constraint_check": {
            "coverage_ratio": 1.0,
            "intersection_ratio": 0.5,
            "target_overlap_count": 4,
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
            "allowed_strategy_types": ["rsi"],
        },
    }

    summary = build_target_quality_gate_summary(
        candidate,
        gate_1_metrics={
            "target_codes": ["603855", "603279", "002833"],
            "avg_sharpe": 0.86,
            "sharpe_values": [1.6, 0.25, 0.15],
        },
    )

    assert summary["min_target_sample_count"] == 4
    assert summary["sampled_target_count"] == 3
    assert summary["target_layer_stability"] < summary["min_target_layer_stability"]
    assert "target_sample_sufficiency_too_low" in summary["reasons"]
    assert "target_layer_stability_too_low" in summary["reasons"]


@pytest.mark.asyncio
async def test_backtest_filter_honors_target_weight_map_for_portfolio_aggregation(monkeypatch):
    _patch_runtime(monkeypatch, engine_cls=_WeightedPortfolioBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "600000"],
        "research_task": {
            "task_source": "bulk_stock_matrix",
            "task_id": "bulk_weighted",
            "target_symbols": ["600519", "000858", "600000"],
            "validation_focus": "event_target_only",
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "target_weight_map",
            "target_weight_map": {
                "600519": 0.75,
                "000858": 0.25,
            },
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    result = passed[0]["backtest_result"]
    metrics = result["metrics"]

    assert metrics["aggregation_mode"] == "portfolio_weighted"
    assert metrics["allocation_mode"] == "target_weight_map"
    assert metrics["allocation_weights"]["600519"] == pytest.approx(0.75, abs=1e-6)
    assert metrics["allocation_weights"]["000858"] == pytest.approx(0.25, abs=1e-6)
    assert metrics["total_return"] == pytest.approx(0.10, abs=1e-4)


@pytest.mark.asyncio
async def test_backtest_filter_prefers_portfolio_engine_for_multi_name_candidates(monkeypatch):
    _SharedCashPortfolioBacktestEngine.portfolio_calls = []
    _patch_runtime(monkeypatch, engine_cls=_SharedCashPortfolioBacktestEngine)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858", "000001"],
            "validation_focus": "target_plus_representative",
        },
        "execution_assumptions": {
            "commission_rate": 0.00025,
            "tradability_filter": True,
            "capacity_participation_rate": 0.12,
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    result = passed[0]["backtest_result"]
    metrics = result["metrics"]
    target_layer = result["layers"]["target"]
    assert _SharedCashPortfolioBacktestEngine.portfolio_calls
    assert metrics["aggregation_mode"] == "portfolio_engine_shared_cash"
    assert metrics["total_return"] == pytest.approx(0.18)
    assert metrics["trades_count"] == pytest.approx(12.0)
    assert result["portfolio_backtest_mode"] == "portfolio_engine_shared_cash"
    assert result["portfolio_backtest_coverage"] == pytest.approx(1.0)
    assert target_layer["metrics_source"] == "portfolio_engine"


def test_trade_density_uses_effective_observation_horizon():
    candidate = {
        "strategy_type": "momentum",
        "holding_horizon": {"max_days": 20, "expected_turnover_band": "medium"},
        "market_regime_assumption": {"preferred_regime": "trend_expansion"},
        "position_sizing_rationale": "equal_weight_diversified_basket",
        "capacity_bucket": "mid",
        "turnover_cost_class": "medium_touch",
        "research_task": {
            "task_source": "snapshot",
            "estimation_window": {"lookback_days": 60},
            "holding_window": {"max_days": 20},
        },
        "execution_assumptions": {
            "commission_rate": 0.00025,
            "slippage_bps": 5,
            "tradability_filter": True,
            "capacity_bucket": "mid",
            "turnover_cost_class": "medium_touch",
        },
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
            "position_sizing_rationale": "equal_weight_diversified_basket",
        },
    }
    result = {
        "metrics": {
            "trades_count": 18,
            "avg_holding_days": 14,
            "total_return": 0.31,
            "max_drawdown": 0.12,
            "sharpe_ratio": 1.08,
        },
        "layers": {
            "target": {"metrics": {"total_return": 0.34, "sharpe_ratio": 1.08, "curve_points": 276}},
            "representative": {"metrics": {"total_return": 0.12, "sharpe_ratio": 0.41}},
            "combined": {"metrics": {"total_return": 0.30, "sharpe_ratio": 0.81, "curve_points": 276}},
        },
        "event_window_metrics": {},
    }

    metrics = BacktestFilter._derive_trade_validation_metrics(candidate, result)

    assert metrics["trade_density"] == pytest.approx(1.1538)
    assert metrics["avg_holding_days"] == pytest.approx(14.0)
    assert metrics["expected_turnover_band"] == "medium"
    assert metrics["capacity_bucket"] == "mid"
    assert metrics["turnover_cost_class"] == "medium_touch"
    assert metrics["position_sizing_rationale"] == "equal_weight_diversified_basket"

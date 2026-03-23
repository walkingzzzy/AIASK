from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from strategy_factory.application.submission_gate import run_submission_quality_gate


@pytest.mark.asyncio
async def test_submission_gate_returns_failure_for_unknown_strategy_type():
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=[])

    result = await run_submission_quality_gate(
        db,
        {"strategy_type": "unknown_strategy_type", "params": {}},
    )

    assert result["passed"] is False
    assert "registry" in str(result.get("reason") or "").lower()


@pytest.mark.asyncio
async def test_submission_gate_normalizes_descending_klines_before_validation(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    captured: dict[str, np.ndarray] = {}

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes):
            return np.linspace(0.0, 1.0, len(closes), dtype=float)

    class _FakeWalkForward:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            captured["return_panel"] = np.array(return_panel, copy=True)
            return SimpleNamespace(oos_ic_ir=1.0)

    class _FakePurgedKFold:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            return SimpleNamespace(oos_ic_mean=0.1)

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(
            WalkForwardValidator=_FakeWalkForward,
            PurgedKFoldCV=_FakePurgedKFold,
            bootstrap_ic_ci=lambda *_args, **_kwargs: {"ci_lower": 0.1},
        ),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )

    ascending = [
        {"date": f"2026-01-{idx + 1:02d}", "close": float(100 + idx)}
        for idx in range(120)
    ]
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=list(reversed(ascending)))

    result = await run_submission_quality_gate(
        db,
        {"strategy_type": "ma_cross", "params": {}, "target_symbols": ["600519"]},
    )

    assert result["passed"] in {True, False}
    assert "return_panel" in captured
    assert float(captured["return_panel"][0, 0]) > 0


@pytest.mark.asyncio
async def test_submission_gate_emits_trade_profile_and_run_correction_proxies(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes):
            return np.linspace(0.0, 1.0, len(closes), dtype=float)

    class _FakeWalkForward:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            return SimpleNamespace(oos_ic_ir=0.9)

    class _FakePurgedKFold:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            return SimpleNamespace(oos_ic_mean=0.12)

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(
            WalkForwardValidator=_FakeWalkForward,
            PurgedKFoldCV=_FakePurgedKFold,
            bootstrap_ic_ci=lambda *_args, **_kwargs: {"ci_lower": 0.08},
        ),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )

    ascending = [
        {"date": f"2026-01-{idx + 1:02d}", "close": float(100 + idx)}
        for idx in range(120)
    ]
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=ascending)

    result = await run_submission_quality_gate(
        db,
        {
            "strategy_type": "ma_cross",
            "params": {"short_period": 5, "long_period": 20},
            "target_symbols": ["600519"],
            "factory_attempt_count": 40,
            "factory_selected_count": 2,
        },
        backtest_metrics={
            "post_cost_sharpe": 0.6,
            "trade_count": 9,
            "avg_holding_days": 8,
            "turnover_proxy": 0.7,
            "target_layer_oos_return": 0.08,
            "target_layer_abnormal_return": 0.05,
            "event_window_hit_ratio": 0.67,
            "post_event_decay": -0.2,
            "trade_density": 0.45,
            "parameter_perturbation_trade_stability": 0.72,
            "primary_validation_layer": "target",
        },
        risk_report={"stress_loss_percent": -10.0},
    )

    assert result["post_event_decay"] == pytest.approx(-0.2)
    assert result["trade_density"] == pytest.approx(0.45)
    assert result["run_correction_mode"] in {"attempt_only_proxy", "bootstrap_family_proxy"}
    assert "deflated_sharpe_proxy" in result
    assert "pbo_proxy" in result
    assert "reality_check_pvalue_proxy" in result
    assert "spa_pvalue_proxy" in result


@pytest.mark.asyncio
async def test_submission_gate_prefers_formal_multiple_testing_outputs(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    class _FakeStrategy:
        def set_parameters(self, params):
            self.params = dict(params or {})

        def generate_signals(self, closes):
            short_period = float(self.params.get("short_period", 5) or 5)
            long_period = float(self.params.get("long_period", 20) or 20)
            slope = max(0.05, min(2.0, short_period / max(long_period, 1.0)))
            return np.linspace(0.1, 0.1 + slope, len(closes), dtype=float)

    class _FakeWalkForward:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            return SimpleNamespace(oos_ic_ir=0.95)

    class _FakePurgedKFold:
        def __init__(self, **_kwargs):
            pass

        def validate(self, factor_panel, return_panel):
            return SimpleNamespace(oos_ic_mean=0.15)

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: _FakeStrategy if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_validation_runtime",
        lambda: SimpleNamespace(
            WalkForwardValidator=_FakeWalkForward,
            PurgedKFoldCV=_FakePurgedKFold,
            bootstrap_ic_ci=lambda *_args, **_kwargs: {"ci_lower": 0.09},
            deflated_sharpe_ratio=lambda *_args, **_kwargs: {
                "dsr": 0.91,
                "reference_sharpe": 0.38,
                "effective_trials": 6.0,
            },
            probability_of_backtest_overfitting=lambda *_args, **_kwargs: {"pbo": 0.21},
            white_reality_check=lambda *_args, **_kwargs: {"p_value": 0.08},
            hansen_spa_test=lambda *_args, **_kwargs: {"p_value": 0.05},
        ),
    )
    monkeypatch.setattr(
        submission_gate_mod,
        "get_normalize_klines",
        lambda: (lambda rows: sorted(list(rows or []), key=lambda row: str(row.get("date") or ""))),
    )

    ascending = [
        {"date": f"2026-01-{(idx % 28) + 1:02d}", "close": float(100 + idx)}
        for idx in range(140)
    ]
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=ascending)

    result = await run_submission_quality_gate(
        db,
        {
            "strategy_type": "ma_cross",
            "params": {"short_period": 5, "long_period": 20},
            "target_symbols": ["600519"],
            "factory_attempt_count": 24,
            "factory_selected_count": 2,
        },
        backtest_metrics={
            "post_cost_sharpe": 0.7,
            "trade_count": 10,
            "avg_holding_days": 7,
            "turnover_proxy": 0.6,
            "target_layer_oos_return": 0.09,
            "target_layer_abnormal_return": 0.06,
            "event_window_hit_ratio": 0.7,
            "post_event_decay": -0.1,
            "trade_density": 0.4,
            "parameter_perturbation_trade_stability": 0.75,
            "primary_validation_layer": "target",
        },
        risk_report={"stress_loss_percent": -8.0},
    )

    assert result["multiple_testing_mode"] == "formal_runtime"
    assert result["deflated_sharpe_ratio"] == pytest.approx(0.91)
    assert result["pbo"] == pytest.approx(0.21)
    assert result["white_reality_check_pvalue"] == pytest.approx(0.08)
    assert result["hansen_spa_pvalue"] == pytest.approx(0.05)
    assert result["multiple_testing"]["pbo"]["pbo"] == pytest.approx(0.21)

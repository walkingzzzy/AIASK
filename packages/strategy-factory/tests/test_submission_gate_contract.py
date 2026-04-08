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
async def test_submission_gate_uses_trade_profile_as_primary_gate_when_trade_audit_exists(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "trade_rule_validation"
        assert klass is object
        return {
            "passed": False,
            "reasons": ["Walk-Forward IC IR 0.000 < 0.050"],
            "warnings": ["run_correction:deflated_sharpe_proxy_negative"],
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": 0.0,
            "run_correction_mode": "attempt_only_proxy",
            "deflated_sharpe_proxy": -0.2,
            "pbo_proxy": 0.61,
            "reality_check_pvalue_proxy": 0.28,
            "spa_pvalue_proxy": 0.24,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {"strategy_type": "ma_cross", "params": {"short_period": 5, "long_period": 20}},
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
            "max_drawdown": 0.12,
        },
        risk_report={"stress_loss_percent": -10.0},
    )

    assert result["passed"] is True
    assert result["gate_protocol"] == "trade_rule_validation:trade_primary_with_supplemental_audit"
    assert result["primary_gate_protocol"] == "trade_rule_validation:trade_primary"
    assert result["reasons"] == []
    assert result["deflated_sharpe_proxy"] == pytest.approx(-0.2)
    assert result["supplemental_statistical_gate"]["passed"] is False
    assert "supplemental_statistical_gate_failed" in result["warning_codes"]


@pytest.mark.asyncio
async def test_submission_gate_keeps_factor_profile_on_statistical_primary(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    stat_calls: list[str] = []
    trade_calls: list[str] = []

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        stat_calls.append(profile["profile"])
        assert klass is object
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "wf_ic_ir": 0.25,
        }

    def _fake_trade_gate(_strategy, profile, _backtest_metrics, _risk_report):
        trade_calls.append(profile["profile"])
        return {"passed": True}

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "value_factor" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)
    monkeypatch.setattr(submission_gate_mod, "_evaluate_trade_profile", _fake_trade_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {"strategy_type": "value_factor", "params": {"lookback": 60}},
        backtest_metrics={
            "post_cost_sharpe": 0.7,
            "trade_count": 12,
            "target_layer_oos_return": 0.09,
            "target_layer_abnormal_return": 0.05,
            "event_window_hit_ratio": 0.65,
            "post_event_decay": -0.1,
            "trade_density": 0.4,
            "parameter_perturbation_trade_stability": 0.8,
            "primary_validation_layer": "combined",
        },
        risk_report={"stress_loss_percent": -8.0},
    )

    assert result["passed"] is True
    assert result["gate_protocol"] == "factor_rank_validation:statistical_primary"
    assert stat_calls == ["factor_rank_validation"]
    assert trade_calls == []


@pytest.mark.asyncio
async def test_submission_gate_routes_single_target_bulk_factor_to_trade_primary(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    stat_calls: list[str] = []
    trade_calls: list[str] = []

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        stat_calls.append(profile["profile"])
        assert klass is object
        return {
            "passed": False,
            "reasons": ["Walk-Forward IC IR 0.000 < 0.050"],
            "warnings": [],
            "wf_ic_ir": 0.0,
            "pkf_ic": 0.0,
            "bootstrap_ci_lower": -0.05,
            "param_sensitivity": 0.31,
        }

    def _fake_trade_gate(_strategy, profile, _backtest_metrics, _risk_report, *, admission_level="incubation", attempt_adjustment=None):
        del attempt_adjustment
        trade_calls.append(f"{profile['profile']}:{admission_level}")
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "profile": profile["profile"],
            "validation_focus": profile["validation_focus"],
            "primary_validation_layer": profile["primary_validation_layer"],
            "post_cost_sharpe": 0.84,
            "target_layer_oos_return": 0.14,
            "target_layer_abnormal_return": 0.03,
            "trade_count": 10,
            "max_drawdown": 0.07,
            "avg_holding_days": 18,
            "turnover_proxy": 10.5,
            "event_window_hit_ratio": 1.0,
            "post_event_decay": 0.0,
            "trade_density": 0.4,
            "parameter_perturbation_trade_stability": 0.71,
            "thresholds": {},
            "admission_level": admission_level,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "quality_factor" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)
    monkeypatch.setattr(submission_gate_mod, "_evaluate_trade_profile", _fake_trade_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {
            "strategy_type": "quality_factor",
            "target_symbols": ["002142"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "validation_focus": "candidate_target_only",
                "target_symbols": ["002142"],
            },
            "params": {
                "portfolio_spec": {
                    "position_assumption": "single_name_full_notional",
                    "target_weight_scheme": "single_name",
                }
            },
        },
        backtest_metrics={
            "post_cost_sharpe": 0.84,
            "trade_count": 10,
            "avg_holding_days": 18,
            "turnover_proxy": 10.5,
            "target_layer_oos_return": 0.14,
            "target_layer_abnormal_return": 0.03,
            "event_window_hit_ratio": 1.0,
            "post_event_decay": 0.0,
            "trade_density": 0.4,
            "parameter_perturbation_trade_stability": 0.71,
            "primary_validation_layer": "target",
            "max_drawdown": 0.07,
        },
        risk_report={"stress_loss_percent": -12.0},
    )

    assert result["passed"] is True
    assert result["gate_protocol"] == "trade_rule_validation:trade_primary_with_supplemental_audit"
    assert trade_calls == [
        "trade_rule_validation:incubation",
        "trade_rule_validation:research",
        "trade_rule_validation:incubation",
        "trade_rule_validation:live",
    ]
    assert stat_calls == ["trade_rule_validation"]
    assert result["primary_validation_layer"] == "target"
    assert result["incubation_candidate_ready"] is True


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
async def test_submission_gate_keeps_event_sample_audit_fields_on_trade_primary(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "event_trade_validation"
        assert klass is object
        return {
            "passed": True,
            "warnings": [],
            "wf_ic_ir": 0.41,
            "pkf_ic": 0.05,
            "bootstrap_ci_lower": 0.01,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {
            "strategy_type": "ma_cross",
            "params": {"short_period": 5, "long_period": 20},
            "research_task": {
                "task_source": "event_driven",
                "event_id": "evt_gate_event_samples",
                "validation_focus": "event_target_only",
            },
            "target_symbols": ["600519"],
        },
        backtest_metrics={
            "post_cost_sharpe": 0.66,
            "trade_count": 9,
            "avg_holding_days": 7,
            "turnover_proxy": 0.8,
            "target_layer_oos_return": 0.09,
            "target_layer_abnormal_return": 0.06,
            "event_window_hit_ratio": 0.75,
            "post_event_decay": -0.18,
            "trade_density": 0.45,
            "parameter_perturbation_trade_stability": 0.76,
            "primary_validation_layer": "target",
            "max_drawdown": 0.11,
            "event_study_mode": "sample_driven",
            "event_sample_count": 3,
            "event_anchor_count": 2,
            "control_group_count": 2,
            "event_sample_source": "research_task.event_samples",
            "event_time_anchors": ["2026-03-01T09:30:00+08:00", "2026-03-05T09:30:00+08:00"],
            "traceable_to_event_samples": True,
        },
        risk_report={"stress_loss_percent": -10.0},
    )

    assert result["passed"] is True
    assert result["gate_protocol"] == "event_trade_validation:trade_primary_with_supplemental_audit"
    assert result["primary_gate_protocol"] == "event_trade_validation:trade_primary"
    assert result["event_study_mode"] == "sample_driven"
    assert result["event_sample_count"] == 3
    assert result["event_anchor_count"] == 2
    assert result["control_group_count"] == 2
    assert result["event_sample_source"] == "research_task.event_samples"
    assert result["traceable_to_event_samples"] is True
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_submission_gate_rejects_minimal_event_samples_from_auto_context(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "event_trade_validation"
        assert klass is object
        return {
            "passed": True,
            "warnings": [],
            "wf_ic_ir": 0.36,
            "pkf_ic": 0.04,
            "bootstrap_ci_lower": 0.01,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {
            "strategy_type": "ma_cross",
            "params": {"short_period": 5, "long_period": 20},
            "research_task": {
                "task_source": "event_driven",
                "event_id": "evt_gate_minimal_samples",
                "validation_focus": "event_target_only",
            },
            "target_symbols": ["600519"],
        },
        backtest_metrics={
            "post_cost_sharpe": 0.66,
            "trade_count": 9,
            "avg_holding_days": 7,
            "turnover_proxy": 0.8,
            "target_layer_oos_return": 0.09,
            "target_layer_abnormal_return": 0.06,
            "event_window_hit_ratio": 0.75,
            "post_event_decay": -0.18,
            "trade_density": 0.45,
            "parameter_perturbation_trade_stability": 0.76,
            "primary_validation_layer": "target",
            "max_drawdown": 0.11,
            "event_study_mode": "sample_driven_minimal",
            "event_sample_count": 2,
            "event_anchor_count": 1,
            "control_group_count": 1,
            "event_sample_source": "auto_context_minimal",
            "event_time_anchors": ["2026-03-10T09:30:00+08:00"],
            "traceable_to_event_samples": True,
            "event_audit_incomplete": True,
        },
        risk_report={"stress_loss_percent": -10.0},
    )

    assert result["passed"] is False
    assert "event_audit_incomplete" in result["reasons"]
    assert "event_study_mode_sample_driven_minimal" in result["reasons"]
    assert "event_sample_source_auto_context_minimal" in result["reasons"]


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
    registry = result["multiple_testing_registry"]
    assert registry["task_signature"]
    assert registry["task_key"].startswith("task|")
    assert registry["strategy_family"] == "ma_cross"
    assert registry["family_key"].startswith("family|")
    assert registry["target_symbols_signature"] == "600519"
    assert registry["universe_key"].startswith("universe|")
    assert registry["template_key"].startswith("template|")
    assert registry["revision_key"].startswith("revision|")
    assert registry["formal_coverage"] is True
    assert registry["formal_runtime_ready"] is True
    assert registry["candidate_contract_hash"]
    assert registry["tested_object_hash"]
    assert registry["candidate_identity_signature"]
    assert registry["lineage_id"]
    assert registry["revision_mode"] == "baseline"
    assert registry["registry_axes"]["task"] == registry["task_key"]
    assert registry["registry_axes"]["tested_object"] == registry["tested_object_key"]
    assert registry["multiple_testing"]["pbo_value"] == pytest.approx(0.21)


@pytest.mark.asyncio
async def test_submission_gate_registry_canonicalizes_target_symbol_order(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "trade_rule_validation"
        assert klass is object
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "wf_ic_ir": 0.61,
            "pkf_ic": 0.07,
            "bootstrap_ci_lower": 0.04,
            "param_sensitivity": 0.11,
            "deflated_sharpe_ratio": 0.24,
            "pbo": 0.2,
            "white_reality_check_pvalue": 0.05,
            "hansen_spa_pvalue": 0.04,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "momentum" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {
            "strategy_type": "momentum",
            "target_symbols": ["600519", "000858"],
            "research_task": {
                "task_source": "snapshot",
                "target_symbols": ["000858", "600519"],
            },
        },
        backtest_metrics={
            "post_cost_sharpe": 0.76,
            "trade_count": 14,
            "avg_holding_days": 8,
            "turnover_proxy": 0.55,
            "target_layer_oos_return": 0.08,
            "trade_density": 0.35,
            "parameter_perturbation_trade_stability": 0.72,
            "primary_validation_layer": "target",
        },
        risk_report={"stress_loss_percent": -7.0},
    )

    assert result["multiple_testing_registry"]["target_symbols_signature"] == "000858,600519"


@pytest.mark.asyncio
async def test_submission_gate_emits_live_candidate_ready_for_strong_trade_profile(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "trade_rule_validation"
        assert klass is object
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "wf_ic_ir": 0.62,
            "pkf_ic": 0.08,
            "bootstrap_ci_lower": 0.05,
            "param_sensitivity": 0.12,
            "multiple_testing_mode": "formal_runtime",
            "deflated_sharpe_ratio": 0.28,
            "pbo": 0.18,
            "white_reality_check_pvalue": 0.04,
            "hansen_spa_pvalue": 0.03,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {"strategy_type": "ma_cross", "params": {"short_period": 5, "long_period": 20}},
        backtest_metrics={
            "post_cost_sharpe": 0.82,
            "trade_count": 16,
            "avg_holding_days": 9,
            "turnover_proxy": 0.65,
            "target_layer_oos_return": 0.15,
            "target_layer_abnormal_return": 0.09,
            "event_window_hit_ratio": 0.80,
            "post_event_decay": -0.10,
            "trade_density": 0.35,
            "parameter_perturbation_trade_stability": 0.76,
            "primary_validation_layer": "target",
            "max_drawdown": 0.14,
        },
        risk_report={"stress_loss_percent": -9.0},
    )

    assert result["passed"] is True
    assert result["incubation_candidate_ready"] is True
    assert result["live_candidate_ready"] is True
    assert result["admission_stage"] == "live"
    assert result["incubation_pass_mode"] == "strict"
    assert result["admission_evaluations"]["live"]["passed"] is True
    assert result["admission_block_reasons"] == []


@pytest.mark.asyncio
async def test_submission_gate_blocks_live_admission_when_only_proxy_multiple_testing_exists(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "trade_rule_validation"
        assert klass is object
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "wf_ic_ir": 0.62,
            "pkf_ic": 0.08,
            "bootstrap_ci_lower": 0.05,
            "param_sensitivity": 0.12,
            "multiple_testing_mode": "bootstrap_family_proxy",
            "deflated_sharpe_proxy": 0.28,
            "pbo_proxy": 0.18,
            "reality_check_pvalue_proxy": 0.04,
            "spa_pvalue_proxy": 0.03,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "ma_cross" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {"strategy_type": "ma_cross", "params": {"short_period": 5, "long_period": 20}},
        backtest_metrics={
            "post_cost_sharpe": 0.82,
            "trade_count": 16,
            "avg_holding_days": 9,
            "turnover_proxy": 0.65,
            "target_layer_oos_return": 0.15,
            "target_layer_abnormal_return": 0.09,
            "event_window_hit_ratio": 0.80,
            "post_event_decay": -0.10,
            "trade_density": 0.35,
            "parameter_perturbation_trade_stability": 0.76,
            "primary_validation_layer": "target",
            "max_drawdown": 0.14,
        },
        risk_report={"stress_loss_percent": -9.0},
    )

    assert result["passed"] is True
    assert result["incubation_candidate_ready"] is True
    assert result["live_candidate_ready"] is False
    assert result["admission_stage"] == "incubation"
    assert "formal_multiple_testing_mode_required_for_live_admission" in result["admission_block_reasons"]
    assert result["admission_evaluations"]["live"]["passed"] is False


@pytest.mark.asyncio
async def test_submission_gate_keeps_factor_profile_below_live_thresholds(monkeypatch):
    import strategy_factory.application.submission_gate as submission_gate_mod

    async def _fake_statistical_gate(_db, _strategy, *, profile, klass):
        assert profile["profile"] == "factor_rank_validation"
        assert klass is object
        return {
            "passed": True,
            "passed_strict": True,
            "reasons": [],
            "warnings": [],
            "wf_ic_ir": 0.33,
            "pkf_ic": 0.03,
            "bootstrap_ci_lower": 0.01,
            "param_sensitivity": 0.22,
            "deflated_sharpe_proxy": 0.04,
            "pbo_proxy": 0.48,
            "reality_check_pvalue_proxy": 0.18,
            "spa_pvalue_proxy": 0.16,
        }

    monkeypatch.setattr(
        submission_gate_mod,
        "get_strategy_registry",
        lambda: SimpleNamespace(get=lambda strategy_type: object if strategy_type == "value_factor" else None),
    )
    monkeypatch.setattr(submission_gate_mod, "_run_statistical_gate", _fake_statistical_gate)

    result = await run_submission_quality_gate(
        MagicMock(),
        {"strategy_type": "value_factor", "params": {"lookback": 60}},
        backtest_metrics={"primary_validation_layer": "combined"},
        risk_report={"stress_loss_percent": -8.0},
    )

    assert result["passed"] is True
    assert result["research_candidate_ready"] is True
    assert result["incubation_candidate_ready"] is True
    assert result["live_candidate_ready"] is False
    assert result["admission_stage"] == "incubation"
    assert result["admission_evaluations"]["incubation"]["passed"] is True
    assert result["admission_evaluations"]["live"]["passed"] is False
    assert result["admission_block_reasons"]

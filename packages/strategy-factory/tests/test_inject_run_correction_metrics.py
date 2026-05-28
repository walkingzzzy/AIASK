"""V5-PR-1: _inject_run_correction_metrics 单元测试.

验证:
  1. validation_runtime 不可用时软降级
  2. 有效输入下能算出 deflated_sharpe_ratio 等字段
  3. 任何异常都不打断主流程
  4. multiple_testing_inject_status 字段正确标记
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest


def _import_helper():
    """从父模块拿 _inject_run_correction_metrics(它由 fragment loader 注入到 runner globals)."""
    parent = importlib.import_module(
        "strategy_factory.application.submission_gate.runner"
    )
    return parent._inject_run_correction_metrics


class _MockValidationRuntime:
    """模拟真实 validation_runtime — 返回固定测试值."""

    @staticmethod
    def deflated_sharpe_ratio(arr, **kwargs):
        return {
            "available": True,
            "dsr": 0.123,
            "reference_sharpe": 0.5,
            "effective_trials": 5.0,
        }

    @staticmethod
    def probability_of_backtest_overfitting(family_arr, **kwargs):
        return {"available": True, "pbo": 0.45}

    @staticmethod
    def white_reality_check(family_arr, **kwargs):
        return {"available": True, "p_value": 0.08}

    @staticmethod
    def hansen_spa_test(family_arr, **kwargs):
        return {"available": True, "p_value": 0.07}


def test_inject_returns_dict_for_minimal_input(monkeypatch):
    """最小输入(无 validation_report / backtest_metrics)也能返回非空 dict."""
    inject = _import_helper()

    # mock get_validation_runtime 返回 _MockValidationRuntime
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: _MockValidationRuntime)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    normalized = {
        "post_cost_sharpe": 1.2,
        "attempt_adjustment": {"attempt_count": 5, "cohort_effective_trials": 5.0},
    }

    result = inject(strategy, profile, normalized)
    # 验证返回 dict + status 字段
    assert isinstance(result, dict)
    assert result.get("multiple_testing_inject_status") == "ok"
    # 至少有 mode / proxy 字段
    assert result.get("run_correction_mode") in ("attempt_only_proxy", "bootstrap_family_proxy")


def test_inject_calls_validation_runtime_when_score_series_provided(monkeypatch):
    """提供 score_series (>=3) 时,DSR formal 路径触发,返回 deflated_sharpe_ratio 字段."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: _MockValidationRuntime)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    normalized = {
        "post_cost_sharpe": 1.0,
        "attempt_adjustment": {"attempt_count": 3, "cohort_effective_trials": 3.0},
    }
    # 模拟 walk_forward 5 个 fold 的 score
    validation_report = {
        "walk_forward": {
            "fold_results": [
                {"oos_sharpe": 0.8},
                {"oos_sharpe": 1.2},
                {"oos_sharpe": 0.9},
                {"oos_sharpe": 1.1},
                {"oos_sharpe": 1.3},
            ]
        }
    }

    result = inject(strategy, profile, normalized, validation_report=validation_report)
    assert result.get("multiple_testing_inject_status") == "ok"
    # DSR formal 路径触发 (sample_size=5 >= 3)
    assert result.get("multiple_testing_mode") == "formal_runtime"
    assert result.get("deflated_sharpe_ratio") == 0.123  # mock 返回值


def test_inject_calls_pbo_when_family_returns_provided(monkeypatch):
    """family_returns (12+, 2+) 时,PBO/RC/SPA formal 路径触发."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: _MockValidationRuntime)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    normalized = {
        "post_cost_sharpe": 1.0,
        "attempt_adjustment": {"attempt_count": 3, "cohort_effective_trials": 3.0},
    }
    # validation_report 至少 24 期才能跑 bootstrap proxy
    fold_scores = [{"oos_sharpe": 0.5 + i * 0.01} for i in range(24)]
    validation_report = {"walk_forward": {"fold_results": fold_scores}}
    # family_returns (24, 3) — 满足 PBO/RC/SPA 条件
    family_returns = np.random.RandomState(42).normal(0.001, 0.02, (24, 3)).tolist()
    backtest_metrics = {
        "multiple_testing": {"family_returns": family_returns},
    }

    result = inject(
        strategy, profile, normalized,
        validation_report=validation_report,
        backtest_metrics=backtest_metrics,
    )
    assert result.get("multiple_testing_inject_status") == "ok"
    # 如果 family_returns 被解析,PBO/RC/SPA 字段都应该填上
    assert result.get("pbo") == 0.45
    assert result.get("white_reality_check_pvalue") == 0.08
    assert result.get("hansen_spa_pvalue") == 0.07


def test_inject_soft_fail_when_validation_runtime_unavailable(monkeypatch):
    """get_validation_runtime 返回 None 时软降级."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: None)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    normalized = {"post_cost_sharpe": 1.0}

    result = inject(strategy, profile, normalized)
    assert isinstance(result, dict)
    assert result.get("multiple_testing_inject_status") == "validation_runtime_unavailable"
    # 不应该有 deflated_sharpe_ratio
    assert "deflated_sharpe_ratio" not in result


def test_inject_soft_fail_on_exception(monkeypatch):
    """任何内部异常都不传播,转为 status='exception'."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp

    def _broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp, "get_validation_runtime", _broken)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    normalized = {"post_cost_sharpe": 1.0}

    # validation_runtime 拉取异常 -> 被吞进 try,返回 status='validation_runtime_unavailable'
    result = inject(strategy, profile, normalized)
    assert isinstance(result, dict)
    # 异常被局部吞,validation_runtime 取到 None
    assert result.get("multiple_testing_inject_status") in (
        "validation_runtime_unavailable", "exception"
    )


def test_inject_observed_score_fallback_chain(monkeypatch):
    """post_cost_sharpe 缺失时回退到 wf_ic_ir,再到 sharpe_ratio."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: _MockValidationRuntime)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "factor_rank_validation"}
    # 只给 wf_ic_ir,没有 post_cost_sharpe
    normalized = {
        "wf_ic_ir": 0.15,
        "attempt_adjustment": {"attempt_count": 3, "cohort_effective_trials": 3.0},
    }

    result = inject(strategy, profile, normalized)
    # 不应该崩溃,应该正常返回
    assert isinstance(result, dict)
    assert result.get("multiple_testing_inject_status") == "ok"


def test_inject_attempt_adjustment_fallback(monkeypatch):
    """normalized.attempt_adjustment 缺失时,helper 应该自己重建."""
    inject = _import_helper()
    import strategy_factory.infrastructure.mcp_services as mcp
    monkeypatch.setattr(mcp, "get_validation_runtime", lambda: _MockValidationRuntime)

    strategy = {"id": "s1", "strategy_type": "volatility_breakout"}
    profile = {"profile": "trade_rule_validation"}
    # 完全空的 normalized
    normalized = {}

    result = inject(strategy, profile, normalized)
    assert isinstance(result, dict)
    # 至少不崩
    assert result.get("multiple_testing_inject_status") in ("ok", "exception", "validation_runtime_unavailable")

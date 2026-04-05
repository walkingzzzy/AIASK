from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import akshare_mcp.services.strategy_factory.runtime as legacy_runtime

from strategy_factory.application.quality_gates import (
    gate_0_structural,
    gate_1_fast_screen,
    pre_gate_screen,
    run_gated_filter,
)


def _complete_candidate(candidate: dict) -> dict:
    defaults = {
        "holding_horizon": {"max_days": 10},
        "trade_plan": {"entry_bias": "signal_confirmed", "exit_bias": "signal_or_time_stop"},
        "risk_rules": {"stop_loss_pct": 0.08, "take_profit_pct": 0.18, "max_holding_days": 10},
        "rebalance_rule": {"mode": "signal_rebalance"},
        "portfolio_spec": {"position_assumption": "single_name_full_notional", "target_weight_scheme": "single_name"},
        "execution_assumptions": {"slippage_bps": 5, "commission_rate": 0.00025, "tradability_filter": True},
        "validation_profile": {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
    }
    enriched = dict(candidate or {})
    params = dict(enriched.get("params") or {})
    for key, value in defaults.items():
        enriched.setdefault(key, dict(value))
        params.setdefault(key, dict(value))
    enriched["params"] = params
    return enriched


def test_gate_0_structural_compiles_dsl_with_strategy_dsl_module():
    candidate = {
        "strategy_type": "dsl_rule",
        "params": {
            "holding_horizon": {"max_days": 10},
            "trade_plan": {"entry_bias": "signal_confirmed"},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "rebalance_rule": {"mode": "signal_rebalance"},
            "portfolio_spec": {"target_weight_scheme": "single_name"},
            "execution_assumptions": {"slippage_bps": 5, "tradability_filter": True},
            "validation_profile": {"profile": "trade_rule_validation"},
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
            }
        },
    }

    result = gate_0_structural(candidate)

    assert result.passed is True
    assert result.reasons == []


def test_gate_0_structural_rejects_incomplete_trade_contract():
    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
    }

    result = gate_0_structural(candidate)

    assert result.passed is False
    assert any(reason.startswith("missing_trade_fields:") for reason in result.reasons)
    missing_reason = next(reason for reason in result.reasons if reason.startswith("missing_trade_fields:"))
    assert "holding_horizon" in missing_reason
    assert "trade_plan" in missing_reason
    assert "validation_profile" in missing_reason


@pytest.mark.asyncio
async def test_gate_1_fast_screen_uses_backtest_engine_run_backtest(monkeypatch):
    calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            calls.append(
                {
                    "code": code,
                    "klines_len": len(klines),
                    "strategy": strategy,
                    "params": dict(params or {}),
                }
            )
            return {"success": True, "data": {"sharpe_ratio": 1.25}}

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    db = SimpleNamespace(
        get_klines=AsyncMock(
            side_effect=[
                [{"close": float(i + 1), "volume": 1000.0} for i in range(40)],
                [{"close": float(i + 2), "volume": 1000.0} for i in range(40)],
            ]
        )
    )

    result = await gate_1_fast_screen(
        _complete_candidate({
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519", "000858"],
            "research_task": {
                "gate_1_representative_count": 2,
                "target_symbols": ["600519", "000858"],
            },
        }),
        db,
    )

    assert result.passed is True
    assert result.metrics["avg_sharpe"] == 1.25
    assert [item["code"] for item in calls] == result.metrics["tested_codes"]
    assert calls[0]["code"] == "600519"


@pytest.mark.asyncio
async def test_gate_1_fast_screen_dispatches_backtest_via_asyncio_to_thread(monkeypatch):
    to_thread_calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            return {"success": True, "data": {"sharpe_ratio": 0.8}}

    async def _fake_to_thread(fn, *args, **kwargs):
        to_thread_calls.append((fn, args, kwargs))
        return fn(*args, **kwargs)

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )
    monkeypatch.setattr("strategy_factory.application.quality_gates.asyncio.to_thread", _fake_to_thread)

    db = SimpleNamespace(
        get_klines=AsyncMock(
            side_effect=[
                [{"close": float(i + 1), "volume": 1000.0} for i in range(40)],
                [{"close": float(i + 2), "volume": 1000.0} for i in range(40)],
            ]
        )
    )

    result = await gate_1_fast_screen(
        _complete_candidate({"strategy_type": "momentum", "params": {"lookback": 20}}),
        db,
    )

    assert result.passed is True
    assert len(to_thread_calls) == len(result.metrics["tested_codes"])
    assert all(call[0] is _FakeBacktestEngine.run_backtest for call in to_thread_calls)


@pytest.mark.asyncio
async def test_gate_1_fast_screen_records_turnover_and_return_aggregates(monkeypatch):
    responses = [
        {"success": True, "data": {"sharpe_ratio": 0.4, "total_return": 0.02, "turnover_proxy": 1.8, "trades_count": 6, "max_drawdown": 0.08}},
        {"success": True, "data": {"sharpe_ratio": 0.8, "total_return": 0.04, "turnover_proxy": 1.2, "trades_count": 8, "max_drawdown": 0.12}},
    ]

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(_code, _klines, _strategy, _params):
            return responses.pop(0)

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    db = SimpleNamespace(
        get_klines=AsyncMock(
            side_effect=[
                [{"close": float(i + 1), "volume": 1000.0} for i in range(40)],
                [{"close": float(i + 2), "volume": 1000.0} for i in range(40)],
            ]
        )
    )

    result = await gate_1_fast_screen(
        _complete_candidate({
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519", "000858"],
            "research_task": {
                "gate_1_representative_count": 2,
                "target_symbols": ["600519", "000858"],
            },
        }),
        db,
    )

    assert result.metrics["avg_sharpe"] == 0.6
    assert result.metrics["avg_total_return"] == 0.03
    assert result.metrics["avg_turnover_proxy"] == 1.5
    assert result.metrics["avg_trades_count"] == 7.0
    assert result.metrics["avg_max_drawdown"] == 0.1


@pytest.mark.asyncio
async def test_gate_1_fast_screen_uses_single_representative_for_bulk_stock_matrix(monkeypatch):
    calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            calls.append({"code": code, "strategy": strategy, "params": dict(params or {})})
            return {"success": True, "data": {"sharpe_ratio": 0.9}}

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    db = SimpleNamespace(
        get_klines=AsyncMock(return_value=[{"close": float(i + 1), "volume": 1000.0} for i in range(40)])
    )

    result = await gate_1_fast_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "target_symbols": ["600519"],
            },
            "target_symbols": ["600519"],
        },
        db,
    )

    assert result.passed is True
    assert result.metrics["tested_codes"] == ["600519"]
    assert [item["code"] for item in calls] == ["600519"]


@pytest.mark.asyncio
async def test_gate_1_fast_screen_expands_pipeline_staged_ma_cross_snapshot_to_five_targets(monkeypatch):
    calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            calls.append(code)
            return {"success": True, "data": {"sharpe_ratio": 0.8}}

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    target_symbols = ["601288", "601988", "600941", "601318", "300439", "601113", "601919", "601666"]
    db = SimpleNamespace(
        get_klines=AsyncMock(return_value=[{"close": float(i + 1), "volume": 1000.0} for i in range(40)])
    )

    result = await gate_1_fast_screen(
        _complete_candidate(
            {
                "strategy_type": "ma_cross",
                "params": {"short_period": 6, "long_period": 24},
                "tags": ["pipeline_staged", "targeted_universe", "generator_pipeline_staged"],
                "target_symbols": target_symbols,
                "research_task": {
                    "task_source": "snapshot",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": target_symbols,
                },
            }
        ),
        db,
    )

    assert result.passed is True
    assert result.metrics["tested_codes"] == target_symbols[:5]
    assert calls == target_symbols[:5]


@pytest.mark.asyncio
async def test_gate_1_fast_screen_expands_pipeline_staged_rsi_snapshot_to_four_targets(monkeypatch):
    calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            calls.append(code)
            return {"success": True, "data": {"sharpe_ratio": 0.8}}

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    target_symbols = ["601998", "601607", "001872", "002142", "601919", "601113", "600780", "600483"]
    db = SimpleNamespace(
        get_klines=AsyncMock(return_value=[{"close": float(i + 1), "volume": 1000.0} for i in range(40)])
    )

    result = await gate_1_fast_screen(
        _complete_candidate(
            {
                "strategy_type": "rsi",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "tags": ["pipeline_staged", "targeted_universe", "generator_pipeline_staged"],
                "target_symbols": target_symbols,
                "research_task": {
                    "task_source": "snapshot",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": target_symbols,
                },
            }
        ),
        db,
    )

    assert result.passed is True
    assert result.metrics["tested_codes"] == target_symbols[:4]
    assert calls == target_symbols[:4]


@pytest.mark.asyncio
async def test_run_gated_filter_applies_pre_gate_before_gate_1(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    gate_1_calls = []

    async def _fake_gate_1(candidate, _db, **_kwargs):
        gate_1_calls.append(candidate["candidate_id"])
        return gates_mod.GateResult(passed=True, gate="gate_1", reasons=[], metrics={"avg_sharpe": 0.6})

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            return list(candidates)

        def get_last_report(self):
            return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}}

    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    bulk_task = {
        "task_source": "bulk_stock_matrix",
        "target_symbols": ["600519"],
        "allowed_strategy_types": ["momentum"],
    }
    candidates = [
        _complete_candidate({
            "candidate_id": "kept",
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "research_task": bulk_task,
            "target_symbols": ["600519"],
        }),
        _complete_candidate({
            "candidate_id": "duplicate",
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "research_task": bulk_task,
            "target_symbols": ["600519"],
        }),
        _complete_candidate({
            "candidate_id": "outside_allowed",
            "strategy_type": "rsi",
            "params": {"rsi_period": 14},
            "research_task": bulk_task,
            "target_symbols": ["600519"],
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    pre_gate = result["gate_report"]["pre_gate"]
    assert pre_gate["failed_count"] == 2
    assert gate_1_calls == ["kept"]
    assert {"duplicate_candidate_signature", "outside_allowed_strategy_types"} <= {
        reason
        for item in pre_gate["failed"]
        for reason in list(item.get("reasons") or [])
    }


@pytest.mark.asyncio
async def test_run_gated_filter_uses_priority_queue_for_gate_2(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    async def _fake_gate_1(candidate, _db, **_kwargs):
        avg_sharpe = 0.7 if candidate["candidate_id"] == "high_sharpe_low_priority" else 0.5
        return gates_mod.GateResult(passed=True, gate="gate_1", reasons=[], metrics={"avg_sharpe": avg_sharpe})

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {"summary": {"input_count": len(captured_gate_2_ids), "passed_count": len(captured_gate_2_ids), "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}}

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 0.5
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "high_sharpe_low_priority",
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "target_symbols": ["600519"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "allowed_strategy_types": ["momentum"],
                "target_symbols": ["600519"],
                "matrix_priority_score": 10.0,
                "stock_family_priority": 0.1,
            },
        }),
        _complete_candidate({
            "candidate_id": "lower_sharpe_high_priority",
            "strategy_type": "value_factor",
            "params": {"lookback": 60},
            "target_symbols": ["000001"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "allowed_strategy_types": ["value_factor"],
                "target_symbols": ["000001"],
                "matrix_priority_score": 60.0,
                "stock_family_priority": 0.9,
            },
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["lower_sharpe_high_priority"]
    assert result["gate_report"]["gate_1"]["selection_mode"] == "priority_queue"
    assert result["gate_report"]["gate_1"]["passed_candidates"][0]["strategy_type"] == "value_factor"


@pytest.mark.asyncio
async def test_run_gated_filter_preloads_gate_1_kline_cache(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    observed_cache_keys = []

    async def _fake_gate_1(candidate, _db, **kwargs):
        observed_cache_keys.append(
            {
                "candidate_id": candidate["candidate_id"],
                "cache_keys": sorted((kwargs.get("kline_cache") or {}).keys()),
            }
        )
        return gates_mod.GateResult(passed=True, gate="gate_1", reasons=[], metrics={"avg_sharpe": 0.62})

    class _DummyBacktestFilter:
        def __init__(self):
            self._kline_cache = {}
            self.preloaded_codes = []

        async def preload_klines(self, _db, codes=None):
            self.preloaded_codes = list(codes or [])
            for code in self.preloaded_codes:
                self._kline_cache[code] = [{"close": 10.0, "volume": 1000.0}]

        async def filter(self, candidates, _db):
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": 2,
                    "passed_count": 2,
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "bulk_1",
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "target_symbols": ["600519"],
                "allowed_strategy_types": ["momentum"],
            },
        }),
        _complete_candidate({
            "candidate_id": "bulk_2",
            "strategy_type": "value_factor",
            "params": {"lookback": 60},
            "target_symbols": ["000858"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "target_symbols": ["000858"],
                "allowed_strategy_types": ["value_factor"],
            },
        }),
    ]

    backtest_filter = _DummyBacktestFilter()
    result = await run_gated_filter(
        candidates,
        SimpleNamespace(),
        backtest_filter,
        kline_cache=backtest_filter._kline_cache,
    )

    assert backtest_filter.preloaded_codes == ["600519", "000858"]
    assert result["summary"]["gate_1_preload_code_count"] == 2
    assert result["summary"]["gate_1_kline_cache_ready"] is True
    assert result["gate_report"]["gate_1"]["preload_status"] == "ready"
    assert all(item["cache_keys"] == ["000858", "600519"] for item in observed_cache_keys)


def test_pre_gate_rejects_low_liquidity_single_name_candidate():
    result = pre_gate_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["300001"],
            "research_task": {
                "task_source": "bulk_stock_matrix",
                "target_symbols": ["300001"],
                "allowed_strategy_types": ["momentum"],
                "liquidity_requirement": "high",
                "source_symbol_summary": {
                    "code": "300001",
                    "market_cap": 1_200_000_000,
                },
            },
        },
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=3,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "liquidity_below_requirement" in result.reasons
    assert result.metrics["liquidity_proxy_kind"] == "market_cap"


def test_pre_gate_rejects_snapshot_candidate_with_zero_target_alignment():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519", "000858", "601398", "601939"],
                "tags": ["targeted_universe", "pipeline_staged"],
                "constraint_check": {"coverage_ratio": 0.0, "intersection_ratio": 0.0},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_misaligned",
                    "validation_focus": "candidate_target_only",
                    "target_symbols": ["600519", "000858", "601398", "601939"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 0.0
    assert result.metrics["intersection_ratio"] == 0.0


def test_pre_gate_rejects_low_alignment_rl_bandit_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "momentum",
                "generator_type": "rl_bandit",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["601628", "600030", "601211", "000776"],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 0.1, "intersection_ratio": 0.12},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_rl_low_alignment",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601628", "600030", "601211", "000776"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 0.1
    assert result.metrics["intersection_ratio"] == 0.12


def test_pre_gate_rejects_moderately_low_alignment_rl_bandit_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "momentum",
                "generator_type": "rl_bandit",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901", "601018", "002736"],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 0.25, "intersection_ratio": 0.375},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_rl_mid_alignment",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901", "601018", "002736"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 0.25
    assert result.metrics["intersection_ratio"] == 0.375


def test_pre_gate_rejects_newly_tightened_alignment_rl_bandit_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "momentum",
                "generator_type": "rl_bandit",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901"],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 0.29, "intersection_ratio": 0.44},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_rl_tightened_alignment",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 0.29
    assert result.metrics["intersection_ratio"] == 0.44


def test_pre_gate_rejects_low_intersection_pipeline_staged_rsi_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "rsi",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
                "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
                "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.375},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_pipeline_rsi_low_intersection",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601766", "600528", "600582", "600894", "603855", "603279", "920599", "002833"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 1.0
    assert result.metrics["intersection_ratio"] == 0.375


def test_pre_gate_rejects_newly_tightened_pipeline_staged_rsi_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "rsi",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
                "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
                "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.45},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_pipeline_rsi_tightened_intersection",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601766", "600528", "600582", "600894", "603855", "603279", "920599", "002833"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["intersection_ratio"] == 0.45


def test_pre_gate_rejects_low_intersection_rl_bandit_volatility_breakout_snapshot_candidate():
    result = pre_gate_screen(
        _complete_candidate(
            {
                "strategy_type": "volatility_breakout",
                "generator_type": "rl_bandit",
                "params": {
                    "generator_mode": "rl_bandit",
                    "dsl": {
                        "metadata": {
                            "strategy_profile": {
                                "generator_mode": "rl_bandit",
                            }
                        }
                    }
                },
                "target_symbols": [
                    "601666",
                    "601825",
                    "600000",
                    "601117",
                    "600027",
                    "600035",
                    "601598",
                    "300439",
                    "601288",
                    "601988",
                    "600941",
                    "601318",
                ],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.125},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_rl_vol_breakout_low_intersection",
                    "validation_focus": "target_plus_representative",
                    "target_symbols": ["601825", "600000", "601117", "601666", "600027", "600035", "601598", "300439"],
                },
            }
        ),
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=6,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert "target_universe_alignment_too_low" in result.reasons
    assert result.metrics["coverage_ratio"] == 1.0
    assert result.metrics["intersection_ratio"] == 0.125


@pytest.mark.parametrize(
    ("candidate", "expected_reason"),
    [
        (
            {
                "strategy_type": "momentum",
                "params": {"lookback": 252, "threshold": 0.05},
                "target_symbols": ["600519"],
                "research_task": {
                    "task_source": "bulk_stock_matrix",
                    "target_symbols": ["600519"],
                    "allowed_strategy_types": ["momentum"],
                },
            },
            "signal_density_too_sparse",
        ),
        (
            {
                "strategy_type": "mean_reversion_short",
                "params": {"rsi_period": 2, "oversold": 45, "overbought": 55},
                "target_symbols": ["600519"],
                "research_task": {
                    "task_source": "bulk_stock_matrix",
                    "target_symbols": ["600519"],
                    "allowed_strategy_types": ["mean_reversion_short"],
                },
            },
            "signal_density_too_dense",
        ),
    ],
)
def test_pre_gate_rejects_signal_density_outliers(candidate, expected_reason):
    result = pre_gate_screen(
        candidate,
        seen_signatures=set(),
        family_counts={},
        stock_counts={},
        family_quota_limit=4,
        per_stock_quota_limit=5,
    )

    assert result.passed is False
    assert expected_reason in result.reasons


def test_pre_gate_enforces_family_and_per_stock_quotas():
    seen_signatures = set()
    family_counts = {}
    stock_counts = {}

    family_task = {
        "task_source": "bulk_stock_matrix",
        "allowed_strategy_types": ["momentum"],
    }
    first = pre_gate_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519"],
            "research_task": {**family_task, "target_symbols": ["600519"]},
        },
        seen_signatures=seen_signatures,
        family_counts=family_counts,
        stock_counts=stock_counts,
        family_quota_limit=2,
        per_stock_quota_limit=5,
    )
    second = pre_gate_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 30, "threshold": 0.02},
            "target_symbols": ["000858"],
            "research_task": {**family_task, "target_symbols": ["000858"]},
        },
        seen_signatures=seen_signatures,
        family_counts=family_counts,
        stock_counts=stock_counts,
        family_quota_limit=2,
        per_stock_quota_limit=5,
    )
    third = pre_gate_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 40, "threshold": 0.02},
            "target_symbols": ["601318"],
            "research_task": {**family_task, "target_symbols": ["601318"]},
        },
        seen_signatures=seen_signatures,
        family_counts=family_counts,
        stock_counts=stock_counts,
        family_quota_limit=2,
        per_stock_quota_limit=5,
    )

    assert first.passed is True
    assert second.passed is True
    assert third.passed is False
    assert "family_quota_exceeded" in third.reasons

    per_stock_seen = set()
    per_stock_family_counts = {}
    per_stock_counts = {}
    base_task = {
        "task_source": "bulk_stock_matrix",
        "target_symbols": ["600519"],
    }
    first_stock = pre_gate_screen(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["600519"],
            "research_task": {**base_task, "allowed_strategy_types": ["momentum"]},
        },
        seen_signatures=per_stock_seen,
        family_counts=per_stock_family_counts,
        stock_counts=per_stock_counts,
        family_quota_limit=5,
        per_stock_quota_limit=2,
    )
    second_stock = pre_gate_screen(
        {
            "strategy_type": "rsi",
            "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
            "target_symbols": ["600519"],
            "research_task": {**base_task, "allowed_strategy_types": ["rsi"]},
        },
        seen_signatures=per_stock_seen,
        family_counts=per_stock_family_counts,
        stock_counts=per_stock_counts,
        family_quota_limit=5,
        per_stock_quota_limit=2,
    )
    third_stock = pre_gate_screen(
        {
            "strategy_type": "value_factor",
            "params": {"lookback": 60},
            "target_symbols": ["600519"],
            "research_task": {**base_task, "allowed_strategy_types": ["value_factor"]},
        },
        seen_signatures=per_stock_seen,
        family_counts=per_stock_family_counts,
        stock_counts=per_stock_counts,
        family_quota_limit=5,
        per_stock_quota_limit=2,
    )

    assert first_stock.passed is True
    assert second_stock.passed is True
    assert third_stock.passed is False
    assert "per_stock_quota_exceeded" in third_stock.reasons


def test_pre_gate_uses_fractional_stock_quota_for_basket_candidates():
    seen_signatures = set()
    family_counts = {}
    stock_counts = {}
    base_task = {
        "task_source": "snapshot",
        "opportunity_type": "sector_breakout",
        "target_symbols": ["600519", "000858", "601318", "600036"],
        "validation_focus": "target_plus_representative",
    }

    results = []
    for index, lookback in enumerate((8, 10, 12, 15, 18), 1):
        results.append(
            pre_gate_screen(
                {
                    "candidate_id": f"basket_{index}",
                    "strategy_type": "momentum",
                    "params": {"lookback": lookback, "threshold": 0.01},
                    "target_symbols": ["600519", "000858", "601318", "600036"],
                    "research_task": dict(base_task),
                },
                seen_signatures=seen_signatures,
                family_counts=family_counts,
                stock_counts=stock_counts,
                family_quota_limit=10,
                per_stock_quota_limit=2,
            )
        )

    assert [item.passed for item in results] == [True, True, True, True, False]
    assert results[-1].metrics["per_stock_quota_increment"] == 0.5
    assert "per_stock_quota_exceeded" in results[-1].reasons


@pytest.mark.asyncio
async def test_run_gated_filter_deprioritizes_generic_candidates_without_target_symbols(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    async def _fake_gate_1(candidate, _db, **_kwargs):
        score_map = {
            "generic_spawner": 0.58,
            "targeted_snapshot": 0.52,
            "targeted_snapshot_2": 0.5,
        }
        return gates_mod.GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics={"avg_sharpe": score_map[candidate["candidate_id"]]},
        )

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": len(captured_gate_2_ids),
                    "passed_count": len(captured_gate_2_ids),
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 0.34
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "generic_spawner",
            "strategy_type": "ma_cross",
            "params": {"short_period": 5, "long_period": 20},
        }),
        _complete_candidate({
            "candidate_id": "targeted_snapshot",
            "strategy_type": "momentum",
            "params": {"lookback": 10, "threshold": 0.01},
            "target_symbols": ["688981", "002371"],
            "tags": ["targeted_universe", "pipeline_staged"],
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_chip",
                "opportunity_type": "sector_breakout",
                "priority": 80,
                "validation_focus": "candidate_target_only",
                    "target_symbols": ["688981", "002371"],
                },
        }),
        _complete_candidate({
            "candidate_id": "targeted_snapshot_2",
            "strategy_type": "quality_factor",
            "params": {"lookback": 30, "buy_quantile": 0.7, "sell_quantile": 0.3},
            "target_symbols": ["300750", "002594"],
            "tags": ["targeted_universe", "pipeline_staged"],
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_battery",
                "opportunity_type": "industry_leadership",
                "priority": 60,
                "validation_focus": "candidate_target_only",
                    "target_symbols": ["300750", "002594"],
                },
        }),
    ]

    await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["targeted_snapshot"]


@pytest.mark.asyncio
async def test_run_gated_filter_penalizes_fragile_snapshot_baskets_before_gate_2(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    score_map = {
        "fragile_snapshot": {"avg_sharpe": 0.58, "avg_turnover_proxy": 2.1, "avg_total_return": -0.01},
        "clean_snapshot": {"avg_sharpe": 0.52, "avg_turnover_proxy": 0.35, "avg_total_return": 0.03},
    }

    async def _fake_gate_1(candidate, _db, **_kwargs):
        return gates_mod.GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics=dict(score_map[candidate["candidate_id"]]),
        )

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": len(captured_gate_2_ids),
                    "passed_count": len(captured_gate_2_ids),
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 0.34
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "fragile_snapshot",
            "strategy_type": "momentum",
            "params": {"lookback": 10, "threshold": 0.01},
            "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901", "601018", "002736"],
            "tags": ["targeted_universe", "pipeline_staged"],
            "constraint_check": {"coverage_ratio": 0.2, "intersection_ratio": 0.15},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_rotation_fragile",
                "opportunity_type": "rotation_balanced",
                "priority": 80,
                "validation_focus": "candidate_target_only",
                "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901", "601018", "002736"],
            },
        }),
        _complete_candidate({
            "candidate_id": "clean_snapshot",
            "strategy_type": "quality_factor",
            "params": {"lookback": 30, "buy_quantile": 0.7, "sell_quantile": 0.3},
            "target_symbols": ["300750", "002594", "601899", "603993"],
            "tags": ["targeted_universe", "pipeline_staged"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.75},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_battery_clean",
                "opportunity_type": "industry_leadership",
                "priority": 60,
                "validation_focus": "candidate_target_only",
                "target_symbols": ["300750", "002594", "601899", "603993"],
            },
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["clean_snapshot"]
    assert result["gate_report"]["gate_1"]["passed_candidates"][0]["strategy_type"] == "quality_factor"


@pytest.mark.asyncio
async def test_run_gated_filter_penalizes_high_turnover_pipeline_ma_cross_before_gate_2(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    score_map = {
        "fragile_pipeline_ma": {"avg_sharpe": 1.05, "avg_turnover_proxy": 2.15, "avg_total_return": 0.005},
        "steady_breakout": {"avg_sharpe": 0.92, "avg_turnover_proxy": 0.85, "avg_total_return": 0.032},
    }

    async def _fake_gate_1(candidate, _db, **_kwargs):
        return gates_mod.GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics=dict(score_map[candidate["candidate_id"]]),
        )

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": len(captured_gate_2_ids),
                    "passed_count": len(captured_gate_2_ids),
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 1.0
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "fragile_pipeline_ma",
            "strategy_type": "ma_cross",
            "generator_type": "pipeline_staged",
            "params": {"short_period": 5, "long_period": 20},
            "target_symbols": ["601288", "601988", "600941", "601318"],
            "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.5},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_rotation_ma",
                "opportunity_type": "rotation_balanced",
                "validation_focus": "target_plus_representative",
                "target_symbols": ["601288", "601988", "600941", "601318"],
            },
        }),
        _complete_candidate({
            "candidate_id": "steady_breakout",
            "strategy_type": "volatility_breakout",
            "generator_type": "pipeline_staged",
            "params": {"lookback": 20, "atr_window": 14, "breakout_pct": 0.03},
            "target_symbols": ["601666", "601825", "600000", "601117"],
            "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.375},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_factor_breakout",
                "opportunity_type": "factor_acceleration",
                "validation_focus": "target_plus_representative",
                "target_symbols": ["601666", "601825", "600000", "601117"],
            },
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["steady_breakout"]
    assert result["gate_report"]["gate_1"]["passed_candidates"][0]["strategy_type"] == "volatility_breakout"


@pytest.mark.asyncio
async def test_run_gated_filter_blocks_low_sample_snapshot_candidate_before_gate_2(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    score_map = {
        "fragile_rsi_snapshot": {
            "avg_sharpe": 0.96,
            "avg_turnover_proxy": 0.82,
            "avg_total_return": 0.028,
            "target_codes": ["603855", "603279", "002833"],
            "sharpe_values": [1.05, 0.92, 0.88],
        },
        "steady_snapshot": {
            "avg_sharpe": 0.9,
            "avg_turnover_proxy": 0.76,
            "avg_total_return": 0.031,
            "target_codes": ["601666", "601825", "600000", "601117"],
            "sharpe_values": [0.95, 0.88, 0.9, 0.87],
        },
    }

    async def _fake_gate_1(candidate, _db, **_kwargs):
        return gates_mod.GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics=dict(score_map[candidate["candidate_id"]]),
        )

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": len(captured_gate_2_ids),
                    "passed_count": len(captured_gate_2_ids),
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 1.0
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
            _complete_candidate({
                "candidate_id": "fragile_rsi_snapshot",
                "strategy_type": "rsi",
                "generator_type": "pipeline_staged",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "target_symbols": ["603855", "603279", "002833"],
                "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
                "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.625, "target_overlap_count": 5},
                "research_task": {
                    "task_source": "snapshot",
                    "task_id": "task_pipeline_rsi_sample",
                "validation_focus": "target_plus_representative",
                "allowed_strategy_types": ["rsi"],
                "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
            },
        }),
        _complete_candidate({
            "candidate_id": "steady_snapshot",
            "strategy_type": "volatility_breakout",
            "generator_type": "pipeline_staged",
            "params": {"lookback": 20, "atr_window": 14, "breakout_pct": 0.03},
            "target_symbols": ["601666", "601825", "600000", "601117"],
            "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 1.0, "target_overlap_count": 4},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_breakout_steady",
                "validation_focus": "target_plus_representative",
                "target_symbols": ["601666", "601825", "600000", "601117"],
            },
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["steady_snapshot"]
    fragile_result = next(
        item for item in result["gate_report"]["gate_1"]["failed"]
        if item["strategy_type"] == "rsi"
    )
    assert "target_sample_sufficiency_too_low" in fragile_result["reasons"]


@pytest.mark.asyncio
async def test_run_gated_filter_blocks_low_stability_snapshot_candidate_before_gate_2(monkeypatch):
    import strategy_factory.application.quality_gates as gates_mod

    score_map = {
        "fragile_rl_momentum": {
            "avg_sharpe": 1.08,
            "avg_turnover_proxy": 0.68,
            "avg_total_return": 0.036,
            "target_codes": ["601628", "600030", "601211"],
            "sharpe_values": [1.65, 0.22, 0.18],
        },
        "clean_quality_snapshot": {
            "avg_sharpe": 0.93,
            "avg_turnover_proxy": 0.41,
            "avg_total_return": 0.029,
            "target_codes": ["300750", "002594", "601899"],
            "sharpe_values": [0.92, 0.89, 0.97],
        },
    }

    async def _fake_gate_1(candidate, _db, **_kwargs):
        return gates_mod.GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics=dict(score_map[candidate["candidate_id"]]),
        )

    captured_gate_2_ids = []

    class _DummyBacktestFilter:
        async def filter(self, candidates, _db):
            captured_gate_2_ids.extend([item["candidate_id"] for item in candidates])
            return list(candidates)

        def get_last_report(self):
            return {
                "summary": {
                    "input_count": len(captured_gate_2_ids),
                    "passed_count": len(captured_gate_2_ids),
                    "failed_count": 0,
                    "failed_reason_counts": {},
                    "thresholds_by_type": {},
                }
            }

    def _compat(name, default):
        if name == "GATE1_PASS_RATIO":
            return 0.5
        if name == "BACKTEST_CONCURRENCY":
            return 1
        return default

    monkeypatch.setattr(gates_mod, "_compat_setting", _compat)
    monkeypatch.setattr(gates_mod, "gate_1_fast_screen", _fake_gate_1)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen", _fake_gate_1)

    candidates = [
        _complete_candidate({
            "candidate_id": "fragile_rl_momentum",
            "strategy_type": "momentum",
            "generator_type": "rl_bandit",
            "params": {"lookback": 20, "threshold": 0.02},
            "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901"],
            "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.5, "target_overlap_count": 3},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_rl_momentum_stability",
                "validation_focus": "target_plus_representative",
                "target_symbols": ["601628", "600030", "601211", "000776", "600999", "601901"],
            },
        }),
        _complete_candidate({
            "candidate_id": "clean_quality_snapshot",
            "strategy_type": "quality_factor",
            "params": {"lookback": 30, "buy_quantile": 0.7, "sell_quantile": 0.3},
            "target_symbols": ["300750", "002594", "601899"],
            "tags": ["targeted_universe", "pipeline_staged"],
            "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 1.0, "target_overlap_count": 3},
            "research_task": {
                "task_source": "snapshot",
                "task_id": "task_clean_quality",
                "validation_focus": "candidate_target_only",
                "target_symbols": ["300750", "002594", "601899"],
            },
        }),
    ]

    result = await run_gated_filter(candidates, SimpleNamespace(), _DummyBacktestFilter())

    assert captured_gate_2_ids == ["clean_quality_snapshot"]
    fragile_result = next(
        item for item in result["gate_report"]["gate_1"]["failed"]
        if item["strategy_type"] == "momentum"
    )
    assert "target_layer_stability_too_low" in fragile_result["reasons"]

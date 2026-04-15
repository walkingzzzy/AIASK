from __future__ import annotations

from copy import deepcopy

import pytest

from akshare_mcp.services import strategy_recompile_backfill as backfill_mod


def _trend_strategy(**overrides):
    strategy = {
        "id": "sid_trend_1",
        "name": "AI 均线趋势 V1",
        "description": "single-name trend strategy",
        "author_id": "strategy_factory",
        "strategy_type": "ma_cross",
        "status": "submitted",
        "target_symbols": ["688981"],
        "factor_weights": {},
        "tags": ["legacy"],
        "params": {
            "short_period": 5,
            "long_period": 20,
            "target_symbols": ["688981"],
            "trade_plan": {
                "entry_trigger": "golden_cross_with_volume_confirmation",
                "exit_trigger": "cross_failure_or_range_reentry",
            },
            "risk_rules": {
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.20,
                "max_holding_days": 48,
            },
            "holding_horizon": {
                "min_days": 14,
                "max_days": 48,
                "cooldown_window_days": 36,
            },
            "execution_assumptions": {
                "tradability_filter": True,
                "slippage_bps": 8,
            },
        },
    }
    strategy.update(overrides)
    if "params" in overrides:
        strategy["params"] = overrides["params"]
    return strategy


def test_build_trend_strategy_recompile_backfill_recompiles_single_name_trend_strategy():
    result = backfill_mod.build_trend_strategy_recompile_backfill(_trend_strategy())

    assert result["status"] == "recompiled"
    params = result["updated_payload"]["params"]
    assert params["execution_semantic_mode"] == "compiled_dsl"
    assert params["dsl_required"] is True
    assert params["dsl_compiled"] is True
    assert params["execution_semantic_gap"] is False
    assert params["revision_required"] is False
    assert "runtime_playbook" in params
    assert "instrument_profile" in params
    assert "annual_volatility_realized_252d" in params["instrument_profile"]
    assert "regime_filter_contract" in params
    assert "parameter_coherence_audit" in params
    assert "thesis_invalidation_contract" in params
    assert "drawdown_invalidation_contract" in params
    assert "high_confidence_recompile_backfill" in result["updated_payload"]["tags"]


def test_build_trend_strategy_recompile_backfill_marks_multi_target_as_revision_required():
    strategy = _trend_strategy(
        id="sid_multi_1",
        target_symbols=["688981", "600519"],
        params={
            **_trend_strategy()["params"],
            "target_symbols": ["688981", "600519"],
        },
    )

    result = backfill_mod.build_trend_strategy_recompile_backfill(strategy)

    assert result["status"] == "revision_required"
    assert result["reason"] == "historical_trend_recompile_requires_single_target_symbol"
    params = result["updated_payload"]["params"]
    assert params["execution_semantic_mode"] == "missing_executable_contract"
    assert params["execution_semantic_gap"] is True
    assert params["revision_required"] is True


def test_build_trend_strategy_recompile_backfill_skips_non_trend_strategy():
    strategy = _trend_strategy(
        id="sid_value_1",
        strategy_type="value_factor",
        params={"buy_quantile": 0.75, "sell_quantile": 0.25},
    )

    result = backfill_mod.build_trend_strategy_recompile_backfill(strategy)

    assert result["status"] == "skipped"
    assert result["reason"] == "unsupported_strategy_type"


def test_build_trend_strategy_recompile_backfill_clears_stale_revision_flag_and_preserves_existing_contract(monkeypatch):
    strategy = _trend_strategy(
        id="sid_preserve_1",
        params={
            **_trend_strategy()["params"],
            "revision_required": True,
            "execution_semantic_gap": True,
            "execution_semantic_gap_reasons": ["legacy_gap"],
            "runtime_playbook": {
                "entry_policy": {"order_style": "custom_limit"},
            },
        },
    )

    def _fake_envelope(_candidate):
        return {
            "params": {
                "runtime_playbook": {
                    "entry_policy": {
                        "order_style": "marketable_limit",
                        "max_slippage_bps": 30,
                    },
                    "exit_policy": {"time_stop_days": 48},
                },
                "execution_semantic_mode": "compiled_dsl",
                "execution_semantic_gap": False,
                "execution_semantic_gap_reasons": [],
                "dsl_required": True,
                "dsl_compiled": True,
                "dsl_compile_failure_reasons": [],
            }
        }

    monkeypatch.setattr(backfill_mod, "apply_resolved_candidate_envelope", _fake_envelope)
    result = backfill_mod.build_trend_strategy_recompile_backfill(strategy)

    params = result["updated_payload"]["params"]
    assert result["status"] == "recompiled"
    assert params["revision_required"] is False
    assert params["execution_semantic_gap"] is False
    assert params["runtime_playbook"]["entry_policy"]["order_style"] == "custom_limit"
    assert params["runtime_playbook"]["entry_policy"]["max_slippage_bps"] == 30
    assert params["runtime_recompile_backfill"]["status"] == "recompiled"


def test_build_trend_strategy_recompile_backfill_marks_revision_required_when_compiled_dsl_still_missing(monkeypatch):
    strategy = _trend_strategy(id="sid_gap_1")

    def _fake_envelope(_candidate):
        return {
            "params": {
                "execution_semantic_mode": "missing_executable_contract",
                "execution_semantic_gap": True,
                "execution_semantic_gap_reasons": ["compiled_dsl_missing_for_single_name_trend_strategy"],
                "dsl_required": True,
                "dsl_compiled": False,
                "dsl_compile_failure_reasons": ["missing_trade_plan_to_dsl_map"],
            }
        }

    monkeypatch.setattr(backfill_mod, "apply_resolved_candidate_envelope", _fake_envelope)
    result = backfill_mod.build_trend_strategy_recompile_backfill(strategy)

    assert result["status"] == "revision_required"
    assert result["reason"] == "deterministic_recompile_did_not_produce_compiled_dsl"
    params = result["updated_payload"]["params"]
    assert params["execution_semantic_gap"] is True
    assert params["revision_required"] is True
    assert "deterministic_recompile_did_not_produce_compiled_dsl" in params["execution_semantic_gap_reasons"]


@pytest.mark.asyncio
async def test_backfill_historical_trend_strategies_saves_when_only_tags_change(monkeypatch):
    strategy = _trend_strategy(id="sid_tags_1", tags=["legacy"], params={"short_period": 5, "long_period": 20})

    class _DB:
        def __init__(self):
            self.saved_payloads = []
            self.rows = [deepcopy(strategy)]

        async def list_strategies(self, status=None, limit=20, offset=0, strategy_type=None):
            return list(self.rows)[offset: offset + limit]

        async def get_strategy_metrics(self, strategy_id):
            return []

        async def save_strategy(self, payload):
            self.saved_payloads.append(deepcopy(payload))
            return payload

    def _fake_build(_strategy, **_kwargs):
        updated = deepcopy(_strategy)
        updated["tags"] = ["legacy", "high_confidence_recompile_backfill"]
        return {
            "strategy_id": updated["id"],
            "status": "recompiled",
            "reason": None,
            "deterministic_recompile_eligible": True,
            "target_symbols": ["688981"],
            "updated_payload": updated,
            "applied_param_fields": [],
            "preserved_param_fields": [],
        }

    monkeypatch.setattr(backfill_mod, "build_trend_strategy_recompile_backfill", _fake_build)
    db = _DB()
    result = await backfill_mod.backfill_historical_trend_strategies(db, dry_run=False)

    assert result["updated"] == 1
    assert len(db.saved_payloads) == 1
    assert db.saved_payloads[0]["tags"] == ["legacy", "high_confidence_recompile_backfill"]

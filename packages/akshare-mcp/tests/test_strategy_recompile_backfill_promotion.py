"""Tests for trend strategy recompile backfill + observe->formal promotion (P0-b / P1)."""

from __future__ import annotations

import math

import pytest

from akshare_mcp.services.strategy_recompile_backfill import (
    backfill_historical_trend_strategies,
    build_trend_strategy_recompile_backfill,
    build_factor_strategy_recompile_backfill,
    _recompiled_formal_ready,
)


def _synth_trend_klines(n: int = 220, *, start: float = 10.0) -> list[dict]:
    rows: list[dict] = []
    close = start
    prev_close = start
    for i in range(n):
        ret = 0.004 + 0.02 * math.sin(i / 7.0)
        close = max(0.5, prev_close * (1.0 + ret))
        high = close * (1.0 + 0.015 + 0.005 * abs(math.sin(i / 3.0)))
        low = close * (1.0 - 0.015 - 0.005 * abs(math.cos(i / 3.0)))
        open_ = prev_close * (1.0 + 0.003 * math.sin(i / 5.0))
        volume = 1_000_000 * (1.0 + 0.4 * abs(math.sin(i / 4.0)))
        rows.append(
            {
                "time": f"2025-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}",
                "code": "600000",
                "open": round(open_, 4),
                "high": round(max(high, open_, close), 4),
                "low": round(min(low, open_, close), 4),
                "close": round(close, 4),
                "volume": round(volume, 2),
                "turnover": round(volume * close, 2),
            }
        )
        prev_close = close
    return rows


class _FakeDB:
    def __init__(self, strategies: list[dict]) -> None:
        self._strategies = {s["id"]: dict(s) for s in strategies}
        self.saved: list[dict] = []
        self.klines = _synth_trend_klines(220)

    async def get_strategy(self, strategy_id):
        s = self._strategies.get(strategy_id)
        return dict(s) if s else None

    async def list_strategies(self, status=None, limit=None, offset=0):
        rows = list(self._strategies.values())
        if status:
            statuses = status if isinstance(status, (list, tuple, set)) else [status]
            rows = [r for r in rows if r.get("status") in set(statuses)]
        return [dict(r) for r in rows[offset: (offset + limit) if limit else None]]

    async def get_strategy_metrics(self, strategy_id):
        return [{"period": "backtest", "trade_count": 14, "max_drawdown": 0.09}]

    async def get_klines(self, code, start_date=None, end_date=None, limit=None):
        rows = list(self.klines)
        return rows[-limit:] if limit else rows

    async def get_financials(self, code, limit=4):
        return [
            {
                "code": code,
                "report_date": "2025-03-31",
                "roe": 0.16,
                "roa": 0.09,
                "gross_margin": 0.43,
                "net_margin": 0.22,
                "eps": 1.3,
                "bvps": 8.7,
                "debt_ratio": 0.38,
                "current_ratio": 1.9,
                "revenue_growth": 0.19,
                "profit_growth": 0.23,
            }
        ]

    async def save_strategy(self, payload):
        self.saved.append(dict(payload))
        self._strategies[payload["id"]] = dict(payload)
        return dict(payload)


def _momentum_strategy(strategy_id: str = "mom-1", *, strict_ready: bool = True) -> dict:
    from strategy_factory.application.trade_prediction_contract import (
        freeze_trade_prediction_contract,
    )

    frozen = freeze_trade_prediction_contract(
        {
            "strategy_id": strategy_id,
            "stock_code": "600000",
            "prediction_as_of": "2026-06-05T09:30:00+08:00",
            "target_trading_date": "2026-06-08",
            "direction": "up",
            "confidence": 0.7,
            "horizon": "next_day",
            "evidence_refs": ["ev-1"],
        }
    )
    return {
        "id": strategy_id,
        "name": "momentum single name",
        "strategy_type": "momentum",
        "status": "submitted",
        "target_symbols": ["600000"],
        "params": {
            "target_symbols": ["600000"],
            "submission_lane": "observe_incubation",
            "strict_incubation_ready": strict_ready,
            "trade_prediction_contract": frozen["contract"],
            "trade_prediction_contract_status": frozen["status"],
            "trade_prediction_contract_hash": frozen["contract_hash"],
            "holding_horizon": {"min_days": 5, "max_days": 20},
            "trade_plan": {"entry_bias": "momentum_breakout", "exit_bias": "momentum_decay"},
            "risk_rules": {"stop_loss_pct": 0.06, "take_profit_pct": 0.15},
            "evidence_chain": {"evidences": [{"evidence_id": "ev-1", "source": "price_runtime"}]},
            "confidence_contract": {
                "confidence": 0.7,
                "calibration": "historical_hit_rate",
                "sample_n": 40,
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "c1",
                        "target_trading_date": "2026-06-08",
                        "horizon": "next_day",
                        "evidence_ids": ["ev-1"],
                    }
                ]
            },
        },
    }


def test_recompile_produces_compiled_dsl_with_measured_profile() -> None:
    strategy = _momentum_strategy()
    summary_rows = _synth_trend_klines(220)
    from akshare_mcp.services.instrument_profile_measurement import measure_instrument_profile

    summary = measure_instrument_profile(summary_rows)
    result = build_trend_strategy_recompile_backfill(
        strategy,
        backtest_metrics={"trade_count": 14},
        measured_profile_summary=summary,
    )
    assert result["status"] == "recompiled"
    params = dict(result["updated_payload"]["params"])
    assert params["execution_semantic_mode"] == "compiled_dsl"
    assert params["dsl_compiled"] is True
    profile = dict(params.get("instrument_profile") or {})
    assert profile.get("measurement_source") in {"measured", "measured_runtime"}
    assert profile.get("measured_profile_complete") is True


@pytest.mark.asyncio
async def test_backfill_promotes_ready_observe_to_formal() -> None:
    db = _FakeDB([_momentum_strategy("mom-promote", strict_ready=True)])
    report = await backfill_historical_trend_strategies(
        db, strategy_ids=["mom-promote"], measure_profile=True, promote_ready=True
    )
    assert report["recompiled"] == 1
    assert report["promoted_to_formal"] == 1
    saved = db.saved[-1]
    assert saved["status"] == "incubating"
    assert dict(saved["params"]).get("submission_lane") == "formal_incubation"


@pytest.mark.asyncio
async def test_backfill_does_not_promote_without_strict_gate() -> None:
    db = _FakeDB([_momentum_strategy("mom-nostrict", strict_ready=False)])
    report = await backfill_historical_trend_strategies(
        db, strategy_ids=["mom-nostrict"], measure_profile=True, promote_ready=True
    )
    # 重编译可发生,但缺 strict gate 证据 → 不升 formal
    assert report["promoted_to_formal"] == 0
    if db.saved:
        assert db.saved[-1]["status"] != "incubating"


def _quality_factor_strategy(strategy_id: str = "qf-1", *, strict_ready: bool = True) -> dict:
    from strategy_factory.application.trade_prediction_contract import (
        freeze_trade_prediction_contract,
    )

    frozen = freeze_trade_prediction_contract(
        {
            "strategy_id": strategy_id,
            "stock_code": "600000",
            "prediction_as_of": "2026-06-05T09:30:00+08:00",
            "target_trading_date": "2026-06-08",
            "direction": "up",
            "confidence": 0.68,
            "horizon": "next_day",
            "evidence_refs": ["ev-f1"],
        }
    )
    return {
        "id": strategy_id,
        "name": "quality factor single name",
        "strategy_type": "quality_factor",
        "status": "submitted",
        "target_symbols": ["600000"],
        "params": {
            "target_symbols": ["600000"],
            "submission_lane": "observe_incubation",
            "strict_incubation_ready": strict_ready,
            "trade_prediction_contract": frozen["contract"],
            "trade_prediction_contract_status": frozen["status"],
            "trade_prediction_contract_hash": frozen["contract_hash"],
            "holding_horizon": {"min_days": 30, "max_days": 84},
            "trade_plan": {"entry_bias": "cross_sectional_rank", "exit_bias": "rank_decay"},
            "risk_rules": {"stop_loss_pct": 0.08, "take_profit_pct": 0.18},
            "evidence_chain": {"evidences": [{"evidence_id": "ev-f1", "source": "fundamental_runtime"}]},
            "confidence_contract": {"confidence": 0.68, "calibration": "historical_hit_rate", "sample_n": 36},
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "cf1",
                        "target_trading_date": "2026-06-08",
                        "horizon": "next_day",
                        "evidence_ids": ["ev-f1"],
                    }
                ]
            },
        },
    }


def test_factor_recompile_attaches_fundamental_runtime_contract() -> None:
    from akshare_mcp.services.fundamental_runtime_contract import (
        build_fundamental_runtime_contract,
    )

    strategy = _quality_factor_strategy()
    contract = build_fundamental_runtime_contract(
        "quality_factor",
        [
            {
                "code": "600000",
                "report_date": "2025-03-31",
                "roe": 0.16,
                "roa": 0.09,
                "gross_margin": 0.43,
                "net_margin": 0.22,
            }
        ],
        code="600000",
    )
    result = build_factor_strategy_recompile_backfill(strategy, fundamental_contract=contract)
    assert result["status"] == "recompiled"
    params = dict(result["updated_payload"]["params"])
    assert params["runtime_family_data_source"] == "fundamental_runtime"
    assert params["fundamental_runtime_contract"]["measured_fields"]
    assert not params.get("proxy_runtime_used")


def test_factor_recompile_without_financials_stays_proxy() -> None:
    strategy = _quality_factor_strategy()
    result = build_factor_strategy_recompile_backfill(strategy, fundamental_contract=None)
    assert result["status"] == "revision_required"
    assert result["reason"] == "fundamental_runtime_contract_unavailable"


@pytest.mark.asyncio
async def test_backfill_promotes_factor_family_with_real_financials() -> None:
    db = _FakeDB([_quality_factor_strategy("qf-promote", strict_ready=True)])
    report = await backfill_historical_trend_strategies(
        db, strategy_ids=["qf-promote"], promote_ready=True
    )
    assert report["recompiled"] == 1
    assert report["promoted_to_formal"] == 1
    saved = db.saved[-1] if db.saved else {}
    assert saved.get("status") == "incubating"
    saved_params = dict(saved.get("params") or {})
    assert saved_params.get("runtime_family_data_source") == "fundamental_runtime"
    assert saved_params.get("submission_lane") == "formal_incubation"
    assert saved_params.get("fundamental_runtime_contract", {}).get("measured_fields")

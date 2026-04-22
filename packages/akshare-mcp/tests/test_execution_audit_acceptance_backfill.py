from __future__ import annotations

import asyncio

from akshare_mcp.storage.timescaledb.strategy_incubation import StrategyIncubationMixin


class _SignalEvidenceBackfillDb(StrategyIncubationMixin):
    def __init__(self, *, strategy: dict, orders: list[dict], trades: list[dict], existing=None):
        self._strategy = dict(strategy)
        self._orders = [dict(item) for item in list(orders or [])]
        self._trades = [dict(item) for item in list(trades or [])]
        self._existing = [dict(item) for item in list(existing or [])]
        self.saved_rows: list[dict] = []

    async def list_strategy_paper_orders(self, strategy_id: str, signal_date=None, status=None, limit: int = 200):
        assert strategy_id == self._strategy["id"]
        return list(self._orders)[:limit]

    async def list_strategy_paper_trades(self, strategy_id: str, account_id=None, limit: int = 500):
        assert strategy_id == self._strategy["id"]
        return list(self._trades)[:limit]

    async def list_strategy_signal_evidence(self, *, signal_id=None, strategy_id=None, limit: int = 200):
        assert strategy_id in {None, self._strategy["id"]}
        rows = list(self._existing)
        if signal_id is not None:
            rows = [row for row in rows if str(row.get("signal_id")) == str(signal_id)]
        return rows[:limit]

    async def get_strategy(self, strategy_id: str):
        assert strategy_id == self._strategy["id"]
        return dict(self._strategy)

    async def save_strategy_signal_evidence(self, evidence: dict):
        payload = dict(evidence)
        self.saved_rows.append(payload)
        self._existing.append({"signal_id": payload.get("signal_id")})
        return payload


class _AcceptanceHarness(StrategyIncubationMixin):
    def __init__(self, *, verification: dict, backfill_result: dict):
        self._verification = dict(verification)
        self._backfill_result = dict(backfill_result)
        self.snapshot_payload = None

    async def backfill_trade_position_links(self, strategy_id=None):
        return {"strategy_id": strategy_id, "position_count": 1, "fill_count": 2}

    async def backfill_strategy_signal_evidence_native(self, strategy_id=None, limit: int = 5000):
        return dict(self._backfill_result)

    async def get_execution_audit_verification(self, strategy_id=None):
        return dict(self._verification)

    async def upsert_execution_audit_snapshot(self, payload: dict):
        self.snapshot_payload = dict(payload or {})
        return dict(payload or {})


def test_backfill_strategy_signal_evidence_native_prefers_compile_stable_records():
    strategy = {
        "id": "strategy-compile-stable",
        "params": {
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev-entry",
                        "source_type": "research_note",
                        "direction": "up",
                        "target_symbols": ["688336"],
                        "raw_confidence": 0.82,
                    }
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim-entry",
                        "evidence_ids": ["ev-entry"],
                    }
                ]
            },
            "claim_to_trade_plan_map": {
                "claim_to_trade_step_ids": {
                    "claim-entry": ["entry_step_1"],
                }
            },
        },
    }
    db = _SignalEvidenceBackfillDb(
        strategy=strategy,
        orders=[
            {
                "id": 101,
                "strategy_id": strategy["id"],
                "account_id": "acc-1",
                "signal_id": "sig-compile",
                "position_id": "pos-compile",
                "code": "688336",
                "direction": "buy",
                "signal_date": "2026-04-17",
            }
        ],
        trades=[],
    )

    result = asyncio.run(
        db.backfill_strategy_signal_evidence_native(strategy_id=strategy["id"])
    )

    assert result["saved_signal_count"] == 1
    assert result["compile_stable_signal_count"] == 1
    assert result["proxy_backfilled_signal_count"] == 0
    assert len(db.saved_rows) == 1
    saved = db.saved_rows[0]
    assert saved["signal_id"] == "sig-compile"
    assert saved["applied_claim_id"] == "claim-entry"
    assert saved["applied_trade_step_id"] == "entry_step_1"
    assert saved["payload"]["build_mode"] == "compile_stable_native"
    assert saved["payload"]["backfill_mode"] == "paper_execution_native_backfill_v1"


def test_backfill_strategy_signal_evidence_native_synthesizes_proxy_lineage_for_legacy_runtime():
    strategy = {
        "id": "strategy-legacy",
        "params": {
            "runtime_playbook": {
                "exit_policy": {"initial_stop_loss_pct": 0.08},
            }
        },
    }
    db = _SignalEvidenceBackfillDb(
        strategy=strategy,
        orders=[
            {
                "id": 201,
                "strategy_id": strategy["id"],
                "account_id": "acc-legacy",
                "signal_id": "sig-buy",
                "position_id": "pos-buy",
                "code": "688303",
                "direction": "buy",
                "signal_date": "2026-04-10",
            },
            {
                "id": 202,
                "strategy_id": strategy["id"],
                "account_id": "acc-legacy",
                "signal_id": "sig-sell",
                "position_id": "pos-buy",
                "code": "688303",
                "direction": "sell",
                "signal_date": "2026-04-11",
            },
        ],
        trades=[
            {
                "id": "trade-sell",
                "strategy_id": strategy["id"],
                "account_id": "acc-legacy",
                "signal_id": "sig-sell",
                "position_id": "pos-buy",
                "stock_code": "688303",
                "trade_type": "sell",
                "source_order_id": "202",
            }
        ],
    )

    result = asyncio.run(
        db.backfill_strategy_signal_evidence_native(strategy_id=strategy["id"])
    )

    assert result["saved_signal_count"] == 2
    assert result["proxy_backfilled_signal_count"] == 2
    assert result["compile_stable_signal_count"] == 0
    assert result["semantic_contract_gap_strategy_ids"] == [strategy["id"]]
    buy_row = next(row for row in db.saved_rows if row["signal_id"] == "sig-buy")
    sell_row = next(row for row in db.saved_rows if row["signal_id"] == "sig-sell")
    assert buy_row["applied_trade_step_id"] == "entry_step_backfill"
    assert buy_row["applied_claim_id"] == "legacy_claim_entry"
    assert buy_row["runtime_action_reason"] == "entry_execution_backfill"
    assert sell_row["applied_trade_step_id"] == "exit_step_backfill"
    assert sell_row["applied_claim_id"] == "legacy_claim_exit"
    assert sell_row["runtime_action_reason"] == "exit_execution_backfill"
    assert sell_row["payload"]["semantic_contract_status"] == "legacy_contract_gap"
    assert sell_row["payload"]["backfill_mode"] == "paper_execution_native_backfill_v1"


def test_run_execution_audit_acceptance_emits_gap_categories_and_actionable_todos():
    verification = {
        "coverage": {
            "paper_orders": {"total": 6, "position_id_ratio": 1.0},
            "paper_trades": {"total": 6, "position_id_ratio": 1.0},
        },
        "lineage_source": {
            "status": "native_backfilled",
            "semantic_contract": {
                "status": "legacy_contract_gap",
                "missing_fields": [
                    "claim_to_trade_plan_map",
                    "trade_plan_to_dsl_map",
                    "evidence_alignment_audit",
                ],
            },
        },
        "trade_round_trip": {
            "position_count": 3,
            "fill_count": 6,
            "audit_summary": {
                "realized_trade_count": 3,
                "incomplete_position_count": 0,
                "audit_ready_for_hard_gate": False,
                "execution_audit_gate_status": "insufficient_samples",
                "execution_audit_gate_reasons": ["realized_trade_count<20"],
            },
        },
        "recommendations": [],
    }
    db = _AcceptanceHarness(
        verification=verification,
        backfill_result={"saved_signal_count": 3, "proxy_backfilled_signal_count": 3},
    )

    result = asyncio.run(
        db.run_execution_audit_acceptance(strategy_id="strategy-gap", backfill=True)
    )

    assert result["acceptance_matrix"]["native_lineage_ready"] is True
    assert result["acceptance_matrix"]["trade_evidence_ready"] is True
    assert result["acceptance_matrix"]["hard_gate_ready"] is False
    assert result["execution_audit_snapshot_id"] == result["snapshot"]["snapshot_id"]
    assert result["execution_audit_gate_status"] == "insufficient_samples"
    assert "sample_gap" in result["gap_categories"]
    assert any(
        detail["blocker"] == "insufficient_samples"
        and detail["category"] == "sample_gap"
        for detail in result["blocker_details"]
    )
    assert any("production hard gate" in todo for todo in result["actionable_todos"])
    assert result["backfill_result"]["native_signal_evidence"]["saved_signal_count"] == 3


def test_normalize_trade_audit_summary_counts_excludes_open_positions_from_incomplete_gate():
    normalized = StrategyIncubationMixin()._normalize_trade_audit_summary_counts(
        {
            "mapped_position_count": 3,
            "realized_trade_count": 1,
            "incomplete_position_count": 3,
            "open_position_count": 2,
        }
    )

    assert normalized["raw_incomplete_position_count"] == 3
    assert normalized["open_position_count"] == 2
    assert normalized["incomplete_position_count"] == 1

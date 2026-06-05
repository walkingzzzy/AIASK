from __future__ import annotations

import asyncio
import sqlite3

from aiask_quant_core.storage.sqlite import SQLiteAdapter


def _prediction_payload() -> dict:
    contract = {
        "strategy_id": "strategy-p0",
        "stock_code": "600000.SH",
        "prediction_as_of": "2026-06-05T01:30:00+00:00",
        "target_trading_date": "2026-06-08",
        "direction": "up",
        "confidence": 0.72,
        "horizon": "next_day",
        "contract_version": "strategy_factory.trade_prediction_contract.v1",
        "contract_source": "explicit",
        "evidence_refs": ["ev-1"],
        "contract_hash": "hash-p0",
    }
    return {
        "prediction_id": "prediction-p0",
        "contract_json": contract,
        "metadata": {"source": "unit"},
    }


def test_strategy_trade_prediction_schema_is_initialized(tmp_path) -> None:
    db_path = tmp_path / "trade_prediction_schema.sqlite3"
    db = SQLiteAdapter(path=db_path)

    async def _run() -> None:
        try:
            await db.initialize()
        finally:
            await db.close()

    asyncio.run(_run())

    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "strategy_trade_predictions" in names
    assert "strategy_trade_prediction_outcomes" in names
    assert "idx_strategy_trade_predictions_strategy" in names
    assert "idx_strategy_trade_prediction_outcomes_prediction" in names


def test_strategy_trade_prediction_crud_round_trips_json(tmp_path) -> None:
    db = SQLiteAdapter(path=tmp_path / "trade_prediction_crud.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            saved = await db.save_strategy_trade_prediction(_prediction_payload())
            loaded = await db.get_strategy_trade_prediction("prediction-p0")
            listed = await db.list_strategy_trade_predictions(strategy_id="strategy-p0")

            assert saved["prediction_id"] == "prediction-p0"
            assert loaded is not None
            assert loaded["contract_hash"] == "hash-p0"
            assert loaded["contract_json"]["evidence_refs"] == ["ev-1"]
            assert loaded["metadata"] == {"source": "unit"}
            assert [row["prediction_id"] for row in listed] == ["prediction-p0"]

            outcome = await db.save_strategy_trade_prediction_outcome(
                {
                    "prediction_id": "prediction-p0",
                    "score_version": "trade_prediction_score_daily_v1",
                    "score_status": "partial_daily_only",
                    "trade_prediction_score": 0.61,
                    "actual_trading_date": "2026-06-08",
                    "outcome_json": {"direction_hit": True},
                    "metadata": {"phase": "p0"},
                }
            )
            outcomes = await db.list_strategy_trade_prediction_outcomes(prediction_id="prediction-p0")

            assert outcome["strategy_id"] == "strategy-p0"
            assert outcome["stock_code"] == "600000.SH"
            assert outcome["outcome_json"] == {"direction_hit": True}
            assert outcomes[0]["score_version"] == "trade_prediction_score_daily_v1"
            assert outcomes[0]["trade_prediction_score"] == 0.61
        finally:
            await db.close()

    asyncio.run(_run())


def test_strategy_trade_prediction_rejects_hash_mutation(tmp_path) -> None:
    db = SQLiteAdapter(path=tmp_path / "trade_prediction_hash_guard.sqlite3")

    async def _run() -> None:
        try:
            await db.initialize()
            await db.save_strategy_trade_prediction(_prediction_payload())
            mutated = _prediction_payload()
            mutated["contract_json"] = {
                **mutated["contract_json"],
                "contract_hash": "hash-mutated",
            }
            try:
                await db.save_strategy_trade_prediction(mutated)
            except ValueError as exc:
                assert "contract_hash mismatch" in str(exc)
            else:
                raise AssertionError("expected immutable contract_hash guard")
        finally:
            await db.close()

    asyncio.run(_run())

"""SQLite persistence for frozen trade prediction contracts and outcomes."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .strategy_factory_json_budget import bounded_json_text, strategy_json_field_max_bytes


def _string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    token = _string(value)
    return token or None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _stable_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _stable_payload_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


class StrategyTradePredictionMixin:
    def _decode_trade_prediction(self, row: dict) -> dict:
        payload = dict(row)
        payload["contract_json"] = self._decode_json_field(payload.get("contract_json"), {})
        payload["metadata"] = self._decode_json_field(payload.get("metadata"), {})
        return payload

    def _decode_trade_prediction_outcome(self, row: dict) -> dict:
        payload = dict(row)
        payload["outcome_json"] = self._decode_json_field(payload.get("outcome_json"), {})
        payload["metadata"] = self._decode_json_field(payload.get("metadata"), {})
        return payload

    async def save_strategy_trade_prediction(self, payload: dict) -> dict:
        contract_json = payload.get("contract_json") or payload.get("contract") or payload.get("trade_prediction_contract") or {}
        if isinstance(contract_json, str):
            try:
                contract_json = json.loads(contract_json)
            except Exception:
                contract_json = {"raw": contract_json}
        if not isinstance(contract_json, dict):
            contract_json = {"value": contract_json}

        prediction_id = _string(payload.get("prediction_id"))
        contract_hash = _string(payload.get("contract_hash") or contract_json.get("contract_hash"))
        if not contract_hash:
            contract_hash = _stable_payload_hash(contract_json)
        if not prediction_id:
            prediction_id = f"tp_{contract_hash[:20]}" if contract_hash else f"tp_{uuid4().hex}"

        strategy_id = _string(payload.get("strategy_id") or contract_json.get("strategy_id"))
        stock_code = _string(payload.get("stock_code") or contract_json.get("stock_code"))
        prediction_as_of = _coerce_iso(payload.get("prediction_as_of") or contract_json.get("prediction_as_of"))
        target_trading_date = _coerce_iso(payload.get("target_trading_date") or contract_json.get("target_trading_date"))
        direction = _string(payload.get("direction") or contract_json.get("direction"))
        contract_version = _string(payload.get("contract_version") or contract_json.get("contract_version"))
        if not strategy_id:
            raise ValueError("strategy_id is required")
        if not stock_code:
            raise ValueError("stock_code is required")
        if not prediction_as_of:
            raise ValueError("prediction_as_of is required")
        if not target_trading_date:
            raise ValueError("target_trading_date is required")
        if not direction:
            raise ValueError("direction is required")
        if not contract_version:
            raise ValueError("contract_version is required")

        now = datetime.now(timezone.utc)
        metadata = payload.get("metadata") or {}
        async with self.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT prediction_id, contract_hash
                FROM strategy_trade_predictions
                WHERE prediction_id = $1
                """,
                prediction_id,
            )
            if existing and _string(dict(existing).get("contract_hash")) != contract_hash:
                raise ValueError("frozen trade prediction contract_hash mismatch")
            await conn.execute(
                """
                INSERT INTO strategy_trade_predictions (
                    prediction_id,
                    strategy_id,
                    stock_code,
                    prediction_as_of,
                    target_trading_date,
                    direction,
                    confidence,
                    horizon,
                    contract_version,
                    contract_source,
                    contract_hash,
                    contract_json,
                    prediction_status,
                    metadata,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $15)
                ON CONFLICT (prediction_id) DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    stock_code = EXCLUDED.stock_code,
                    prediction_as_of = EXCLUDED.prediction_as_of,
                    target_trading_date = EXCLUDED.target_trading_date,
                    direction = EXCLUDED.direction,
                    confidence = EXCLUDED.confidence,
                    horizon = EXCLUDED.horizon,
                    contract_version = EXCLUDED.contract_version,
                    contract_source = EXCLUDED.contract_source,
                    prediction_status = EXCLUDED.prediction_status,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                prediction_id,
                strategy_id,
                stock_code,
                prediction_as_of,
                target_trading_date,
                direction,
                _coerce_float(payload.get("confidence") if payload.get("confidence") is not None else contract_json.get("confidence")),
                _string(payload.get("horizon") or contract_json.get("horizon")) or None,
                contract_version,
                _string(payload.get("contract_source") or contract_json.get("contract_source") or "explicit"),
                contract_hash,
                bounded_json_text(
                    "strategy_trade_predictions.contract_json",
                    contract_json,
                    max_bytes=strategy_json_field_max_bytes(),
                ),
                _string(payload.get("prediction_status") or "pending") or "pending",
                bounded_json_text(
                    "strategy_trade_predictions.metadata",
                    metadata,
                    max_bytes=strategy_json_field_max_bytes(),
                ),
                now,
            )
            row = await conn.fetchrow(
                "SELECT * FROM strategy_trade_predictions WHERE prediction_id = $1",
                prediction_id,
            )
        return self._decode_trade_prediction(dict(row))

    async def get_strategy_trade_prediction(self, prediction_id: str) -> Optional[dict]:
        token = _string(prediction_id)
        if not token:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM strategy_trade_predictions WHERE prediction_id = $1",
                token,
            )
        return self._decode_trade_prediction(dict(row)) if row else None

    async def list_strategy_trade_predictions(
        self,
        *,
        strategy_id: str | None = None,
        stock_code: str | None = None,
        prediction_status: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        where = ["1=1"]
        params: list[Any] = []
        if strategy_id:
            params.append(strategy_id)
            where.append(f"strategy_id = ${len(params)}")
        if stock_code:
            params.append(stock_code)
            where.append(f"stock_code = ${len(params)}")
        if prediction_status:
            params.append(prediction_status)
            where.append(f"prediction_status = ${len(params)}")
        try:
            limit_value = max(1, min(int(limit or 200), 1000))
        except Exception:
            limit_value = 200
        params.append(limit_value)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM strategy_trade_predictions
                WHERE {" AND ".join(where)}
                ORDER BY datetime(target_trading_date) DESC, datetime(updated_at) DESC
                LIMIT ${len(params)}
                """,
                *params,
            )
        return [self._decode_trade_prediction(dict(row)) for row in rows]

    async def save_strategy_trade_prediction_outcome(self, payload: dict) -> dict:
        prediction_id = _string(payload.get("prediction_id"))
        if not prediction_id:
            raise ValueError("prediction_id is required")
        outcome_json = payload.get("outcome_json") or payload.get("outcome") or {}
        if isinstance(outcome_json, str):
            try:
                outcome_json = json.loads(outcome_json)
            except Exception:
                outcome_json = {"raw": outcome_json}
        if not isinstance(outcome_json, dict):
            outcome_json = {"value": outcome_json}

        strategy_id = _string(payload.get("strategy_id") or outcome_json.get("strategy_id"))
        stock_code = _string(payload.get("stock_code") or outcome_json.get("stock_code"))
        async with self.acquire() as conn:
            if not strategy_id or not stock_code:
                prediction = await conn.fetchrow(
                    """
                    SELECT strategy_id, stock_code
                    FROM strategy_trade_predictions
                    WHERE prediction_id = $1
                    """,
                    prediction_id,
                )
                if prediction:
                    prediction_payload = dict(prediction)
                    strategy_id = strategy_id or _string(prediction_payload.get("strategy_id"))
                    stock_code = stock_code or _string(prediction_payload.get("stock_code"))
            if not strategy_id:
                raise ValueError("strategy_id is required")
            if not stock_code:
                raise ValueError("stock_code is required")
            score_version = _string(payload.get("score_version") or outcome_json.get("score_version"))
            if not score_version:
                raise ValueError("score_version is required")
            outcome_id = _string(payload.get("outcome_id"))
            if not outcome_id:
                outcome_id = f"tpo_{_stable_payload_hash([prediction_id, score_version])[:20]}"
            await conn.execute(
                """
                INSERT INTO strategy_trade_prediction_outcomes (
                    outcome_id,
                    prediction_id,
                    strategy_id,
                    stock_code,
                    actual_trading_date,
                    score_version,
                    score_status,
                    trade_prediction_score,
                    outcome_json,
                    data_quality_status,
                    metadata,
                    calculated_at,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (outcome_id) DO UPDATE SET
                    prediction_id = EXCLUDED.prediction_id,
                    strategy_id = EXCLUDED.strategy_id,
                    stock_code = EXCLUDED.stock_code,
                    actual_trading_date = EXCLUDED.actual_trading_date,
                    score_version = EXCLUDED.score_version,
                    score_status = EXCLUDED.score_status,
                    trade_prediction_score = EXCLUDED.trade_prediction_score,
                    outcome_json = EXCLUDED.outcome_json,
                    data_quality_status = EXCLUDED.data_quality_status,
                    metadata = EXCLUDED.metadata,
                    calculated_at = EXCLUDED.calculated_at
                """,
                outcome_id,
                prediction_id,
                strategy_id,
                stock_code,
                _coerce_iso(payload.get("actual_trading_date") or outcome_json.get("actual_trading_date")),
                score_version,
                _string(payload.get("score_status") or outcome_json.get("score_status") or "pending") or "pending",
                _coerce_float(payload.get("trade_prediction_score") if payload.get("trade_prediction_score") is not None else outcome_json.get("trade_prediction_score")),
                bounded_json_text(
                    "strategy_trade_prediction_outcomes.outcome_json",
                    outcome_json,
                    max_bytes=strategy_json_field_max_bytes(),
                ),
                _string(payload.get("data_quality_status") or outcome_json.get("data_quality_status") or "unknown") or "unknown",
                bounded_json_text(
                    "strategy_trade_prediction_outcomes.metadata",
                    payload.get("metadata") or {},
                    max_bytes=strategy_json_field_max_bytes(),
                ),
                _coerce_iso(payload.get("calculated_at")) or datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )
            row = await conn.fetchrow(
                "SELECT * FROM strategy_trade_prediction_outcomes WHERE outcome_id = $1",
                outcome_id,
            )
        return self._decode_trade_prediction_outcome(dict(row))

    async def list_strategy_trade_prediction_outcomes(
        self,
        *,
        prediction_id: str | None = None,
        strategy_id: str | None = None,
        stock_code: str | None = None,
        score_status: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        where = ["1=1"]
        params: list[Any] = []
        if prediction_id:
            params.append(prediction_id)
            where.append(f"prediction_id = ${len(params)}")
        if strategy_id:
            params.append(strategy_id)
            where.append(f"strategy_id = ${len(params)}")
        if stock_code:
            params.append(stock_code)
            where.append(f"stock_code = ${len(params)}")
        if score_status:
            params.append(score_status)
            where.append(f"score_status = ${len(params)}")
        try:
            limit_value = max(1, min(int(limit or 200), 1000))
        except Exception:
            limit_value = 200
        params.append(limit_value)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM strategy_trade_prediction_outcomes
                WHERE {" AND ".join(where)}
                ORDER BY datetime(COALESCE(actual_trading_date, calculated_at, created_at)) DESC
                LIMIT ${len(params)}
                """,
                *params,
            )
        return [self._decode_trade_prediction_outcome(dict(row)) for row in rows]

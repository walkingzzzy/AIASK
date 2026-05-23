"""SQLite 策略超市 Mixin — CRUD / 静态工具 / 工厂 / 质量报告 / 领域事件"""

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

from .strategy_factory_json_budget import (
    bounded_json_text,
    strategy_json_field_max_bytes,
    strategy_params_max_bytes,
)


class _StrategyCrudCoreMixin:
        async def save_strategy(self, data: dict) -> dict:
            sid = str(data.get("id", "")).strip()
            if not sid:
                raise ValueError("strategy id is required")
            now = datetime.now(timezone.utc)
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategies (id, name, description, author_id, strategy_type, params, factor_weights, status, tags, backtest_artifact_id, subscriber_count, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 0, $11, $11)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        strategy_type = EXCLUDED.strategy_type,
                        params = EXCLUDED.params,
                        factor_weights = EXCLUDED.factor_weights,
                        tags = EXCLUDED.tags,
                        backtest_artifact_id = EXCLUDED.backtest_artifact_id,
                        updated_at = EXCLUDED.updated_at
                    """,
                    sid,
                    str(data.get("name", "")),
                    data.get("description"),
                    str(data.get("author_id", "default")),
                    str(data.get("strategy_type", "custom")),
                    bounded_json_text(
                        "strategies.params",
                        data.get("params") or {},
                        max_bytes=strategy_params_max_bytes(),
                    ),
                    bounded_json_text(
                        "strategies.factor_weights",
                        data.get("factor_weights") or {},
                        max_bytes=strategy_json_field_max_bytes(),
                    ),
                    str(data.get("status", "draft")),
                    list(data.get("tags") or []),
                    data.get("backtest_artifact_id"),
                    now,
                )
            return {**data, "id": sid, "created_at": now.isoformat(), "updated_at": now.isoformat()}

        async def get_strategy(self, strategy_id: str) -> Optional[dict]:
            sid = str(strategy_id or "").strip()
            if not sid:
                return None
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT s.*,
                           COALESCE((SELECT AVG(rating) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating,
                           COALESCE((SELECT COUNT(*) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS review_count
                    FROM strategies s WHERE s.id = $1
                    """,
                    sid,
                )
            if not row:
                return None
            return self._decode_strategy_row(dict(row))

        async def list_strategies(self, status: Any = "listed", strategy_type: str = None, limit: int = 20, offset: int = 0) -> List[dict]:
            statuses = self._normalize_strategy_statuses(status)
            async with self.acquire() as conn:
                where_parts = ["1=1"]
                params: list[Any] = []
                idx = 1
                if statuses:
                    where_parts.append(f"s.status IN (${idx})")
                    params.append(statuses)
                    idx += 1
                if strategy_type:
                    where_parts.append(f"s.strategy_type = ${idx}")
                    params.append(strategy_type)
                    idx += 1
                params.extend([limit, offset])
                rows = await conn.fetch(
                    f"""
                    SELECT s.*,
                           COALESCE((SELECT AVG(rating) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                    FROM strategies s
                    WHERE {" AND ".join(where_parts)}
                    ORDER BY s.updated_at DESC LIMIT ${idx} OFFSET ${idx + 1}
                    """,
                    *params,
                )
            return [self._decode_strategy_row(dict(r)) for r in rows]

        async def update_strategy_status(
            self,
            strategy_id: str,
            status: str,
            actor_id: str = "system",
            reason: Optional[str] = None,
            metadata: Optional[dict] = None,
        ) -> None:
            now = datetime.now(timezone.utc)
            async with self.acquire() as conn:
                row = await conn.fetchrow("SELECT status FROM strategies WHERE id = $1", strategy_id)
                if not row:
                    return
                from_status = row["status"]
                await conn.execute(
                    "UPDATE strategies SET status = $1, updated_at = $2 WHERE id = $3",
                    status, now, strategy_id,
                )
                if from_status != status:
                    metadata_payload = metadata if isinstance(metadata, dict) else {}
                    encoded_metadata = bounded_json_text(
                        "strategy_status_events.metadata",
                        metadata_payload,
                        max_bytes=strategy_json_field_max_bytes(),
                    )
                    domain_payload = {
                        "from_status": from_status,
                        "to_status": status,
                        "reason": reason,
                        "metadata": metadata_payload,
                    }
                    await conn.execute(
                        """
                        INSERT INTO strategy_status_events
                            (strategy_id, from_status, to_status, event_type, actor_id, reason, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        strategy_id,
                        from_status,
                        status,
                        "status_change",
                        actor_id,
                        reason,
                        encoded_metadata,
                    )
                    await conn.execute(
                        """
                        INSERT INTO strategy_domain_events
                            (strategy_id, aggregate_type, aggregate_id, event_type, source, severity, correlation_id, payload, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        strategy_id,
                        "strategy",
                        strategy_id,
                        "strategy.status_changed",
                        actor_id or "system",
                        "info",
                        metadata_payload.get("task_run_id"),
                        bounded_json_text(
                            "strategy_domain_events.payload",
                            domain_payload,
                            max_bytes=strategy_json_field_max_bytes(),
                        ),
                        now,
                    )

        async def save_strategy_metrics(self, strategy_id: str, period: str, metrics: dict) -> None:
            now = datetime.now(timezone.utc)
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategy_metrics (strategy_id, period, total_return, annual_return, sharpe_ratio, max_drawdown, win_rate, calmar_ratio, trade_count, computed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (strategy_id, period) DO UPDATE SET
                        total_return = EXCLUDED.total_return,
                        annual_return = EXCLUDED.annual_return,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        max_drawdown = EXCLUDED.max_drawdown,
                        win_rate = EXCLUDED.win_rate,
                        calmar_ratio = EXCLUDED.calmar_ratio,
                        trade_count = EXCLUDED.trade_count,
                        computed_at = EXCLUDED.computed_at
                    """,
                    strategy_id, period,
                    metrics.get("total_return"), metrics.get("annual_return"),
                    metrics.get("sharpe_ratio"), metrics.get("max_drawdown"),
                    metrics.get("win_rate"), metrics.get("calmar_ratio"),
                    metrics.get("trade_count"), now,
                )

        async def get_strategy_metrics(self, strategy_id: str) -> List[dict]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM strategy_metrics WHERE strategy_id = $1 ORDER BY period",
                    strategy_id,
                )
            return [dict(r) for r in rows]

        async def save_review(self, strategy_id: str, user_id: str, rating: int, comment: str = None) -> None:
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategy_reviews (strategy_id, user_id, rating, comment)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (strategy_id, user_id) DO UPDATE SET
                        rating = EXCLUDED.rating,
                        comment = EXCLUDED.comment,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    strategy_id, user_id, rating, comment,
                )

        async def get_reviews(self, strategy_id: str, limit: int = 20) -> List[dict]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM strategy_reviews WHERE strategy_id = $1 ORDER BY created_at DESC LIMIT $2",
                    strategy_id, limit,
                )
            return [dict(r) for r in rows]

        async def subscribe_strategy(self, strategy_id: str, user_id: str) -> None:
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategy_subscriptions (strategy_id, user_id, status)
                    VALUES ($1, $2, 'active')
                    ON CONFLICT (strategy_id, user_id) DO UPDATE SET status = 'active', subscribed_at = CURRENT_TIMESTAMP
                    """,
                    strategy_id, user_id,
                )
                await conn.execute(
                    "UPDATE strategies SET subscriber_count = (SELECT COUNT(*) FROM strategy_subscriptions WHERE strategy_id = $1 AND status = 'active') WHERE id = $1",
                    strategy_id,
                )

        async def unsubscribe_strategy(self, strategy_id: str, user_id: str) -> None:
            async with self.acquire() as conn:
                await conn.execute(
                    "UPDATE strategy_subscriptions SET status = 'cancelled' WHERE strategy_id = $1 AND user_id = $2",
                    strategy_id, user_id,
                )
                await conn.execute(
                    "UPDATE strategies SET subscriber_count = (SELECT COUNT(*) FROM strategy_subscriptions WHERE strategy_id = $1 AND status = 'active') WHERE id = $1",
                    strategy_id,
                )

        async def list_user_subscriptions(self, user_id: str) -> List[dict]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT s.*, ss.subscribed_at,
                           COALESCE((SELECT AVG(rating) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                    FROM strategy_subscriptions ss
                    JOIN strategies s ON s.id = ss.strategy_id
                    WHERE ss.user_id = $1 AND ss.status = 'active'
                    ORDER BY ss.subscribed_at DESC
                    """,
                    user_id,
                )
            return [self._decode_strategy_row(dict(r)) for r in rows]

        async def list_user_strategies(
            self,
            user_id: str,
            *,
            include_archived: bool = False,
            limit: int = 50,
            offset: int = 0,
        ) -> List[dict]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT s.*,
                           COALESCE((SELECT AVG(rating) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating,
                           COALESCE((SELECT COUNT(*) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS review_count
                    FROM strategies s
                    WHERE s.author_id = $1
                      AND ($2 OR s.status <> 'archived')
                    ORDER BY s.updated_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    user_id,
                    bool(include_archived),
                    max(1, min(int(limit or 50), 200)),
                    max(0, int(offset or 0)),
                )
            return [self._decode_strategy_row(dict(row)) for row in rows]

        async def update_strategy_fields(self, strategy_id: str, updates: dict) -> Optional[dict]:
            payload = dict(updates or {})
            if not payload:
                return await self.get_strategy(strategy_id)
            assignments: list[str] = []
            values: list[Any] = []
            allowed_fields = (
                "name",
                "description",
                "params",
                "factor_weights",
                "tags",
                "backtest_artifact_id",
            )
            for field in allowed_fields:
                if field not in payload:
                    continue
                idx = len(values) + 2
                if field == "params":
                    assignments.append(f"{field} = ${idx}")
                    values.append(
                        bounded_json_text(
                            "strategies.params",
                            payload.get(field) or {},
                            max_bytes=strategy_params_max_bytes(),
                        )
                    )
                    continue
                if field == "factor_weights":
                    assignments.append(f"{field} = ${idx}")
                    values.append(
                        bounded_json_text(
                            "strategies.factor_weights",
                            payload.get(field) or {},
                            max_bytes=strategy_json_field_max_bytes(),
                        )
                    )
                    continue
                if field == "tags":
                    assignments.append(f"{field} = ${idx}[]")
                    values.append(list(payload.get(field) or []))
                    continue
                assignments.append(f"{field} = ${idx}")
                values.append(payload.get(field))
            if not assignments:
                return await self.get_strategy(strategy_id)
            values.append(datetime.now(timezone.utc))
            updated_at_idx = len(values) + 1
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    UPDATE strategies
                    SET {", ".join(assignments)},
                        updated_at = ${updated_at_idx}
                    WHERE id = $1
                    RETURNING *
                    """,
                    strategy_id,
                    *values,
                )
            return self._decode_strategy_row(dict(row)) if row else None

        async def save_strategy_paper_session(self, session: dict) -> dict:
            payload = dict(session or {})
            session_id = str(payload.get("id") or f"sps_{uuid4().hex[:16]}").strip()
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO strategy_paper_sessions
                        (id, strategy_id, user_id, account_id, session_type, source_strategy_id,
                         created_at, updated_at, last_used_at)
                    VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, COALESCE($7, CURRENT_TIMESTAMP))
                    ON CONFLICT (user_id, strategy_id, session_type) DO UPDATE SET
                        account_id = EXCLUDED.account_id,
                        source_strategy_id = EXCLUDED.source_strategy_id,
                        updated_at = CURRENT_TIMESTAMP,
                        last_used_at = COALESCE(EXCLUDED.last_used_at, strategy_paper_sessions.last_used_at, CURRENT_TIMESTAMP)
                    RETURNING *
                    """,
                    session_id,
                    str(payload.get("strategy_id") or ""),
                    str(payload.get("user_id") or "default"),
                    str(payload.get("account_id") or ""),
                    str(payload.get("session_type") or "personal_paper"),
                    payload.get("source_strategy_id"),
                    self._coerce_timestamp(payload.get("last_used_at")),
                )
            return dict(row)

        async def get_strategy_paper_session(
            self,
            strategy_id: str,
            user_id: str,
            session_type: str = "personal_paper",
        ) -> Optional[dict]:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT sps.*, pa.name AS account_name, pa.status AS account_status,
                           pa.account_type, pa.strategy_id AS account_strategy_id
                    FROM strategy_paper_sessions sps
                    LEFT JOIN paper_accounts pa ON pa.id = sps.account_id
                    WHERE sps.strategy_id = $1 AND sps.user_id = $2 AND sps.session_type = $3
                    ORDER BY sps.updated_at DESC, sps.created_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                    user_id,
                    session_type,
                )
            return dict(row) if row else None

        async def touch_strategy_paper_session(
            self,
            strategy_id: str,
            user_id: str,
            session_type: str = "personal_paper",
        ) -> Optional[dict]:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE strategy_paper_sessions
                    SET last_used_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE strategy_id = $1 AND user_id = $2 AND session_type = $3
                    RETURNING *
                    """,
                    strategy_id,
                    user_id,
                    session_type,
                )
            return dict(row) if row else None

        async def save_strategy_lineage(self, strategy_id: str, parent_id: Optional[str],
                                         spawn_reason: str, birth_regime: dict) -> None:
            async with self.acquire() as conn:
                await conn.execute(
                    """INSERT INTO strategy_lineage (strategy_id, parent_id, spawn_reason, birth_regime)
                       VALUES ($1, $2, $3, $4)""",
                    strategy_id, parent_id, spawn_reason,
                    json.dumps(birth_regime, ensure_ascii=False, default=str),
                )

        async def save_elimination_log(self, strategy_id: str, elimination_date, red_flags: list,
                                        reason: str) -> None:
            async with self.acquire() as conn:
                await conn.execute(
                    """INSERT INTO strategy_elimination_log (strategy_id, elimination_date, red_flags, reason)
                       VALUES ($1, $2, $3, $4)""",
                    strategy_id, elimination_date,
                    json.dumps(red_flags, ensure_ascii=False, default=str), reason,
                )

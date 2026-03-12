"""TimescaleDB 策略超市 Mixin — 运行时风控 / 运行时控制 / 晋升审核 / 投影快照"""

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class StrategyRuntimeMixin:
    """运行时风险事件/快照 + 运行时告警 + 运行时控制 + 晋升审核 + 投影快照"""

    # ── 运行时风险事件 ──

    def _decode_runtime_risk_event(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        return result

    async def save_strategy_runtime_risk_event(self, event: dict) -> dict:
        payload = dict(event or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_runtime_risk_events
                    (strategy_id, account_id, severity, event_type, action, status, title, reason, payload, detected_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, COALESCE($10::timestamptz, NOW()), NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                payload.get("account_id"),
                str(payload.get("severity") or "info"),
                str(payload.get("event_type") or "unknown"),
                payload.get("action"),
                str(payload.get("status") or "open"),
                payload.get("title"),
                payload.get("reason"),
                json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
                self._coerce_timestamp(payload.get("detected_at")),
            )
        return self._decode_runtime_risk_event(dict(row))

    async def resolve_strategy_runtime_risk_event(
        self,
        event_id: int,
        resolution: Optional[dict] = None,
        status: str = "resolved",
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE strategy_runtime_risk_events
                SET status = $2,
                    resolved_at = NOW(),
                    payload = COALESCE(payload, '{}'::jsonb) || $3::jsonb
                WHERE id = $1
                RETURNING *
                """,
                int(event_id),
                str(status or "resolved"),
                json.dumps(resolution or {}, ensure_ascii=False, default=str),
            )
        if not row:
            return None
        return self._decode_runtime_risk_event(dict(row))

    async def list_strategy_runtime_risk_events(
        self,
        strategy_id: Optional[str] = None,
        account_id: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_runtime_risk_events WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if account_id:
                sql += f" AND account_id = ${idx}"
                params.append(account_id)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            if severity:
                sql += f" AND severity = ${idx}"
                params.append(severity)
                idx += 1
            sql += f" ORDER BY detected_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 50), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_runtime_risk_event(dict(row)) for row in rows]

    # ── 运行时风险快照 ──

    def _decode_runtime_risk_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["summary"] = self._decode_json_field(result.get("summary"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_runtime_risk_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_runtime_risk_snapshots
                    (strategy_id, account_id, posture_level, escalation_level, control_mode, open_event_count, critical_open_count,
                     warning_open_count, recommended_action, recovery_eligible, blockers, summary, metadata, task_run_id, source, evaluated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13::jsonb, $14, $15, $16::timestamptz, NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                payload.get("account_id"),
                str(payload.get("posture_level") or "safe"),
                int(payload.get("escalation_level") or 0),
                str(payload.get("control_mode") or "active"),
                int(payload.get("open_event_count") or 0),
                int(payload.get("critical_open_count") or 0),
                int(payload.get("warning_open_count") or 0),
                payload.get("recommended_action"),
                bool(payload.get("recovery_eligible")),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("task_run_id"),
                str(payload.get("source") or "system"),
                self._coerce_timestamp(payload.get("evaluated_at")),
            )
        return self._decode_runtime_risk_snapshot(dict(row))

    async def get_latest_strategy_runtime_risk_snapshot(self, strategy_id: str) -> Optional[dict]:
        rows = await self.list_strategy_runtime_risk_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_risk_snapshots(
        self,
        strategy_id: Optional[str] = None,
        posture_level: Optional[str] = None,
        control_mode: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_runtime_risk_snapshots WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if posture_level:
                sql += f" AND posture_level = ${idx}"
                params.append(posture_level)
                idx += 1
            if control_mode:
                sql += f" AND control_mode = ${idx}"
                params.append(control_mode)
                idx += 1
            sql += f" ORDER BY evaluated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_runtime_risk_snapshot(dict(row)) for row in rows]

    # ── 运行时告警 ──

    def _decode_runtime_alert(self, row: dict) -> dict:
        result = dict(row)
        result["channels"] = self._decode_json_field(result.get("channels"), [])
        result["related_event_ids"] = self._decode_json_field(result.get("related_event_ids"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_runtime_alert(self, alert: dict) -> dict:
        payload = dict(alert or {})
        async with self.acquire() as conn:
            if payload.get("alert_id"):
                row = await conn.fetchrow(
                    """
                    UPDATE strategy_runtime_alerts
                    SET strategy_id = $2,
                        account_id = $3,
                        alert_key = $4,
                        category = $5,
                        severity = $6,
                        status = $7,
                        title = $8,
                        message = $9,
                        escalation_level = $10,
                        channels = $11::jsonb,
                        related_event_ids = $12::jsonb,
                        metadata = COALESCE(metadata, '{}'::jsonb) || $13::jsonb,
                        source = $14,
                        resolved_at = CASE WHEN $7 = 'resolved' THEN COALESCE(resolved_at, NOW()) ELSE NULL END,
                        updated_at = NOW()
                    WHERE alert_id = $1
                    RETURNING *
                    """,
                    int(payload.get("alert_id")),
                    str(payload.get("strategy_id") or ""),
                    payload.get("account_id"),
                    str(payload.get("alert_key") or "unknown"),
                    str(payload.get("category") or "general"),
                    str(payload.get("severity") or "info"),
                    str(payload.get("status") or "open"),
                    payload.get("title"),
                    payload.get("message"),
                    int(payload.get("escalation_level") or 0),
                    json.dumps(payload.get("channels") or [], ensure_ascii=False, default=str),
                    json.dumps(payload.get("related_event_ids") or [], ensure_ascii=False, default=str),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                    str(payload.get("source") or "system"),
                )
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO strategy_runtime_alerts
                        (strategy_id, account_id, alert_key, category, severity, status, title, message, escalation_level,
                         channels, related_event_ids, metadata, source, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb, $13, NOW(), NOW())
                    RETURNING *
                    """,
                    str(payload.get("strategy_id") or ""),
                    payload.get("account_id"),
                    str(payload.get("alert_key") or "unknown"),
                    str(payload.get("category") or "general"),
                    str(payload.get("severity") or "info"),
                    str(payload.get("status") or "open"),
                    payload.get("title"),
                    payload.get("message"),
                    int(payload.get("escalation_level") or 0),
                    json.dumps(payload.get("channels") or [], ensure_ascii=False, default=str),
                    json.dumps(payload.get("related_event_ids") or [], ensure_ascii=False, default=str),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                    str(payload.get("source") or "system"),
                )
        return self._decode_runtime_alert(dict(row))

    async def get_latest_strategy_runtime_alert(
        self,
        strategy_id: str,
        alert_key: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = 'open_or_ack',
    ) -> Optional[dict]:
        rows = await self.list_strategy_runtime_alerts(
            strategy_id=strategy_id,
            category=category,
            status=status,
            alert_key=alert_key,
            limit=1,
        )
        return rows[0] if rows else None

    async def list_strategy_runtime_alerts(
        self,
        strategy_id: Optional[str] = None,
        account_id: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        alert_key: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_runtime_alerts WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if account_id:
                sql += f" AND account_id = ${idx}"
                params.append(account_id)
                idx += 1
            if category:
                sql += f" AND category = ${idx}"
                params.append(category)
                idx += 1
            if severity:
                sql += f" AND severity = ${idx}"
                params.append(severity)
                idx += 1
            if alert_key:
                sql += f" AND alert_key = ${idx}"
                params.append(alert_key)
                idx += 1
            if status:
                if status == 'open_or_ack':
                    sql += " AND status IN ('open', 'acknowledged')"
                else:
                    sql += f" AND status = ${idx}"
                    params.append(status)
                    idx += 1
            sql += f" ORDER BY updated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 50), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_runtime_alert(dict(row)) for row in rows]

    async def acknowledge_strategy_runtime_alert(
        self,
        alert_id: int,
        acknowledged_by: Optional[str] = None,
        source: str = 'runtime_alerts',
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE strategy_runtime_alerts
                SET status = CASE WHEN status = 'resolved' THEN status ELSE 'acknowledged' END,
                    acknowledged_by = COALESCE($2, acknowledged_by),
                    acknowledged_at = COALESCE(acknowledged_at, NOW()),
                    metadata = COALESCE(metadata, '{}'::jsonb) || $3::jsonb,
                    updated_at = NOW()
                WHERE alert_id = $1
                RETURNING *
                """,
                int(alert_id),
                acknowledged_by,
                json.dumps({'ack_source': source}, ensure_ascii=False, default=str),
            )
        if not row:
            return None
        return self._decode_runtime_alert(dict(row))

    async def resolve_strategy_runtime_alerts(
        self,
        strategy_id: Optional[str] = None,
        alert_id: Optional[int] = None,
        alert_key: Optional[str] = None,
        category: Optional[str] = None,
        resolution: Optional[dict] = None,
        source: str = 'runtime_alerts',
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = """
                UPDATE strategy_runtime_alerts
                SET status = 'resolved',
                    resolved_at = COALESCE(resolved_at, NOW()),
                    metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb,
                    updated_at = NOW()
                WHERE status IN ('open', 'acknowledged')
            """
            params: list = [json.dumps({'resolution': resolution or {}, 'resolution_source': source}, ensure_ascii=False, default=str)]
            idx = 2
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if alert_id is not None:
                sql += f" AND alert_id = ${idx}"
                params.append(int(alert_id))
                idx += 1
            if alert_key:
                sql += f" AND alert_key = ${idx}"
                params.append(alert_key)
                idx += 1
            if category:
                sql += f" AND category = ${idx}"
                params.append(category)
                idx += 1
            sql += " RETURNING *"
            rows = await conn.fetch(sql, *params)
        return [self._decode_runtime_alert(dict(row)) for row in rows]

    # ── 运行时控制 ──

    def _decode_runtime_control(self, row: dict) -> dict:
        result = dict(row)
        result["action_summary"] = self._decode_json_field(result.get("action_summary"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_runtime_control(self, control: dict) -> dict:
        payload = dict(control or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_runtime_controls
                    (strategy_id, account_id, control_mode, status, source, trigger_event_type, reason, action_summary, metadata, activated_at, released_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, COALESCE($10::timestamptz, NOW()), $11::timestamptz, NOW(), NOW())
                ON CONFLICT (strategy_id) DO UPDATE SET
                    account_id = EXCLUDED.account_id,
                    control_mode = EXCLUDED.control_mode,
                    status = EXCLUDED.status,
                    source = EXCLUDED.source,
                    trigger_event_type = EXCLUDED.trigger_event_type,
                    reason = EXCLUDED.reason,
                    action_summary = EXCLUDED.action_summary,
                    metadata = EXCLUDED.metadata,
                    activated_at = EXCLUDED.activated_at,
                    released_at = EXCLUDED.released_at,
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get("strategy_id") or ""),
                payload.get("account_id"),
                str(payload.get("control_mode") or "active"),
                str(payload.get("status") or "active"),
                str(payload.get("source") or "system"),
                payload.get("trigger_event_type"),
                payload.get("reason"),
                json.dumps(payload.get("action_summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("activated_at"),
                payload.get("released_at"),
            )
        return self._decode_runtime_control(dict(row))

    async def get_strategy_runtime_control(self, strategy_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_runtime_controls
                WHERE strategy_id = $1
                LIMIT 1
                """,
                strategy_id,
            )
        if not row:
            return None
        return self._decode_runtime_control(dict(row))

    async def list_strategy_runtime_controls(
        self,
        strategy_id: Optional[str] = None,
        control_mode: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_runtime_controls WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if control_mode:
                sql += f" AND control_mode = ${idx}"
                params.append(control_mode)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY updated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 50), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_runtime_control(dict(row)) for row in rows]

    # ── 晋升审核 ──

    def _decode_promotion_review(self, row: dict) -> dict:
        result = dict(row)
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["risk_flags"] = self._decode_json_field(result.get("risk_flags"), [])
        result["summary"] = self._decode_json_field(result.get("summary"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_promotion_review(self, review: dict) -> dict:
        payload = dict(review or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_promotion_reviews
                    (strategy_id, account_id, review_source, stage, status, recommendation, score, blockers, risk_flags, summary, metadata, reviewed_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, COALESCE($12::timestamptz, NOW()), NOW())
                RETURNING *
                """,
                str(payload.get("strategy_id") or ""),
                payload.get("account_id"),
                str(payload.get("review_source") or "system"),
                str(payload.get("stage") or "incubating"),
                str(payload.get("status") or "watch"),
                payload.get("recommendation"),
                float(payload.get("score") or 0.0),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("risk_flags") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("reviewed_at"),
            )
        return self._decode_promotion_review(dict(row))

    async def get_latest_strategy_promotion_review(self, strategy_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_promotion_reviews
                WHERE strategy_id = $1
                ORDER BY reviewed_at DESC, created_at DESC
                LIMIT 1
                """,
                strategy_id,
            )
        if not row:
            return None
        return self._decode_promotion_review(dict(row))

    async def list_strategy_promotion_reviews(
        self,
        strategy_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_promotion_reviews WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY reviewed_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 50), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_promotion_review(dict(row)) for row in rows]

    # ── 投影快照 ──

    def _decode_projection_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["projection"] = self._decode_json_field(result.get("projection"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_projection_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_projection_snapshots
                    (strategy_id, projection_type, aggregate_version, current_status, runtime_control_mode, timeline_count, projection, metadata, task_run_id, source, rebuilt_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, COALESCE($11::timestamptz, NOW()), NOW())
                RETURNING *
                """,
                str(payload.get("strategy_id") or ""),
                str(payload.get("projection_type") or "strategy_state"),
                int(payload.get("aggregate_version") or 0),
                payload.get("current_status"),
                payload.get("runtime_control_mode"),
                int(payload.get("timeline_count") or 0),
                json.dumps(payload.get("projection") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("task_run_id"),
                str(payload.get("source") or "system"),
                payload.get("rebuilt_at"),
            )
        return self._decode_projection_snapshot(dict(row))

    async def get_latest_strategy_projection_snapshot(
        self,
        strategy_id: str,
        projection_type: str = 'strategy_state',
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_projection_snapshots
                WHERE strategy_id = $1 AND projection_type = $2
                ORDER BY rebuilt_at DESC, created_at DESC
                LIMIT 1
                """,
                strategy_id,
                projection_type,
            )
        if not row:
            return None
        return self._decode_projection_snapshot(dict(row))

    async def list_strategy_projection_snapshots(
        self,
        strategy_id: Optional[str] = None,
        projection_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_projection_snapshots WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if projection_type:
                sql += f" AND projection_type = ${idx}"
                params.append(projection_type)
                idx += 1
            sql += f" ORDER BY rebuilt_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 50), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_projection_snapshot(dict(row)) for row in rows]

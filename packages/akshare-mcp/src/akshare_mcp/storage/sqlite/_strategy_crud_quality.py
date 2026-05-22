"""SQLite 策略超市 Mixin — CRUD / 静态工具 / 工厂 / 质量报告 / 领域事件"""

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _StrategyCrudQualityMixin:
        async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report: dict) -> None:
            now = datetime.now(timezone.utc)
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO strategy_quality_reports
                        (strategy_id, report_type, passed, summary, quality_gate, validation_report,
                         risk_report, dedup_report, backtest_metrics, snapshot, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                            $9, $10, $11, $11)
                    ON CONFLICT (strategy_id, report_type) DO UPDATE SET
                        passed = EXCLUDED.passed,
                        summary = EXCLUDED.summary,
                        quality_gate = EXCLUDED.quality_gate,
                        validation_report = EXCLUDED.validation_report,
                        risk_report = EXCLUDED.risk_report,
                        dedup_report = EXCLUDED.dedup_report,
                        backtest_metrics = EXCLUDED.backtest_metrics,
                        snapshot = EXCLUDED.snapshot,
                        updated_at = EXCLUDED.updated_at
                    """,
                    strategy_id,
                    str(report_type or "submission"),
                    bool(report.get("passed")),
                    json.dumps(report.get("summary") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("quality_gate") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("validation_report") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("risk_report") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("dedup_report") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("backtest_metrics") or {}, ensure_ascii=False, default=str),
                    json.dumps(report.get("snapshot") or {}, ensure_ascii=False, default=str),
                    now,
                )

        async def get_strategy_quality_report(self, strategy_id: str, report_type: str = "submission") -> Optional[dict]:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_quality_reports
                    WHERE strategy_id = $1 AND report_type = $2
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                    report_type,
                )
            if not row:
                return None
            return self._decode_quality_report(dict(row))

        def _decode_quality_report(self, row: dict) -> dict:
            result = dict(row)
            for key in (
                "summary",
                "quality_gate",
                "validation_report",
                "risk_report",
                "dedup_report",
                "backtest_metrics",
                "snapshot",
            ):
                result[key] = self._decode_json_field(result.get(key), {})
            return result

        async def list_strategy_quality_reports(self, strategy_id: str, limit: int = 10) -> List[dict]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM strategy_quality_reports
                    WHERE strategy_id = $1
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT $2
                    """,
                    strategy_id,
                    max(1, min(int(limit or 10), 50)),
                )
            return [self._decode_quality_report(dict(row)) for row in rows]

        async def get_latest_strategy_quality_report(self, strategy_id: str) -> Optional[dict]:
            rows = await self.list_strategy_quality_reports(strategy_id, limit=1)
            return rows[0] if rows else None

        async def list_strategy_status_events(
            self,
            strategy_id: str,
            event_type: Optional[str] = None,
            from_status: Optional[str] = None,
            to_status: Optional[str] = None,
            actor_id: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            limit: int = 50,
        ) -> List[dict]:
            async with self.acquire() as conn:
                sql = "SELECT * FROM strategy_status_events WHERE strategy_id = $1"
                params: list = [strategy_id]
                idx = 2
                if event_type:
                    sql += f" AND event_type = ${idx}"
                    params.append(event_type)
                    idx += 1
                if from_status:
                    sql += f" AND from_status = ${idx}"
                    params.append(from_status)
                    idx += 1
                if to_status:
                    sql += f" AND to_status = ${idx}"
                    params.append(to_status)
                    idx += 1
                if actor_id:
                    sql += f" AND actor_id = ${idx}"
                    params.append(actor_id)
                    idx += 1
                if start_time:
                    sql += f" AND created_at >= ${idx}"
                    params.append(start_time)
                    idx += 1
                if end_time:
                    sql += f" AND created_at <= ${idx}"
                    params.append(end_time)
                    idx += 1
                sql += f" ORDER BY created_at DESC LIMIT ${idx}"
                params.append(max(1, min(int(limit or 50), 200)))
                rows = await conn.fetch(sql, *params)
            events = [dict(r) for r in rows]
            for item in events:
                item["metadata"] = self._decode_json_field(item.get("metadata"), {})
            return events

        def _decode_domain_event(self, row: dict) -> dict:
            result = dict(row)
            result["payload"] = self._decode_json_field(result.get("payload"), {})
            return result

        async def save_strategy_domain_event(self, event: dict) -> dict:
            payload = dict(event or {})
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO strategy_domain_events
                        (strategy_id, aggregate_type, aggregate_id, event_type, source, severity, correlation_id, payload, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, CURRENT_TIMESTAMP))
                    RETURNING *
                    """,
                    payload.get("strategy_id"),
                    str(payload.get("aggregate_type") or "strategy"),
                    payload.get("aggregate_id") or payload.get("strategy_id"),
                    str(payload.get("event_type") or "unknown"),
                    str(payload.get("source") or "system"),
                    str(payload.get("severity") or "info"),
                    payload.get("correlation_id"),
                    json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
                    self._coerce_timestamp(payload.get("created_at")),
                )
            return self._decode_domain_event(dict(row))

        async def list_strategy_domain_events(
            self,
            strategy_id: Optional[str] = None,
            aggregate_type: Optional[str] = None,
            event_type: Optional[str] = None,
            source: Optional[str] = None,
            correlation_id: Optional[str] = None,
            limit: int = 50,
        ) -> List[dict]:
            async with self.acquire() as conn:
                sql = "SELECT * FROM strategy_domain_events WHERE 1=1"
                params: list = []
                idx = 1
                if strategy_id:
                    sql += f" AND strategy_id = ${idx}"
                    params.append(strategy_id)
                    idx += 1
                if aggregate_type:
                    sql += f" AND aggregate_type = ${idx}"
                    params.append(aggregate_type)
                    idx += 1
                if event_type:
                    sql += f" AND event_type = ${idx}"
                    params.append(event_type)
                    idx += 1
                if source:
                    sql += f" AND source = ${idx}"
                    params.append(source)
                    idx += 1
                if correlation_id:
                    sql += f" AND correlation_id = ${idx}"
                    params.append(correlation_id)
                    idx += 1
                sql += f" ORDER BY created_at DESC LIMIT ${idx}"
                params.append(max(1, min(int(limit or 50), 500)))
                rows = await conn.fetch(sql, *params)
            return [self._decode_domain_event(dict(row)) for row in rows]

        async def count_strategies_by_type(self, status: str = "listed") -> Dict[str, int]:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT strategy_type, COUNT(*) AS cnt FROM strategies WHERE status = $1 GROUP BY strategy_type",
                    status,
                )
            return {r["strategy_type"]: r["cnt"] for r in rows}

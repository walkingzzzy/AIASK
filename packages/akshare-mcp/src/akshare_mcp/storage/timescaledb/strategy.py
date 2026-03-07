"""TimescaleDB 适配器 — 策略超市 Mixin"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyMixin:
    """策略超市 CRUD（strategies / strategy_metrics / strategy_reviews / strategy_subscriptions）"""

    @staticmethod
    def _decode_json_field(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return value

    async def save_strategy(self, data: dict) -> dict:
        sid = str(data.get("id", "")).strip()
        if not sid:
            raise ValueError("strategy id is required")
        now = datetime.now(timezone.utc).isoformat()
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategies (id, name, description, author_id, strategy_type, params, factor_weights, status, tags, backtest_artifact_id, subscriber_count, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::text[], $10, 0, $11::timestamptz, $11::timestamptz)
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
                json.dumps(data.get("params") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_weights") or {}, ensure_ascii=False, default=str),
                str(data.get("status", "draft")),
                list(data.get("tags") or []),
                data.get("backtest_artifact_id"),
                now,
            )
        return {**data, "id": sid, "created_at": now, "updated_at": now}

    async def get_strategy(self, strategy_id: str) -> Optional[dict]:
        sid = str(strategy_id or "").strip()
        if not sid:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT s.*,
                       COALESCE((SELECT AVG(rating)::float FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating,
                       COALESCE((SELECT COUNT(*) FROM strategy_reviews WHERE strategy_id = s.id), 0) AS review_count
                FROM strategies s WHERE s.id = $1
                """,
                sid,
            )
        if not row:
            return None
        result = dict(row)
        if isinstance(result.get("params"), str):
            try: result["params"] = json.loads(result["params"])
            except Exception: pass
        if isinstance(result.get("factor_weights"), str):
            try: result["factor_weights"] = json.loads(result["factor_weights"])
            except Exception: pass
        return result

    async def list_strategies(self, status: str = "published", strategy_type: str = None, limit: int = 20, offset: int = 0) -> List[dict]:
        async with self.acquire() as conn:
            if strategy_type:
                rows = await conn.fetch(
                    """
                    SELECT s.*,
                           COALESCE((SELECT AVG(rating)::float FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                    FROM strategies s
                    WHERE s.status = $1 AND s.strategy_type = $2
                    ORDER BY s.updated_at DESC LIMIT $3 OFFSET $4
                    """,
                    status, strategy_type, limit, offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT s.*,
                           COALESCE((SELECT AVG(rating)::float FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                    FROM strategies s
                    WHERE s.status = $1
                    ORDER BY s.updated_at DESC LIMIT $2 OFFSET $3
                    """,
                    status, limit, offset,
                )
        return [dict(r) for r in rows]

    async def update_strategy_status(
        self,
        strategy_id: str,
        status: str,
        actor_id: str = "system",
        reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self.acquire() as conn:
            row = await conn.fetchrow("SELECT status FROM strategies WHERE id = $1", strategy_id)
            if not row:
                return
            from_status = row["status"]
            await conn.execute(
                "UPDATE strategies SET status = $1, updated_at = $2::timestamptz WHERE id = $3",
                status, now, strategy_id,
            )
            if from_status != status:
                encoded_metadata = json.dumps(metadata or {}, ensure_ascii=False, default=str)
                await conn.execute(
                    """
                    INSERT INTO strategy_status_events
                        (strategy_id, from_status, to_status, event_type, actor_id, reason, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
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
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::timestamptz)
                    """,
                    strategy_id,
                    "strategy",
                    strategy_id,
                    "strategy.status_changed",
                    actor_id or "system",
                    "info",
                    (metadata or {}).get("task_run_id") if isinstance(metadata, dict) else None,
                    json.dumps({
                        "from_status": from_status,
                        "to_status": status,
                        "reason": reason,
                        "metadata": metadata or {},
                    }, ensure_ascii=False, default=str),
                    now,
                )

    async def save_strategy_metrics(self, strategy_id: str, period: str, metrics: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_metrics (strategy_id, period, total_return, annual_return, sharpe_ratio, max_drawdown, win_rate, calmar_ratio, trade_count, computed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::timestamptz)
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
                    created_at = NOW()
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
                ON CONFLICT (strategy_id, user_id) DO UPDATE SET status = 'active', subscribed_at = NOW()
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
                       COALESCE((SELECT AVG(rating)::float FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                FROM strategy_subscriptions ss
                JOIN strategies s ON s.id = ss.strategy_id
                WHERE ss.user_id = $1 AND ss.status = 'active'
                ORDER BY ss.subscribed_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    # ── 策略工厂辅助方法 ──

    async def save_strategy_lineage(self, strategy_id: str, parent_id: Optional[str],
                                     spawn_reason: str, birth_regime: dict) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO strategy_lineage (strategy_id, parent_id, spawn_reason, birth_regime)
                   VALUES ($1, $2, $3, $4::jsonb)""",
                strategy_id, parent_id, spawn_reason,
                json.dumps(birth_regime, ensure_ascii=False, default=str),
            )

    async def save_elimination_log(self, strategy_id: str, elimination_date, red_flags: list,
                                    reason: str) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO strategy_elimination_log (strategy_id, elimination_date, red_flags, reason)
                   VALUES ($1, $2, $3::jsonb, $4)""",
                strategy_id, elimination_date,
                json.dumps(red_flags, ensure_ascii=False, default=str), reason,
            )

    async def save_daily_snapshot(self, snapshot_date, data: dict) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO daily_snapshot_history
                   (snapshot_date, fear_greed_index, fg_components, factor_ic, factor_ic_trend,
                    north_fund_3d_net, margin_5d_change_pct, hot_sectors, cold_sectors,
                    listed_count, category_counts, summary, completeness, sources,
                    failure_reasons, missing_fields, degraded)
                   VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb,
                           $10, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17)
                   ON CONFLICT (snapshot_date) DO UPDATE SET
                    fear_greed_index = EXCLUDED.fear_greed_index,
                    fg_components = EXCLUDED.fg_components,
                    factor_ic = EXCLUDED.factor_ic,
                    factor_ic_trend = EXCLUDED.factor_ic_trend,
                    north_fund_3d_net = EXCLUDED.north_fund_3d_net,
                    margin_5d_change_pct = EXCLUDED.margin_5d_change_pct,
                    hot_sectors = EXCLUDED.hot_sectors,
                    cold_sectors = EXCLUDED.cold_sectors,
                    listed_count = EXCLUDED.listed_count,
                    category_counts = EXCLUDED.category_counts,
                    summary = EXCLUDED.summary,
                    completeness = EXCLUDED.completeness,
                    sources = EXCLUDED.sources,
                    failure_reasons = EXCLUDED.failure_reasons,
                    missing_fields = EXCLUDED.missing_fields,
                    degraded = EXCLUDED.degraded
                """,
                snapshot_date,
                data.get("fear_greed_index"),
                json.dumps(data.get("fg_components") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_ic") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_ic_trend") or {}, ensure_ascii=False, default=str),
                data.get("north_fund_3d_net"),
                data.get("margin_5d_change_pct"),
                json.dumps(data.get("hot_sectors") or [], ensure_ascii=False, default=str),
                json.dumps(data.get("cold_sectors") or [], ensure_ascii=False, default=str),
                data.get("listed_count", 0),
                json.dumps(data.get("category_counts") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("completeness") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("sources") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("failure_reasons") or [], ensure_ascii=False, default=str),
                json.dumps(data.get("missing_fields") or [], ensure_ascii=False, default=str),
                bool(data.get("degraded")),
            )

    def _decode_daily_snapshot(self, row: dict) -> dict:
        result = dict(row)
        for key in ("fg_components", "factor_ic", "factor_ic_trend", "category_counts", "summary", "completeness", "sources"):
            result[key] = self._decode_json_field(result.get(key), {})
        for key in ("hot_sectors", "cold_sectors", "failure_reasons", "missing_fields"):
            result[key] = self._decode_json_field(result.get(key), [])
        return result

    async def get_daily_snapshot(self, snapshot_date = None) -> Optional[dict]:
        async with self.acquire() as conn:
            if snapshot_date is None:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM daily_snapshot_history
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                    """
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM daily_snapshot_history
                    WHERE snapshot_date = $1
                    LIMIT 1
                    """,
                    snapshot_date,
                )
        if not row:
            return None
        return self._decode_daily_snapshot(dict(row))

    async def list_daily_snapshots(
        self,
        limit: int = 20,
        start_date = None,
        end_date = None,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM daily_snapshot_history WHERE 1=1"
            params: list = []
            idx = 1
            if start_date is not None:
                sql += f" AND snapshot_date >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date is not None:
                sql += f" AND snapshot_date <= ${idx}"
                params.append(end_date)
                idx += 1
            sql += f" ORDER BY snapshot_date DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_daily_snapshot(dict(row)) for row in rows]

    async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_quality_reports
                    (strategy_id, report_type, passed, summary, quality_gate, validation_report,
                     risk_report, dedup_report, backtest_metrics, snapshot, created_at, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb,
                        $9::jsonb, $10::jsonb, $11::timestamptz, $11::timestamptz)
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
                sql += f" AND created_at >= ${idx}::timestamptz"
                params.append(start_time)
                idx += 1
            if end_time:
                sql += f" AND created_at <= ${idx}::timestamptz"
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
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, COALESCE($9::timestamptz, NOW()))
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
                payload.get("created_at"),
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

    def _decode_incubation_account(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_incubation_account(
        self,
        strategy_id: str,
        account_id: str,
        stage: str = "warmup",
        status: str = "active",
        source_run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_accounts
                    (strategy_id, account_id, stage, status, source_run_id, metadata, bound_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), NOW())
                ON CONFLICT (strategy_id, account_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    status = EXCLUDED.status,
                    source_run_id = EXCLUDED.source_run_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                strategy_id,
                account_id,
                str(stage or "warmup"),
                str(status or "active"),
                source_run_id,
                json.dumps(metadata or {}, ensure_ascii=False, default=str),
            )
        return self._decode_incubation_account(dict(row))

    async def get_strategy_incubation_account(
        self,
        strategy_id: str,
        account_id: Optional[str] = None,
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            if account_id:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_incubation_accounts
                    WHERE strategy_id = $1 AND account_id = $2
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                    account_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_incubation_accounts
                    WHERE strategy_id = $1
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                )
        if not row:
            return None
        return self._decode_incubation_account(dict(row))

    async def list_strategy_incubation_accounts(
        self,
        strategy_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_accounts WHERE 1=1"
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
            sql += f" ORDER BY updated_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_account(dict(row)) for row in rows]

    def _decode_incubation_metric(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["risk_flags"] = self._decode_json_field(result.get("risk_flags"), [])
        return result

    async def save_strategy_incubation_metric(self, strategy_id: str, metric_date, metric: dict) -> dict:
        payload = dict(metric or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_metrics
                    (strategy_id, account_id, metric_date, stage, total_value, cash, market_value, nav,
                     daily_return, max_drawdown, sharpe_ratio, hit_rate_5d, forward_ic_5d, forward_sharpe_5d,
                     total_signals, total_orders, total_trades, turnover_rate, exposure_rate, alpha_decay,
                     drift_score, blockers, risk_flags, decision, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14,
                        $15, $16, $17, $18, $19, $20,
                        $21, $22::jsonb, $23::jsonb, $24, $25::jsonb, NOW(), NOW())
                ON CONFLICT (strategy_id, metric_date) DO UPDATE SET
                    account_id = EXCLUDED.account_id,
                    stage = EXCLUDED.stage,
                    total_value = EXCLUDED.total_value,
                    cash = EXCLUDED.cash,
                    market_value = EXCLUDED.market_value,
                    nav = EXCLUDED.nav,
                    daily_return = EXCLUDED.daily_return,
                    max_drawdown = EXCLUDED.max_drawdown,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    hit_rate_5d = EXCLUDED.hit_rate_5d,
                    forward_ic_5d = EXCLUDED.forward_ic_5d,
                    forward_sharpe_5d = EXCLUDED.forward_sharpe_5d,
                    total_signals = EXCLUDED.total_signals,
                    total_orders = EXCLUDED.total_orders,
                    total_trades = EXCLUDED.total_trades,
                    turnover_rate = EXCLUDED.turnover_rate,
                    exposure_rate = EXCLUDED.exposure_rate,
                    alpha_decay = EXCLUDED.alpha_decay,
                    drift_score = EXCLUDED.drift_score,
                    blockers = EXCLUDED.blockers,
                    risk_flags = EXCLUDED.risk_flags,
                    decision = EXCLUDED.decision,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                strategy_id,
                payload.get("account_id"),
                metric_date,
                str(payload.get("stage") or "warmup"),
                payload.get("total_value"),
                payload.get("cash"),
                payload.get("market_value"),
                payload.get("nav"),
                payload.get("daily_return"),
                payload.get("max_drawdown"),
                payload.get("sharpe_ratio"),
                payload.get("hit_rate_5d"),
                payload.get("forward_ic_5d"),
                payload.get("forward_sharpe_5d"),
                int(payload.get("total_signals") or 0),
                int(payload.get("total_orders") or 0),
                int(payload.get("total_trades") or 0),
                payload.get("turnover_rate"),
                payload.get("exposure_rate"),
                payload.get("alpha_decay"),
                payload.get("drift_score"),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("risk_flags") or [], ensure_ascii=False, default=str),
                payload.get("decision"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_incubation_metric(dict(row))

    async def get_latest_strategy_incubation_metric(self, strategy_id: str) -> Optional[dict]:
        rows = await self.list_strategy_incubation_metrics(strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_metrics(
        self,
        strategy_id: str,
        limit: int = 30,
        start_date = None,
        end_date = None,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_metrics WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if start_date is not None:
                sql += f" AND metric_date >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date is not None:
                sql += f" AND metric_date <= ${idx}"
                params.append(end_date)
                idx += 1
            sql += f" ORDER BY metric_date DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 30), 365)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_metric(dict(row)) for row in rows]

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
                payload.get("detected_at"),
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

    def _decode_vector_profile(self, row: dict) -> dict:
        result = dict(row)
        result["embedding"] = self._decode_json_field(result.get("embedding"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_vector_profile(self, profile: dict) -> dict:
        payload = dict(profile or {})
        embedding = payload.get("embedding") or []
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_vector_profiles
                    (strategy_id, profile_type, vector_method, metric, vector_dim, embedding, signature,
                     backend, index_version, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10::jsonb, NOW(), NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                str(payload.get("profile_type") or "behavior"),
                str(payload.get("vector_method") or "price_volume"),
                str(payload.get("metric") or "cosine"),
                int(payload.get("vector_dim") or len(embedding)),
                json.dumps(embedding, ensure_ascii=False, default=str),
                payload.get("signature"),
                str(payload.get("backend") or "index"),
                payload.get("index_version"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_vector_profile(dict(row))

    async def list_strategy_vector_profiles(
        self,
        strategy_id: Optional[str] = None,
        profile_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_vector_profiles WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if profile_type:
                sql += f" AND profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            sql += f" ORDER BY updated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_profile(dict(row)) for row in rows]

    def _decode_vector_index(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_vector_index_registry(self, entry: dict) -> dict:
        payload = dict(entry or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO vector_index_registry
                    (index_name, backend, status, profile_type, vector_method, metric, sample_count,
                     index_version, metadata, built_at, activated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::timestamptz, $11::timestamptz, NOW())
                ON CONFLICT (index_name, index_version) DO UPDATE SET
                    backend = EXCLUDED.backend,
                    status = EXCLUDED.status,
                    profile_type = EXCLUDED.profile_type,
                    vector_method = EXCLUDED.vector_method,
                    metric = EXCLUDED.metric,
                    sample_count = EXCLUDED.sample_count,
                    metadata = EXCLUDED.metadata,
                    built_at = EXCLUDED.built_at,
                    activated_at = EXCLUDED.activated_at
                RETURNING *
                """,
                str(payload.get("index_name") or "default"),
                str(payload.get("backend") or "index"),
                str(payload.get("status") or "building"),
                payload.get("profile_type"),
                payload.get("vector_method"),
                str(payload.get("metric") or "cosine"),
                int(payload.get("sample_count") or 0),
                str(payload.get("index_version") or "v1"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("built_at"),
                payload.get("activated_at"),
            )
        return self._decode_vector_index(dict(row))

    async def list_vector_index_registry(
        self,
        index_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM vector_index_registry WHERE 1=1"
            params: list = []
            idx = 1
            if index_name:
                sql += f" AND index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_index(dict(row)) for row in rows]

    def _decode_generation_experiment(self, row: dict) -> dict:
        result = dict(row)
        for key in ("parameters", "strategy_spec", "evaluation", "result"):
            result[key] = self._decode_json_field(result.get(key), {})
        return result

    async def save_strategy_generation_experiment(self, experiment: dict) -> dict:
        payload = dict(experiment or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_generation_experiments
                    (experiment_id, strategy_id, source, generator_type, optimizer_type, status, hypothesis,
                     prompt, parameters, strategy_spec, evaluation, result, parent_experiment_id,
                     artifact_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7,
                        $8, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13,
                        $14, NOW(), NOW())
                ON CONFLICT (experiment_id) DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    source = EXCLUDED.source,
                    generator_type = EXCLUDED.generator_type,
                    optimizer_type = EXCLUDED.optimizer_type,
                    status = EXCLUDED.status,
                    hypothesis = EXCLUDED.hypothesis,
                    prompt = EXCLUDED.prompt,
                    parameters = EXCLUDED.parameters,
                    strategy_spec = EXCLUDED.strategy_spec,
                    evaluation = EXCLUDED.evaluation,
                    result = EXCLUDED.result,
                    parent_experiment_id = EXCLUDED.parent_experiment_id,
                    artifact_id = EXCLUDED.artifact_id,
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get("experiment_id") or ""),
                payload.get("strategy_id"),
                str(payload.get("source") or "unknown"),
                str(payload.get("generator_type") or "rule"),
                payload.get("optimizer_type"),
                str(payload.get("status") or "draft"),
                payload.get("hypothesis"),
                payload.get("prompt"),
                json.dumps(payload.get("parameters") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("strategy_spec") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("evaluation") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("result") or {}, ensure_ascii=False, default=str),
                payload.get("parent_experiment_id"),
                payload.get("artifact_id"),
            )
        return self._decode_generation_experiment(dict(row))

    async def get_strategy_generation_experiment(self, experiment_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_generation_experiments
                WHERE experiment_id = $1
                LIMIT 1
                """,
                experiment_id,
            )
        if not row:
            return None
        return self._decode_generation_experiment(dict(row))

    async def list_strategy_generation_experiments(
        self,
        strategy_id: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_generation_experiments WHERE 1=1"
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
            if source:
                sql += f" AND source = ${idx}"
                params.append(source)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_generation_experiment(dict(row)) for row in rows]

    def _decode_task_run(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        result["result"] = self._decode_json_field(result.get("result"), {})
        return result

    async def save_strategy_task_run(self, run: dict) -> dict:
        payload = dict(run or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_task_runs
                    (task_name, task_scope, task_key, status, trace_id, payload, result, error, started_at, completed_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, COALESCE($9::timestamptz, NOW()), $10::timestamptz)
                RETURNING *
                """,
                str(payload.get("task_name") or "unknown"),
                payload.get("task_scope"),
                payload.get("task_key"),
                str(payload.get("status") or "running"),
                payload.get("trace_id"),
                json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("result") or {}, ensure_ascii=False, default=str),
                payload.get("error"),
                payload.get("started_at"),
                payload.get("completed_at"),
            )
        return self._decode_task_run(dict(row))

    async def update_strategy_task_run(
        self,
        run_id: int,
        status: Optional[str] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        completed_at = None,
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE strategy_task_runs
                SET status = COALESCE($2, status),
                    result = CASE WHEN $3::jsonb IS NULL THEN result ELSE $3::jsonb END,
                    error = COALESCE($4, error),
                    completed_at = COALESCE($5::timestamptz, completed_at, NOW())
                WHERE id = $1
                RETURNING *
                """,
                int(run_id),
                status,
                None if result is None else json.dumps(result, ensure_ascii=False, default=str),
                error,
                completed_at,
            )
        if not row:
            return None
        return self._decode_task_run(dict(row))

    async def list_strategy_task_runs(
        self,
        task_name: Optional[str] = None,
        task_scope: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_task_runs WHERE 1=1"
            params: list = []
            idx = 1
            if task_name:
                sql += f" AND task_name = ${idx}"
                params.append(task_name)
                idx += 1
            if task_scope:
                sql += f" AND task_scope = ${idx}"
                params.append(task_scope)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY started_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_task_run(dict(row)) for row in rows]

    def _decode_factory_run(self, row: dict) -> dict:
        result = dict(row)
        for key in ("summary", "stages", "snapshot_summary"):
            result[key] = self._decode_json_field(result.get(key), {})
        return result

    async def save_strategy_factory_run(self, run: dict) -> None:
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")
        started_at = run.get("started_at") or datetime.now(timezone.utc).isoformat()
        completed_at = run.get("completed_at")
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_runs
                    (run_id, status, started_at, completed_at, elapsed_seconds, summary, stages,
                     snapshot_summary, error)
                VALUES ($1, $2, $3::timestamptz, $4::timestamptz, $5, $6::jsonb, $7::jsonb,
                        $8::jsonb, $9)
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    elapsed_seconds = EXCLUDED.elapsed_seconds,
                    summary = EXCLUDED.summary,
                    stages = EXCLUDED.stages,
                    snapshot_summary = EXCLUDED.snapshot_summary,
                    error = EXCLUDED.error
                """,
                run_id,
                str(run.get("status") or "unknown"),
                started_at,
                completed_at,
                float(run.get("elapsed_seconds") or 0),
                json.dumps(run.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(run.get("stages") or {}, ensure_ascii=False, default=str),
                json.dumps(run.get("snapshot_summary") or {}, ensure_ascii=False, default=str),
                run.get("error"),
            )

    async def list_strategy_factory_runs(self, limit: int = 20) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM strategy_factory_runs
                ORDER BY started_at DESC
                LIMIT $1
                """,
                max(1, min(int(limit or 20), 100)),
            )
        return [self._decode_factory_run(dict(row)) for row in rows]

    async def get_strategy_factory_run(self, run_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_factory_runs
                WHERE run_id = $1
                LIMIT 1
                """,
                run_id,
            )
        if not row:
            return None
        return self._decode_factory_run(dict(row))

    async def get_latest_strategy_factory_run(self) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_factory_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        if not row:
            return None
        return self._decode_factory_run(dict(row))

    async def count_strategies_by_type(self, status: str = "listed") -> Dict[str, int]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT strategy_type, COUNT(*)::int AS cnt FROM strategies WHERE status = $1 GROUP BY strategy_type",
                status,
            )
        return {r["strategy_type"]: r["cnt"] for r in rows}

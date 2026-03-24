"""TimescaleDB 策略超市 Mixin — CRUD / 静态工具 / 工厂 / 质量报告 / 领域事件"""

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyCrudMixin:
    """静态工具方法 + 策略 CRUD + 工厂辅助 + 质量报告 + 领域事件 + 每日快照"""

    # ── 静态 / 类工具方法 ──

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

    @staticmethod
    def _coerce_timestamp(value: Any) -> Optional[datetime]:
        if value is None or isinstance(value, datetime):
            return value
        raw = str(value or '').strip()
        if not raw:
            return None
        normalized = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            return None

    @staticmethod
    def _coerce_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raw = str(value or '').strip()
        if not raw:
            return None
        normalized = raw[:-1] + '+00:00' if raw.endswith('Z') else raw
        try:
            return datetime.fromisoformat(normalized).date()
        except Exception:
            pass
        try:
            return date.fromisoformat(raw.split('T', 1)[0])
        except Exception:
            return None

    @staticmethod
    def _coerce_ts_code(value: Any) -> Optional[str]:
        if value is None:
            return None
        raw = str(value or "").strip().upper()
        if not raw:
            return None
        if "." in raw:
            return raw
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) == 6:
            suffix = "SH" if digits.startswith(("5", "6", "9")) else "SZ"
            return f"{digits}.{suffix}"
        return raw

    @staticmethod
    def _normalize_strategy_statuses(status: Any) -> Optional[list[str]]:
        if status is None:
            return None
        raw_values = status if isinstance(status, (list, tuple, set)) else str(status).split(",")
        normalized: list[str] = []
        for item in raw_values:
            token = str(item or "").strip().lower()
            if not token:
                continue
            if token in {"all", "*"}:
                return None
            if token == "published":
                token = "listed"
            if token not in normalized:
                normalized.append(token)
        return normalized or None

    @staticmethod
    def _encode_pgvector(values: Any) -> Optional[str]:
        try:
            vector = [float(item) for item in list(values or [])]
        except Exception:
            return None
        if not vector:
            return None
        cleaned: List[float] = []
        for item in vector:
            if item != item or item in {float('inf'), float('-inf')}:
                cleaned.append(0.0)
            else:
                cleaned.append(float(item))
        return '[' + ','.join(format(item, '.10g') for item in cleaned) + ']'

    @staticmethod
    def _resolve_vector_index_name(payload: dict) -> str:
        meta = dict(payload.get('metadata') or {})
        return str(payload.get('index_name') or meta.get('index_name') or 'strategy_behavior')

    @classmethod
    def _pgvector_distance_sql(cls, column: str, metric: str, dim: int, query_ref: str = '$1') -> tuple[str, str]:
        cast_column = f"{column}::vector({int(dim)})"
        cast_query = f"{query_ref}::vector({int(dim)})"
        resolved_metric = str(metric or 'cosine').lower()
        if resolved_metric == 'euclidean':
            distance = f"({cast_column} <-> {cast_query})"
            similarity = f"(1 / (1 + {distance}))"
            return distance, similarity
        distance = f"({cast_column} <=> {cast_query})"
        similarity = f"(1 - {distance})"
        return distance, similarity

    @staticmethod
    def _pgvector_opclass(metric: str) -> str:
        return 'vector_l2_ops' if str(metric or 'cosine').lower() == 'euclidean' else 'vector_cosine_ops'

    @staticmethod
    def _sql_quote(value: Any) -> str:
        return "'" + str(value or '').replace("'", "''") + "'"

    @classmethod
    def _pgvector_partial_index_name(cls, prefix: str, *parts: Any) -> str:
        digest = hashlib.sha1('|'.join(str(part or '') for part in parts).encode('utf-8')).hexdigest()[:12]
        return f"{prefix}_{digest}"

    # ── 行解码 ──

    def _decode_strategy_row(self, row: dict) -> dict:
        result = dict(row)
        result["params"] = self._decode_json_field(result.get("params"), {})
        result["factor_weights"] = self._decode_json_field(result.get("factor_weights"), {})
        result["tags"] = self._decode_json_field(result.get("tags"), result.get("tags") or [])
        return result

    # ── 策略 CRUD ──

    async def save_strategy(self, data: dict) -> dict:
        sid = str(data.get("id", "")).strip()
        if not sid:
            raise ValueError("strategy id is required")
        now = datetime.now(timezone.utc)
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
        return {**data, "id": sid, "created_at": now.isoformat(), "updated_at": now.isoformat()}

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
        return self._decode_strategy_row(dict(row))

    async def list_strategies(self, status: Any = "listed", strategy_type: str = None, limit: int = 20, offset: int = 0) -> List[dict]:
        statuses = self._normalize_strategy_statuses(status)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.*,
                       COALESCE((SELECT AVG(rating)::float FROM strategy_reviews WHERE strategy_id = s.id), 0) AS avg_rating
                FROM strategies s
                WHERE ($1::text[] IS NULL OR s.status = ANY($1::text[]))
                  AND ($2::text IS NULL OR s.strategy_type = $2)
                ORDER BY s.updated_at DESC LIMIT $3 OFFSET $4
                """,
                statuses,
                strategy_type,
                limit,
                offset,
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

    # ── 策略指标 ──

    async def save_strategy_metrics(self, strategy_id: str, period: str, metrics: dict) -> None:
        now = datetime.now(timezone.utc)
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

    # ── 评论 ──

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

    # ── 订阅 ──

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

    # ── 每日快照 ──

    async def save_daily_snapshot(self, snapshot_date, data: dict) -> None:
        normalized_snapshot_date = self._coerce_date(snapshot_date)
        if normalized_snapshot_date is None:
            raise ValueError("snapshot_date is required")
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO daily_snapshot_history
                   (snapshot_date, fear_greed_index, fg_components, factor_ic, factor_ic_trend, factor_research,
                    north_fund_3d_net, margin_5d_change_pct, hot_sectors, cold_sectors,
                    listed_count, category_counts, summary, completeness, sources,
                    failure_reasons, missing_fields, degraded)
                   VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7, $8, $9::jsonb, $10::jsonb,
                           $11, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17::jsonb, $18)
                   ON CONFLICT (snapshot_date) DO UPDATE SET
                    fear_greed_index = EXCLUDED.fear_greed_index,
                    fg_components = EXCLUDED.fg_components,
                    factor_ic = EXCLUDED.factor_ic,
                    factor_ic_trend = EXCLUDED.factor_ic_trend,
                    factor_research = EXCLUDED.factor_research,
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
                normalized_snapshot_date,
                data.get("fear_greed_index"),
                json.dumps(data.get("fg_components") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_ic") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_ic_trend") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("factor_research") or {}, ensure_ascii=False, default=str),
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
        for key in ("fg_components", "factor_ic", "factor_ic_trend", "factor_research", "category_counts", "summary", "completeness", "sources"):
            result[key] = self._decode_json_field(result.get(key), {})
        for key in ("hot_sectors", "cold_sectors", "failure_reasons", "missing_fields"):
            result[key] = self._decode_json_field(result.get(key), [])
        fg_level = result.get("fg_level")
        if not fg_level:
            fg_value = result.get("fear_greed_index")
            try:
                fg_numeric = int(fg_value)
            except Exception:
                fg_numeric = 50
            fg_level = "greed" if fg_numeric >= 70 else ("fear" if fg_numeric <= 30 else "neutral")
            result["fg_level"] = fg_level
        result.setdefault("date", str(result.get("snapshot_date") or ""))
        result.setdefault("fear_greed", result.get("fear_greed_index"))
        result.setdefault("sentiment", fg_level)
        result["north_fund"] = dict(result.get("north_fund") or {})
        result["north_fund"].setdefault("net_3d", result.get("north_fund_3d_net"))
        return result

    async def get_daily_snapshot(self, snapshot_date = None) -> Optional[dict]:
        normalized_snapshot_date = None if snapshot_date is None else self._coerce_date(snapshot_date)
        if snapshot_date is not None and normalized_snapshot_date is None:
            raise ValueError("snapshot_date is invalid")
        async with self.acquire() as conn:
            if normalized_snapshot_date is None:
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
                    normalized_snapshot_date,
                )
        if not row:
            return None
        return self._decode_daily_snapshot(dict(row))

    async def get_north_fund_history(self, days: int = 30, end_date = None) -> List[dict]:
        normalized_end_date = self._coerce_date(end_date) or date.today()
        fetch_limit = max(1, min(int(days or 30), 365))
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT trade_date, north_money, south_money, net_amount, ggt_ss, ggt_sz, hgt, sgt
                FROM north_fund_flow
                WHERE trade_date <= $1
                ORDER BY trade_date DESC
                LIMIT $2
                """,
                normalized_end_date,
                fetch_limit,
            )
        return [
            {
                "trade_date": row.get("trade_date"),
                "north_money": float(row.get("north_money") or 0.0),
                "south_money": float(row.get("south_money") or 0.0),
                "net_amount": float(row.get("net_amount") or 0.0),
                "ggt_ss": float(row.get("ggt_ss") or 0.0),
                "ggt_sz": float(row.get("ggt_sz") or 0.0),
                "hgt": float(row.get("hgt") or 0.0),
                "sgt": float(row.get("sgt") or 0.0),
                "source": "north_fund_flow",
            }
            for row in rows
            if isinstance(row.get("trade_date"), date)
        ]

    async def get_recent_north_fund_summary(self, days: int = 3, sample_limit: int = 5, end_date = None) -> Optional[dict]:
        rows = await self.get_north_fund_history(
            days=max(int(sample_limit or 5), int(days or 3), 1),
            end_date=end_date,
        )
        if not rows:
            return None
        selected = list(rows[: max(1, int(days or 3))])
        latest_trade_date = rows[0].get("trade_date") if rows else None
        stale_age_days = None
        stale = False
        if isinstance(latest_trade_date, date):
            stale_age_days = max(0, (date.today() - latest_trade_date).days)
            stale = stale_age_days > 7
        return {
            "days": max(1, int(days or 3)),
            "sample_count": len(rows),
            "trade_dates": [row.get("trade_date") for row in selected],
            "total_net": round(sum(float(row.get("north_money") or 0.0) for row in selected), 2),
            "latest_trade_date": latest_trade_date,
            "stale_age_days": stale_age_days,
            "stale": stale,
            "source": "north_fund_flow",
            "series": [
                {"trade_date": row.get("trade_date"), "north_money": float(row.get("north_money") or 0.0)}
                for row in rows
            ],
        }

    async def get_margin_market_history(self, days: int = 30, end_date = None) -> List[dict]:
        fetch_limit = max(1, min(int(days or 30), 365))
        normalized_end_date = self._coerce_date(end_date) or date.today()
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT trade_date, exchange_id, rzye, rzmre, rzche, rqye, rqmcl, rqyl, rzrqye
                FROM margin_market_flow
                WHERE trade_date <= $1
                ORDER BY trade_date DESC, exchange_id ASC
                LIMIT $2
                """,
                normalized_end_date,
                fetch_limit * 3,
            )
        source = "margin_market_flow"
        normalized_rows: List[Dict[str, Any]] = []
        if rows:
            grouped: Dict[date, Dict[str, Any]] = {}
            for row in rows:
                trade_date = row.get("trade_date")
                if not isinstance(trade_date, date):
                    continue
                bucket = grouped.setdefault(
                    trade_date,
                    {
                        "trade_date": trade_date,
                        "marginBalance": 0.0,
                        "marginBuy": 0.0,
                        "marginRepay": 0.0,
                        "shortBalance": 0.0,
                        "shortSell": 0.0,
                        "shortVolume": 0.0,
                        "totalBalance": 0.0,
                        "source": source,
                    },
                )
                bucket["marginBalance"] += float(row.get("rzye") or 0.0)
                bucket["marginBuy"] += float(row.get("rzmre") or 0.0)
                bucket["marginRepay"] += float(row.get("rzche") or 0.0)
                bucket["shortBalance"] += float(row.get("rqye") or 0.0)
                bucket["shortSell"] += float(row.get("rqmcl") or 0.0)
                bucket["shortVolume"] += float(row.get("rqyl") or 0.0)
                bucket["totalBalance"] += float(row.get("rzrqye") or 0.0)
            normalized_rows = sorted(grouped.values(), key=lambda item: item["trade_date"], reverse=True)

        if normalized_rows:
            return normalized_rows[:fetch_limit]

        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    trade_date,
                    SUM(rzye) AS rzye,
                    SUM(rzmre) AS rzmre,
                    SUM(rzche) AS rzche,
                    SUM(rqye) AS rqye,
                    SUM(rqmcl) AS rqmcl,
                    SUM(rqyl) AS rqyl,
                    SUM(rzrqye) AS rzrqye
                FROM margin_detail
                WHERE trade_date <= $1
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT $2
                """,
                normalized_end_date,
                fetch_limit,
            )
        return [
            {
                "trade_date": row.get("trade_date"),
                "marginBalance": float(row.get("rzye") or 0.0),
                "marginBuy": float(row.get("rzmre") or 0.0),
                "marginRepay": float(row.get("rzche") or 0.0),
                "shortBalance": float(row.get("rqye") or 0.0),
                "shortSell": float(row.get("rqmcl") or 0.0),
                "shortVolume": float(row.get("rqyl") or 0.0),
                "totalBalance": float(row.get("rzrqye") or 0.0),
                "source": "margin_detail_aggregate",
            }
            for row in rows
            if isinstance(row.get("trade_date"), date)
        ]

    async def get_margin_detail_latest(self, limit: int = 20, ts_code = None, end_date = None) -> List[dict]:
        normalized_end_date = self._coerce_date(end_date) or date.today()
        normalized_ts_code = self._coerce_ts_code(ts_code)
        fetch_limit = max(1, min(int(limit or 20), 500))
        async with self.acquire() as conn:
            if normalized_ts_code:
                rows = await conn.fetch(
                    """
                    SELECT trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye
                    FROM margin_detail
                    WHERE trade_date <= $1 AND ts_code = $2
                    ORDER BY trade_date DESC, ts_code ASC
                    LIMIT $3
                    """,
                    normalized_end_date,
                    normalized_ts_code,
                    fetch_limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye
                    FROM margin_detail
                    WHERE trade_date <= $1
                    ORDER BY trade_date DESC, ts_code ASC
                    LIMIT $2
                    """,
                    normalized_end_date,
                    fetch_limit,
                )
        return [
            {
                "trade_date": row.get("trade_date"),
                "ts_code": str(row.get("ts_code") or ""),
                "code": str(row.get("ts_code") or "").split(".", 1)[0],
                "marginBalance": float(row.get("rzye") or 0.0),
                "shortBalance": float(row.get("rqye") or 0.0),
                "marginBuy": float(row.get("rzmre") or 0.0),
                "shortVolume": float(row.get("rqyl") or 0.0),
                "marginRepay": float(row.get("rzche") or 0.0),
                "shortRepay": float(row.get("rqchl") or 0.0),
                "shortSell": float(row.get("rqmcl") or 0.0),
                "totalBalance": float(row.get("rzrqye") or 0.0),
                "source": "margin_detail",
            }
            for row in rows
            if isinstance(row.get("trade_date"), date)
        ]

    async def get_margin_ranking(self, top_n: int = 20, sort_by: str = "balance", end_date = None) -> List[dict]:
        normalized_end_date = self._coerce_date(end_date) or date.today()
        fetch_limit = max(1, min(int(top_n or 20), 200))
        sort_key = str(sort_by or "balance").lower()
        sort_column_map = {
            "balance": "rzrqye",
            "buy": "rzmre",
            "sell": "rqmcl",
        }
        sort_column = sort_column_map.get(sort_key, "rzrqye")
        async with self.acquire() as conn:
            latest_trade_date = await conn.fetchval(
                """
                SELECT MAX(trade_date)
                FROM margin_detail
                WHERE trade_date <= $1
                """,
                normalized_end_date,
            )
            if latest_trade_date is None:
                return []
            rows = await conn.fetch(
                f"""
                SELECT trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye
                FROM margin_detail
                WHERE trade_date = $1
                ORDER BY {sort_column} DESC NULLS LAST, ts_code ASC
                LIMIT $2
                """,
                latest_trade_date,
                fetch_limit,
            )
        return [
            {
                "trade_date": row.get("trade_date"),
                "ts_code": str(row.get("ts_code") or ""),
                "code": str(row.get("ts_code") or "").split(".", 1)[0],
                "marginBalance": float(row.get("rzye") or 0.0),
                "shortBalance": float(row.get("rqye") or 0.0),
                "marginBuy": float(row.get("rzmre") or 0.0),
                "shortVolume": float(row.get("rqyl") or 0.0),
                "marginRepay": float(row.get("rzche") or 0.0),
                "shortRepay": float(row.get("rqchl") or 0.0),
                "shortSell": float(row.get("rqmcl") or 0.0),
                "totalBalance": float(row.get("rzrqye") or 0.0),
                "source": "margin_detail_ranking",
            }
            for row in rows
            if isinstance(row.get("trade_date"), date)
        ]

    async def get_recent_margin_summary(
        self,
        days: int = 10,
        sample_limit: int = 10,
        change_lookback_days: int = 5,
    ) -> Optional[dict]:
        fetch_limit = max(
            int(sample_limit or 10),
            int(days or 10),
            int(change_lookback_days or 5) + 1,
            1,
        )
        normalized_rows = await self.get_margin_market_history(days=fetch_limit)
        if not normalized_rows:
            return None
        source = str((normalized_rows[0] or {}).get("source") or "margin_market_flow")

        latest = normalized_rows[0]
        older = normalized_rows[min(max(int(change_lookback_days or 5), 1), len(normalized_rows) - 1)]
        latest_balance = float(latest.get("marginBalance") or 0.0)
        older_balance = float(older.get("marginBalance") or 0.0)
        change_5d = None
        if older_balance > 0:
            change_5d = round((latest_balance - older_balance) / older_balance * 100, 2)
        stale_age_days = max(0, (date.today() - latest["trade_date"]).days) if isinstance(latest.get("trade_date"), date) else None
        stale = bool(stale_age_days is not None and stale_age_days > 7)
        return {
            "days": max(1, int(days or 10)),
            "sample_count": len(normalized_rows),
            "latest_trade_date": latest.get("trade_date"),
            "stale_age_days": stale_age_days,
            "stale": stale,
            "source": source,
            "margin_balance_latest": round(latest_balance, 2),
            "margin_buy_latest": round(float(latest.get("marginBuy") or 0.0), 2),
            "margin_balance_change_5d": change_5d,
            "recent_rows": normalized_rows[: max(1, min(fetch_limit, 5))],
            "series": normalized_rows[:fetch_limit],
        }

    async def list_daily_snapshots(
        self,
        limit: int = 20,
        start_date = None,
        end_date = None,
    ) -> List[dict]:
        normalized_start_date = None if start_date is None else self._coerce_date(start_date)
        normalized_end_date = None if end_date is None else self._coerce_date(end_date)
        if start_date is not None and normalized_start_date is None:
            raise ValueError("start_date is invalid")
        if end_date is not None and normalized_end_date is None:
            raise ValueError("end_date is invalid")
        async with self.acquire() as conn:
            sql = "SELECT * FROM daily_snapshot_history WHERE 1=1"
            params: list = []
            idx = 1
            if normalized_start_date is not None:
                sql += f" AND snapshot_date >= ${idx}"
                params.append(normalized_start_date)
                idx += 1
            if normalized_end_date is not None:
                sql += f" AND snapshot_date <= ${idx}"
                params.append(normalized_end_date)
                idx += 1
            sql += f" ORDER BY snapshot_date DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_daily_snapshot(dict(row)) for row in rows]

    # ── 质量报告 ──

    async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report: dict) -> None:
        now = datetime.now(timezone.utc)
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

    # ── 状态事件 ──

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

    # ── 领域事件 ──

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

    # ── 策略类型统计 ──

    async def count_strategies_by_type(self, status: str = "listed") -> Dict[str, int]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT strategy_type, COUNT(*)::int AS cnt FROM strategies WHERE status = $1 GROUP BY strategy_type",
                status,
            )
        return {r["strategy_type"]: r["cnt"] for r in rows}

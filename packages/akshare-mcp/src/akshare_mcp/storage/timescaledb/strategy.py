"""TimescaleDB 适配器 — 策略超市 Mixin"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyMixin:
    """策略超市 CRUD（strategies / strategy_metrics / strategy_reviews / strategy_subscriptions）"""

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

    async def update_strategy_status(self, strategy_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self.acquire() as conn:
            await conn.execute(
                "UPDATE strategies SET status = $1, updated_at = $2::timestamptz WHERE id = $3",
                status, now, strategy_id,
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
                    listed_count, category_counts)
                   VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, $9::jsonb, $10, $11::jsonb)
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
                    category_counts = EXCLUDED.category_counts
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
            )

    async def count_strategies_by_type(self, status: str = "listed") -> Dict[str, int]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT strategy_type, COUNT(*)::int AS cnt FROM strategies WHERE status = $1 GROUP BY strategy_type",
                status,
            )
        return {r["strategy_type"]: r["cnt"] for r in rows}

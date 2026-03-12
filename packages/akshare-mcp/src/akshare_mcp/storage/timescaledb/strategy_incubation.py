"""TimescaleDB 策略超市 Mixin — 孵化账户 / 孵化指标 / 模拟交易"""

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class StrategyIncubationMixin:
    """孵化账户 + 孵化指标 + 模拟盘(paper) + 孵化流水线快照"""

    # ── 孵化账户 ──

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

    # ── 孵化指标 ──

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

    # ── 模拟盘 ──

    async def get_paper_account(self, account_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE id = $1 LIMIT 1",
                account_id,
            )
        return dict(row) if row else None

    async def get_paper_account_by_strategy(self, strategy_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id = $1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        return dict(row) if row else None

    async def save_paper_account(self, account: dict) -> dict:
        payload = dict(account or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_accounts
                    (id, user_id, name, initial_capital, current_capital, total_value, risk_rules,
                     strategy_id, account_type, incubation_stage, promotion_candidate, archived_reason, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb,
                        $8, $9, $10, $11, $12, $13, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    name = EXCLUDED.name,
                    initial_capital = EXCLUDED.initial_capital,
                    current_capital = EXCLUDED.current_capital,
                    total_value = EXCLUDED.total_value,
                    risk_rules = EXCLUDED.risk_rules,
                    strategy_id = EXCLUDED.strategy_id,
                    account_type = EXCLUDED.account_type,
                    incubation_stage = EXCLUDED.incubation_stage,
                    promotion_candidate = EXCLUDED.promotion_candidate,
                    archived_reason = EXCLUDED.archived_reason,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get('id') or ''),
                payload.get('user_id') or 'default',
                str(payload.get('name') or 'paper_account'),
                float(payload.get('initial_capital') or 0.0),
                float(payload.get('current_capital') or 0.0),
                float(payload.get('total_value') or 0.0),
                json.dumps(payload.get('risk_rules') or {}, ensure_ascii=False, default=str),
                payload.get('strategy_id'),
                payload.get('account_type') or 'manual',
                payload.get('incubation_stage') or 'warmup',
                bool(payload.get('promotion_candidate')),
                payload.get('archived_reason'),
                payload.get('status') or 'active',
            )
        return dict(row)

    async def update_paper_account_status(self, account_id: str, status: str, stage = None, promotion_candidate = None) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_accounts
                SET status = $2,
                    incubation_stage = COALESCE($3, incubation_stage),
                    promotion_candidate = COALESCE($4, promotion_candidate),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                account_id,
                status,
                stage,
                promotion_candidate,
            )
        return dict(row) if row else None

    async def list_strategy_paper_orders(self, strategy_id: str, signal_date = None, status: Optional[str] = None, limit: int = 200) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM paper_orders WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if signal_date is not None:
                sql += f" AND signal_date = ${idx}"
                params.append(signal_date)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 2000)))
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def save_paper_order(self, order: dict) -> dict:
        payload = dict(order or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_orders
                    (account_id, strategy_id, signal_date, source, code, direction, shares, price,
                     order_type, stop_price, status, commission, reason, filled_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, NOW(), NOW())
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('strategy_id'),
                payload.get('signal_date'),
                payload.get('source') or 'manual',
                payload.get('code'),
                payload.get('direction'),
                int(payload.get('shares') or 0),
                payload.get('price'),
                payload.get('order_type') or 'market',
                payload.get('stop_price'),
                payload.get('status') or 'pending',
                float(payload.get('commission') or 0.0),
                payload.get('reason'),
                payload.get('filled_at'),
            )
        return dict(row)

    async def update_paper_order(self, order_id: int, updates: dict) -> Optional[dict]:
        payload = dict(updates or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_orders
                SET price = COALESCE($2, price),
                    shares = COALESCE($3, shares),
                    status = COALESCE($4, status),
                    commission = COALESCE($5, commission),
                    reason = COALESCE($6, reason),
                    filled_at = COALESCE($7, filled_at),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                int(order_id),
                payload.get('price'),
                payload.get('shares'),
                payload.get('status'),
                payload.get('commission'),
                payload.get('reason'),
                payload.get('filled_at'),
            )
        return dict(row) if row else None

    async def list_paper_positions(self, account_id: str) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_positions WHERE account_id = $1 ORDER BY stock_code",
                account_id,
            )
        return [dict(row) for row in rows]

    async def save_paper_position(self, position: dict) -> dict:
        payload = dict(position or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_positions
                    (account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value, profit_rate, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                ON CONFLICT (account_id, stock_code) DO UPDATE SET
                    stock_name = EXCLUDED.stock_name,
                    quantity = EXCLUDED.quantity,
                    cost_price = EXCLUDED.cost_price,
                    current_price = EXCLUDED.current_price,
                    market_value = EXCLUDED.market_value,
                    profit_rate = EXCLUDED.profit_rate,
                    updated_at = NOW()
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('stock_code'),
                payload.get('stock_name') or payload.get('stock_code') or '',
                int(payload.get('quantity') or 0),
                float(payload.get('cost_price') or 0.0),
                payload.get('current_price'),
                payload.get('market_value'),
                payload.get('profit_rate'),
            )
        return dict(row)

    async def save_paper_trade(self, trade: dict) -> dict:
        payload = dict(trade or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_trades
                    (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission, trade_time, reason, strategy_id, source_order_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                RETURNING *
                """,
                str(payload.get('id') or ''),
                payload.get('account_id'),
                payload.get('stock_code'),
                payload.get('stock_name') or payload.get('stock_code') or '',
                payload.get('trade_type'),
                float(payload.get('price') or 0.0),
                int(payload.get('quantity') or 0),
                float(payload.get('amount') or 0.0),
                float(payload.get('commission') or 0.0),
                payload.get('trade_time'),
                payload.get('reason'),
                payload.get('strategy_id'),
                payload.get('source_order_id'),
            )
        return dict(row)

    async def save_paper_nav(self, nav: dict) -> dict:
        payload = dict(nav or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_nav
                    (account_id, nav_date, total_value, cash, market_value, daily_return, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (account_id, nav_date) DO UPDATE SET
                    total_value = EXCLUDED.total_value,
                    cash = EXCLUDED.cash,
                    market_value = EXCLUDED.market_value,
                    daily_return = EXCLUDED.daily_return
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('nav_date'),
                float(payload.get('total_value') or 0.0),
                float(payload.get('cash') or 0.0),
                float(payload.get('market_value') or 0.0),
                payload.get('daily_return'),
            )
        return dict(row)

    async def get_paper_nav_rows(self, account_id: str, limit: int = 60) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_nav WHERE account_id = $1 ORDER BY nav_date DESC LIMIT $2",
                account_id,
                max(1, min(int(limit or 60), 365)),
            )
        return [dict(row) for row in rows]

    async def get_paper_order_summary(self, account_id: str) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int AS total_orders,
                    COUNT(*) FILTER (WHERE status = 'filled')::int AS total_trades,
                    COALESCE(SUM(price * shares) FILTER (WHERE status = 'filled'), 0)::float AS trade_amount
                FROM paper_orders
                WHERE account_id = $1
                """,
                account_id,
            )
        return {
            'total_orders': int((row or {}).get('total_orders') or 0),
            'total_trades': int((row or {}).get('total_trades') or 0),
            'trade_amount': float((row or {}).get('trade_amount') or 0.0),
        }

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

    # ── 孵化流水线快照 ──

    def _decode_incubation_pipeline_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["risk_flags"] = self._decode_json_field(result.get("risk_flags"), [])
        result["summary"] = self._decode_json_field(result.get("summary"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_incubation_pipeline_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_pipeline_snapshots
                    (strategy_id, account_id, pipeline_stage, pipeline_status, observed_days, promote_streak,
                     halt_streak, latest_decision, readiness_score, next_action, auto_review, auto_promoted,
                     blockers, risk_flags, summary, metadata, task_run_id, source, evaluated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17, $18, $19::timestamptz, NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                payload.get("account_id"),
                str(payload.get("pipeline_stage") or "warmup"),
                str(payload.get("pipeline_status") or "collecting"),
                int(payload.get("observed_days") or 0),
                int(payload.get("promote_streak") or 0),
                int(payload.get("halt_streak") or 0),
                payload.get("latest_decision"),
                float(payload.get("readiness_score") or 0.0),
                payload.get("next_action"),
                bool(payload.get("auto_review")),
                bool(payload.get("auto_promoted")),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("risk_flags") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("task_run_id"),
                str(payload.get("source") or "system"),
                self._coerce_timestamp(payload.get("evaluated_at")),
            )
        return self._decode_incubation_pipeline_snapshot(dict(row))

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id: str) -> Optional[dict]:
        rows = await self.list_strategy_incubation_pipeline_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_pipeline_snapshots(
        self,
        strategy_id: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        pipeline_status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_pipeline_snapshots WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if pipeline_stage:
                sql += f" AND pipeline_stage = ${idx}"
                params.append(pipeline_stage)
                idx += 1
            if pipeline_status:
                sql += f" AND pipeline_status = ${idx}"
                params.append(pipeline_status)
                idx += 1
            sql += f" ORDER BY evaluated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_pipeline_snapshot(dict(row)) for row in rows]

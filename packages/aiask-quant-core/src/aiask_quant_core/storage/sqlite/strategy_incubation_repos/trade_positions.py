from __future__ import annotations

from ._base import *  # noqa: F401,F403
from ._base import (
    _coerce_ts,
    _fallback_execution_audit_gate,
    _safe_float,
    _safe_int,
    _safe_rules_dict,
    _string,
)


class _TradePositionsMixin:
    async def backfill_trade_position_links(self, strategy_id: Optional[str] = None) -> dict:
        strategy_filter = str(strategy_id or "").strip() or None
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE paper_trades
                SET signal_id = COALESCE(paper_trades.signal_id, paper_orders.signal_id),
                    position_id = COALESCE(paper_trades.position_id, paper_orders.position_id),
                    strategy_id = COALESCE(paper_trades.strategy_id, paper_orders.strategy_id)
                FROM paper_orders
                WHERE paper_trades.source_order_id = paper_orders.id
                  AND paper_orders.position_id IS NOT NULL
                  AND ($1 IS NULL OR COALESCE(paper_trades.strategy_id, paper_orders.strategy_id) = $1)
                """,
                strategy_filter,
            )
        positions_touched: set[str] = set()
        trades = await self.list_strategy_paper_trades(strategy_filter, limit=5000) if strategy_filter else []
        if not strategy_filter:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM paper_trades ORDER BY trade_time DESC, created_at DESC LIMIT 5000"
                )
            trades = [dict(row) for row in rows]
        for trade in trades:
            position_id_value = str(trade.get("position_id") or "").strip()
            if not position_id_value:
                continue
            fill_id = str(trade.get("id") or "").strip()
            await self.save_strategy_trade_position_fill(
                {
                    "fill_id": f"fill_{fill_id}" if fill_id else "",
                    "position_id": position_id_value,
                    "trade_id": trade.get("id"),
                    "order_id": trade.get("source_order_id"),
                    "signal_id": trade.get("signal_id"),
                    "strategy_id": trade.get("strategy_id"),
                    "account_id": trade.get("account_id"),
                    "code": trade.get("stock_code"),
                    "fill_side": trade.get("trade_type"),
                    "quantity": int(trade.get("quantity") or 0),
                    "price": float(trade.get("price") or 0.0),
                    "amount": float(trade.get("amount") or 0.0),
                    "commission": float(trade.get("commission") or 0.0),
                    "trade_time": trade.get("trade_time"),
                    "payload": {"source": "paper_trades_backfill"},
                }
            )
            positions_touched.add(position_id_value)
        for position_id_value in positions_touched:
            await self.refresh_strategy_trade_position(position_id_value)
        return {
            "strategy_id": strategy_filter,
            "position_count": len(positions_touched),
            "fill_count": len(
                [
                    trade
                    for trade in trades
                    if str(trade.get("position_id") or "").strip()
                ]
            ),
        }

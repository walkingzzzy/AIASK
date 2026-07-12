"""Exit evidence data access used by the incubation runner."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from .intake import _resolve_db_async_method

logger = logging.getLogger(__name__)


class ExitEvidenceService:
    def __init__(
        self,
        *,
        decode_mapping: Callable[[Any], dict[str, Any]],
        max_holding_days: Callable[[dict[str, Any]], int],
    ) -> None:
        self._decode_mapping = decode_mapping
        self._max_holding_days = max_holding_days

    def strategy_has_exit_policy(self, strategy: dict[str, Any]) -> bool:
        payload = dict(strategy or {})
        params = self._decode_mapping(payload.get("params"))
        runtime_playbook = self._decode_mapping(
            payload.get("runtime_playbook") or params.get("runtime_playbook")
        )
        if self._decode_mapping(runtime_playbook.get("exit_policy")):
            return True
        return self._max_holding_days(payload) > 0

    @staticmethod
    def is_open_position_status(status: Any) -> bool:
        return str(status or "").strip().lower() in {
            "open", "pending_exit", "pending_entry", "created", "submitted", "",
        }

    @staticmethod
    def is_exit_order_direction(direction: Any) -> bool:
        return str(direction or "").strip().lower() in {
            "sell", "exit", "short", "close", "reduce",
        }

    @staticmethod
    def is_open_exit_order_status(status: Any) -> bool:
        return str(status or "").strip().lower() in {
            "pending", "submitted", "partial", "partially_filled", "open", "new", "",
        }

    async def list_open_positions(self, db: Any, *, strategy_id: str) -> list[dict[str, Any]]:
        list_positions = _resolve_db_async_method(db, "list_strategy_trade_positions")
        rows: list[Any] = []
        if list_positions is not None:
            try:
                rows = list(await list_positions(strategy_id=strategy_id, status="open", limit=500) or [])
            except TypeError:
                try:
                    rows = list(await list_positions(strategy_id, limit=500) or [])
                except Exception:
                    rows = []
            except Exception:
                rows = []
        if not rows:
            acquire = getattr(db, "acquire", None)
            if callable(acquire):
                try:
                    async with acquire() as conn:
                        rows = list(await conn.fetch(
                            """
                            SELECT * FROM strategy_trade_positions
                            WHERE strategy_id = $1
                              AND LOWER(COALESCE(status, 'open')) IN
                                  ('open', 'pending_exit', 'pending_entry', 'created', 'submitted')
                            LIMIT 500
                            """,
                            strategy_id,
                        ) or [])
                except Exception:
                    rows = []
            else:
                connection = getattr(db, "connection", None)
                if connection is not None:
                    try:
                        cursor = connection.execute(
                            """
                            SELECT * FROM strategy_trade_positions
                            WHERE strategy_id = ?
                              AND LOWER(COALESCE(status, 'open')) IN
                                  ('open', 'pending_exit', 'pending_entry', 'created', 'submitted')
                            LIMIT 500
                            """,
                            (strategy_id,),
                        )
                        columns = [item[0] for item in cursor.description]
                        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    except Exception:
                        rows = []
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row or {})
            if not self.is_open_position_status(item.get("status") or "open"):
                continue
            code = str(item.get("code") or item.get("stock_code") or "").strip()
            if code:
                result.append({
                    "id": item.get("id") or item.get("position_id"),
                    "position_id": item.get("position_id") or item.get("id"),
                    "code": code,
                    "status": item.get("status") or "open",
                    "opened_at": item.get("opened_at") or item.get("entry_ts") or item.get("created_at"),
                })
        return result

    async def list_exit_orders(self, db: Any, *, strategy_id: str) -> list[dict[str, Any]]:
        list_orders = _resolve_db_async_method(db, "list_strategy_paper_orders")
        rows: list[Any] = []
        if list_orders is not None:
            try:
                rows = list(await list_orders(strategy_id, limit=1000) or [])
            except TypeError:
                try:
                    rows = list(await list_orders(strategy_id=strategy_id, limit=1000) or [])
                except Exception:
                    rows = []
            except Exception:
                rows = []
        if not rows:
            acquire = getattr(db, "acquire", None)
            if callable(acquire):
                try:
                    async with acquire() as conn:
                        rows = list(await conn.fetch(
                            """
                            SELECT * FROM paper_orders WHERE strategy_id = $1
                            ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 1000
                            """,
                            strategy_id,
                        ) or [])
                except Exception:
                    rows = []
            else:
                connection = getattr(db, "connection", None)
                if connection is not None:
                    try:
                        cursor = connection.execute(
                            """
                            SELECT * FROM paper_orders WHERE strategy_id = ?
                            ORDER BY COALESCE(updated_at, created_at) DESC LIMIT 1000
                            """,
                            (strategy_id,),
                        )
                        columns = [item[0] for item in cursor.description]
                        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    except Exception:
                        rows = []
        return [dict(row or {}) for row in rows]

    async def count_exit_signals(
        self,
        db: Any,
        *,
        strategy_id: str,
        codes: set[str] | None = None,
    ) -> int:
        normalized_codes = {str(code).strip() for code in (codes or set()) if str(code).strip()}
        get_signals = _resolve_db_async_method(db, "get_signals")
        if get_signals is not None:
            try:
                signals = list(await get_signals(strategy_id, limit=2000) or [])
            except TypeError:
                try:
                    signals = list(await get_signals(strategy_id=strategy_id, limit=2000) or [])
                except Exception:
                    signals = []
            except Exception:
                signals = []
            count = 0
            for row in signals:
                item = dict(row or {})
                try:
                    signal_value = int(item.get("signal") or 0)
                except Exception:
                    signal_value = 0
                action = str(item.get("event_action") or item.get("action") or "").strip().lower()
                code = str(item.get("code") or "").strip()
                if (signal_value < 0 or action in {"sell", "exit", "close", "reduce"}) and (
                    not normalized_codes or not code or code in normalized_codes
                ):
                    count += 1
            return count
        connection = getattr(db, "connection", None)
        if connection is None:
            return 0
        try:
            params: tuple[Any, ...] = (strategy_id,)
            code_filter = ""
            if normalized_codes:
                code_filter = f" AND code IN ({','.join('?' for _ in normalized_codes)})"
                params = (strategy_id, *sorted(normalized_codes))
            cursor = connection.execute(
                """
                SELECT COUNT(*) FROM strategy_signals
                WHERE strategy_id = ?
                  AND (CAST(signal AS INTEGER) < 0
                       OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce'))
                """ + code_filter,
                params,
            )
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0
        except Exception:
            return 0

    def funnel_snapshot(
        self,
        *,
        open_positions: list[dict[str, Any]],
        exit_signal_count: int,
        has_exit_policy: bool,
        exit_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        open_codes = {str(item.get("code") or "").strip() for item in open_positions if str(item.get("code") or "").strip()}
        pending = [order for order in exit_orders if self.is_exit_order_direction(order.get("direction")) and self.is_open_exit_order_status(order.get("status"))]
        filled = [order for order in exit_orders if self.is_exit_order_direction(order.get("direction")) and str(order.get("status") or "").strip().lower() in {"filled", "closed", "done", "completed"}]
        pending_codes = {str(order.get("code") or "").strip() for order in pending if str(order.get("code") or "").strip()}
        codes_needing_exit = sorted(open_codes - pending_codes)
        eligible = bool(open_codes) and (exit_signal_count > 0 or has_exit_policy)
        return {
            "open_position_count": len(open_positions),
            "open_codes": sorted(open_codes),
            "exit_signal_count": int(exit_signal_count),
            "has_exit_policy": bool(has_exit_policy),
            "pending_exit_order_count": len(pending),
            "filled_exit_order_count": len(filled),
            "codes_needing_exit": codes_needing_exit,
            "eligible_for_exit_order": eligible and bool(codes_needing_exit),
        }

    async def select_candidates(
        self,
        db: Any,
        *,
        strategies: list[dict[str, Any]] | None = None,
        limit: int = 200,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        candidates: list[dict[str, Any]] = []
        funnel = {
            "strategies_scanned": 0,
            "with_open_positions": 0,
            "with_exit_signal": 0,
            "with_exit_policy": 0,
            "eligible_open_with_exit": 0,
            "eligible_exit_code_count": 0,
            "blocked_pending_exit_order": 0,
            "blocked_no_exit_trigger": 0,
        }
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for strategy in list(strategies or []):
            sid = str((strategy or {}).get("id") or "").strip()
            if sid and sid not in seen:
                seen.add(sid)
                unique.append(dict(strategy or {}))

        for strategy in unique:
            sid = str(strategy.get("id") or "").strip()
            funnel["strategies_scanned"] += 1
            try:
                positions = await self.list_open_positions(db, strategy_id=sid)
                if not positions:
                    continue
                funnel["with_open_positions"] += 1
                codes = {
                    str(item.get("code") or "").strip()
                    for item in positions
                    if str(item.get("code") or "").strip()
                }
                signal_count = await self.count_exit_signals(
                    db, strategy_id=sid, codes=codes
                )
                has_policy = self.strategy_has_exit_policy(strategy)
                funnel["with_exit_signal"] += int(signal_count > 0)
                funnel["with_exit_policy"] += int(has_policy)
                if signal_count <= 0 and not has_policy:
                    funnel["blocked_no_exit_trigger"] += 1
                    continue
                orders = await self.list_exit_orders(db, strategy_id=sid)
                snapshot = self.funnel_snapshot(
                    open_positions=positions,
                    exit_signal_count=signal_count,
                    has_exit_policy=has_policy,
                    exit_orders=orders,
                )
                if not snapshot["eligible_for_exit_order"]:
                    if snapshot["pending_exit_order_count"] > 0 and not snapshot["codes_needing_exit"]:
                        funnel["blocked_pending_exit_order"] += 1
                    continue
                funnel["eligible_open_with_exit"] += 1
                funnel["eligible_exit_code_count"] += len(snapshot["codes_needing_exit"])
                strategy.update({
                    "_exit_signal_count": signal_count,
                    "_open_positions": positions,
                    "_has_exit_policy": has_policy,
                    "_exit_codes": list(snapshot["codes_needing_exit"]),
                    "_exit_funnel": snapshot,
                })
                candidates.append(strategy)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "exit candidate selection failed strategy_id=%s error=%s", sid, exc
                )
        if candidates:
            candidates[0]["_exit_selection_funnel_totals"] = dict(funnel)
        return candidates[:limit], len(candidates), funnel


__all__ = ["ExitEvidenceService"]

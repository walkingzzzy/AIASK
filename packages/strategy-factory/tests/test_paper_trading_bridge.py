from __future__ import annotations

import asyncio


class _FakePaperDb:
    def __init__(self):
        self.accounts = {
            "paper-1": {
                "id": "paper-1",
                "strategy_id": "strategy-1",
                "status": "active",
                "current_capital": 100_000.0,
            }
        }
        self.orders: list[dict] = []
        self._next_order_id = 1

    async def fetchrow(self, query: str, *args):
        if "FROM paper_orders" in query:
            strategy_id, signal_date, code, direction = [str(item) for item in args[:4]]
            for order in self.orders:
                if (
                    order.get("source") == "paper_trading_bridge"
                    and str(order.get("strategy_id")) == strategy_id
                    and str(order.get("signal_date")) == signal_date
                    and str(order.get("code")) == code
                    and str(order.get("direction")) == direction
                ):
                    return dict(order)
            return None
        if "FROM paper_positions" in query:
            return None
        if "FROM paper_accounts WHERE id" in query:
            account_id = str(args[0])
            return dict(self.accounts.get(account_id) or {})
        if "FROM paper_accounts WHERE strategy_id" in query:
            strategy_id = str(args[0])
            for account in self.accounts.values():
                if account.get("strategy_id") == strategy_id and account.get("status") == "active":
                    return dict(account)
            return None
        if "INSERT INTO paper_orders" in query:
            account_id, code, direction, shares, strategy_id, signal_date = args[:6]
            for order in self.orders:
                if (
                    order.get("source") == "paper_trading_bridge"
                    and str(order.get("strategy_id")) == str(strategy_id)
                    and str(order.get("signal_date")) == str(signal_date)
                    and str(order.get("code")) == str(code)
                    and str(order.get("direction")) == str(direction)
                ):
                    raise RuntimeError("UNIQUE constraint failed: paper_orders")
            row = {
                "id": self._next_order_id,
                "account_id": account_id,
                "code": code,
                "direction": direction,
                "shares": int(shares),
                "status": "pending",
                "order_type": "market",
                "strategy_id": strategy_id,
                "signal_date": signal_date,
                "source": "paper_trading_bridge",
            }
            self._next_order_id += 1
            self.orders.append(row)
            return dict(row)
        return None

    async def execute(self, query: str, *args):
        return None


def test_bridge_reuses_same_day_same_strategy_symbol_direction_order() -> None:
    from strategy_factory.application.research.paper_trading_bridge import PaperTradingBridge

    db = _FakePaperDb()
    bridge = PaperTradingBridge(db)

    async def _run():
        first = await bridge._place_paper_order(
            account_id="paper-1",
            code="600519",
            signal=1,
            strategy_id="strategy-1",
            signal_date="2026-05-21",
        )
        second = await bridge._place_paper_order(
            account_id="paper-1",
            code="600519",
            signal=1,
            strategy_id="strategy-1",
            signal_date="2026-05-21",
        )
        third = await bridge._place_paper_order(
            account_id=" paper-1 ",
            code=" 600519 ",
            signal=1,
            strategy_id=" strategy-1 ",
            signal_date=" 2026-05-21 ",
        )
        return first, second, third

    first, second, third = asyncio.run(_run())

    assert len(db.orders) == 1
    assert first["placed"] is True
    assert first["order_id"] == "1"
    assert second["placed"] is False
    assert second["reused"] is True
    assert second["order_id"] == first["order_id"]
    assert third["placed"] is False
    assert third["reused"] is True
    assert third["order_id"] == first["order_id"]

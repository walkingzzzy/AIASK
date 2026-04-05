from __future__ import annotations

import json
from datetime import datetime

import pytest

import akshare_mcp.tools.managers.paper_trading_manager as ptm


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _OrderEventConn:
    def __init__(self):
        self.accounts = {
            "acc1": {
                "id": "acc1",
                "user_id": "default",
                "current_capital": 100000.0,
                "total_value": 100000.0,
                "initial_capital": 100000.0,
            }
        }
        self.positions = {}
        self.trades = []
        self.paper_orders = []
        self.order_events = []
        self._next_order_id = 1

    async def fetchrow(self, query, *args):
        if "FROM paper_accounts WHERE id = $1" in query or "FROM paper_accounts WHERE id=$1" in query:
            return self.accounts.get(args[0])
        if "FROM paper_positions WHERE account_id = $1 AND stock_code = $2" in query:
            return self.positions.get((args[0], args[1]))
        if "INSERT INTO paper_orders" in query:
            row = {
                "id": self._next_order_id,
                "account_id": args[0],
                "strategy_id": args[1],
                "signal_date": args[2],
                "source": args[3],
                "code": args[4],
                "direction": args[5],
                "shares": args[6],
                "price": args[7],
                "order_type": args[8],
                "stop_price": args[9],
                "status": "pending",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
            self._next_order_id += 1
            self.paper_orders.append(row)
            return {"id": row["id"]}
        if "SELECT * FROM paper_orders WHERE id=$1 AND status='pending'" in query:
            order_id = int(args[0])
            for row in self.paper_orders:
                if int(row.get("id") or 0) == order_id and str(row.get("status") or "") == "pending":
                    return row
            return None
        return None

    async def fetch(self, query, *args):
        if "FROM order_events WHERE order_id=$1" in query:
            order_id, limit = str(args[0]), int(args[1])
            rows = [row for row in self.order_events if str(row.get("order_id")) == order_id]
            return list(reversed(rows))[:limit]
        if "FROM order_events WHERE account_id=$1" in query:
            account_id, limit = args[0], int(args[1])
            rows = [row for row in self.order_events if row.get("account_id") == account_id]
            return list(reversed(rows))[:limit]
        if "FROM paper_positions WHERE account_id=$1" in query:
            account_id = args[0]
            return [row for (aid, _), row in self.positions.items() if aid == account_id]
        if "FROM paper_orders WHERE account_id=$1 AND status='pending'" in query:
            account_id = args[0]
            return [row for row in self.paper_orders if row.get("account_id") == account_id and row.get("status") == "pending"]
        if "FROM paper_trades WHERE account_id=$1" in query:
            account_id = args[0]
            return [row for row in reversed(self.trades) if row.get("account_id") == account_id]
        return []

    async def fetchval(self, query, *args):
        if "FROM paper_trades" in query:
            account_id, code = args
            sellable = 0
            today = datetime.now().date()
            for trade in self.trades:
                if trade.get("account_id") != account_id or trade.get("stock_code") != code:
                    continue
                trade_date = (trade.get("trade_time") or datetime.now()).date()
                if trade.get("trade_type") == "buy" and trade_date < today:
                    sellable += int(trade.get("quantity") or 0)
                elif trade.get("trade_type") == "sell":
                    sellable -= int(trade.get("quantity") or 0)
            return sellable
        if "SUM(market_value)" in query:
            account_id = args[0]
            return sum(float(row.get("market_value") or 0.0) for (aid, _), row in self.positions.items() if aid == account_id)
        if "COUNT(*) FROM paper_orders WHERE account_id=$1 AND status='pending'" in query:
            account_id = args[0]
            return sum(1 for row in self.paper_orders if row.get("account_id") == account_id and row.get("status") == "pending")
        return 0

    async def execute(self, query, *args):
        if "INSERT INTO order_events" in query:
            self.order_events.append(
                {
                    "order_id": str(args[0]),
                    "account_id": args[1],
                    "code": args[2],
                    "event_type": args[3],
                    "payload": json.loads(args[4] or "{}"),
                    "created_at": datetime.now(),
                }
            )
            return
        if "INSERT INTO paper_trades" in query:
            self.trades.append(
                {
                    "id": args[0],
                    "account_id": args[1],
                    "stock_code": args[2],
                    "stock_name": args[3],
                    "trade_type": args[4],
                    "price": args[5],
                    "quantity": args[6],
                    "amount": args[7],
                    "commission": args[8],
                    "strategy_id": args[9],
                    "source_order_id": args[10],
                    "trade_time": datetime.now(),
                    "created_at": datetime.now(),
                }
            )
            return
        if "UPDATE paper_positions" in query and "cost_price=$2" in query:
            qty, cost, current_price, market_value, profit_rate, account_id, code = args
            self.positions[(account_id, code)] = {
                "account_id": account_id,
                "stock_code": code,
                "stock_name": code,
                "quantity": qty,
                "cost_price": cost,
                "current_price": current_price,
                "market_value": market_value,
                "profit_rate": profit_rate,
            }
            return
        if "INSERT INTO paper_positions" in query:
            account_id, code, stock_name, qty, cost, current_price, market_value, profit_rate = args
            self.positions[(account_id, code)] = {
                "account_id": account_id,
                "stock_code": code,
                "stock_name": stock_name,
                "quantity": qty,
                "cost_price": cost,
                "current_price": current_price,
                "market_value": market_value,
                "profit_rate": profit_rate,
            }
            return
        if "UPDATE paper_accounts SET current_capital" in query:
            capital, total, account_id = args
            self.accounts[account_id]["current_capital"] = capital
            self.accounts[account_id]["total_value"] = total
            return
        if "UPDATE paper_orders SET status='cancelled'" in query:
            order_id = int(args[0])
            for row in self.paper_orders:
                if int(row.get("id") or 0) == order_id:
                    row["status"] = "cancelled"
                    row["updated_at"] = datetime.now()
                    break


class _OrderEventDB:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)

    async def get_klines(self, code, limit=2):
        return []


@pytest.mark.asyncio
async def test_p1_paper_order_events_expose_lifecycle_schema(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _OrderEventConn()
    monkeypatch.setattr(ptm, "get_db", lambda: _OrderEventDB(conn))

    async def _fake_quote(_code):
        return {"name": "贵州茅台", "preClose": 11.0, "price": 11.0}

    monkeypatch.setattr(ptm, "_get_quote_snapshot", _fake_quote)

    created = await mcp.paper_trading_manager(
        action="place_order",
        account_id="acc1",
        code="600519",
        direction="buy",
        quantity=100,
        price=10,
        order_type="limit",
    )
    assert created["success"] is True

    cancelled = await mcp.paper_trading_manager(action="cancel_order", order_id=created["data"]["order_id"])
    assert cancelled["success"] is True

    events = await mcp.paper_trading_manager(
        action="order_events",
        account_id="acc1",
        order_id=created["data"]["order_id"],
    )

    assert events["success"] is True
    data = events["data"]
    assert data["summary"]["schema_version"] == "v1"
    assert data["summary"]["by_type"]["created"] == 1
    assert data["summary"]["by_type"]["cancelled"] == 1

    created_event = next(item for item in data["events"] if item["event_type"] == "created")
    cancelled_event = next(item for item in data["events"] if item["event_type"] == "cancelled")
    assert created_event["event_category"] == "order_lifecycle"
    assert created_event["event_status"] == "pending"
    assert created_event["payload"]["order"]["shares"] == 100
    assert created_event["payload"]["transition"]["to_status"] == "pending"
    assert cancelled_event["event_status"] == "cancelled"
    assert cancelled_event["payload"]["transition"]["from_status"] == "pending"


@pytest.mark.asyncio
async def test_p1_paper_order_events_expose_execution_payload(monkeypatch):
    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)
    conn = _OrderEventConn()
    monkeypatch.setattr(ptm, "get_db", lambda: _OrderEventDB(conn))

    async def _fake_quote(_code):
        return {"name": "贵州茅台", "preClose": 11.0, "price": 10.0}

    monkeypatch.setattr(ptm, "_get_quote_snapshot", _fake_quote)

    buy = await mcp.paper_trading_manager(
        action="place_order",
        account_id="acc1",
        code="600519",
        direction="buy",
        quantity=100,
        price=10,
    )
    assert buy["success"] is True

    events = await mcp.paper_trading_manager(
        action="order_events",
        account_id="acc1",
        order_id=buy["data"]["order_id"],
    )

    assert events["success"] is True
    fill_event = events["data"]["events"][0]
    assert fill_event["event_type"] == "filled"
    assert fill_event["event_category"] == "execution"
    assert fill_event["event_status"] == "filled"
    assert fill_event["payload"]["order"]["amount"] == pytest.approx(1000.0)
    assert fill_event["payload"]["order"]["commission"] is not None
    assert events["data"]["summary"]["by_status"]["filled"] == 1

from __future__ import annotations

from types import SimpleNamespace

import pytest

import akshare_mcp.tools.managers.live_trading_manager as live_mod
from akshare_mcp.services import get_artifact_async
from akshare_mcp.services.live_broker import AlpacaBrokerAdapter, build_live_order_events


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeAdapter:
    provider_name = "alpaca"

    def __init__(self, *, can_write: bool = False):
        self.config = SimpleNamespace(
            read_only=not can_write,
            allow_write=can_write,
            paper=True,
        )
        self.closed_count = 0
        self.submitted_payloads: list[dict] = []
        self.cancelled_ids: list[str] = []
        self.list_orders_args = None

    def is_configured(self) -> bool:
        return True

    def can_write(self) -> bool:
        return bool(self.config.allow_write and not self.config.read_only)

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "multi_broker": True,
            "order_events": True,
            "fills": True,
            "broker_receipts": True,
            "write_enabled": self.can_write(),
        }

    async def close(self) -> None:
        self.closed_count += 1

    async def gateway_status(self) -> dict:
        return {"provider": self.provider_name, "connected": True, "clock": {"is_open": False}}

    async def get_account(self) -> dict:
        return {"account_id": "acct_live_001", "status": "ACTIVE"}

    async def list_positions(self) -> list[dict]:
        return [{"symbol": "AAPL", "qty": 3.0, "avg_entry_price": 100.0}]

    async def list_orders(self, *, status: str = "open", limit: int = 50, symbols: list[str] | None = None) -> list[dict]:
        self.list_orders_args = {"status": status, "limit": limit, "symbols": list(symbols or [])}
        return [{"order_id": "ord_live_001", "symbol": "AAPL", "status": status}]

    async def get_order(self, order_id: str) -> dict:
        return {
            "provider": self.provider_name,
            "account_id": "acct_live_001",
            "order_id": order_id,
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "market",
            "status": "filled",
            "qty": 2.0,
            "filled_qty": 2.0,
            "filled_avg_price": 101.5,
            "created_at": "2026-03-25T09:30:00+08:00",
            "submitted_at": "2026-03-25T09:30:01+08:00",
            "updated_at": "2026-03-25T09:30:05+08:00",
            "filled_at": "2026-03-25T09:30:05+08:00",
        }

    async def list_order_events(self, *, order_id: str, limit: int = 50) -> list[dict]:
        order = await self.get_order(order_id)
        fills = await self.list_fills(order_id=order_id, limit=limit)
        receipt = await self.get_order_receipt(order_id)
        return build_live_order_events(order, fills=fills, receipt=receipt)[:limit]

    async def list_fills(self, *, order_id: str | None = None, limit: int = 50, symbols: list[str] | None = None) -> list[dict]:
        rows = [
            {
                "provider": self.provider_name,
                "fill_id": "fill_live_001",
                "order_id": order_id or "ord_live_001",
                "account_id": "acct_live_001",
                "symbol": "AAPL",
                "side": "buy",
                "fill_type": "fill",
                "occurred_at": "2026-03-25T09:30:05+08:00",
                "price": 101.5,
                "qty": 2.0,
                "shares": 2,
                "amount": 203.0,
                "commission": 0.0,
                "source": "alpaca.account_activities",
                "raw": {"order_id": order_id or "ord_live_001"},
            }
        ]
        if symbols:
            target_symbols = {str(item).upper() for item in symbols}
            rows = [item for item in rows if str(item.get("symbol") or "").upper() in target_symbols]
        return rows[:limit]

    async def get_order_receipt(self, order_id: str) -> dict:
        return {
            "provider": self.provider_name,
            "message_id": "receipt_live_001",
            "receipt_id": "receipt_live_001",
            "order_id": order_id,
            "account_id": "acct_live_001",
            "symbol": "AAPL",
            "message_type": "brokerage_ack",
            "occurred_at": "2026-03-25T09:30:02+08:00",
            "status": "accepted",
            "severity": "low",
            "reason": "accepted by broker",
            "source": "alpaca.order_receipt",
            "retryable": False,
            "raw": {"order_id": order_id},
        }

    async def submit_order(self, payload: dict) -> dict:
        self.submitted_payloads.append(dict(payload))
        return {"order_id": "ord_submit_001", "symbol": payload.get("symbol"), "status": "accepted"}

    async def cancel_order(self, order_id: str) -> dict:
        self.cancelled_ids.append(order_id)
        return {"order_id": order_id, "cancelled": True}


def test_live_broker_normalizers_should_expose_private_helper_imports():
    account = AlpacaBrokerAdapter._normalize_account(
        {
            "id": "acct_live_001",
            "status": "ACTIVE",
            "buying_power": "100000.5",
        }
    )
    order = AlpacaBrokerAdapter._normalize_order(
        {
            "id": "ord_live_001",
            "symbol": "aapl",
            "status": "filled",
            "qty": "2",
        }
    )

    assert account["account_id"] == "acct_live_001"
    assert account["buying_power"] == 100000.5
    assert order["order_id"] == "ord_live_001"
    assert order["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_live_trading_manager_read_only_gateway_and_preview_paths(monkeypatch):
    mcp = _DummyMCP()
    live_mod.register_live_trading_manager(mcp)
    adapter = _FakeAdapter(can_write=False)
    monkeypatch.setattr(live_mod, "get_live_broker_adapter", lambda: adapter)

    gateway = await mcp.live_trading_manager(action="gateway_status")
    assert gateway["success"] is True
    assert gateway["data"]["connected"] is True
    assert gateway["meta"]["provider"] == "alpaca"
    assert gateway["meta"]["read_only"] is True

    account = await mcp.live_trading_manager(action="account")
    assert account["success"] is True
    assert account["data"]["account"]["account_id"] == "acct_live_001"

    positions = await mcp.live_trading_manager(action="positions")
    assert positions["success"] is True
    assert positions["data"]["count"] == 1
    assert positions["data"]["positions"][0]["symbol"] == "AAPL"

    orders = await mcp.live_trading_manager(action="orders", symbols="AAPL,TSLA", limit=5, status="closed")
    assert orders["success"] is True
    assert orders["data"]["count"] == 1
    assert adapter.list_orders_args == {"status": "closed", "limit": 5, "symbols": ["AAPL", "TSLA"]}

    order_status = await mcp.live_trading_manager(action="order_status", order_id="ord_live_001")
    assert order_status["success"] is True
    assert order_status["data"]["order"]["order_id"] == "ord_live_001"

    submit_preview = await mcp.live_trading_manager(action="submit_order", symbol="AAPL", qty=2, side="buy")
    assert submit_preview["success"] is True
    assert submit_preview["data"]["submitted"] is False
    assert submit_preview["data"]["mode"] == "read_only"
    assert submit_preview["data"]["preview"]["symbol"] == "AAPL"
    assert adapter.submitted_payloads == []

    cancel_preview = await mcp.live_trading_manager(action="cancel_order", order_id="ord_live_001")
    assert cancel_preview["success"] is True
    assert cancel_preview["data"]["cancelled"] is False
    assert cancel_preview["data"]["mode"] == "read_only"
    assert adapter.cancelled_ids == []
    assert adapter.closed_count >= 6


@pytest.mark.asyncio
async def test_live_trading_manager_executes_submit_and_cancel_when_write_enabled(monkeypatch):
    mcp = _DummyMCP()
    live_mod.register_live_trading_manager(mcp)
    adapter = _FakeAdapter(can_write=True)
    adapter.config.paper = False
    monkeypatch.setattr(live_mod, "get_live_broker_adapter", lambda: adapter)

    submit_resp = await mcp.live_trading_manager(
        action="submit_order",
        symbol="AAPL",
        qty=1,
        side="buy",
        type="market",
        time_in_force="day",
    )
    assert submit_resp["success"] is True
    assert submit_resp["data"]["submitted"] is True
    assert submit_resp["data"]["order"]["order_id"] == "ord_submit_001"
    assert adapter.submitted_payloads[0]["symbol"] == "AAPL"

    cancel_resp = await mcp.live_trading_manager(action="cancel_order", order_id="ord_submit_001")
    assert cancel_resp["success"] is True
    assert cancel_resp["data"]["cancelled"] is True
    assert adapter.cancelled_ids == ["ord_submit_001"]


@pytest.mark.asyncio
async def test_live_trading_manager_exposes_order_events_fills_receipts_and_sync(monkeypatch):
    import akshare_mcp.services.artifact_registry as artifact_mod

    mcp = _DummyMCP()
    live_mod.register_live_trading_manager(mcp)
    adapter = _FakeAdapter(can_write=False)
    monkeypatch.setattr(live_mod, "get_live_broker_adapter", lambda: adapter)
    monkeypatch.setattr(artifact_mod, "_get_db", lambda: None)

    events_resp = await mcp.live_trading_manager(action="order_events", order_id="ord_live_001", limit=10)
    assert events_resp["success"] is True
    assert events_resp["data"]["order_id"] == "ord_live_001"
    assert events_resp["data"]["count"] >= 3
    assert events_resp["data"]["summary"]["by_type"]["submitted"] >= 1
    assert events_resp["data"]["state_machine"]["current_status"] == "filled"

    fills_resp = await mcp.live_trading_manager(action="fills", order_id="ord_live_001", limit=10)
    assert fills_resp["success"] is True
    assert fills_resp["data"]["count"] == 1
    assert fills_resp["data"]["fills"][0]["order_id"] == "ord_live_001"

    receipt_resp = await mcp.live_trading_manager(action="broker_receipts", order_id="ord_live_001")
    assert receipt_resp["success"] is True
    assert receipt_resp["data"]["receipt"]["message_type"] == "brokerage_ack"

    sync_resp = await mcp.live_trading_manager(
        action="sync_order_events",
        order_id="ord_live_001",
        output_artifact_id="live_order_sync_test_001",
        persist_artifact=True,
    )
    assert sync_resp["success"] is True
    assert sync_resp["data"]["synced"] is True
    artifact = await get_artifact_async("live_order_sync_test_001")
    assert artifact is not None
    assert artifact["strategy"] == "live_order_event_sync"

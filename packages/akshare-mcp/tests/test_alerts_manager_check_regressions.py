from __future__ import annotations

import pytest

import akshare_mcp.storage as storage_mod
import akshare_mcp.tools.alerts as alerts_tool_mod
import akshare_mcp.tools.managers.alerts_manager as alerts_manager_mod


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


class _AlertConn:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    async def fetch(self, query: str, *args):
        user_id = str(args[0])
        items = [dict(row) for row in self.rows if str(row.get("user_id", "default")) == user_id]
        if "status = $2" in query:
            status = str(args[1])
            items = [row for row in items if str(row.get("status", "active")) == status]
        return items


class _AlertDb:
    def __init__(self, conn: _AlertConn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.fixture(autouse=True)
def _reset_alert_cache():
    alerts_tool_mod._alerts_store.clear()
    yield
    alerts_tool_mod._alerts_store.clear()


@pytest.mark.asyncio
async def test_alerts_manager_check_honors_specific_alert_id(monkeypatch):
    conn = _AlertConn(
        [
            {
                "id": 1,
                "user_id": "default",
                "code": "600519",
                "indicator": "price",
                "condition": ">",
                "value": 1800.0,
                "status": "active",
            },
            {
                "id": 2,
                "user_id": "default",
                "code": "000858",
                "indicator": "price",
                "condition": ">",
                "value": 100.0,
                "status": "active",
            },
        ]
    )
    monkeypatch.setattr(storage_mod, "get_db", lambda: _AlertDb(conn))

    async def _fake_evaluate_indicator(alert: dict, _quote_cache: dict):
        current_value = 101.0 if alert.get("code") == "000858" else 1812.0
        return {**alert, "current_value": current_value, "triggered": True}

    monkeypatch.setattr(alerts_tool_mod, "_evaluate_indicator", _fake_evaluate_indicator)

    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)
    target_alert_id = alerts_manager_mod._make_alert_id("default", "000858", "price", ">")

    result = await mcp.alerts_manager(action="check", alert_id=target_alert_id)

    assert result["success"] is True
    assert result["data"]["checked_count"] == 1
    assert result["data"]["checked_alert_ids"] == [target_alert_id]
    assert result["data"]["count"] == 1
    assert result["data"]["triggered"][0]["alert_id"] == target_alert_id
    assert result["data"]["triggered"][0]["code"] == "000858"

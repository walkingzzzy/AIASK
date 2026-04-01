"""P2 contract tests for alerts_manager DB-first persistence behavior."""

from __future__ import annotations

import pytest

import akshare_mcp.storage as storage_mod
import akshare_mcp.tools.alerts as alerts_tool_mod
import akshare_mcp.tools.managers.alerts_manager as alerts_manager_mod


class _DummyMCP:
    def tool(self):
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
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, query: str, *args):
        user_id = str(args[0])
        items = [dict(row) for row in self.rows if str(row.get("user_id", "default")) == user_id]
        if "status = $2" in query:
            status = str(args[1])
            items = [row for row in items if str(row.get("status", "active")) == status]
        return items

    async def execute(self, query: str, *args):
        self.executed.append((query, args))
        normalized = " ".join(query.split())
        if normalized.startswith("UPDATE alerts"):
            if "WHERE id = $6" in normalized:
                target = next(row for row in self.rows if int(row["id"]) == int(args[5]))
            else:
                target = next(
                    row
                    for row in self.rows
                    if str(row.get("user_id", "default")) == str(args[5])
                    and str(row.get("code", "")) == str(args[6])
                    and str(row.get("indicator", "")) == str(args[7])
                    and str(row.get("condition", "")) == str(args[8])
                )
            target.update(
                {
                    "code": args[0],
                    "indicator": args[1],
                    "condition": args[2],
                    "value": float(args[3]),
                    "status": args[4],
                }
            )
            return "UPDATE 1"
        if normalized == "DELETE FROM alerts WHERE id = $1":
            self.rows = [row for row in self.rows if int(row["id"]) != int(args[0])]
            return "DELETE 1"
        if normalized.startswith("DELETE FROM alerts WHERE user_id = $1"):
            self.rows = [
                row
                for row in self.rows
                if not (
                    str(row.get("user_id", "default")) == str(args[0])
                    and str(row.get("code", "")) == str(args[1])
                    and str(row.get("indicator", "")) == str(args[2])
                    and str(row.get("condition", "")) == str(args[3])
                )
            ]
            return "DELETE 1"
        raise AssertionError(f"Unexpected SQL: {normalized}")


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
async def test_alerts_manager_check_should_reload_active_alerts_from_db(monkeypatch):
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
            }
        ]
    )
    monkeypatch.setattr(storage_mod, "get_db", lambda: _AlertDb(conn))

    async def _fake_evaluate_indicator(alert: dict, _quote_cache: dict):
        return {**alert, "current_value": 1812.0, "triggered": True}

    monkeypatch.setattr(alerts_tool_mod, "_evaluate_indicator", _fake_evaluate_indicator)

    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)

    result = await mcp.alerts_manager(action="check")

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["triggered"][0]["code"] == "600519"
    assert result["data"]["triggered"][0]["current_value"] == pytest.approx(1812.0)
    assert "alert_600519_price_>" in alerts_tool_mod._alerts_store


@pytest.mark.asyncio
async def test_alerts_manager_update_and_delete_should_recover_alert_from_db(monkeypatch):
    conn = _AlertConn(
        [
            {
                "id": 7,
                "user_id": "default",
                "code": "600519",
                "indicator": "price",
                "condition": ">",
                "value": 1800.0,
                "status": "active",
            }
        ]
    )
    monkeypatch.setattr(storage_mod, "get_db", lambda: _AlertDb(conn))

    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)
    alert_id = alerts_manager_mod._make_alert_id("default", "600519", "price", ">")

    updated = await mcp.alerts_manager(action="update", alert_id=alert_id, value=1900)
    assert updated["success"] is True
    assert updated["data"]["status"] == "active"
    assert updated["data"]["alert"]["value"] == pytest.approx(1900.0)
    assert conn.rows[0]["value"] == pytest.approx(1900.0)

    alerts_tool_mod._alerts_store.clear()

    deleted = await mcp.alerts_manager(action="delete", alert_id=alert_id)
    assert deleted["success"] is True
    assert conn.rows == []

    listed = await mcp.alerts_manager(action="list", params={"status": "all"})
    assert listed["success"] is True
    assert listed["data"]["count"] == 0

from __future__ import annotations

import json

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


class _RiskRuleConn:
    def __init__(self):
        self.accounts = {
            "acc1": {
                "id": "acc1",
                "user_id": "default",
                "risk_rules": "{\"max_position_pct\": 30.0, \"max_drawdown_pct\": 20.0, \"stop_loss_pct\": 10.0}",
                "initial_capital": 100000.0,
                "total_value": 100000.0,
            }
        }

    async def fetchrow(self, query, *args):
        if "FROM paper_accounts WHERE id=$1" in query:
            return self.accounts.get(args[0])
        raise AssertionError(f"Unexpected SQL: {query}")

    async def fetch(self, query, *args):
        if "FROM paper_positions WHERE account_id=$1" in query:
            return []
        if "FROM paper_trades WHERE account_id=$1" in query:
            return []
        raise AssertionError(f"Unexpected SQL: {query}")

    async def fetchval(self, query, *args):
        if "COUNT(*) FROM paper_orders WHERE account_id=$1 AND status='pending'" in query:
            return 0
        raise AssertionError(f"Unexpected SQL: {query}")

    async def execute(self, query, *args):
        if "UPDATE paper_accounts SET risk_rules=$1::jsonb" in query:
            account_id = args[1]
            self.accounts[account_id]["risk_rules"] = args[0]
            return "UPDATE 1"
        raise AssertionError(f"Unexpected SQL: {query}")


class _RiskRuleDb:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_set_risk_rules_accepts_top_level_rules_payload(monkeypatch):
    conn = _RiskRuleConn()
    monkeypatch.setattr(ptm, "get_db", lambda: _RiskRuleDb(conn))

    mcp = _DummyMCP()
    ptm.register_paper_trading_manager(mcp)

    result = await mcp.paper_trading_manager(
        action="set_risk_rules",
        account_id="acc1",
        rules={
            "max_position_pct": 25,
            "max_drawdown_pct": 15,
            "stop_loss_pct": 8,
        },
    )

    assert result["success"] is True
    assert result["data"]["risk_rules"] == {
        "max_position_pct": pytest.approx(25.0),
        "max_drawdown_pct": pytest.approx(15.0),
        "stop_loss_pct": pytest.approx(8.0),
    }
    assert json.loads(conn.accounts["acc1"]["risk_rules"]) == {
        "max_position_pct": pytest.approx(25.0),
        "max_drawdown_pct": pytest.approx(15.0),
        "stop_loss_pct": pytest.approx(8.0),
    }

    summary = await mcp.paper_trading_manager(
        action="summary",
        account_id="acc1",
    )

    assert summary["success"] is True
    assert summary["data"]["account"]["risk_rules"] == {
        "max_position_pct": pytest.approx(25.0),
        "max_drawdown_pct": pytest.approx(15.0),
        "stop_loss_pct": pytest.approx(8.0),
    }

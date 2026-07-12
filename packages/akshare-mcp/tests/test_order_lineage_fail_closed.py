"""P0-A: paper order / matching fail-closed when signal lineage is missing."""

from __future__ import annotations

import asyncio
import pytest

from akshare_mcp.config import _strategy_factory_toggles as toggles
from akshare_mcp.services import incubation as incubation_mod
from akshare_mcp.services.matching_engine import MatchingEngine


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self):
        self.executed = []

    async def execute(self, query: str, *args):
        self.executed.append((query, args))


class _Db:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


@pytest.fixture(autouse=True)
def _clear_fail_closed_env(monkeypatch):
    monkeypatch.delenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", raising=False)
    yield


def test_fail_closed_toggle_default_on():
    assert toggles.fail_closed_signal_id_enabled() is True
    assert incubation_mod.fail_closed_signal_id_enabled() is True


def test_fail_closed_toggle_can_disable(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "0")
    assert toggles.fail_closed_signal_id_enabled() is False
    assert incubation_mod.fail_closed_signal_id_enabled() is False


def test_require_order_lineage_rejects_missing_signal_id(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    gap = incubation_mod._require_order_lineage(
        strategy_id="s1",
        signal_id="",
        position_id="p1",
        context="unit",
    )
    assert gap == "missing_signal_id"


def test_require_order_lineage_rejects_missing_position_id(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    gap = incubation_mod._require_order_lineage(
        strategy_id="s1",
        signal_id="sig1",
        position_id="  ",
        context="unit",
    )
    assert gap == "missing_position_id"


def test_require_order_lineage_rejects_missing_strategy_id(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    gap = incubation_mod._require_order_lineage(
        strategy_id=None,
        signal_id="sig1",
        position_id="p1",
        context="unit",
    )
    assert gap == "missing_strategy_id"


def test_require_order_lineage_allows_complete(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    gap = incubation_mod._require_order_lineage(
        strategy_id="s1",
        signal_id="sig1",
        position_id="p1",
        context="unit",
    )
    assert gap is None


def test_require_order_lineage_warns_but_allows_when_off(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "0")
    gap = incubation_mod._require_order_lineage(
        strategy_id="s1",
        signal_id="",
        position_id="p1",
        context="unit",
    )
    assert gap is None


def test_order_requires_signal_lineage_for_strategy_orders(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    assert incubation_mod.order_requires_signal_lineage({"strategy_id": "s1"}) is True
    assert incubation_mod.order_requires_signal_lineage({"source": "manual"}) is False
    assert incubation_mod.order_requires_signal_lineage({"source": "strategy_signal"}) is True


def test_matching_rejects_strategy_order_missing_signal_id(monkeypatch):
    asyncio.run(_async_test_matching_rejects_strategy_order_missing_signal_id(monkeypatch))


async def _async_test_matching_rejects_strategy_order_missing_signal_id(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    conn = _Conn()
    engine = MatchingEngine()
    filled = {"called": False}

    async def fake_fill_order(*args, **kwargs):
        filled["called"] = True
        return "trade-1", 0.0

    async def fake_record_order_event(conn_arg, order_id, event_type, **kwargs):
        assert order_id == "order-missing-sid"
        assert event_type == "rejected_by_engine"
        assert kwargs["payload"]["reason"] == "missing_signal_lineage"

    monkeypatch.setattr(engine, "_get_current_price", lambda code, db: _async_value(10.0))
    monkeypatch.setattr(engine, "_get_prev_close", lambda code, db: _async_value(None))
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._fill_order",
        fake_fill_order,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._record_order_event",
        fake_record_order_event,
    )

    await engine._try_match_order(
        _Db(conn),
        {
            "id": "order-missing-sid",
            "account_id": "acc-1",
            "strategy_id": "strategy-1",
            "code": "600000",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "order_type": "marketable_limit",
            "signal_id": "",
            "position_id": "pos-1",
        },
    )

    assert filled["called"] is False
    assert engine.matched_count == 0
    assert any(
        "status='rejected'" in query and "missing_signal_lineage" in str(args)
        for query, args in conn.executed
    )


def test_matching_fills_when_lineage_complete(monkeypatch):
    asyncio.run(_async_test_matching_fills_when_lineage_complete(monkeypatch))


async def _async_test_matching_fills_when_lineage_complete(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    conn = _Conn()
    engine = MatchingEngine()

    async def fake_fill_order(*args, **kwargs):
        assert kwargs["signal_id"] == "sig-1"
        assert kwargs["position_id"] == "pos-1"
        return "trade-1", 0.5

    async def fake_record_order_event(conn_arg, order_id, event_type, **kwargs):
        assert event_type == "filled_by_engine"

    monkeypatch.setattr(engine, "_get_current_price", lambda code, db: _async_value(10.0))
    monkeypatch.setattr(engine, "_get_prev_close", lambda code, db: _async_value(None))
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._fill_order",
        fake_fill_order,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._record_order_event",
        fake_record_order_event,
    )

    await engine._try_match_order(
        _Db(conn),
        {
            "id": "order-ok",
            "account_id": "acc-1",
            "strategy_id": "strategy-1",
            "code": "600000",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "order_type": "marketable_limit",
            "signal_id": "sig-1",
            "position_id": "pos-1",
        },
    )

    assert engine.matched_count == 1
    assert any("status='filled'" in query for query, _ in conn.executed)


def test_matching_allows_manual_order_without_lineage(monkeypatch):
    asyncio.run(_async_test_matching_allows_manual_order_without_lineage(monkeypatch))


async def _async_test_matching_allows_manual_order_without_lineage(monkeypatch):
    """Manual UI orders without strategy_id are not fail-closed by P0-A."""
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    conn = _Conn()
    engine = MatchingEngine()

    async def fake_fill_order(*args, **kwargs):
        return "trade-manual", 0.1

    async def fake_record_order_event(*args, **kwargs):
        return None

    monkeypatch.setattr(engine, "_get_current_price", lambda code, db: _async_value(10.0))
    monkeypatch.setattr(engine, "_get_prev_close", lambda code, db: _async_value(None))
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._fill_order",
        fake_fill_order,
    )
    monkeypatch.setattr(
        "akshare_mcp.tools.managers.paper_trading_manager._record_order_event",
        fake_record_order_event,
    )

    await engine._try_match_order(
        _Db(conn),
        {
            "id": "order-manual",
            "account_id": "acc-1",
            "strategy_id": None,
            "source": "manual",
            "code": "600000",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "order_type": "marketable_limit",
            "signal_id": None,
            "position_id": None,
        },
    )

    assert engine.matched_count == 1


async def _async_value(value):
    return value

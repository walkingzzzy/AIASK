from __future__ import annotations

import asyncio

from aiask_agent.adapters import strategy_factory


def test_agent_confirmed_factory_action_queues_dispatch_without_strategy_manager(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_call_db_facade(loader, params=None):
        calls.append({"loader": getattr(loader, "__name__", ""), "params": dict(params or {})})
        return {"success": True, "data": {"dispatch_id": "dispatch_test", "queued": True}, "error": None}

    monkeypatch.setattr(strategy_factory, "_call_db_facade", fake_call_db_facade)

    result = asyncio.run(
        strategy_factory.execute_confirmed_action(
            "factory_run_once",
            {"execution_mode": "dry_run"},
        )
    )

    assert result["success"] is True
    assert result["data"]["queued"] is True
    assert calls == [{"loader": "_load_factory_dispatch_handler", "params": {"execution_mode": "dry_run"}}]


def test_agent_read_only_factory_status_uses_db_facade(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_call_db_facade(loader, params=None):
        calls.append(getattr(loader, "__name__", ""))
        return {"success": True, "data": {"running": False}, "error": None}

    monkeypatch.setattr(strategy_factory, "_call_db_facade", fake_call_db_facade)

    result = asyncio.run(strategy_factory.factory_status({"recent_run_limit": 1}))

    assert result["success"] is True
    assert result["data"]["running"] is False
    assert calls == ["_load_factory_status_handler"]

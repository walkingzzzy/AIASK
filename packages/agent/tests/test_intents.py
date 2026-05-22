from __future__ import annotations

import asyncio
import pytest

from aiask_agent.intents import ActionIntentStore, IntentExecutor


def test_intent_create_get_deny_and_unauthorized_action(tmp_path) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    intent = store.create(action="factory_run_once", params={"execution_mode": "dry_run"}, user_id="u1")
    assert intent["status"] == "awaiting_confirmation"
    assert intent["target_action"] == "factory_run_once"
    assert store.get(intent["intent_id"])["params"]["execution_mode"] == "dry_run"

    with pytest.raises(ValueError):
        store.create(action="strategy_manager.not_allowed", params={})


def test_confirm_executes_allowed_action_once_and_rejects_repeat(tmp_path, monkeypatch) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(store)
    intent = store.create(action="strategy_manager.factory_run_once", params={"execution_mode": "dry_run"})
    calls: list[dict] = []

    async def fake_execute_confirmed_action(action: str, params: dict | None = None) -> dict:
        calls.append({"action": action, "params": dict(params or {})})
        return {"success": True, "data": {"dispatch_id": "dispatch_test", "queued": True}, "error": None}

    from aiask_agent.adapters import strategy_factory

    monkeypatch.setattr(strategy_factory, "execute_confirmed_action", fake_execute_confirmed_action)

    confirmed = asyncio.run(executor.confirm(intent["intent_id"]))
    assert confirmed["success"] is True
    assert calls == [{"action": "factory_run_once", "params": {"execution_mode": "dry_run"}}]
    assert store.get(intent["intent_id"])["status"] == "succeeded"

    repeated = asyncio.run(executor.confirm(intent["intent_id"]))
    assert repeated["success"] is False
    assert repeated["error_code"] == "INVALID_STATUS"


def test_deny_rejects_repeat_confirm(tmp_path) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(store)
    intent = store.create(action="runtime_alert_ack", params={"alert_id": "a1"})

    denied = asyncio.run(executor.deny(intent["intent_id"], reason="not now"))
    assert denied["success"] is True
    assert store.get(intent["intent_id"])["status"] == "denied"

    confirmed = asyncio.run(executor.confirm(intent["intent_id"]))
    assert confirmed["success"] is False
    assert confirmed["error_code"] == "INVALID_STATUS"

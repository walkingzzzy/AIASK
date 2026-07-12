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


def _force_expire(store: ActionIntentStore, intent_id: str) -> None:
    """Backdate expires_at so the intent is past its TTL."""
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(str(store.path))) as conn:
        conn.execute(
            "UPDATE action_intents SET expires_at = ? WHERE intent_id = ?",
            ("2000-01-01T00:00:00+00:00", intent_id),
        )
        conn.commit()


def test_get_on_expired_intent_does_not_recurse(tmp_path) -> None:
    # Regression: an awaiting_confirmation intent past its TTL used to recurse
    # infinitely (get -> update_status -> get -> ...) and raise
    # "maximum recursion depth exceeded" on GET /intents/{id}.
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    intent = store.create(action="data_sync.sync", params={"codes": ["600519"]})
    _force_expire(store, intent["intent_id"])

    fetched = store.get(intent["intent_id"])
    assert fetched is not None
    assert fetched["status"] == "expired"
    # A second get stays expired (no flip-flop / no recursion).
    assert store.get(intent["intent_id"])["status"] == "expired"


def test_deny_on_expired_intent_is_graceful(tmp_path) -> None:
    # Regression: deny() on an expired intent used to surface a 500 because
    # the underlying get() recursed. It should now return a clean failure.
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(store)
    intent = store.create(action="data_sync.sync", params={"codes": ["600519"]})
    _force_expire(store, intent["intent_id"])

    result = asyncio.run(executor.deny(intent["intent_id"], reason="cleanup"))
    # The intent already expired, so deny is rejected with a defined error
    # code rather than crashing.
    assert result["success"] is False
    assert result["error_code"] == "INVALID_STATUS"
    assert store.get(intent["intent_id"])["status"] == "expired"


def test_incubation_factory_actions_are_allowed(tmp_path) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    for action in (
        "incubation_factory.dry_run",
        "incubation_factory.run_once",
        "incubation_factory.maintenance",
        "factor_factory.run_once",
    ):
        intent = store.create(action=action, params={"source": "test", "dry_run": action != "incubation_factory.run_once"})
        assert intent["status"] == "awaiting_confirmation"
        assert intent["target_tool"] in {"incubation_factory", "factor_factory"}
        assert intent["action"] == action


def test_confirm_incubation_dry_run_executes_once(tmp_path, monkeypatch) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(store)
    intent = store.create(
        action="incubation_factory.dry_run",
        params={"source": "test", "dry_run": True},
    )
    calls: list[dict] = []

    async def fake_execute(target_tool: str, action: str, params: dict | None = None) -> dict:
        calls.append({"tool": target_tool, "action": action, "params": dict(params or {})})
        return {"success": True, "data": {"status": "dry_run_ok"}, "error": None}

    from aiask_agent.adapters import desktop_ops

    monkeypatch.setattr(desktop_ops, "execute_confirmed_action", fake_execute)

    confirmed = asyncio.run(executor.confirm(intent["intent_id"]))
    assert confirmed["success"] is True
    assert calls == [{"tool": "incubation_factory", "action": "dry_run", "params": {"source": "test", "dry_run": True}}]
    assert store.get(intent["intent_id"])["status"] == "succeeded"


def test_ops_db_soak_intent_is_allowed(tmp_path) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    for action in ("ops.db_soak", "factory.soak_check"):
        intent = store.create(action=action, params={"duration_min": 0})
        assert intent["status"] == "awaiting_confirmation"
        assert intent["target_tool"] == "ops"
        assert intent["target_action"] == "db_soak"


def test_confirm_ops_db_soak_executes_once(tmp_path, monkeypatch) -> None:
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(store)
    intent = store.create(action="ops.db_soak", params={"duration_min": 0, "db": "x.sqlite3"})
    calls: list[dict] = []

    async def fake_execute(target_tool: str, action: str, params: dict | None = None) -> dict:
        calls.append({"tool": target_tool, "action": action, "params": dict(params or {})})
        return {
            "success": True,
            "data": {"passed": True, "sample_count": 1, "side_effect": "read_only"},
            "error": None,
        }

    from aiask_agent.adapters import desktop_ops

    monkeypatch.setattr(desktop_ops, "execute_confirmed_action", fake_execute)

    confirmed = asyncio.run(executor.confirm(intent["intent_id"]))
    assert confirmed["success"] is True
    assert calls == [
        {
            "tool": "ops",
            "action": "db_soak",
            "params": {"duration_min": 0, "db": "x.sqlite3"},
        }
    ]
    assert store.get(intent["intent_id"])["status"] == "succeeded"


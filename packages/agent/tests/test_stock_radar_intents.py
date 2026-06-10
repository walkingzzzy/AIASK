from __future__ import annotations

import asyncio

import pytest

from aiask_agent.intents import ALLOWED_ACTIONS, ActionIntentStore, IntentExecutor


@pytest.mark.parametrize("action", ["run_once", "push_digest", "schedule_update"])
def test_stock_radar_actions_are_allowlisted_for_intent(action: str) -> None:
    descriptor = ALLOWED_ACTIONS[f"stock_radar.{action}"]
    assert descriptor == {"tool": "stock_radar", "action": action}


def test_stock_radar_intent_create_does_not_execute_without_confirm(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    async def fake_execute(tool: str, action: str, params: dict):
        calls.append((tool, action, params))
        return {"success": True, "data": {"ok": True}, "error": None}

    monkeypatch.setattr("aiask_agent.adapters.desktop_ops.execute_confirmed_action", fake_execute)
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    intent = store.create(
        action="stock_radar.run_once",
        params={"days": 3, "limit": 5, "allow_network": False},
        rationale="test stock radar",
    )

    assert intent["status"] == "awaiting_confirmation"
    assert intent["target_tool"] == "stock_radar"
    assert intent["target_action"] == "run_once"
    assert calls == []


def test_stock_radar_intent_confirm_dispatches_executor(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    async def fake_execute(tool: str, action: str, params: dict):
        calls.append((tool, action, params))
        return {"success": True, "data": {"status": "completed"}, "error": None}

    monkeypatch.setattr("aiask_agent.adapters.desktop_ops.execute_confirmed_action", fake_execute)
    store = ActionIntentStore(tmp_path / "intents.sqlite3")
    intent = store.create(
        action="stock_radar.push_digest",
        params={"channels": ["wecom", "telegram"], "dry_run": True},
        rationale="preview push digest",
    )

    result = asyncio.run(IntentExecutor(store).confirm(intent["intent_id"]))

    assert result["success"] is True
    assert calls == [("stock_radar", "push_digest", {"channels": ["wecom", "telegram"], "dry_run": True})]
    assert store.get(intent["intent_id"])["status"] == "succeeded"


def test_stock_radar_push_digest_dry_run_does_not_send_gateway(tmp_path, monkeypatch) -> None:
    import aiask_agent.adapters.desktop_ops as desktop_ops

    desktop_ops._ensure_monorepo_paths()
    calls: list[dict] = []

    class FakeDb:
        logs: list[dict] = []

        async def initialize(self):
            return None

        async def save_stock_radar_push_log(self, item):
            self.logs.append(dict(item))
            return dict(item)

    async def fake_push(db, payload):
        return {
            "success": True,
            "data": {
                "dry_run": True,
                "channels": payload["channels"],
                "message_preview": "preview",
                "gateway_status": "preview_recorded",
            },
            "error": None,
        }

    class FakeRouter:
        def __init__(self, *args, **kwargs):
            pass

        async def send(self, **kwargs):
            calls.append(kwargs)
            return {"adapter": {"ok": True, "status": "delivered"}, "message": {"message_id": "m1"}, "platform": {"name": kwargs["platform"]}}

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: FakeDb())
    monkeypatch.setattr("akshare_mcp.services.stock_radar.push_stock_radar_digest", fake_push)
    monkeypatch.setattr("aiask_agent.gateway.DeliveryRouter", FakeRouter)

    result = asyncio.run(
        desktop_ops.execute_confirmed_action(
            "stock_radar",
            "push_digest",
            {"channels": ["local"], "dry_run": True, "target": "radar"},
        )
    )

    assert result["success"] is True
    assert result["data"]["gateway_status"] == "preview_recorded"
    assert calls == []


def test_stock_radar_push_digest_blocked_does_not_send_gateway(tmp_path, monkeypatch) -> None:
    import aiask_agent.adapters.desktop_ops as desktop_ops

    desktop_ops._ensure_monorepo_paths()
    calls: list[dict] = []

    class FakeDb:
        logs: list[dict] = []

        async def initialize(self):
            return None

        async def save_stock_radar_push_log(self, item):
            self.logs.append(dict(item))
            return dict(item)

    async def fake_push(db, payload):
        return {
            "success": False,
            "data": {"dry_run": False, "channels": payload["channels"], "message_preview": "preview"},
            "error": "blocked",
            "error_code": "STOCK_RADAR_PUSH_REQUIRES_HIGH_CONFIDENCE",
        }

    class FakeRouter:
        def __init__(self, *args, **kwargs):
            pass

        async def send(self, **kwargs):
            calls.append(kwargs)
            return {"adapter": {"ok": True, "status": "delivered"}, "message": {"message_id": "m1"}, "platform": {"name": kwargs["platform"]}}

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: FakeDb())
    monkeypatch.setattr("akshare_mcp.services.stock_radar.push_stock_radar_digest", fake_push)
    monkeypatch.setattr("aiask_agent.gateway.DeliveryRouter", FakeRouter)

    result = asyncio.run(
        desktop_ops.execute_confirmed_action(
            "stock_radar",
            "push_digest",
            {"channels": ["local"], "dry_run": False, "target": "radar"},
        )
    )

    assert result["success"] is False
    assert result["error_code"] == "STOCK_RADAR_PUSH_REQUIRES_HIGH_CONFIDENCE"
    assert calls == []


def test_stock_radar_push_digest_non_dry_run_sends_gateway(tmp_path, monkeypatch) -> None:
    import aiask_agent.adapters.desktop_ops as desktop_ops

    desktop_ops._ensure_monorepo_paths()
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    calls: list[dict] = []

    class FakeDb:
        def __init__(self):
            self.logs: list[dict] = []

        async def initialize(self):
            return None

        async def save_stock_radar_push_log(self, item):
            self.logs.append(dict(item))
            return {**dict(item), "push_id": f"audit_{len(self.logs)}"}

    async def fake_push(db, payload):
        return {
            "success": True,
            "data": {
                "dry_run": False,
                "channels": payload["channels"],
                "message_preview": "Stock Radar Digest",
                "gateway_status": "queued_for_gateway_adapter",
            },
            "error": None,
        }

    class FakeRouter:
        def __init__(self, *args, **kwargs):
            pass

        async def send(self, **kwargs):
            calls.append(kwargs)
            return {
                "adapter": {"ok": True, "status": "delivered", "configured": True},
                "message": {"message_id": f"m{len(calls)}"},
                "platform": {"name": kwargs["platform"]},
            }

    fake_db = FakeDb()
    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: fake_db)
    monkeypatch.setattr("akshare_mcp.services.stock_radar.push_stock_radar_digest", fake_push)
    monkeypatch.setattr("aiask_agent.gateway.DeliveryRouter", FakeRouter)

    result = asyncio.run(
        desktop_ops.execute_confirmed_action(
            "stock_radar",
            "push_digest",
            {"channels": ["wecom", "telegram"], "dry_run": False, "target": "radar"},
        )
    )

    assert result["success"] is True
    assert result["data"]["gateway_status"] == "delivered"
    assert result["data"]["gateway_delivered_count"] == 2
    assert [item["status"] for item in result["data"]["gateway_push_logs"]] == ["delivered", "delivered"]
    assert fake_db.logs[0]["metadata"]["gateway_message_id"] == "m1"
    assert fake_db.logs[1]["metadata"]["gateway_message_id"] == "m2"
    assert calls == [
        {
            "platform": "wecom",
            "target": "radar",
            "message": "Stock Radar Digest",
            "thread_id": None,
            "session_id": None,
            "user_id": None,
        },
        {
            "platform": "telegram",
            "target": "radar",
            "message": "Stock Radar Digest",
            "thread_id": None,
            "session_id": None,
            "user_id": None,
        }
    ]

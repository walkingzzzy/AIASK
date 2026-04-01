"""Security regression tests for user_manager tenant boundaries."""

from __future__ import annotations

import pytest

import akshare_mcp.tools.managers.user_manager as user_manager_mod


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


class _UserConn:
    def __init__(self):
        self.users = {
            "alice": {
                "id": "alice",
                "username": "alice",
                "settings": {"theme": "light"},
                "created_at": "2026-03-18",
            },
            "bob": {
                "id": "bob",
                "username": "bob",
                "settings": {"theme": "dark"},
                "created_at": "2026-03-19",
            },
        }

    async def fetchrow(self, query, *args):
        user_id = args[0]
        user = self.users.get(user_id)
        if not user:
            return None
        if "SELECT settings FROM users" in query:
            return {"settings": user.get("settings")}
        return dict(user)

    async def fetch(self, query, *args):
        if "WHERE id = $1" in query:
            user_id = args[0]
            user = self.users.get(user_id)
            return [dict(user)] if user else []
        limit = int(args[0]) if args else 50
        return [dict(item) for item in self.users.values()][:limit]

    async def execute(self, query, *args):
        return "OK"


class _UserDB:
    def __init__(self):
        self.conn = _UserConn()

    def acquire(self):
        return _Acquire(self.conn)


@pytest.mark.asyncio
async def test_user_manager_should_reject_cross_user_updates_by_default(monkeypatch):
    mcp = _DummyMCP()
    user_manager_mod.register_user_manager(mcp)
    monkeypatch.setattr(user_manager_mod, "get_db", lambda: _UserDB())
    monkeypatch.delenv("AKSHARE_USER_MANAGER_ALLOW_IMPERSONATION", raising=False)

    result = await mcp.user_manager(
        action="update_preferences",
        params={
            "actor_user_id": "alice",
            "user_id": "bob",
            "preferences": {"risk_level": "balanced"},
        },
    )

    assert result["success"] is False
    assert result["error_code"] == "AUTH_ERROR"


@pytest.mark.asyncio
async def test_user_manager_should_default_list_to_actor_scope(monkeypatch):
    mcp = _DummyMCP()
    user_manager_mod.register_user_manager(mcp)
    monkeypatch.setattr(user_manager_mod, "get_db", lambda: _UserDB())
    monkeypatch.delenv("AKSHARE_USER_MANAGER_ALLOW_IMPERSONATION", raising=False)

    result = await mcp.user_manager(
        action="list_users",
        params={
            "actor_user_id": "alice",
            "user_id": "alice",
            "list_all": True,
        },
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["users"][0]["id"] == "alice"

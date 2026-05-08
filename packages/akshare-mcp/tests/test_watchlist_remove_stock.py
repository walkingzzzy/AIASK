import pytest

from akshare_mcp.tools.managers import watchlist_manager as watchlist_manager_module


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, update_rowcount: int = 1):
        self.commands: list[tuple[str, tuple[object, ...]]] = []
        self.update_rowcount = update_rowcount

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.commands.append((normalized, args))
        if normalized.startswith("UPDATE watchlist SET group_id = $1, sort_order = 0"):
            return f"UPDATE {self.update_rowcount}"
        if normalized.startswith("DELETE FROM watchlist"):
            return "DELETE 1"
        return "OK"


class FakeDb:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeMcp:
    def __init__(self):
        self.fn = None

    def tool(self):
        def decorator(fn):
            self.fn = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_remove_stock_from_custom_group_moves_back_to_default(monkeypatch):
    conn = FakeConn(update_rowcount=1)
    fake_mcp = FakeMcp()
    monkeypatch.setattr(watchlist_manager_module, "get_db", lambda: FakeDb(conn))
    watchlist_manager_module.register_watchlist_manager(fake_mcp)

    result = await fake_mcp.fn(action="remove_stock", params={
        "user_id": "u1",
        "group_id": "custom-group",
        "code": "600036",
    })

    assert result["success"] is True
    assert result["data"]["moved_to_default"] is True
    assert result["data"]["target_group_id"] == watchlist_manager_module.DEFAULT_GROUP_ID
    assert conn.commands == [
        (
            "UPDATE watchlist SET group_id = $1, sort_order = 0 WHERE user_id = $2 AND code = $3 AND group_id = $4",
            (watchlist_manager_module.DEFAULT_GROUP_ID, "u1", "600036", "custom-group"),
        ),
    ]


@pytest.mark.asyncio
async def test_remove_stock_from_default_group_deletes_globally(monkeypatch):
    conn = FakeConn()
    fake_mcp = FakeMcp()
    monkeypatch.setattr(watchlist_manager_module, "get_db", lambda: FakeDb(conn))
    watchlist_manager_module.register_watchlist_manager(fake_mcp)

    result = await fake_mcp.fn(action="remove_stock", params={
        "user_id": "u1",
        "group_id": watchlist_manager_module.DEFAULT_GROUP_ID,
        "code": "600036",
    })

    assert result["success"] is True
    assert result["data"]["removed"] is True
    assert result["data"]["moved_to_default"] is False
    assert conn.commands == [
        (
            "DELETE FROM watchlist WHERE user_id = $1 AND code = $2",
            ("u1", "600036"),
        ),
    ]

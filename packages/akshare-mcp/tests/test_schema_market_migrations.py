import pytest

from akshare_mcp.storage.timescaledb.schema_market import _run_market_migration_once


class _FakeConn:
    def __init__(self):
        self.applied: set[str] = set()
        self.executed: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.executed.append((normalized, args))
        if "INSERT INTO market_schema_migrations" in normalized:
            self.applied.add(str(args[0]))

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT 1 FROM market_schema_migrations" in normalized:
            return 1 if str(args[0]) in self.applied else None
        return None


@pytest.mark.asyncio
async def test_run_market_migration_once_marks_state_and_skips_repeat_execution():
    conn = _FakeConn()

    first = await _run_market_migration_once(conn, "stock_quotes_backfill_change_amt", "UPDATE stock_quotes SET change_amt = 1")
    second = await _run_market_migration_once(conn, "stock_quotes_backfill_change_amt", "UPDATE stock_quotes SET change_amt = 1")

    update_calls = [query for query, _args in conn.executed if query == "UPDATE stock_quotes SET change_amt = 1"]

    assert first is True
    assert second is False
    assert len(update_calls) == 1

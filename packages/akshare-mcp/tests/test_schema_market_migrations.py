import pytest

from akshare_mcp.storage.timescaledb._schema_market_phase_5 import init_market_tables_phase_5
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


@pytest.mark.asyncio
async def test_market_phase_5_init_is_idempotent_and_backfills_once():
    conn = _FakeConn()

    await init_market_tables_phase_5(conn)
    await init_market_tables_phase_5(conn)

    normalized_queries = [query for query, _args in conn.executed]
    phase_5_ddl_calls = [
        query
        for query in normalized_queries
        if "CREATE TABLE IF NOT EXISTS strategy_trade_positions" in query
    ]
    backfill_calls = [
        query
        for query in normalized_queries
        if "UPDATE paper_trades AS trades" in query
    ]

    assert phase_5_ddl_calls
    assert any("ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS signal_id TEXT" in query for query in normalized_queries)
    assert any("ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS position_id TEXT" in query for query in normalized_queries)
    assert len(backfill_calls) == 1

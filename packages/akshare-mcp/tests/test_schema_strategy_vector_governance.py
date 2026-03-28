"""Tests: schema_strategy vector governance columns (model_id / collection_name)."""
from __future__ import annotations

import pytest

from akshare_mcp.storage.timescaledb.schema_strategy import init_strategy_tables


class _Conn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.calls.append((normalized, args))
        return "OK"

    async def fetchrow(self, query, *args):
        return None

    async def fetch(self, query, *args):
        return []


@pytest.mark.asyncio
async def test_strategy_schema_adds_model_id_column_to_vector_tables():
    conn = _Conn()
    await init_strategy_tables(conn, pgvector_enabled=False)

    sql_text = "\n".join(q for q, _ in conn.calls)

    assert "strategy_vector_profiles" in sql_text
    assert "strategy_vector_index_snapshots" in sql_text
    assert "strategy_vector_index_items" in sql_text

    # model_id and collection_name migration must be present
    assert "ADD COLUMN IF NOT EXISTS model_id" in sql_text
    assert "ADD COLUMN IF NOT EXISTS collection_name" in sql_text


@pytest.mark.asyncio
async def test_strategy_schema_adds_model_id_to_pgvector_store_tables():
    conn = _Conn()
    await init_strategy_tables(conn, pgvector_enabled=True)

    sql_text = "\n".join(q for q, _ in conn.calls)

    assert "strategy_vector_profile_store" in sql_text
    assert "strategy_vector_index_item_store" in sql_text
    assert "ADD COLUMN IF NOT EXISTS model_id" in sql_text
    assert "ADD COLUMN IF NOT EXISTS collection_name" in sql_text


@pytest.mark.asyncio
async def test_strategy_schema_creates_model_governance_indexes():
    conn = _Conn()
    await init_strategy_tables(conn, pgvector_enabled=False)

    sql_text = "\n".join(q for q, _ in conn.calls)

    assert "idx_strategy_vector_profiles_model" in sql_text
    assert "idx_strategy_vector_index_snapshots_model" in sql_text
    assert "idx_strategy_vector_index_items_model" in sql_text


@pytest.mark.asyncio
async def test_strategy_schema_backfills_model_id_default():
    conn = _Conn()
    await init_strategy_tables(conn, pgvector_enabled=False)

    updates = [q for q, _ in conn.calls if "strategy_vector_profiles" in q and "UPDATE" in q]
    assert any("strategy_behavior_v1" in q for q in updates), (
        "Expected UPDATE statement setting model_id default 'strategy_behavior_v1'"
    )


@pytest.mark.asyncio
async def test_strategy_schema_backfills_collection_name_default():
    conn = _Conn()
    await init_strategy_tables(conn, pgvector_enabled=False)

    updates = [q for q, _ in conn.calls if "strategy_behavior_embeddings" in q]
    assert updates, "Expected UPDATE statement with default collection_name 'strategy_behavior_embeddings'"

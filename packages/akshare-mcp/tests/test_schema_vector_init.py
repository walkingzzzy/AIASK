from __future__ import annotations

import pytest

from akshare_mcp.storage.timescaledb.schema_vector import init_vector_tables


class _Conn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.calls.append((normalized, args))
        return "OK"


@pytest.mark.asyncio
async def test_init_vector_tables_creates_core_tables_and_seeds_default_collections():
    conn = _Conn()

    await init_vector_tables(conn, pgvector_enabled=True)

    sql_text = "\n".join(query for query, _ in conn.calls)
    seed_rows = [args[0] for query, args in conn.calls if "INSERT INTO vector_collections" in query]

    assert "CREATE TABLE IF NOT EXISTS vector_collections" in sql_text
    assert "CREATE TABLE IF NOT EXISTS market_documents" in sql_text
    assert "CREATE TABLE IF NOT EXISTS market_doc_chunks" in sql_text
    assert "CREATE TABLE IF NOT EXISTS vector_profile_store" in sql_text
    assert "CREATE TABLE IF NOT EXISTS vector_index_item_store" in sql_text
    assert "ADD COLUMN IF NOT EXISTS bucket_id TEXT" in sql_text
    assert "idx_vector_index_item_store_bucket_lookup" in sql_text
    assert "market_doc_chunks" in seed_rows
    assert "kline_pattern_embeddings" in seed_rows
    assert "stock_profile_embeddings" in seed_rows


@pytest.mark.asyncio
async def test_init_vector_tables_skips_pgvector_store_tables_when_extension_disabled():
    conn = _Conn()

    await init_vector_tables(conn, pgvector_enabled=False)

    sql_text = "\n".join(query for query, _ in conn.calls)

    assert "CREATE TABLE IF NOT EXISTS vector_profile_store" not in sql_text
    assert "CREATE TABLE IF NOT EXISTS vector_index_item_store" not in sql_text
    assert "CREATE TABLE IF NOT EXISTS vector_collections" in sql_text

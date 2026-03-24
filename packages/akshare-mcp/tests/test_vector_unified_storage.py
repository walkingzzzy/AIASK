from __future__ import annotations

import json

import pytest

from akshare_mcp.storage.timescaledb.vector_unified import VectorUnifiedMixin


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _StoreConn:
    def __init__(self):
        self.executemany_calls: list[tuple[str, list[tuple]]] = []

    def transaction(self):
        return _Txn()

    async def execute(self, _query, *_args):
        return "OK"

    async def executemany(self, query, rows):
        self.executemany_calls.append((" ".join(str(query).split()), list(rows)))
        return "OK"

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT id, profile_id FROM vector_index_items" in normalized:
            return [{"id": 101, "profile_id": 1}]
        raise AssertionError(f"unexpected fetch: {normalized} args={args}")


class _SearchConn:
    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        assert "iv.bucket_id = ANY(" in normalized
        assert args[5] == ["b_0000", "b_0001"]
        return [
            {
                "id": 1,
                "collection_name": "stock_profile_embeddings",
                "index_version": "snap_v1",
                "profile_id": 1,
                "entity_type": "stock_profile",
                "entity_id": "600519|both",
                "stock_code": "600519",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "metric": "cosine",
                "vector_dim": 2,
                "bucket_id": "b_0000",
                "coarse_score": 0.98,
                "embedding_json": [1.0, 0.0],
                "metadata": {"stock_name": "贵州茅台"},
                "similarity": 0.99,
            }
        ]


class _ListConn:
    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        assert "bucket_id = ANY(" in normalized
        assert "profile_type = $" in normalized
        assert "stock_code = ANY(" in normalized
        assert "entity_id = ANY(" in normalized
        assert "COALESCE(stock_code, '') !=" in normalized
        assert "entity_id !=" in normalized
        assert args[2] == ["b_0000", "b_0001"]
        assert args[3] == "both"
        assert args[4] == ["000001", "000002"]
        assert args[5] == ["000001|both", "000002|both"]
        assert args[6] == "600519"
        assert args[7] == "000002|both"
        return [
            {
                "entity_id": "000001|both",
                "stock_code": "000001",
                "profile_type": "both",
                "bucket_id": "b_0000",
                "embedding_json": [1.0, 0.0],
                "metadata": {"stock_name": "平安银行"},
            }
        ]


class _Adapter(VectorUnifiedMixin):
    def __init__(self, conn):
        self._conn = conn

    @staticmethod
    def _decode_json_field(value, default):
        if value is None:
            return default
        if isinstance(value, str):
            return json.loads(value)
        return value

    def supports_pgvector(self):
        return True

    def acquire(self):
        return _Acquire(self._conn)

    @staticmethod
    def _encode_pgvector(values):
        rows = [float(item) for item in list(values or [])]
        if not rows:
            return None
        return "[" + ",".join(str(item) for item in rows) + "]"

    @staticmethod
    def _pgvector_distance_sql(_column, _metric, _dim):
        return "0.01", "0.99"


@pytest.mark.asyncio
async def test_replace_vector_index_items_persists_bucket_id_into_pgvector_store():
    conn = _StoreConn()
    adapter = _Adapter(conn)

    await adapter.replace_vector_index_items(
        "stock_profile_embeddings",
        "snap_v1",
        [
            {
                "profile_id": 1,
                "entity_type": "stock_profile",
                "entity_id": "600519|both",
                "stock_code": "600519",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "metric": "cosine",
                "vector_dim": 2,
                "bucket_id": "b_0001",
                "coarse_score": 0.97,
                "embedding": [1.0, 0.0],
                "metadata": {"stock_name": "贵州茅台"},
            }
        ],
    )

    assert len(conn.executemany_calls) == 2
    store_sql, store_rows = conn.executemany_calls[1]
    assert "INSERT INTO vector_index_item_store" in store_sql
    assert "bucket_id" in store_sql
    assert store_rows[0][11] == "b_0001"


@pytest.mark.asyncio
async def test_search_vector_index_items_by_embedding_filters_bucket_ids_on_store_table():
    adapter = _Adapter(_SearchConn())

    rows = await adapter.search_vector_index_items_by_embedding(
        query_embedding=[1.0, 0.0],
        collection_name="stock_profile_embeddings",
        index_version="snap_v1",
        profile_type="both",
        bucket_ids=["b_0000", "b_0001"],
        limit=5,
    )

    assert len(rows) == 1
    assert rows[0]["bucket_id"] == "b_0000"
    assert rows[0]["similarity"] == 0.99


@pytest.mark.asyncio
async def test_list_vector_index_items_pushes_pruning_filters_into_sql():
    adapter = _Adapter(_ListConn())

    rows = await adapter.list_vector_index_items(
        collection_name="stock_profile_embeddings",
        index_version="snap_v1",
        bucket_ids=["b_0000", "b_0001"],
        profile_type="both",
        stock_codes=["000001", "000002"],
        entity_ids=["000001|both", "000002|both"],
        exclude_stock_code="600519",
        exclude_entity_id="000002|both",
        limit=20,
    )

    assert len(rows) == 1
    assert rows[0]["entity_id"] == "000001|both"

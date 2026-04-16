from __future__ import annotations

import json
import os
from datetime import date

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

    @staticmethod
    def _coerce_timestamp(value):
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

    @staticmethod
    def _pgvector_opclass(metric):
        return "vector_l2_ops" if str(metric or "cosine").lower() == "euclidean" else "vector_cosine_ops"

    @staticmethod
    def _pgvector_partial_index_name(prefix, *parts):
        suffix = "_".join(str(part or "x") for part in parts)
        return f"{prefix}_{suffix}".replace(".", "_").replace("|", "_")

    @staticmethod
    def _coerce_positive_int(value, default):
        try:
            resolved = int(value)
        except Exception:
            resolved = int(default)
        return max(1, resolved)

    @classmethod
    def _resolve_pgvector_hnsw_params(cls, index_params=None):
        params = dict(index_params or {})
        return {
            "m": cls._coerce_positive_int(params.get("m") or 16, 16),
            "ef_construction": cls._coerce_positive_int(params.get("ef_construction") or 64, 64),
            "ef_search": cls._coerce_positive_int(params.get("ef_search") or 80, 80),
        }

    @classmethod
    def _pgvector_hnsw_with_clause(cls, index_params=None):
        params = cls._resolve_pgvector_hnsw_params(index_params)
        return f" WITH (m = {params['m']}, ef_construction = {params['ef_construction']})"

    @classmethod
    def _resolve_pgvector_index_build_settings(cls, index_params=None):
        params = dict(index_params or {})
        return {
            "maintenance_work_mem": str(
                params.get("maintenance_work_mem")
                or os.getenv("VECTOR_INDEX_BUILD_MAINTENANCE_WORK_MEM")
                or "256MB"
            ),
            "max_parallel_maintenance_workers": cls._coerce_positive_int(
                params.get("max_parallel_maintenance_workers")
                or os.getenv("VECTOR_INDEX_BUILD_MAX_PARALLEL_MAINTENANCE_WORKERS")
                or 1,
                1,
            ),
        }


class _WindowConn:
    def __init__(self):
        self.args = None

    async def fetchrow(self, query, *args):
        normalized = " ".join(str(query).split())
        assert "INSERT INTO kline_pattern_windows" in normalized
        self.args = args
        return {
            "window_uid": args[0],
            "stock_code": args[1],
            "end_date": args[2],
            "start_date": args[3],
            "period": args[4],
            "adjust": args[5],
            "window_size": args[6],
            "vector_method": args[7],
            "metric": args[8],
            "vector_dim": args[9],
            "forward_return_5d": args[10],
            "forward_return_10d": args[11],
            "forward_return_20d": args[12],
            "payload": json.loads(args[13]),
            "metadata": json.loads(args[14]),
        }


class _IndexSqlConn:
    def __init__(self):
        self.fetchval_calls: list[tuple[str, tuple]] = []
        self.executed_sql: list[str] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    def transaction(self):
        return _Txn()

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split())
        self.fetchval_calls.append((normalized, args))
        with_clause = str(args[3])
        profile_type = f" AND profile_type = '{args[7]}'" if len(args) > 7 else ""
        return (
            f"CREATE INDEX IF NOT EXISTS {args[0]} ON vector_profile_store USING hnsw "
            f"((embedding::vector({args[1]})) {args[2]}){with_clause} "
            f"WHERE collection_name = '{args[4]}' AND version = '{args[5]}' AND vector_dim = {args[6]}{profile_type}"
        )

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.executed_sql.append(normalized)
        self.execute_calls.append((normalized, args))
        return "OK"


class _HnswSearchConn:
    def __init__(self):
        self.commands: list[str] = []
        self.fetch_calls: list[tuple[str, tuple]] = []

    def transaction(self):
        return _Txn()

    async def execute(self, query, *args):
        self.commands.append(" ".join(str(query).split()))
        return "OK"

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        self.fetch_calls.append((normalized, args))
        return [
            {
                "id": 1,
                "collection_name": "stock_profile_embeddings",
                "version": "snap_v1",
                "entity_type": "stock_profile",
                "entity_id": "600519|both",
                "stock_code": "600519",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "metric": "cosine",
                "vector_dim": 2,
                "embedding_json": [1.0, 0.0],
                "metadata": {"stock_name": "贵州茅台"},
                "similarity": 0.98,
            }
        ]


class _SnapshotSaveConn:
    def __init__(self):
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        normalized = " ".join(str(query).split())
        self.fetchrow_calls.append((normalized, args))
        return {
            "collection_name": args[0],
            "index_version": args[1],
            "status": args[2],
            "model_id": args[3],
            "profile_type": args[4],
            "metric": args[5],
            "vector_dim": args[6],
            "sample_count": args[7],
            "bucket_count": args[8],
            "index_params": json.loads(args[9]),
            "metrics": json.loads(args[10]),
            "metadata": json.loads(args[11]),
            "built_at": args[12],
            "activated_at": args[13],
        }

    async def execute(self, query, *args):
        self.execute_calls.append((" ".join(str(query).split()), args))
        return "UPDATE 1"


class _CleanupConn:
    def __init__(self):
        self.execute_calls: list[tuple[str, tuple]] = []

    def transaction(self):
        return _Txn()

    async def fetchrow(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT * FROM vector_collections" in normalized:
            return {
                "collection_name": "market_doc_chunks",
                "active_version": "v_keep",
                "backend": "pgvector",
                "model_id": "text-embedding-3-small",
            }
        raise AssertionError(f"unexpected fetchrow: {normalized} args={args}")

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM vector_profiles" in normalized and "GROUP BY version" in normalized:
            return [
                {"version": "v_keep", "profile_rows": 1, "last_seen": "2026-03-25T00:00:00+00:00"},
                {"version": "v_old", "profile_rows": 1, "last_seen": "2026-03-24T00:00:00+00:00"},
            ]
        if "FROM vector_profile_store" in normalized and "GROUP BY version" in normalized:
            return [
                {"version": "v_keep", "profile_store_rows": 1, "last_seen": "2026-03-25T00:00:00+00:00"},
                {"version": "v_old", "profile_store_rows": 1, "last_seen": "2026-03-24T00:00:00+00:00"},
            ]
        if "FROM vector_index_snapshots" in normalized and "ORDER BY" in normalized:
            return [
                {
                    "index_version": "v_keep",
                    "status": "active",
                    "bucket_count": 1,
                    "vector_dim": 3,
                    "model_id": "text-embedding-3-small",
                    "activated_at": "2026-03-25T00:00:00+00:00",
                    "profile_type": "news",
                },
                {
                    "index_version": "v_old",
                    "status": "built",
                    "bucket_count": 1,
                    "vector_dim": 3,
                    "model_id": "text-embedding-3-small",
                    "created_at": "2026-03-24T00:00:00+00:00",
                    "profile_type": "news",
                },
            ]
        if "FROM vector_index_items" in normalized and "GROUP BY index_version" in normalized:
            return [
                {"version": "v_keep", "index_item_rows": 1, "last_seen": "2026-03-25T00:00:00+00:00"},
                {"version": "v_old", "index_item_rows": 1, "last_seen": "2026-03-24T00:00:00+00:00"},
            ]
        if "FROM vector_index_item_store" in normalized and "GROUP BY index_version" in normalized:
            return [
                {"version": "v_keep", "index_item_store_rows": 1, "last_seen": "2026-03-25T00:00:00+00:00"},
                {"version": "v_old", "index_item_store_rows": 1, "last_seen": "2026-03-24T00:00:00+00:00"},
            ]
        raise AssertionError(f"unexpected fetch: {normalized} args={args}")

    async def execute(self, query, *args):
        normalized = " ".join(str(query).split())
        self.execute_calls.append((normalized, args))
        if normalized.startswith("DELETE FROM"):
            return "DELETE 1"
        return "OK"


class _CleanupAdapter(_Adapter):
    async def list_vector_hnsw_indexes(self, **_kwargs):
        return []


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


@pytest.mark.asyncio
async def test_ensure_vector_profile_pgvector_index_includes_hnsw_with_clause():
    conn = _IndexSqlConn()
    adapter = _Adapter(conn)

    idx_name = await adapter.ensure_vector_profile_pgvector_index(
        collection_name="stock_profile_embeddings",
        version="snap_v1",
        vector_dim=32,
        profile_type="both",
        index_params={"m": 24, "ef_construction": 96},
    )

    assert idx_name is not None
    assert conn.fetchval_calls
    _, args = conn.fetchval_calls[0]
    assert args[3] == " WITH (m = 24, ef_construction = 96)"
    assert conn.executed_sql[0] == "SELECT set_config('maintenance_work_mem', $1, true)"
    assert conn.executed_sql[1] == "SELECT set_config('max_parallel_maintenance_workers', $1, true)"
    assert conn.execute_calls[0][1] == ("256MB",)
    assert conn.execute_calls[1][1] == ("1",)
    assert "WITH (m = 24, ef_construction = 96)" in conn.executed_sql[2]


@pytest.mark.asyncio
async def test_ensure_vector_profile_pgvector_index_uses_low_memory_build_defaults(monkeypatch):
    conn = _IndexSqlConn()
    adapter = _Adapter(conn)
    monkeypatch.setenv("VECTOR_INDEX_BUILD_MAINTENANCE_WORK_MEM", "96MB")
    monkeypatch.setenv("VECTOR_INDEX_BUILD_MAX_PARALLEL_MAINTENANCE_WORKERS", "1")

    await adapter.ensure_vector_profile_pgvector_index(
        collection_name="stock_profile_embeddings",
        version="snap_v1",
        vector_dim=32,
        profile_type="both",
    )

    assert conn.executed_sql[0] == "SELECT set_config('maintenance_work_mem', $1, true)"
    assert conn.executed_sql[1] == "SELECT set_config('max_parallel_maintenance_workers', $1, true)"
    assert conn.execute_calls[0][1] == ("96MB",)
    assert conn.execute_calls[1][1] == ("1",)


@pytest.mark.asyncio
async def test_search_vector_profiles_by_embedding_sets_hnsw_ef_search_locally():
    conn = _HnswSearchConn()
    adapter = _Adapter(conn)

    rows = await adapter.search_vector_profiles_by_embedding(
        query_embedding=[1.0, 0.0],
        collection_name="stock_profile_embeddings",
        version="snap_v1",
        profile_type="both",
        limit=3,
        index_params={"ef_search": 123},
    )

    assert conn.commands[0] == "SET LOCAL hnsw.ef_search = 123"
    assert "FROM vector_profile_store ps" in conn.fetch_calls[0][0]
    assert len(rows) == 1
    assert rows[0]["similarity"] == 0.98


@pytest.mark.asyncio
async def test_save_kline_pattern_window_coerces_string_dates_before_execute():
    conn = _WindowConn()
    adapter = _Adapter(conn)

    row = await adapter.save_kline_pattern_window(
        {
            "window_uid": "kwin_demo",
            "stock_code": "600519",
            "end_date": "2026-03-23",
            "start_date": "20260304",
            "period": "daily",
            "adjust": "",
            "window_size": 20,
            "vector_method": "returns",
            "metric": "cosine",
            "vector_dim": 5,
            "payload": {"close_series": [1, 2, 3]},
            "metadata": {"source": "test"},
        }
    )

    assert isinstance(conn.args[2], date)
    assert isinstance(conn.args[3], date)
    assert conn.args[2].isoformat() == "2026-03-23"
    assert conn.args[3].isoformat() == "2026-03-04"
    assert row["window_uid"] == "kwin_demo"


@pytest.mark.asyncio
async def test_save_vector_index_snapshot_deactivates_prior_active_scope():
    conn = _SnapshotSaveConn()
    adapter = _Adapter(conn)

    row = await adapter.save_vector_index_snapshot(
        {
            "collection_name": "market_doc_chunks",
            "index_version": "snap_news_v2",
            "status": "active",
            "model_id": "text-embedding-3-small",
            "profile_type": "news",
            "metric": "cosine",
            "vector_dim": 3,
            "sample_count": 2,
            "bucket_count": 1,
            "index_params": {"neighbor_count": 2},
            "metrics": {"items_count": 2},
            "metadata": {"profile_version": "v2"},
            "built_at": "2026-03-25T00:00:00+00:00",
            "activated_at": "2026-03-25T00:00:01+00:00",
        }
    )

    assert row["collection_name"] == "market_doc_chunks__news"
    assert "UPDATE vector_index_snapshots SET status = 'stale'" in conn.execute_calls[0][0]
    assert conn.execute_calls[0][1][0] == "market_doc_chunks__news"
    assert conn.execute_calls[0][1][1] == "snap_news_v2"
    assert conn.execute_calls[0][1][2] == "news"
    assert "UPDATE vector_collections SET active_version = $2" in conn.execute_calls[1][0]
    assert conn.execute_calls[1][1] == ("market_doc_chunks__news", "snap_news_v2")


@pytest.mark.asyncio
async def test_cleanup_vector_collection_history_filters_store_deletes_by_profile_type():
    conn = _CleanupConn()
    adapter = _CleanupAdapter(conn)

    summary = await adapter.cleanup_vector_collection_history(
        collection_name="market_doc_chunks",
        keep_versions=1,
        dry_run=False,
        profile_type="news",
    )

    delete_sql = {sql: args for sql, args in conn.execute_calls if sql.startswith("DELETE FROM")}
    assert summary["deleted"]["vector_profile_store"] == 1
    assert summary["deleted"]["vector_index_item_store"] == 1
    assert "DELETE FROM vector_index_item_store WHERE collection_name = $1 AND index_version = ANY($2::text[]) AND COALESCE(profile_type, '') = $3" in delete_sql
    assert delete_sql["DELETE FROM vector_index_item_store WHERE collection_name = $1 AND index_version = ANY($2::text[]) AND COALESCE(profile_type, '') = $3"][2] == "news"
    assert "DELETE FROM vector_profile_store WHERE collection_name = $1 AND version = ANY($2::text[]) AND COALESCE(profile_type, '') = $3" in delete_sql
    assert delete_sql["DELETE FROM vector_profile_store WHERE collection_name = $1 AND version = ANY($2::text[]) AND COALESCE(profile_type, '') = $3"][2] == "news"

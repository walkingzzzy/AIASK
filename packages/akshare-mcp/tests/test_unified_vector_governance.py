from __future__ import annotations

import pytest

from akshare_mcp.services.unified_vector_governance import build_vector_collection_snapshot
from akshare_mcp.storage.timescaledb.vector_unified import VectorUnifiedMixin


class _GovernanceDb:
    def __init__(self):
        self.collection = {
            "collection_name": "stock_profile_embeddings",
            "entity_family": "stock_profile",
            "backend": "pgvector",
            "metric": "cosine",
            "model_id": "stock-profile-v1",
            "vector_dim": 11,
            "status": "active",
            "active_version": None,
            "metadata": {"domain": "market-quant"},
        }
        self.snapshots: list[dict] = []
        self.replaced_items: list[dict] = []

    async def list_vector_profiles(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["profile_type"] == "both"
        assert kwargs["version"] == "v1"
        return [
            {
                "id": 1,
                "collection_name": "stock_profile_embeddings",
                "entity_type": "stock_profile",
                "entity_id": "600519|both",
                "stock_code": "600519",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "vector_dim": 11,
                "metric": "cosine",
                "version": "v1",
                "embedding": [0.1] * 11,
                "metadata": {"stock_name": "贵州茅台"},
            },
            {
                "id": 2,
                "collection_name": "stock_profile_embeddings",
                "entity_type": "stock_profile",
                "entity_id": "000001|both",
                "stock_code": "000001",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "vector_dim": 11,
                "metric": "cosine",
                "version": "v1",
                "embedding": [0.2] * 11,
                "metadata": {"stock_name": "平安银行"},
            },
        ]

    async def get_vector_collection(self, collection_name):
        assert collection_name == "stock_profile_embeddings"
        return dict(self.collection)

    async def save_vector_collection(self, payload):
        self.collection.update(dict(payload))
        return dict(self.collection)

    async def save_vector_index_snapshot(self, snapshot):
        item = dict(snapshot)
        self.snapshots.append(item)
        if item.get("activated_at"):
            self.collection["active_version"] = item.get("index_version")
        return item

    async def replace_vector_index_items(self, collection_name, index_version, items):
        self.replaced_items = [
            {
                **dict(item),
                "collection_name": collection_name,
                "index_version": index_version,
            }
            for item in list(items)
        ]
        return {"collection_name": collection_name, "index_version": index_version, "count": len(items)}

    async def list_vector_index_snapshots(self, **kwargs):
        rows = list(self.snapshots)
        if kwargs.get("collection_name"):
            rows = [row for row in rows if row.get("collection_name") == kwargs.get("collection_name")]
        if kwargs.get("index_version"):
            rows = [row for row in rows if row.get("index_version") == kwargs.get("index_version")]
        if kwargs.get("profile_type"):
            rows = [row for row in rows if row.get("profile_type") == kwargs.get("profile_type")]
        return [dict(row) for row in rows]

    async def list_vector_index_items(self, **kwargs):
        rows = list(self.replaced_items)
        if kwargs.get("collection_name"):
            rows = [row for row in rows if row.get("collection_name") == kwargs.get("collection_name")]
        if kwargs.get("index_version"):
            rows = [row for row in rows if row.get("index_version") == kwargs.get("index_version")]
        if kwargs.get("profile_type"):
            rows = [row for row in rows if row.get("profile_type") == kwargs.get("profile_type")]
        return [dict(row) for row in rows]

    async def ensure_vector_profile_pgvector_index(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        return "idx_profile"

    async def ensure_vector_index_item_pgvector_index(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        return "idx_item"


@pytest.mark.asyncio
async def test_build_vector_collection_snapshot_updates_active_version_and_items():
    db = _GovernanceDb()

    result = await build_vector_collection_snapshot(
        db,
        collection_name="stock_profile_embeddings",
        version="v1",
        index_version="snap_v1",
        profile_type="both",
        activate=True,
    )

    assert result["status"] == "active"
    assert result["degraded"] is False
    assert result["quality_flags"] == []
    assert result["sample_count"] == 2
    assert result["items_count"] == 2
    assert db.collection["active_version"] == "snap_v1"
    assert db.snapshots[0]["status"] == "building"
    assert db.snapshots[0]["index_params"]["bucket_strategy"] == "centroid_kmeans"
    assert db.snapshots[-1]["status"] == "active"
    assert db.snapshots[-1]["metadata"]["profile_version"] == "v1"
    assert db.snapshots[-1]["metadata"]["centroids"]
    assert db.snapshots[-1]["metadata"]["qa"]["status"] == "passed"
    assert db.snapshots[-1]["index_params"]["bucket_strategy"] == "centroid_kmeans"
    assert db.replaced_items[0]["bucket_id"].startswith("b_")
    assert db.replaced_items[0]["coarse_score"] <= 1.0


@pytest.mark.asyncio
async def test_build_vector_collection_snapshot_marks_quality_degraded_when_scope_has_multiple_active_snapshots():
    db = _GovernanceDb()
    db.snapshots.append(
        {
            "collection_name": "stock_profile_embeddings",
            "index_version": "snap_old",
            "status": "active",
            "profile_type": "both",
            "metadata": {"profile_version": "v0"},
        }
    )

    result = await build_vector_collection_snapshot(
        db,
        collection_name="stock_profile_embeddings",
        version="v1",
        index_version="snap_v1",
        profile_type="both",
        activate=True,
    )

    assert result["status"] == "degraded"
    assert result["degraded"] is True
    assert "active_snapshot_not_unique" in result["quality_flags"]


class _MixedDimGovernanceDb(_GovernanceDb):
    async def list_vector_profiles(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["profile_type"] == "both"
        assert kwargs["version"] == "v1"
        return [
            {
                "id": 1,
                "collection_name": "stock_profile_embeddings",
                "entity_type": "stock_profile",
                "entity_id": "600519|both",
                "stock_code": "600519",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "vector_dim": 256,
                "metric": "cosine",
                "version": "v1",
                "embedding": [0.1] * 256,
                "metadata": {"stock_name": "贵州茅台"},
            },
            {
                "id": 2,
                "collection_name": "stock_profile_embeddings",
                "entity_type": "stock_profile",
                "entity_id": "000001|both",
                "stock_code": "000001",
                "profile_type": "both",
                "model_id": "stock-profile-v1",
                "vector_dim": 1536,
                "metric": "cosine",
                "version": "v1",
                "embedding": [0.2] * 1536,
                "metadata": {"stock_name": "平安银行"},
            },
        ]


@pytest.mark.asyncio
async def test_build_vector_collection_snapshot_fails_on_mixed_vector_dimensions():
    db = _MixedDimGovernanceDb()

    result = await build_vector_collection_snapshot(
        db,
        collection_name="stock_profile_embeddings",
        version="v1",
        index_version="snap_v1",
        profile_type="both",
        activate=True,
    )

    assert result["status"] == "failed"
    assert result["degraded"] is True
    assert result["reason"] == "mixed_vector_dimensions"
    assert result["quality_flags"] == ["mixed_vector_dimensions"]
    assert result["vector_dim_counts"] == {"256": 1, "1536": 1}


class _SearchAdapter(VectorUnifiedMixin):
    def __init__(self):
        self.collection = {
            "collection_name": "factor_candidate_embeddings",
            "active_version": "snap_mem_v1",
            "metadata": {},
        }
        self.snapshot = {
            "collection_name": "factor_candidate_embeddings",
            "index_version": "snap_mem_v1",
            "metadata": {"profile_version": "v1"},
        }

    @staticmethod
    def _decode_json_field(value, default):
        return value if value is not None else default

    async def get_vector_collection(self, collection_name):
        assert collection_name == "factor_candidate_embeddings"
        return dict(self.collection)

    async def list_vector_index_snapshots(self, **kwargs):
        assert kwargs["collection_name"] == "factor_candidate_embeddings"
        assert kwargs["index_version"] == "snap_mem_v1"
        return [dict(self.snapshot)]

    async def search_vector_profiles_by_embedding(self, **kwargs):
        assert kwargs["version"] == "v1"
        return []

    async def list_vector_profiles(self, **kwargs):
        assert kwargs["collection_name"] == "factor_candidate_embeddings"
        assert kwargs["version"] == "v1"
        return [
            {
                "entity_id": "mem_001",
                "stock_code": "600519",
                "profile_type": "memory",
                "embedding": [1.0, 0.0, 0.0],
                "metadata": {"candidate_name": "mom_a"},
            },
            {
                "entity_id": "mem_002",
                "stock_code": "000001",
                "profile_type": "memory",
                "embedding": [0.0, 1.0, 0.0],
                "metadata": {"candidate_name": "value_a"},
            },
        ]


@pytest.mark.asyncio
async def test_search_vector_collection_uses_active_snapshot_and_exact_fallback():
    adapter = _SearchAdapter()

    result = await adapter.search_vector_collection(
        collection_name="factor_candidate_embeddings",
        query_embedding=[0.9, 0.1, 0.0],
        profile_type="memory",
        entity_ids=["mem_001", "mem_002"],
        limit=2,
        metric="cosine",
    )

    assert result["backend_used"] == "exact_json"
    assert result["fallback_used"] is True
    assert result["profile_version"] == "v1"
    assert result["index_version"] == "snap_mem_v1"
    assert result["items"][0]["entity_id"] == "mem_001"


class _KlineConn:
    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM kline_pattern_windows" not in normalized:
            return []
        entity_ids = set(args[0] or [])
        rows = [
            {
                "window_uid": "kwin_001",
                "stock_code": "000001",
                "end_date": "2026-03-20",
                "start_date": "2026-03-01",
                "period": "daily",
                "adjust": "",
                "window_size": 20,
                "vector_method": "returns",
                "metric": "cosine",
                "vector_dim": 20,
                "forward_return_5d": 0.05,
                "forward_return_10d": 0.08,
                "forward_return_20d": 0.12,
                "payload": {"stock_name": "平安银行"},
                "metadata": {"source": "kline_1d"},
            }
        ]
        return [row for row in rows if row["window_uid"] in entity_ids]


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _KlineSearchAdapter(VectorUnifiedMixin):
    def __init__(self):
        self._conn = _KlineConn()
        self.search_vector_collection_calls: list[dict] = []

    def acquire(self):
        return _Acquire(self._conn)

    @staticmethod
    def _decode_json_field(value, default):
        return value if value is not None else default

    async def search_vector_collection(self, **kwargs):
        self.search_vector_collection_calls.append(dict(kwargs))
        return {
            "items": [
                {
                    "entity_id": "kwin_001",
                    "stock_code": "000001",
                    "metadata": {"stock_name": "平安银行"},
                    "similarity": 0.88,
                }
            ],
            "backend_used": "pgvector",
            "fallback_used": False,
            "fallback_reason": None,
            "active_version": "v1",
            "index_version": "v1",
            "profile_version": "v1",
        }


@pytest.mark.asyncio
async def test_search_kline_pattern_windows_uses_search_vector_collection():
    adapter = _KlineSearchAdapter()

    result = await adapter.search_kline_pattern_windows(
        query_embedding=[0.1] * 20,
        window_size=20,
        vector_method="returns",
        period="daily",
        adjust="",
        version="v1",
        stock_codes=["000001"],
        exclude_stock_code="600519",
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["window_uid"] == "kwin_001"
    assert result[0]["stock_code"] == "000001"
    assert result[0]["similarity"] == 0.88
    assert adapter.search_vector_collection_calls[0]["collection_name"] == "kline_pattern_embeddings"
    assert adapter.search_vector_collection_calls[0]["profile_type"] == "returns|daily||20"
    assert adapter.search_vector_collection_calls[0]["version"] == "v1"


class _SnapshotAnnAdapter(VectorUnifiedMixin):
    def __init__(self):
        self.collection = {
            "collection_name": "stock_profile_embeddings",
            "active_version": "snap_profile_v2",
            "metadata": {},
        }
        self.snapshot = {
            "collection_name": "stock_profile_embeddings",
            "index_version": "snap_profile_v2",
            "index_params": {"neighbor_count": 1},
            "metadata": {
                "profile_version": "v2",
                "centroids": [
                    {
                        "bucket_id": "b_0000",
                        "centroid": [1.0] + [0.0] * 10,
                        "neighbors": ["b_0001"],
                    },
                    {
                        "bucket_id": "b_0001",
                        "centroid": [0.0, 1.0] + [0.0] * 9,
                        "neighbors": ["b_0000"],
                    },
                ],
            },
        }
        self.profile_search_called = False

    @staticmethod
    def _decode_json_field(value, default):
        return value if value is not None else default

    async def get_vector_collection(self, collection_name):
        assert collection_name == "stock_profile_embeddings"
        return dict(self.collection)

    async def list_vector_index_snapshots(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["index_version"] == "snap_profile_v2"
        return [dict(self.snapshot)]

    async def search_vector_index_items_by_embedding(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["index_version"] == "snap_profile_v2"
        assert kwargs["profile_type"] == "both"
        assert kwargs["bucket_ids"] == ["b_0000", "b_0001"]
        return [
            {
                "entity_id": "000001|both",
                "stock_code": "000001",
                "profile_type": "both",
                "metadata": {"stock_name": "平安银行"},
                "similarity": 0.9512,
            }
        ]

    async def search_vector_profiles_by_embedding(self, **kwargs):
        self.profile_search_called = True
        raise AssertionError("snapshot ANN hit should not fall back to profile search")


@pytest.mark.asyncio
async def test_search_vector_collection_prefers_snapshot_index_items():
    adapter = _SnapshotAnnAdapter()

    result = await adapter.search_vector_collection(
        collection_name="stock_profile_embeddings",
        query_embedding=[0.1] * 11,
        profile_type="both",
        stock_codes=["000001", "000002"],
        limit=2,
        metric="cosine",
    )

    assert result["backend_used"] == "pgvector_index_item"
    assert result["fallback_used"] is False
    assert result["profile_version"] == "v2"
    assert result["index_version"] == "snap_profile_v2"
    assert result["query_bucket_id"] == "b_0000"
    assert result["candidate_bucket_ids"] == ["b_0000", "b_0001"]
    assert result["items"][0]["entity_id"] == "000001|both"
    assert adapter.profile_search_called is False


class _ExactPrunedAdapter(VectorUnifiedMixin):
    def __init__(self):
        self.collection = {
            "collection_name": "stock_profile_embeddings",
            "active_version": "snap_profile_v2",
            "metadata": {},
        }
        self.snapshot = {
            "collection_name": "stock_profile_embeddings",
            "index_version": "snap_profile_v2",
            "index_params": {"neighbor_count": 1},
            "metadata": {
                "profile_version": "v2",
                "centroids": [
                    {
                        "bucket_id": "b_0000",
                        "centroid": [1.0] + [0.0] * 10,
                        "neighbors": ["b_0001"],
                    },
                    {
                        "bucket_id": "b_0001",
                        "centroid": [0.0, 1.0] + [0.0] * 9,
                        "neighbors": ["b_0000"],
                    },
                ],
            },
        }

    @staticmethod
    def _decode_json_field(value, default):
        return value if value is not None else default

    async def get_vector_collection(self, collection_name):
        assert collection_name == "stock_profile_embeddings"
        return dict(self.collection)

    async def list_vector_index_snapshots(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["index_version"] == "snap_profile_v2"
        return [dict(self.snapshot)]

    async def search_vector_index_items_by_embedding(self, **kwargs):
        assert kwargs["bucket_ids"] == ["b_0000", "b_0001"]
        return []

    async def search_vector_profiles_by_embedding(self, **kwargs):
        assert kwargs["version"] == "v2"
        return []

    async def list_vector_index_items(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["index_version"] == "snap_profile_v2"
        assert kwargs["bucket_ids"] == ["b_0000", "b_0001"]
        assert kwargs["profile_type"] == "both"
        assert kwargs["stock_codes"] == ["000001", "000002"]
        assert kwargs["entity_ids"] == ["000001|both", "000002|both"]
        assert kwargs["exclude_stock_code"] == "600519"
        assert kwargs["exclude_entity_id"] == "000002|both"
        return [
            {
                "entity_id": "000001|both",
                "stock_code": "000001",
                "profile_type": "both",
                "embedding": [1.0] + [0.0] * 10,
                "metadata": {"stock_name": "平安银行"},
            }
        ]


@pytest.mark.asyncio
async def test_search_vector_collection_pushes_exact_fallback_filters_into_sql():
    adapter = _ExactPrunedAdapter()

    result = await adapter.search_vector_collection(
        collection_name="stock_profile_embeddings",
        query_embedding=[0.1] * 11,
        profile_type="both",
        stock_codes=["000001", "000002"],
        entity_ids=["000001|both", "000002|both"],
        exclude_stock_code="600519",
        exclude_entity_id="000002|both",
        limit=2,
        metric="cosine",
    )

    assert result["backend_used"] == "exact_json"
    assert result["fallback_used"] is True
    assert result["items"][0]["entity_id"] == "000001|both"

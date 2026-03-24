from __future__ import annotations

import pytest

from akshare_mcp.services.unified_vector_benchmark import benchmark_vector_collection_search
from akshare_mcp.storage.timescaledb.vector_unified import VectorUnifiedMixin


class _BenchmarkDb(VectorUnifiedMixin):
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
                    {"bucket_id": "b_0000", "centroid": [1.0, 0.0], "neighbors": ["b_0001"]},
                    {"bucket_id": "b_0001", "centroid": [0.70710678, 0.70710678], "neighbors": ["b_0000"]},
                    {"bucket_id": "b_0002", "centroid": [0.0, 1.0], "neighbors": ["b_0001"]},
                ],
            },
        }
        self.saved_snapshots: list[dict] = []
        self.rows = [
            {"entity_id": "A", "stock_code": "600001", "profile_type": "both", "bucket_id": "b_0000", "embedding": [1.0, 0.0]},
            {"entity_id": "B", "stock_code": "600002", "profile_type": "both", "bucket_id": "b_0000", "embedding": [0.98, 0.2]},
            {"entity_id": "C", "stock_code": "600003", "profile_type": "both", "bucket_id": "b_0001", "embedding": [0.7, 0.7]},
            {"entity_id": "D", "stock_code": "600004", "profile_type": "both", "bucket_id": "b_0001", "embedding": [0.6, 0.8]},
            {"entity_id": "E", "stock_code": "600005", "profile_type": "both", "bucket_id": "b_0002", "embedding": [0.0, 1.0]},
            {"entity_id": "F", "stock_code": "600006", "profile_type": "both", "bucket_id": "b_0002", "embedding": [0.1, 0.99]},
        ]
        for row in self.rows:
            row["embedding"] = self._normalize_embedding(row["embedding"])

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

    async def list_vector_index_items(self, **kwargs):
        assert kwargs["collection_name"] == "stock_profile_embeddings"
        assert kwargs["index_version"] == "snap_profile_v2"
        assert kwargs["profile_type"] == "both"
        return [dict(row) for row in self.rows[: int(kwargs.get("limit") or len(self.rows))]]

    async def save_vector_index_snapshot(self, snapshot):
        item = dict(snapshot)
        self.saved_snapshots.append(item)
        self.snapshot = dict(item)
        return dict(item)

    async def search_vector_collection(self, **kwargs):
        query_embedding = list(kwargs["query_embedding"] or [])
        exclude_entity_id = str(kwargs.get("exclude_entity_id") or "").strip()
        query_bucket_id, candidate_bucket_ids = self._resolve_query_buckets(self.snapshot, query_embedding)
        candidate_rows = [
            dict(row)
            for row in self.rows
            if row["entity_id"] != exclude_entity_id and row["bucket_id"] in candidate_bucket_ids
        ]
        candidate_rows.sort(
            key=lambda row: self._vector_similarity(query_embedding, row["embedding"], metric="cosine"),
            reverse=True,
        )
        return {
            "items": [
                {
                    **row,
                    "similarity": self._vector_similarity(query_embedding, row["embedding"], metric="cosine"),
                }
                for row in candidate_rows[: int(kwargs.get("limit") or 10)]
            ],
            "backend_used": "pgvector_index_item",
            "fallback_used": False,
            "fallback_reason": None,
            "profile_version": "v2",
            "index_version": "snap_profile_v2",
            "query_bucket_id": query_bucket_id,
            "candidate_bucket_ids": candidate_bucket_ids,
        }


@pytest.mark.asyncio
async def test_benchmark_vector_collection_search_reports_quality_latency_and_pruning():
    db = _BenchmarkDb()

    result = await benchmark_vector_collection_search(
        db,
        collection_name="stock_profile_embeddings",
        profile_type="both",
        sample_size=3,
        top_k=2,
        limit_profiles=20,
    )

    assert result["status"] == "completed"
    assert result["collection_name"] == "stock_profile_embeddings"
    assert result["index_version"] == "snap_profile_v2"
    assert result["universe_source"] == "vector_index_items"
    assert result["backend_used_counts"]["pgvector_index_item"] == 3
    assert result["ann_backend_only_query_count"] == 3
    assert result["retrieval_quality"]["recall_at_k"] >= 0.99
    assert result["retrieval_quality"]["ndcg_at_k"] >= 0.99
    assert result["coarse_pruning_query_count"] == 3
    assert result["coarse_pruning"]["avg_candidate_ratio"] is not None
    assert result["coarse_pruning"]["avg_candidate_ratio"] < 1.0
    assert result["latency_ms"]["exact_p95"] >= 0.0
    assert result["latency_ms"]["ann_p95"] >= 0.0
    assert result["benchmark_persisted"] is True
    assert db.saved_snapshots[-1]["metrics"]["benchmark"]["retrieval_quality"]["recall_at_k"] >= 0.99
    assert result["queries"][0]["candidate_bucket_ids"]

import pytest

from akshare_mcp.services.vector_platform import StrategyVectorPlatform


class _VectorAuditDb:
    def __init__(self, *, pgvector_enabled: bool):
        self._pgvector_enabled = pgvector_enabled

    def supports_pgvector(self):
        return self._pgvector_enabled

    async def get_strategy_vector_health(self, **_kwargs):
        return {
            "backend": "index",
            "counts": {"profiles": 1},
            "versions": [],
        }


@pytest.mark.asyncio
async def test_search_similar_marks_backend_mismatch_as_fallback(monkeypatch):
    platform = StrategyVectorPlatform()
    platform.preferred_backend = "pgvector"
    db = _VectorAuditDb(pgvector_enabled=False)

    async def _fake_active_index(_db, _index_name="strategy_behavior", index_version=None):
        return {
            "index_name": "strategy_behavior",
            "index_version": index_version or "v1",
            "backend": "index",
            "status": "active",
            "source": "snapshot",
        }

    async def _fake_ann_search(*_args, **_kwargs):
        return [
            {
                "strategy_id": "sid_peer",
                "backend": "index",
                "index_name": "strategy_behavior",
                "index_version": "v1",
                "similarity": 0.91,
            }
        ]

    async def _fake_find_similar(*_args, **_kwargs):
        raise AssertionError("fallback vector search should not run when ANN has rows")

    monkeypatch.setattr(platform, "get_active_index", _fake_active_index)
    monkeypatch.setattr(platform, "ann_search_profiles", _fake_ann_search)
    monkeypatch.setattr(platform, "find_similar_profiles", _fake_find_similar)

    result = await platform.search_similar(db, "sid_query", index_version="v1")

    assert result["backend_requested"] == "pgvector"
    assert result["backend_used"] == "index"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "preferred_backend_unavailable"
    assert result["production_backend_standard"] == "pgvector_with_observable_fallback"
    assert result["fallback_allowed"] is True
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_health_check_marks_backend_mismatch_as_fallback(monkeypatch):
    platform = StrategyVectorPlatform()
    platform.preferred_backend = "pgvector"
    db = _VectorAuditDb(pgvector_enabled=False)

    async def _fake_active_index(_db, index_name="strategy_behavior", index_version=None):
        del index_name, index_version
        return {
            "index_name": "strategy_behavior",
            "index_version": "v_health",
            "backend": "index",
            "status": "active",
            "source": "snapshot",
        }

    monkeypatch.setattr(platform, "get_active_index", _fake_active_index)

    result = await platform.health_check(db, index_name="strategy_behavior")

    assert result["backend_requested"] == "pgvector"
    assert result["backend_used"] == "index"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "preferred_backend_unavailable"
    assert result["production_backend_standard"] == "pgvector_with_observable_fallback"
    assert result["fallback_allowed"] is True
    assert result["latency_ms"] >= 0

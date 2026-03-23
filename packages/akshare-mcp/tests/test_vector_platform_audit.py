import pytest
import numpy as np

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


@pytest.mark.asyncio
async def test_build_strategy_profile_handles_numpy_panels_for_text_embedding(monkeypatch):
    import strategy_factory

    class _EmbeddingService:
        def __init__(self):
            self.config = type("Cfg", (), {"provider": "openai_compatible", "model": "text-embedding-3-small"})()
            self.captured_text = ""

        def is_enabled(self):
            return True

        async def embed_text(self, text: str):
            self.captured_text = text
            return [0.1, 0.2, 0.3]

    class _ProfileDb:
        def __init__(self):
            self.saved_profile = None
            self.saved_registry = None

        def supports_pgvector(self):
            return False

        async def save_strategy_vector_profile(self, payload):
            self.saved_profile = dict(payload)
            return dict(payload)

        async def save_vector_index_registry(self, payload):
            self.saved_registry = dict(payload)
            return dict(payload)

    async def _fake_build_strategy_panels(*_args, **_kwargs):
        return {
            "strategy_returns": np.linspace(0.001, 0.04, 40, dtype=np.float64),
            "holdings": [{"code": "600519", "weight": 0.4}],
            "factor_panel": np.ones((40, 3), dtype=np.float64),
            "return_panel": np.full((40, 3), 0.01, dtype=np.float64),
        }

    monkeypatch.setattr(strategy_factory, "build_strategy_panels", _fake_build_strategy_panels)

    platform = StrategyVectorPlatform()
    platform.text_embedding_service = _EmbeddingService()
    db = _ProfileDb()

    profile = await platform.build_strategy_profile(
        db,
        {"id": "sid_numpy", "name": "NumPy Profile", "strategy_type": "momentum", "params": {"lookback": 20}},
        vector_method="text_embedding",
    )

    assert profile is not None
    assert db.saved_profile is not None
    assert db.saved_profile["vector_dim"] == 3
    assert "策略文本画像" in platform.text_embedding_service.captured_text
    assert "因子面板形状: 40x3" in platform.text_embedding_service.captured_text
    assert "收益面板形状: 40x3" in platform.text_embedding_service.captured_text


@pytest.mark.asyncio
async def test_build_strategy_profile_falls_back_when_text_embedding_request_fails(monkeypatch):
    import strategy_factory

    class _FlakyEmbeddingService:
        def __init__(self):
            self.config = type("Cfg", (), {"provider": "openai_compatible", "model": "text-embedding-3-large"})()

        def is_enabled(self):
            return True

        async def embed_text(self, _text: str):
            raise RuntimeError("embedding gateway unavailable")

    class _ProfileDb:
        def __init__(self):
            self.saved_profile = None
            self.saved_registry = None

        def supports_pgvector(self):
            return False

        async def save_strategy_vector_profile(self, payload):
            self.saved_profile = dict(payload)
            return dict(payload)

        async def save_vector_index_registry(self, payload):
            self.saved_registry = dict(payload)
            return dict(payload)

    async def _fake_build_strategy_panels(*_args, **_kwargs):
        return {
            "strategy_returns": np.linspace(0.001, 0.04, 40, dtype=np.float64),
            "holdings": [{"code": "600519", "weight": 0.4}],
            "factor_panel": np.ones((40, 3), dtype=np.float64),
            "return_panel": np.full((40, 3), 0.01, dtype=np.float64),
        }

    monkeypatch.setattr(strategy_factory, "build_strategy_panels", _fake_build_strategy_panels)

    platform = StrategyVectorPlatform()
    platform.text_embedding_service = _FlakyEmbeddingService()
    monkeypatch.setattr(platform.engine, "kline_to_vector", lambda _klines, _method: np.asarray([0.2, 0.4, 0.6]))
    db = _ProfileDb()

    profile = await platform.build_strategy_profile(
        db,
        {"id": "sid_fallback", "name": "Fallback Profile", "strategy_type": "momentum", "params": {"lookback": 20}},
        vector_method="text_embedding",
    )

    assert profile is not None
    assert db.saved_profile is not None
    assert db.saved_profile["vector_method"] == "price_volume"
    assert db.saved_registry["vector_method"] == "price_volume"
    assert db.saved_profile["metadata"]["requested_vector_method"] == "text_embedding"
    assert db.saved_profile["metadata"]["effective_vector_method"] == "price_volume"
    assert db.saved_profile["metadata"]["resolved_vector_method"] == "price_volume"
    assert db.saved_profile["metadata"]["fallback_used"] is True
    assert db.saved_profile["metadata"]["fallback_reason"] == "text_embedding_request_failed"
    assert db.saved_profile["metadata"]["fallback_error_type"] == "RuntimeError"

from __future__ import annotations

import math

import httpx
import pytest

from akshare_mcp.services.text_embedding import (
    StrategyTextEmbeddingConfig,
    StrategyTextEmbeddingError,
    StrategyTextEmbeddingService,
)


@pytest.mark.asyncio
async def test_text_embedding_uses_hash_fallback_when_provider_not_configured():
    service = StrategyTextEmbeddingService(
        StrategyTextEmbeddingConfig(
            enabled=False,
            provider="openai_compatible",
            allow_hash_fallback=True,
            hash_dimensions=64,
        )
    )
    try:
        assert service.is_enabled() is True
        assert service.prefers_text_embedding_default() is False

        vector = await service.embed_text("向量数据库 coarse pruning 基线")

        assert len(vector) == 64
        assert math.isclose(math.sqrt(sum(item * item for item in vector)), 1.0, rel_tol=1e-6)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_text_embedding_retries_transient_gateway_routing_errors():
    service = StrategyTextEmbeddingService(
        StrategyTextEmbeddingConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://embedding.example.test/v1",
            api_key="test-key",
            model="text-embedding-3-small",
            allow_hash_fallback=False,
            retry_count=2,
            retry_backoff_sec=0.0,
        )
    )

    def _response(status_code: int, payload: dict) -> httpx.Response:
        request = httpx.Request("POST", "https://embedding.example.test/v1/embeddings")
        return httpx.Response(status_code, request=request, json=payload)

    class _FakeClient:
        def __init__(self):
            self.is_closed = False
            self.calls = 0
            self.responses = [
                _response(
                    400,
                    {
                        "error": {
                            "message": "Unknown model: text-embedding-3-small-global",
                            "type": "upstream_error",
                            "code": "unknown_model",
                        }
                    },
                ),
                _response(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "object": "embedding",
                                "index": 0,
                                "embedding": [3.0, 4.0],
                            }
                        ],
                    },
                ),
            ]

        async def post(self, *_args, **_kwargs):
            response = self.responses[min(self.calls, len(self.responses) - 1)]
            self.calls += 1
            return response

        async def aclose(self):
            self.is_closed = True

    fake_client = _FakeClient()
    service._client = fake_client
    try:
        vector = await service.embed_text("retry transient gateway routing")
        assert fake_client.calls == 2
        assert math.isclose(vector[0], 0.6, rel_tol=1e-6)
        assert math.isclose(vector[1], 0.8, rel_tol=1e-6)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_text_embedding_smoke_check_updates_service_status():
    service = StrategyTextEmbeddingService(
        StrategyTextEmbeddingConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://embedding.example.test/v1",
            api_key="test-key",
            model="text-embedding-3-small",
            allow_hash_fallback=False,
            retry_count=0,
            smoke_check_enabled=True,
            smoke_check_ttl_sec=300.0,
        )
    )

    class _FakeClient:
        def __init__(self):
            self.is_closed = False
            self.calls = 0

        async def post(self, *_args, **_kwargs):
            self.calls += 1
            request = httpx.Request("POST", "https://embedding.example.test/v1/embeddings")
            return httpx.Response(
                200,
                request=request,
                json={
                    "object": "list",
                    "data": [
                        {
                            "object": "embedding",
                            "index": 0,
                            "embedding": [1.0, 2.0, 2.0],
                        }
                    ],
                },
            )

        async def aclose(self):
            self.is_closed = True

    fake_client = _FakeClient()
    service._client = fake_client
    try:
        smoke = await service.smoke_check(force=True)
        status = service.status()
        cached = await service.smoke_check(force=False)

        assert smoke["status"] == "passed"
        assert smoke["vector_length"] == 3
        assert status["ready"] is True
        assert status["health_status"] == "ready"
        assert status["request_count"] == 1
        assert status["success_count"] == 1
        assert status["last_smoke_check_ok_at"] is not None
        assert cached["status"] == "cached_success"
        assert fake_client.calls == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_text_embedding_raises_when_hash_fallback_is_disabled():
    service = StrategyTextEmbeddingService(
        StrategyTextEmbeddingConfig(
            enabled=False,
            provider="openai_compatible",
            allow_hash_fallback=False,
        )
    )
    try:
        assert service.is_enabled() is False
        with pytest.raises(StrategyTextEmbeddingError, match="provider not configured"):
            await service.embed_text("no fallback")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_text_embedding_rebuilds_http_client_after_close(monkeypatch):
    service = StrategyTextEmbeddingService(
        StrategyTextEmbeddingConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://embedding.example.test/v1",
            api_key="test-key",
            model="text-embedding-3-small",
            allow_hash_fallback=False,
        )
    )
    try:
        original_client = service._client
        await service.close()

        assert service.is_closed() is True

        captured = {}

        async def _fake_embed_openai(normalized: str, *, model: str):
            captured["normalized"] = normalized
            captured["model"] = model
            captured["client"] = service._client
            return [3.0, 4.0]

        monkeypatch.setattr(service, "_embed_openai_compatible", _fake_embed_openai)

        vector = await service.embed_text("  rebuild the embedding client  ")

        assert service.is_closed() is False
        assert service._client is not None
        assert service._client is not original_client
        assert captured["normalized"] == "rebuild the embedding client"
        assert captured["model"] == "text-embedding-3-small"
        assert captured["client"] is service._client
        assert math.isclose(vector[0], 0.6, rel_tol=1e-6)
        assert math.isclose(vector[1], 0.8, rel_tol=1e-6)
    finally:
        await service.close()

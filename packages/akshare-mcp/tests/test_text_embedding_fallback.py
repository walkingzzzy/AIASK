from __future__ import annotations

import math

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

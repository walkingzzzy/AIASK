"""文本 embedding 服务（OpenAI-compatible）。"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from ..env_loader import load_mcp_env


class StrategyTextEmbeddingError(RuntimeError):
    pass


@dataclass
class StrategyTextEmbeddingConfig:
    enabled: bool = False
    provider: str = 'openai_compatible'
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    timeout_sec: float = 20.0
    connect_timeout_sec: float = 8.0
    write_timeout_sec: float = 10.0
    pool_timeout_sec: float = 5.0
    max_text_chars: int = 6000

    @classmethod
    def from_env(cls) -> 'StrategyTextEmbeddingConfig':
        load_mcp_env(override=False, only_prefixes=('STRATEGY_EMBEDDING_', 'STRATEGY_LLM_'))
        enabled_value = str(
            os.getenv('STRATEGY_EMBEDDING_ENABLED', os.getenv('STRATEGY_LLM_ENABLED', '0')) or '0'
        ).strip().lower()
        timeout_sec = float(
            os.getenv('STRATEGY_EMBEDDING_TIMEOUT_SEC', os.getenv('STRATEGY_LLM_TIMEOUT_SEC', '20')) or 20
        )
        return cls(
            enabled=enabled_value in {'1', 'true', 'yes', 'on'},
            provider=str(os.getenv('STRATEGY_EMBEDDING_PROVIDER', os.getenv('STRATEGY_LLM_PROVIDER', 'openai_compatible')) or 'openai_compatible').strip(),
            base_url=str(os.getenv('STRATEGY_EMBEDDING_BASE_URL', os.getenv('STRATEGY_LLM_BASE_URL', '')) or '').strip(),
            api_key=str(os.getenv('STRATEGY_EMBEDDING_API_KEY', os.getenv('STRATEGY_LLM_API_KEY', '')) or '').strip(),
            model=str(os.getenv('STRATEGY_EMBEDDING_MODEL', os.getenv('STRATEGY_LLM_EMBEDDING_MODEL', 'text-embedding-3-small')) or '').strip(),
            timeout_sec=timeout_sec,
            connect_timeout_sec=float(os.getenv('STRATEGY_EMBEDDING_CONNECT_TIMEOUT_SEC', os.getenv('STRATEGY_LLM_CONNECT_TIMEOUT_SEC', str(min(timeout_sec, 8.0)))) or min(timeout_sec, 8.0)),
            write_timeout_sec=float(os.getenv('STRATEGY_EMBEDDING_WRITE_TIMEOUT_SEC', os.getenv('STRATEGY_LLM_WRITE_TIMEOUT_SEC', str(min(timeout_sec, 10.0)))) or min(timeout_sec, 10.0)),
            pool_timeout_sec=float(os.getenv('STRATEGY_EMBEDDING_POOL_TIMEOUT_SEC', os.getenv('STRATEGY_LLM_POOL_TIMEOUT_SEC', str(min(timeout_sec, 5.0)))) or min(timeout_sec, 5.0)),
            max_text_chars=max(512, int(os.getenv('STRATEGY_EMBEDDING_MAX_TEXT_CHARS', '6000') or 6000)),
        )


class StrategyTextEmbeddingService:
    def __init__(self, config: Optional[StrategyTextEmbeddingConfig] = None):
        self.config = config or StrategyTextEmbeddingConfig.from_env()
        self._cache: dict[str, list[float]] = {}
        self._client = httpx.AsyncClient(follow_redirects=True, http2=False)

    async def close(self) -> None:
        """关闭共享 HTTP 连接池。"""
        try:
            await self._client.aclose()
        except Exception:
            pass

    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.config.base_url and self.config.api_key and self.config.model)

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip('/')
        if base.endswith('/embeddings'):
            return base
        return f'{base}/embeddings'

    def _timeout(self) -> httpx.Timeout:
        timeout_sec = max(float(self.config.timeout_sec or 20.0), 5.0)
        connect_timeout = max(1.0, min(float(self.config.connect_timeout_sec or timeout_sec), timeout_sec))
        write_timeout = max(1.0, min(float(self.config.write_timeout_sec or timeout_sec), timeout_sec))
        pool_timeout = max(1.0, min(float(self.config.pool_timeout_sec or timeout_sec), timeout_sec))
        return httpx.Timeout(connect=connect_timeout, read=timeout_sec, write=write_timeout, pool=pool_timeout)

    def _normalize_text(self, text: str) -> str:
        normalized = ' '.join(str(text or '').strip().split())
        max_chars = max(256, int(self.config.max_text_chars or 6000))
        return normalized[:max_chars]

    async def embed_text(self, text: str, *, model: Optional[str] = None) -> list[float]:
        normalized = self._normalize_text(text)
        if not normalized:
            raise StrategyTextEmbeddingError('embedding text is empty')
        if not self.is_enabled():
            raise StrategyTextEmbeddingError('text embedding provider not configured')
        resolved_model = str(model or self.config.model or '').strip()
        cache_key = hashlib.sha1(f'{resolved_model}\n{normalized}'.encode('utf-8')).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached)
        headers = {
            'Authorization': f'Bearer {self.config.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        payload = {
            'model': resolved_model,
            'input': normalized,
            'encoding_format': 'float',
        }
        response = await self._client.post(self._endpoint(), headers=headers, json=payload, timeout=self._timeout())
        response.raise_for_status()
        body = response.json()
        rows = list(body.get('data') or []) if isinstance(body, dict) else []
        if not rows:
            raise StrategyTextEmbeddingError('embedding response missing data')
        embedding = rows[0].get('embedding') if isinstance(rows[0], dict) else None
        if not isinstance(embedding, list) or not embedding:
            raise StrategyTextEmbeddingError('embedding response missing vector')
        values = [float(item) for item in embedding]
        self._cache[cache_key] = values
        return list(values)


_text_embedding_service: Optional[StrategyTextEmbeddingService] = None


def get_strategy_text_embedding_service() -> StrategyTextEmbeddingService:
    global _text_embedding_service
    if _text_embedding_service is None:
        _text_embedding_service = StrategyTextEmbeddingService()
    return _text_embedding_service

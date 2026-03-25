"""Text embedding service with multiple provider backends."""

from __future__ import annotations

import asyncio
import hashlib
import math
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
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    local_model_path: str = ""
    timeout_sec: float = 20.0
    connect_timeout_sec: float = 8.0
    write_timeout_sec: float = 10.0
    pool_timeout_sec: float = 5.0
    max_text_chars: int = 6000
    normalize_embeddings: bool = True
    hash_dimensions: int = 256
    allow_hash_fallback: bool = True

    @classmethod
    def from_env(cls) -> "StrategyTextEmbeddingConfig":
        load_mcp_env(override=False, only_prefixes=("STRATEGY_EMBEDDING_", "STRATEGY_LLM_"))

        def _env_text(name: str, fallback: str = "", default: str = "") -> str:
            raw = str(os.getenv(name, "") or "").strip()
            if raw:
                return raw
            if fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
                if raw:
                    return raw
            return str(default or "").strip()

        def _env_bool(name: str, fallback: str = "", default: bool = False) -> bool:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return bool(default)
            return raw.lower() in {"1", "true", "yes", "on"}

        def _env_float(name: str, fallback: str = "", default: float = 20.0) -> float:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return float(default)
            try:
                return float(raw)
            except Exception:
                return float(default)

        def _env_int(name: str, fallback: str = "", default: int = 256) -> int:
            raw = str(os.getenv(name, "") or "").strip()
            if not raw and fallback:
                raw = str(os.getenv(fallback, "") or "").strip()
            if not raw:
                return int(default)
            try:
                return int(raw)
            except Exception:
                return int(default)

        enabled_value = _env_bool("STRATEGY_EMBEDDING_ENABLED", "STRATEGY_LLM_ENABLED", False)
        timeout_sec = _env_float("STRATEGY_EMBEDDING_TIMEOUT_SEC", "STRATEGY_LLM_TIMEOUT_SEC", 20.0)
        provider = _env_text("STRATEGY_EMBEDDING_PROVIDER", "STRATEGY_LLM_PROVIDER", "openai_compatible").lower()
        return cls(
            enabled=enabled_value,
            provider=provider or "openai_compatible",
            base_url=_env_text("STRATEGY_EMBEDDING_BASE_URL", "STRATEGY_LLM_BASE_URL"),
            api_key=_env_text("STRATEGY_EMBEDDING_API_KEY", "STRATEGY_LLM_API_KEY"),
            model=_env_text("STRATEGY_EMBEDDING_MODEL", "STRATEGY_LLM_EMBEDDING_MODEL", "text-embedding-3-small"),
            local_model_path=_env_text("STRATEGY_EMBEDDING_LOCAL_MODEL_PATH", default=""),
            timeout_sec=timeout_sec,
            connect_timeout_sec=_env_float("STRATEGY_EMBEDDING_CONNECT_TIMEOUT_SEC", "STRATEGY_LLM_CONNECT_TIMEOUT_SEC", min(timeout_sec, 8.0)),
            write_timeout_sec=_env_float("STRATEGY_EMBEDDING_WRITE_TIMEOUT_SEC", "STRATEGY_LLM_WRITE_TIMEOUT_SEC", min(timeout_sec, 10.0)),
            pool_timeout_sec=_env_float("STRATEGY_EMBEDDING_POOL_TIMEOUT_SEC", "STRATEGY_LLM_POOL_TIMEOUT_SEC", min(timeout_sec, 5.0)),
            max_text_chars=max(512, _env_int("STRATEGY_EMBEDDING_MAX_TEXT_CHARS", default=6000)),
            normalize_embeddings=_env_bool("STRATEGY_EMBEDDING_NORMALIZE", default=True),
            hash_dimensions=max(32, min(_env_int("STRATEGY_EMBEDDING_HASH_DIMENSIONS", default=256), 2048)),
            allow_hash_fallback=_env_bool("STRATEGY_EMBEDDING_ALLOW_HASH_FALLBACK", default=True),
        )


class StrategyTextEmbeddingService:
    def __init__(self, config: Optional[StrategyTextEmbeddingConfig] = None):
        self.config = config or StrategyTextEmbeddingConfig.from_env()
        self._cache: dict[str, list[float]] = {}
        self._client = httpx.AsyncClient(follow_redirects=True, http2=False)
        self._sentence_transformer = None

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass
        self._sentence_transformer = None

    def is_enabled(self) -> bool:
        if self._has_ready_provider():
            return True
        return bool(self.config.allow_hash_fallback)

    def prefers_text_embedding_default(self) -> bool:
        return self._has_ready_provider()

    def _has_ready_provider(self) -> bool:
        if not self.config.enabled:
            return False
        provider = str(self.config.provider or "openai_compatible").strip().lower()
        if provider == "openai_compatible":
            return bool(self.config.base_url and self.config.api_key and self.config.model)
        if provider == "ollama":
            return bool(self.config.base_url and self.config.model)
        if provider == "sentence_transformers":
            return bool(self.config.local_model_path or self.config.model)
        if provider == "hash_fallback":
            return True
        return False

    def _resolve_provider(self) -> str:
        provider = str(self.config.provider or "openai_compatible").strip().lower()
        if self._has_ready_provider():
            return provider
        if self.config.allow_hash_fallback:
            return "hash_fallback"
        raise StrategyTextEmbeddingError("text embedding provider not configured")

    def _timeout(self) -> httpx.Timeout:
        timeout_sec = max(float(self.config.timeout_sec or 20.0), 5.0)
        connect_timeout = max(1.0, min(float(self.config.connect_timeout_sec or timeout_sec), timeout_sec))
        write_timeout = max(1.0, min(float(self.config.write_timeout_sec or timeout_sec), timeout_sec))
        pool_timeout = max(1.0, min(float(self.config.pool_timeout_sec or timeout_sec), timeout_sec))
        return httpx.Timeout(connect=connect_timeout, read=timeout_sec, write=write_timeout, pool=pool_timeout)

    def _normalize_text(self, text: str) -> str:
        normalized = " ".join(str(text or "").strip().split())
        max_chars = max(256, int(self.config.max_text_chars or 6000))
        return normalized[:max_chars]

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        if not vector:
            return []
        if not self.config.normalize_embeddings:
            return [float(item) for item in vector]
        norm = math.sqrt(sum(float(item) * float(item) for item in vector))
        if norm <= 1e-12:
            return [float(item) for item in vector]
        return [float(item) / norm for item in vector]

    def _endpoint_openai(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/embeddings"):
            return base
        return f"{base}/embeddings"

    def _endpoint_ollama(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/api/embed") or base.endswith("/api/embeddings"):
            return base
        return f"{base}/api/embed"

    async def _embed_openai_compatible(self, normalized: str, *, model: str) -> list[float]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"model": model, "input": normalized, "encoding_format": "float"}
        response = await self._client.post(self._endpoint_openai(), headers=headers, json=payload, timeout=self._timeout())
        response.raise_for_status()
        body = response.json()
        rows = list(body.get("data") or []) if isinstance(body, dict) else []
        if not rows:
            raise StrategyTextEmbeddingError("embedding response missing data")
        embedding = rows[0].get("embedding") if isinstance(rows[0], dict) else None
        if not isinstance(embedding, list) or not embedding:
            raise StrategyTextEmbeddingError("embedding response missing vector")
        return [float(item) for item in embedding]

    async def _embed_ollama(self, normalized: str, *, model: str) -> list[float]:
        payload = {"model": model, "input": normalized}
        response = await self._client.post(self._endpoint_ollama(), json=payload, timeout=self._timeout())
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            if isinstance(body.get("embeddings"), list) and body.get("embeddings"):
                first = body["embeddings"][0]
                if isinstance(first, list) and first:
                    return [float(item) for item in first]
            if isinstance(body.get("embedding"), list) and body.get("embedding"):
                return [float(item) for item in body.get("embedding")]
        raise StrategyTextEmbeddingError("ollama embedding response missing vector")

    def _load_sentence_transformer(self):
        if self._sentence_transformer is not None:
            return self._sentence_transformer
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise StrategyTextEmbeddingError(f"sentence_transformers unavailable: {exc}") from exc
        model_name = str(self.config.local_model_path or self.config.model or "").strip()
        if not model_name:
            raise StrategyTextEmbeddingError("sentence_transformers requires model/local_model_path")
        self._sentence_transformer = SentenceTransformer(model_name)
        return self._sentence_transformer

    async def _embed_sentence_transformers(self, normalized: str) -> list[float]:
        model = await asyncio.to_thread(self._load_sentence_transformer)
        vector = await asyncio.to_thread(
            model.encode,
            normalized,
            normalize_embeddings=False,
            convert_to_numpy=False,
            show_progress_bar=False,
        )
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        if not isinstance(vector, list) or not vector:
            raise StrategyTextEmbeddingError("sentence_transformers returned empty vector")
        return [float(item) for item in vector]

    def _embed_hash_fallback(self, normalized: str) -> list[float]:
        dims = max(32, int(self.config.hash_dimensions or 256))
        vector = [0.0] * dims
        text = f" {normalized} "
        grams = []
        for size in (2, 3, 4):
            grams.extend(text[idx: idx + size] for idx in range(max(len(text) - size + 1, 0)))
        if not grams:
            grams = [normalized]
        for gram in grams:
            digest = hashlib.sha1(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % dims
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[bucket] += sign
        return vector

    async def embed_text(self, text: str, *, model: Optional[str] = None) -> list[float]:
        normalized = self._normalize_text(text)
        if not normalized:
            raise StrategyTextEmbeddingError("embedding text is empty")
        provider = self._resolve_provider()
        resolved_model = str(model or self.config.model or self.config.local_model_path or "").strip()
        cache_key = hashlib.sha1(f"{provider}\n{resolved_model}\n{normalized}".encode("utf-8")).hexdigest()
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached)
        if provider == "openai_compatible":
            values = await self._embed_openai_compatible(normalized, model=resolved_model)
        elif provider == "ollama":
            values = await self._embed_ollama(normalized, model=resolved_model)
        elif provider == "sentence_transformers":
            values = await self._embed_sentence_transformers(normalized)
        elif provider == "hash_fallback":
            values = self._embed_hash_fallback(normalized)
        else:
            raise StrategyTextEmbeddingError(f"unsupported embedding provider: {provider}")
        normalized_values = self._normalize_vector(values)
        self._cache[cache_key] = normalized_values
        return list(normalized_values)


_text_embedding_service: Optional[StrategyTextEmbeddingService] = None


def get_strategy_text_embedding_service() -> StrategyTextEmbeddingService:
    global _text_embedding_service
    if _text_embedding_service is None:
        _text_embedding_service = StrategyTextEmbeddingService()
    return _text_embedding_service


async def close_strategy_text_embedding_service() -> None:
    global _text_embedding_service
    service = _text_embedding_service
    _text_embedding_service = None
    if service is None:
        return
    await service.close()

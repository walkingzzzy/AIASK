"""策略向量平台：统一画像、持久化索引和 ANN-like 相似检索。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from .text_embedding import get_strategy_text_embedding_service
from .vector_search import VectorSearchEngine

logger = logging.getLogger(__name__)


class StrategyVectorPlatform:
    SUPPORTED_NUMERIC_METHODS = {'price_volume', 'ohlc', 'returns', 'technical'}
    TEXT_EMBEDDING_ALIASES = {'text', 'text_embedding', 'text_embed', 'semantic', 'semantic_text'}
    PRODUCTION_BACKEND_STANDARD = 'pgvector_with_observable_fallback'

    def __init__(self):
        self.engine = VectorSearchEngine(backend='index', allow_fallback=True)
        self.text_embedding_service = get_strategy_text_embedding_service()
        self.preferred_backend = str(os.getenv('STRATEGY_VECTOR_BACKEND') or '').strip().lower()
        self.allow_fallback = str(os.getenv('STRATEGY_VECTOR_ALLOW_FALLBACK', '1')).strip().lower() not in {
            '0', 'false', 'no', 'off'
        }

    def _resolved_preferred_backend(self) -> str:
        requested = str(self.preferred_backend or '').strip().lower()
        if requested in {'pgvector', 'index', 'python'}:
            return requested
        return 'pgvector'

    def _policy_meta(self) -> dict:
        return {
            'production_backend_standard': self.PRODUCTION_BACKEND_STANDARD,
            'fallback_allowed': bool(self.allow_fallback),
        }

    def requested_backend_name(self, db) -> str:
        del db
        return self._resolved_preferred_backend()

    def backend_name(self, db) -> str:
        requested = self.requested_backend_name(db)
        if requested == 'pgvector' and not getattr(db, 'supports_pgvector', lambda: False)():
            if not self.allow_fallback:
                return 'pgvector'
            if hasattr(db, 'get_vector_backend'):
                try:
                    fallback = str(db.get_vector_backend() or '').strip().lower()
                    if fallback in {'index', 'python'}:
                        return fallback
                except Exception:
                    pass
            return str(getattr(self.engine, 'backend', 'index') or 'index')
        if requested in {'pgvector', 'index', 'python'}:
            return requested
        return 'pgvector' if getattr(db, 'supports_pgvector', lambda: False)() else self.engine.backend

    def _build_backend_audit(self, db, started_at: float) -> dict:
        backend_requested = self.requested_backend_name(db)
        backend_used = self.backend_name(db)
        return {
            'backend_requested': backend_requested,
            'backend_used': backend_used,
            'fallback_used': backend_requested != backend_used,
            'fallback_reason': None if backend_requested == backend_used else 'preferred_backend_unavailable',
            'latency_ms': round((time.perf_counter() - started_at) * 1000, 3),
            **self._policy_meta(),
        }

    def _merge_backend_audit(
        self,
        *,
        backend_requested: str,
        backend_used: str,
        started_at: float,
        fallback_reason: Optional[str] = None,
        fallback_used: Optional[bool] = None,
    ) -> dict:
        resolved_fallback_used = (
            bool(fallback_reason) or backend_requested != backend_used
            if fallback_used is None
            else bool(fallback_used or backend_requested != backend_used)
        )
        resolved_reason = fallback_reason
        if resolved_reason is None and backend_requested != backend_used:
            resolved_reason = 'preferred_backend_unavailable'
        return {
            'backend_requested': backend_requested,
            'backend_used': backend_used,
            'fallback_used': resolved_fallback_used,
            'fallback_reason': resolved_reason,
            'latency_ms': round((time.perf_counter() - started_at) * 1000, 3),
            **self._policy_meta(),
        }

    def default_vector_method(self) -> str:
        return 'text_embedding' if getattr(self.text_embedding_service, 'prefers_text_embedding_default', lambda: self.text_embedding_service.is_enabled())() else 'price_volume'

    def resolve_vector_method(self, vector_method: Optional[str]) -> str:
        normalized = str(vector_method or '').strip().lower()
        if not normalized:
            return self.default_vector_method()
        if normalized in self.TEXT_EMBEDDING_ALIASES:
            return 'text_embedding'
        return normalized

    def ensure_vector_method_available(self, vector_method: Optional[str]) -> str:
        resolved = self.resolve_vector_method(vector_method)
        if resolved == 'text_embedding' and not self.text_embedding_service.is_enabled():
            raise RuntimeError('text_embedding requested but provider not configured')
        if resolved not in self.SUPPORTED_NUMERIC_METHODS and resolved != 'text_embedding':
            raise ValueError(f'unsupported vector_method: {resolved}')
        return resolved

    @staticmethod
    def _text_embedding_fallback_method() -> str:
        return 'price_volume'

    @staticmethod
    def _sanitize_collection_part(value: Any, max_len: int = 48) -> str:
        normalized = ''.join(ch.lower() if str(ch).isalnum() else '_' for ch in str(value or '').strip())
        normalized = '_'.join(part for part in normalized.split('_') if part)
        truncated = normalized[: max(8, int(max_len or 48))].strip('_')
        return truncated or 'na'

    @staticmethod
    def _default_strategy_model_id(vector_method: str, vector_dim: int) -> str:
        normalized_method = str(vector_method or 'price_volume').strip().lower() or 'price_volume'
        if normalized_method == 'price_volume' and int(vector_dim or 0) == 120:
            return 'strategy-behavior-v1'
        return f'strategy-{normalized_method}-v1'

    def _resolve_strategy_model_id(
        self,
        *,
        vector_method: str,
        vector_dim: int,
        embedding_meta: Optional[dict] = None,
    ) -> str:
        meta = dict(embedding_meta or {})
        explicit = str(meta.get('model_id') or meta.get('embedding_model') or '').strip()
        return explicit or self._default_strategy_model_id(vector_method, vector_dim)

    @classmethod
    def _strategy_collection_name(
        cls,
        *,
        index_name: str,
        model_id: str,
        vector_dim: int,
        metric: str = 'cosine',
        normalization: str = 'unit',
    ) -> str:
        resolved_index_name = str(index_name or 'strategy_behavior').strip() or 'strategy_behavior'
        base = f'{resolved_index_name}_embeddings'
        resolved_model_id = str(model_id or '').strip() or 'strategy-behavior-v1'
        resolved_metric = str(metric or 'cosine').strip().lower() or 'cosine'
        resolved_normalization = str(normalization or 'unit').strip().lower() or 'unit'
        if (
            resolved_model_id == 'strategy-behavior-v1'
            and int(vector_dim or 0) == 120
            and resolved_metric == 'cosine'
            and resolved_normalization == 'unit'
        ):
            return base
        suffix = '__'.join(
            [
                cls._sanitize_collection_part(resolved_model_id),
                f'd{int(vector_dim or 0)}',
                cls._sanitize_collection_part(resolved_metric, max_len=16),
                cls._sanitize_collection_part(resolved_normalization, max_len=16),
            ]
        )
        return f'{base}__{suffix}'

    @staticmethod
    def _strategy_index_name_from_collection(collection_name: Optional[str], collection: Optional[dict] = None) -> str:
        meta = dict((collection or {}).get('metadata') or {})
        explicit = str(meta.get('index_name') or '').strip()
        if explicit:
            return explicit
        normalized = str(collection_name or '').strip()
        if normalized.endswith('_embeddings'):
            return normalized[: -len('_embeddings')]
        if '_embeddings__' in normalized:
            return normalized.split('_embeddings__', 1)[0]
        return 'strategy_behavior'

    @classmethod
    def _collection_sort_key(cls, collection: dict) -> tuple:
        active_priority = 0 if str(collection.get('active_version') or '').strip() else 1
        updated_at = str(collection.get('updated_at') or collection.get('created_at') or '')
        return (
            active_priority,
            updated_at,
            str(collection.get('collection_name') or ''),
        )

    @staticmethod
    def _pgvector_backend_family(backend_used: Optional[str]) -> str:
        normalized = str(backend_used or '').strip().lower()
        if normalized.startswith('pgvector'):
            return 'pgvector'
        return normalized or 'unavailable'

    @staticmethod
    def _unified_retrieval_mode(backend_used: Optional[str]) -> str:
        normalized = str(backend_used or '').strip().lower()
        if normalized == 'pgvector_index_item':
            return 'unified_pgvector_ann'
        if normalized == 'pgvector_profile':
            return 'unified_pgvector_exact'
        if normalized == 'exact_json':
            return 'unified_exact_json'
        return f'unified_{normalized}' if normalized else 'unified_unknown'

    @staticmethod
    def _signature(strategy: dict, profile_type: str, vector_method: str) -> str:
        payload = {
            'strategy_id': strategy.get('id'),
            'strategy_type': strategy.get('strategy_type'),
            'params': strategy.get('params') or {},
            'profile_type': profile_type,
            'vector_method': vector_method,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    @staticmethod
    def _as_float_array(values: Any) -> np.ndarray:
        if values is None:
            return np.asarray([], dtype=np.float64)
        return np.asarray(values, dtype=np.float64)

    @staticmethod
    def _returns_to_pseudo_klines(series: np.ndarray) -> List[dict]:
        price = 100.0
        rows: List[dict] = []
        for ret in np.asarray(series[-60:], dtype=np.float64):
            open_price = price
            price = open_price * (1 + float(ret))
            rows.append({
                'open': round(open_price, 6),
                'high': round(max(open_price, price), 6),
                'low': round(min(open_price, price), 6),
                'close': round(price, 6),
                'volume': 1.0,
            })
        return rows

    @staticmethod
    def _normalize_embedding(values: Any) -> np.ndarray:
        vector = StrategyVectorPlatform._as_float_array(values)
        if vector.ndim != 1 or len(vector) == 0:
            return np.asarray([], dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            return np.asarray([], dtype=np.float64)
        return vector / norm

    @staticmethod
    def _resolved_index_name(index_name: Optional[str], profile: Optional[dict]) -> str:
        meta = dict((profile or {}).get('metadata') or {})
        return str(index_name or meta.get('index_name') or 'strategy_behavior')

    @staticmethod
    def _resolve_bucket_count(sample_count: int) -> int:
        if sample_count <= 1:
            return 1
        return max(1, min(8, int(round(math.sqrt(sample_count)))))

    @staticmethod
    def _bucket_label(idx: int) -> str:
        return f'bucket_{idx + 1:02d}'

    @staticmethod
    def _summarize_holdings(holdings: Any, limit: int = 5) -> str:
        rows = []
        for item in list(holdings or [])[: max(1, min(int(limit or 5), 10))]:
            if not isinstance(item, dict):
                continue
            code = str(item.get('code') or item.get('symbol') or '').strip()
            if not code:
                continue
            weight = float(item.get('weight') or 0.0)
            rows.append(f'{code}({weight:.2%})')
        return ', '.join(rows) if rows else '无显著持仓'

    @staticmethod
    def _max_drawdown(series: np.ndarray) -> float:
        if len(series) == 0:
            return 0.0
        nav = np.cumprod(1.0 + np.asarray(series, dtype=np.float64))
        peaks = np.maximum.accumulate(nav)
        drawdowns = nav / np.maximum(peaks, 1e-12) - 1.0
        return float(np.min(drawdowns)) if len(drawdowns) else 0.0

    def _build_text_embedding_document(
        self,
        strategy: dict,
        panels: dict,
        *,
        profile_type: str,
        index_name: str,
        index_version: str,
    ) -> str:
        series = self._as_float_array(panels.get('strategy_returns'))
        holdings = list(panels.get('holdings') or [])
        params_text = json.dumps(strategy.get('params') or {}, ensure_ascii=False, sort_keys=True)
        latest = series[-20:] if len(series) >= 20 else series
        recent_returns = ', '.join(f'{float(item):.4f}' for item in latest.tolist()) if len(latest) else '无'
        mean_return = float(np.mean(series)) if len(series) else 0.0
        volatility = float(np.std(series)) if len(series) else 0.0
        recent_5 = float(np.prod(1.0 + series[-5:]) - 1.0) if len(series) >= 5 else float(np.prod(1.0 + series) - 1.0) if len(series) else 0.0
        recent_20 = float(np.prod(1.0 + series[-20:]) - 1.0) if len(series) >= 20 else float(np.prod(1.0 + series) - 1.0) if len(series) else 0.0
        recent_60 = float(np.prod(1.0 + series[-60:]) - 1.0) if len(series) >= 60 else float(np.prod(1.0 + series) - 1.0) if len(series) else 0.0
        positive_ratio = float(np.mean(series > 0)) if len(series) else 0.0
        drawdown = self._max_drawdown(series)
        factor_panel = self._as_float_array(panels.get('factor_panel'))
        return_panel = self._as_float_array(panels.get('return_panel'))
        factor_shape = f'{factor_panel.shape[0]}x{factor_panel.shape[1]}' if factor_panel.ndim == 2 else '0x0'
        return_shape = f'{return_panel.shape[0]}x{return_panel.shape[1]}' if return_panel.ndim == 2 else '0x0'
        return "\n".join([
            '策略文本画像',
            f"策略ID: {strategy.get('id') or 'unknown'}",
            f"策略名称: {strategy.get('name') or strategy.get('strategy_type') or 'unknown'}",
            f"策略类型: {strategy.get('strategy_type') or 'unknown'}",
            f"画像类型: {profile_type}",
            f"索引名称: {index_name}",
            f"索引版本: {index_version}",
            f"参数: {params_text}",
            f"样本持仓: {self._summarize_holdings(holdings)}",
            f"行为序列长度: {int(len(series))}",
            f"因子面板形状: {factor_shape}",
            f"收益面板形状: {return_shape}",
            f"平均单期收益: {mean_return:.6f}",
            f"波动率: {volatility:.6f}",
            f"正收益占比: {positive_ratio:.2%}",
            f"最大回撤: {drawdown:.2%}",
            f"最近5期累计收益: {recent_5:.2%}",
            f"最近20期累计收益: {recent_20:.2%}",
            f"最近60期累计收益: {recent_60:.2%}",
            f"最近收益序列: {recent_returns}",
        ])

    async def _build_embedding(
        self,
        *,
        strategy: dict,
        panels: dict,
        vector_method: str,
        profile_type: str,
        index_name: str,
        index_version: str,
    ) -> tuple[np.ndarray, dict, str]:
        series = panels.get('strategy_returns')
        if series is None or len(series) < 30:
            return np.asarray([], dtype=np.float64), {}, vector_method
        if vector_method == 'text_embedding':
            document = self._build_text_embedding_document(
                strategy,
                panels,
                profile_type=profile_type,
                index_name=index_name,
                index_version=index_version,
            )
            text_meta = {
                'embedding_source': 'strategy_text_profile',
                'embedding_provider': getattr(getattr(self.text_embedding_service, 'config', None), 'provider', 'openai_compatible'),
                'embedding_model': getattr(getattr(self.text_embedding_service, 'config', None), 'model', None),
                'embedding_text_preview': document[:240],
                'embedding_text_hash': hashlib.sha1(document.encode('utf-8')).hexdigest(),
                'sample_length': int(len(series)),
                'pattern_length': int(min(len(series), 60)),
            }
            try:
                embedding = np.asarray(await self.text_embedding_service.embed_text(document), dtype=np.float64)
                return embedding, {
                    **text_meta,
                    'requested_vector_method': 'text_embedding',
                    'resolved_vector_method': 'text_embedding',
                    'fallback_used': False,
                    'fallback_reason': None,
                }, 'text_embedding'
            except Exception as exc:
                fallback_method = self._text_embedding_fallback_method()
                logger.info(
                    'StrategyVectorPlatform text embedding unavailable for %s, fallback to %s: %s',
                    strategy.get('id'),
                    fallback_method,
                    exc.__class__.__name__,
                )
                klines = self._returns_to_pseudo_klines(np.asarray(series, dtype=np.float64))
                fallback_embedding = self.engine.kline_to_vector(klines, fallback_method)
                return np.asarray(fallback_embedding if fallback_embedding is not None else [], dtype=np.float64), {
                    **text_meta,
                    'embedding_source': 'strategy_returns_fallback',
                    'requested_vector_method': 'text_embedding',
                    'resolved_vector_method': fallback_method,
                    'fallback_used': True,
                    'fallback_reason': 'text_embedding_request_failed',
                    'fallback_error_type': exc.__class__.__name__,
                    'fallback_error': str(exc or exc.__class__.__name__)[:240],
                }, fallback_method
        klines = self._returns_to_pseudo_klines(np.asarray(series, dtype=np.float64))
        embedding = self.engine.kline_to_vector(klines, vector_method)
        return np.asarray(embedding if embedding is not None else [], dtype=np.float64), {
            'sample_length': int(len(klines)),
            'pattern_length': int(len(klines)),
            'requested_vector_method': vector_method,
            'resolved_vector_method': vector_method,
            'fallback_used': False,
            'fallback_reason': None,
        }, vector_method

    async def build_strategy_profile(
        self,
        db,
        strategy: dict,
        profile_type: str = 'behavior',
        vector_method: Optional[str] = None,
        metric: str = 'cosine',
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
    ) -> Optional[dict]:
        try:
            from strategy_factory import build_strategy_panels
            started_at = time.perf_counter()

            resolved_vector_method = self.ensure_vector_method_available(vector_method)
            panels = await build_strategy_panels(
                strategy.get('strategy_type') or '',
                strategy.get('params') or {},
                db,
                sample_size=4,
            )
            series = panels.get('strategy_returns')
            if series is None or len(series) < 30:
                return None

            embedding, embedding_meta, effective_vector_method = await self._build_embedding(
                strategy=strategy,
                panels=panels,
                vector_method=resolved_vector_method,
                profile_type=profile_type,
                index_name=index_name,
                index_version=index_version,
            )
            if embedding is None or len(embedding) == 0:
                return None
            vector_dim = int(len(embedding))
            model_id = self._resolve_strategy_model_id(
                vector_method=effective_vector_method,
                vector_dim=vector_dim,
                embedding_meta=embedding_meta,
            )
            collection_name = self._strategy_collection_name(
                index_name=index_name,
                model_id=model_id,
                vector_dim=vector_dim,
                metric=metric,
            )
            backend_audit = self._build_backend_audit(db, started_at)

            profile = await db.save_strategy_vector_profile({
                'strategy_id': strategy.get('id'),
                'profile_type': profile_type,
                'vector_method': effective_vector_method,
                'metric': metric,
                'vector_dim': vector_dim,
                'embedding': embedding.tolist(),
                'signature': self._signature(strategy, profile_type, effective_vector_method),
                'backend': self.backend_name(db),
                'index_name': index_name,
                'index_version': index_version,
                'metadata': {
                    'strategy_type': strategy.get('strategy_type'),
                    'index_name': index_name,
                    'index_version': index_version,
                    'profile_type': profile_type,
                    'requested_vector_method': resolved_vector_method,
                    'effective_vector_method': effective_vector_method,
                    'audit': backend_audit,
                    'unified_collection_name': collection_name,
                    'model_id': model_id,
                    **embedding_meta,
                },
            })
            unified_profile = None
            if hasattr(db, 'save_vector_collection') and hasattr(db, 'save_vector_profile'):
                try:
                    await db.save_vector_collection({
                        'collection_name': collection_name,
                        'entity_family': 'strategy_behavior',
                        'backend': self.backend_name(db),
                        'metric': metric,
                        'model_id': model_id,
                        'vector_dim': vector_dim,
                        'normalization': 'unit',
                        'status': 'active',
                        'metadata': {
                            'domain': 'strategy',
                            'index_name': index_name,
                            'profile_type': profile_type,
                            'vector_method': effective_vector_method,
                        },
                    })
                    unified_profile = await db.save_vector_profile({
                        'collection_name': collection_name,
                        'entity_type': 'strategy',
                        'entity_id': str(strategy.get('id') or ''),
                        'profile_type': profile_type,
                        'model_id': model_id,
                        'vector_dim': vector_dim,
                        'metric': metric,
                        'version': index_version,
                        'signature': self._signature(strategy, profile_type, effective_vector_method),
                        'status': 'active',
                        'embedding': embedding.tolist(),
                        'metadata': {
                            'strategy_type': strategy.get('strategy_type'),
                            'index_name': index_name,
                            'index_version': index_version,
                            'profile_type': profile_type,
                            'requested_vector_method': resolved_vector_method,
                            'effective_vector_method': effective_vector_method,
                            'legacy_profile_id': profile.get('id'),
                            'audit': backend_audit,
                            **embedding_meta,
                        },
                    })
                    if (
                        getattr(db, 'supports_pgvector', lambda: False)()
                        and hasattr(db, 'ensure_vector_profile_pgvector_index')
                    ):
                        await db.ensure_vector_profile_pgvector_index(
                            collection_name=collection_name,
                            version=index_version,
                            vector_dim=vector_dim,
                            profile_type=profile_type,
                            metric=metric,
                        )
                except Exception as exc:
                    logger.warning(
                        'StrategyVectorPlatform.build_strategy_profile unified dual-write failed for %s: %s',
                        strategy.get('id'),
                        exc,
                    )
            await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': self.backend_name(db),
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': effective_vector_method,
                'metric': metric,
                'sample_count': 1,
                'index_version': index_version,
                'metadata': {
                    'last_strategy_id': strategy.get('id'),
                    'requested_vector_method': resolved_vector_method,
                    'effective_vector_method': effective_vector_method,
                    'unified_collection_name': collection_name,
                    'unified_profile_id': (unified_profile or {}).get('id'),
                    'model_id': model_id,
                    'audit': backend_audit,
                },
            })
            return {
                **dict(profile or {}),
                'unified_collection_name': collection_name,
                'unified_profile_id': (unified_profile or {}).get('id'),
                'model_id': model_id,
            }
        except Exception as exc:
            logger.warning('StrategyVectorPlatform.build_strategy_profile failed for %s: %s', strategy.get('id'), exc)
            return None

    async def build_profiles_for_strategies(
        self,
        db,
        strategies: List[dict],
        profile_type: str = 'behavior',
        vector_method: Optional[str] = None,
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
    ) -> dict:
        resolved_vector_method = self.ensure_vector_method_available(vector_method)
        sem = asyncio.Semaphore(max(1, min(4, len(list(strategies or [])) or 1)))

        async def _build_one(strategy: dict) -> Optional[dict]:
            async with sem:
                return await self.build_strategy_profile(
                    db,
                    strategy,
                    profile_type=profile_type,
                    vector_method=resolved_vector_method,
                    index_name=index_name,
                    index_version=index_version,
                )

        built_profiles = await asyncio.gather(*[_build_one(strategy) for strategy in list(strategies or [])])
        items = [profile for profile in built_profiles if profile]
        if items:
            await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': self.backend_name(db),
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': resolved_vector_method,
                'metric': 'cosine',
                'sample_count': len(items),
                'index_version': index_version,
                'metadata': {
                    'profile_ids': [item.get('id') for item in items if item.get('id') is not None],
                },
            })
            if getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'ensure_strategy_vector_profile_pgvector_index'):
                dims = sorted({int(item.get('vector_dim') or len(item.get('embedding') or [])) for item in items if int(item.get('vector_dim') or len(item.get('embedding') or [])) > 0})
                metric = str((items[0] if items else {}).get('metric') or 'cosine')
                for dim in dims:
                    try:
                        await db.ensure_strategy_vector_profile_pgvector_index(
                            index_name=index_name,
                            index_version=index_version,
                            vector_dim=dim,
                            profile_type=profile_type,
                            metric=metric,
                        )
                    except Exception as exc:
                        logger.warning('StrategyVectorPlatform.build_profiles_for_strategies failed to create profile pgvector index: %s', exc)
        return {'count': len(items), 'items': items}

    async def _list_unified_strategy_collections(
        self,
        db,
        *,
        index_name: Optional[str] = None,
    ) -> List[dict]:
        if not hasattr(db, 'list_vector_collections'):
            return []
        try:
            rows = await db.list_vector_collections(entity_family='strategy_behavior', limit=200)
        except Exception:
            return []
        resolved_index_name = str(index_name or '').strip()
        filtered: List[dict] = []
        for row in list(rows or []):
            item = dict(row or {})
            collection_name = str(item.get('collection_name') or '').strip()
            logical_index_name = self._strategy_index_name_from_collection(collection_name, item)
            if resolved_index_name and logical_index_name != resolved_index_name:
                continue
            filtered.append(
                {
                    **item,
                    'collection_name': collection_name,
                    'index_name': logical_index_name,
                }
            )
        filtered.sort(key=self._collection_sort_key)
        return filtered

    async def _load_unified_query_profile(
        self,
        db,
        strategy_id: str,
        *,
        profile_type: str = 'behavior',
        preferred_version: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> Optional[dict]:
        if not hasattr(db, 'list_vector_profiles'):
            return None
        collections = await self._list_unified_strategy_collections(db, index_name=index_name)
        for collection in collections:
            version_candidates: List[Optional[str]] = []
            explicit_version = str(preferred_version or '').strip() or None
            active_version = str(collection.get('active_version') or '').strip() or None
            if explicit_version:
                version_candidates.append(explicit_version)
            if active_version and active_version not in version_candidates:
                version_candidates.append(active_version)
            version_candidates.append(None)
            seen_versions: set[Optional[str]] = set()
            for version in version_candidates:
                if version in seen_versions:
                    continue
                seen_versions.add(version)
                try:
                    rows = await db.list_vector_profiles(
                        collection_name=collection.get('collection_name'),
                        entity_type='strategy',
                        entity_id=strategy_id,
                        profile_type=profile_type,
                        version=version,
                        limit=5,
                    )
                except Exception:
                    rows = []
                if rows:
                    return {
                        **dict(rows[0] or {}),
                        'collection_name': collection.get('collection_name'),
                        '_collection': dict(collection),
                    }
        return None

    async def _select_primary_unified_collection(
        self,
        db,
        *,
        index_name: str,
        profile_type: str,
        version: Optional[str],
    ) -> tuple[Optional[dict], int]:
        if not hasattr(db, 'list_vector_profiles'):
            return None, 0
        collections = await self._list_unified_strategy_collections(db, index_name=index_name)
        best_collection: Optional[dict] = None
        best_count = 0
        for collection in collections:
            try:
                rows = await db.list_vector_profiles(
                    collection_name=collection.get('collection_name'),
                    entity_type='strategy',
                    profile_type=profile_type,
                    version=version,
                    limit=5000,
                )
            except Exception:
                rows = []
            count = len(list(rows or []))
            if count > best_count:
                best_collection = dict(collection)
                best_count = count
        return best_collection, best_count

    def _map_unified_profile_row(
        self,
        row: dict,
        collection: dict,
        *,
        index_name: Optional[str] = None,
    ) -> dict:
        metadata = dict((row or {}).get('metadata') or {})
        resolved_index_name = str(
            index_name
            or metadata.get('index_name')
            or collection.get('index_name')
            or self._strategy_index_name_from_collection(collection.get('collection_name'), collection)
        )
        return {
            'id': row.get('id'),
            'profile_id': row.get('id'),
            'strategy_id': row.get('entity_id'),
            'profile_type': row.get('profile_type') or metadata.get('profile_type'),
            'vector_method': metadata.get('effective_vector_method') or metadata.get('vector_method'),
            'metric': row.get('metric') or collection.get('metric') or 'cosine',
            'vector_dim': row.get('vector_dim'),
            'embedding': row.get('embedding'),
            'signature': row.get('signature') or metadata.get('signature'),
            'backend': self._pgvector_backend_family(collection.get('backend')),
            'index_name': resolved_index_name,
            'index_version': str(row.get('version') or metadata.get('index_version') or ''),
            'collection_name': collection.get('collection_name') or row.get('collection_name'),
            'model_id': row.get('model_id') or collection.get('model_id'),
            'metadata': metadata,
        }

    def _map_unified_snapshot_row(
        self,
        snapshot: dict,
        collection: dict,
        *,
        index_name: Optional[str] = None,
    ) -> dict:
        resolved_index_name = str(
            index_name
            or collection.get('index_name')
            or self._strategy_index_name_from_collection(collection.get('collection_name'), collection)
        )
        metadata = dict((snapshot or {}).get('metadata') or {})
        return {
            'id': snapshot.get('id'),
            'index_name': resolved_index_name,
            'index_version': str(snapshot.get('index_version') or ''),
            'collection_name': collection.get('collection_name'),
            'status': snapshot.get('status'),
            'backend': self._pgvector_backend_family(collection.get('backend') or metadata.get('backend_used')),
            'profile_type': snapshot.get('profile_type'),
            'vector_method': metadata.get('vector_method'),
            'metric': snapshot.get('metric') or collection.get('metric') or 'cosine',
            'vector_dim': snapshot.get('vector_dim') or collection.get('vector_dim'),
            'profile_count': int(snapshot.get('sample_count') or snapshot.get('profile_count') or 0),
            'bucket_count': int(snapshot.get('bucket_count') or 0),
            'model_id': snapshot.get('model_id') or collection.get('model_id'),
            'built_at': snapshot.get('built_at'),
            'activated_at': snapshot.get('activated_at'),
            'metadata': metadata,
            'source': 'unified_snapshot',
        }

    async def list_profiles(
        self,
        db,
        *,
        strategy_id: Optional[str] = None,
        profile_type: Optional[str] = None,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        resolved_limit = max(1, min(int(limit or 20), 200))
        unified_rows: List[dict] = []
        if hasattr(db, 'list_vector_profiles'):
            collections = await self._list_unified_strategy_collections(db, index_name=index_name)
            for collection in collections:
                try:
                    rows = await db.list_vector_profiles(
                        collection_name=collection.get('collection_name'),
                        entity_type='strategy',
                        entity_id=strategy_id,
                        profile_type=profile_type,
                        version=index_version,
                        limit=resolved_limit,
                    )
                except Exception:
                    rows = []
                for row in rows:
                    unified_rows.append(self._map_unified_profile_row(dict(row or {}), dict(collection), index_name=index_name))
        if unified_rows:
            return unified_rows[:resolved_limit]
        if not hasattr(db, 'list_strategy_vector_profiles'):
            return []
        rows = await db.list_strategy_vector_profiles(
            strategy_id=strategy_id,
            profile_type=profile_type,
            index_name=index_name,
            index_version=index_version,
            limit=resolved_limit,
        )
        return list(rows or [])[:resolved_limit]

    async def list_index_snapshots(
        self,
        db,
        *,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        resolved_limit = max(1, min(int(limit or 20), 200))
        unified_rows: List[dict] = []
        if hasattr(db, 'list_vector_index_snapshots'):
            collections = await self._list_unified_strategy_collections(db, index_name=index_name)
            for collection in collections:
                try:
                    rows = await db.list_vector_index_snapshots(
                        collection_name=collection.get('collection_name'),
                        index_version=index_version,
                        status=status,
                        latest_only=False,
                        limit=resolved_limit,
                    )
                except Exception:
                    rows = []
                for row in rows:
                    unified_rows.append(self._map_unified_snapshot_row(dict(row or {}), dict(collection), index_name=index_name))
        if unified_rows:
            unified_rows.sort(
                key=lambda row: (
                    str(row.get('activated_at') or row.get('built_at') or ''),
                    str(row.get('index_version') or ''),
                    int(row.get('id') or 0),
                ),
                reverse=True,
            )
            return unified_rows[:resolved_limit]
        if not hasattr(db, 'list_strategy_vector_index_snapshots'):
            return []
        rows = await db.list_strategy_vector_index_snapshots(
            index_name=index_name,
            index_version=index_version,
            status=status,
            limit=resolved_limit,
        )
        return list(rows or [])[:resolved_limit]

    async def _load_query_profile(
        self,
        db,
        strategy_id: str,
        profile_type: str = 'behavior',
        preferred_version: Optional[str] = None,
    ) -> Optional[dict]:
        if not hasattr(db, 'list_strategy_vector_profiles'):
            return None
        rows = await db.list_strategy_vector_profiles(
            strategy_id=strategy_id,
            profile_type=profile_type,
            index_version=preferred_version,
            limit=20,
        )
        if rows:
            return rows[0]
        if preferred_version:
            fallback = await db.list_strategy_vector_profiles(
                strategy_id=strategy_id,
                profile_type=profile_type,
                limit=20,
            )
            if fallback:
                return fallback[0]
        return None

    def _build_ann_layout(self, profiles: List[dict]) -> tuple[dict, List[dict]]:
        valid: List[tuple[dict, np.ndarray]] = []
        skipped: List[dict] = []
        for profile in profiles:
            embedding = self._normalize_embedding(profile.get('embedding'))
            if len(embedding) == 0:
                skipped.append({'profile_id': profile.get('id'), 'strategy_id': profile.get('strategy_id'), 'reason': 'empty_embedding'})
                continue
            valid.append((profile, embedding))
        if not valid:
            return {
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'centroids': [],
                'metadata': {'skipped_profiles': skipped},
            }, []

        dim_counts: dict[int, int] = {}
        for _, embedding in valid:
            dim_counts[len(embedding)] = dim_counts.get(len(embedding), 0) + 1
        dominant_dim = max(dim_counts.items(), key=lambda item: (item[1], item[0]))[0]
        selected = [(profile, embedding) for profile, embedding in valid if len(embedding) == dominant_dim]
        for profile, embedding in valid:
            if len(embedding) != dominant_dim:
                skipped.append({'profile_id': profile.get('id'), 'strategy_id': profile.get('strategy_id'), 'reason': f'dim_mismatch:{len(embedding)}'})
        if not selected:
            return {
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': dominant_dim,
                'centroids': [],
                'metadata': {'skipped_profiles': skipped},
            }, []

        ordered = sorted(selected, key=lambda item: f"{item[0].get('strategy_id') or ''}:{item[0].get('id') or 0}")
        vectors = np.vstack([embedding for _, embedding in ordered])
        bucket_count = self._resolve_bucket_count(len(ordered))
        if bucket_count == 1:
            centroids = [self._normalize_embedding(np.mean(vectors, axis=0).tolist())]
        else:
            initial = np.linspace(0, len(ordered) - 1, num=bucket_count, dtype=int)
            centroids = [vectors[idx].copy() for idx in initial.tolist()]
            for _ in range(12):
                assignments: List[List[int]] = [[] for _ in range(bucket_count)]
                for row_idx, vector in enumerate(vectors):
                    sims = [self.engine.calculate_similarity(vector, centroid, 'cosine') for centroid in centroids]
                    best_idx = int(max(range(bucket_count), key=lambda idx: sims[idx]))
                    assignments[best_idx].append(row_idx)
                updated: List[np.ndarray] = []
                for centroid_idx, members in enumerate(assignments):
                    if not members:
                        updated.append(centroids[centroid_idx])
                        continue
                    new_centroid = self._normalize_embedding(np.mean(vectors[members], axis=0).tolist())
                    updated.append(new_centroid if len(new_centroid) else centroids[centroid_idx])
                max_shift = max(
                    float(np.linalg.norm(updated[idx] - centroids[idx]))
                    for idx in range(bucket_count)
                ) if bucket_count else 0.0
                centroids = updated
                if max_shift <= 1e-4:
                    break

        bucket_members: List[List[int]] = [[] for _ in range(bucket_count)]
        assignments_meta: List[tuple[int, float]] = []
        for row_idx, vector in enumerate(vectors):
            sims = [self.engine.calculate_similarity(vector, centroid, 'cosine') for centroid in centroids]
            best_idx = int(max(range(bucket_count), key=lambda idx: sims[idx]))
            best_score = float(sims[best_idx])
            bucket_members[best_idx].append(row_idx)
            assignments_meta.append((best_idx, best_score))

        centroid_rows = []
        for centroid_idx, centroid in enumerate(centroids):
            neighbors = []
            if bucket_count > 1:
                sims = []
                for other_idx, other_centroid in enumerate(centroids):
                    if other_idx == centroid_idx:
                        continue
                    sims.append((other_idx, float(self.engine.calculate_similarity(centroid, other_centroid, 'cosine'))))
                sims.sort(key=lambda item: item[1], reverse=True)
                neighbors = [self._bucket_label(item[0]) for item in sims[: min(2, len(sims))]]
            centroid_rows.append({
                'bucket_id': self._bucket_label(centroid_idx),
                'centroid': np.round(centroid, 8).tolist(),
                'size': len(bucket_members[centroid_idx]),
                'neighbors': neighbors,
                'mean_similarity': round(
                    float(np.mean([assignments_meta[row_idx][1] for row_idx in bucket_members[centroid_idx]]) if bucket_members[centroid_idx] else 0.0),
                    6,
                ),
            })

        items: List[dict] = []
        for row_idx, (profile, vector) in enumerate(ordered):
            bucket_idx, coarse_score = assignments_meta[row_idx]
            items.append({
                'profile_id': profile.get('id'),
                'strategy_id': profile.get('strategy_id'),
                'profile_type': profile.get('profile_type') or 'behavior',
                'vector_method': profile.get('vector_method') or 'price_volume',
                'metric': profile.get('metric') or 'cosine',
                'vector_dim': len(vector),
                'bucket_id': self._bucket_label(bucket_idx),
                'coarse_score': round(float(coarse_score), 6),
                'embedding': np.round(vector, 8).tolist(),
                'metadata': {
                    'signature': profile.get('signature'),
                    'backend': profile.get('backend') or self.engine.backend,
                    'source_profile_id': profile.get('id'),
                },
            })

        return {
            'profile_count': len(items),
            'bucket_count': bucket_count,
            'vector_dim': dominant_dim,
            'centroids': centroid_rows,
            'metadata': {
                'skipped_profiles': skipped,
                'dominant_dim': dominant_dim,
                'cluster_sizes': {self._bucket_label(idx): len(members) for idx, members in enumerate(bucket_members)},
            },
        }, items

    async def build_persisted_ann_index(
        self,
        db,
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
        profile_type: str = 'behavior',
        task_run_id: Optional[int] = None,
        source: str = 'vector_governance',
        limit_profiles: int = 5000,
    ) -> dict:
        if not hasattr(db, 'list_strategy_vector_profiles'):
            return {'snapshot': None, 'items_count': 0, 'bucket_count': 0, 'unified_snapshot': None}
        profiles = await db.list_strategy_vector_profiles(
            profile_type=profile_type,
            index_version=index_version,
            limit=max(1, min(int(limit_profiles or 5000), 10000)),
        )
        layout, items = self._build_ann_layout(profiles)
        now = datetime.now(timezone.utc).isoformat()
        snapshot = None
        if hasattr(db, 'save_strategy_vector_index_snapshot'):
            snapshot = await db.save_strategy_vector_index_snapshot({
                'index_name': index_name,
                'index_version': index_version,
                'status': 'building' if items else 'empty',
                'profile_type': profile_type,
                'vector_method': str((profiles[0] if profiles else {}).get('vector_method') or 'price_volume'),
                'metric': str((profiles[0] if profiles else {}).get('metric') or 'cosine'),
                'backend': self.backend_name(db),
                'profile_count': int(layout.get('profile_count') or len(items)),
                'bucket_count': int(layout.get('bucket_count') or 0),
                'vector_dim': int(layout.get('vector_dim') or 0),
                'centroids': layout.get('centroids') or [],
                'metadata': {
                    **dict(layout.get('metadata') or {}),
                    'index_name': index_name,
                    'index_version': index_version,
                    'source': source,
                    'task_run_id': task_run_id,
                },
                'task_run_id': task_run_id,
                'source': source,
                'built_at': now,
                'activated_at': None,
            })
        try:
            if hasattr(db, 'replace_strategy_vector_index_items'):
                await db.replace_strategy_vector_index_items(index_name, index_version, items)
            if items and getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'ensure_strategy_vector_index_item_pgvector_index'):
                try:
                    await db.ensure_strategy_vector_index_item_pgvector_index(
                        index_name=index_name,
                        index_version=index_version,
                        vector_dim=int(layout.get('vector_dim') or 0),
                        metric=str((profiles[0] if profiles else {}).get('metric') or 'cosine'),
                    )
                except Exception as exc:
                    logger.warning('StrategyVectorPlatform.build_persisted_ann_index failed to create pgvector index: %s', exc)
            if hasattr(db, 'save_strategy_vector_index_snapshot'):
                snapshot = await db.save_strategy_vector_index_snapshot({
                    'index_name': index_name,
                    'index_version': index_version,
                    'status': 'active' if items else 'empty',
                    'profile_type': profile_type,
                    'vector_method': str((profiles[0] if profiles else {}).get('vector_method') or 'price_volume'),
                    'metric': str((profiles[0] if profiles else {}).get('metric') or 'cosine'),
                    'backend': self.backend_name(db),
                    'profile_count': int(layout.get('profile_count') or len(items)),
                    'bucket_count': int(layout.get('bucket_count') or 0),
                    'vector_dim': int(layout.get('vector_dim') or 0),
                    'centroids': layout.get('centroids') or [],
                    'metadata': {
                        **dict(layout.get('metadata') or {}),
                        'index_name': index_name,
                        'index_version': index_version,
                        'source': source,
                        'task_run_id': task_run_id,
                    },
                    'task_run_id': task_run_id,
                    'source': source,
                    'built_at': now,
                    'activated_at': datetime.now(timezone.utc).isoformat(),
                })
        except Exception as exc:
            if hasattr(db, 'save_strategy_vector_index_snapshot'):
                snapshot = await db.save_strategy_vector_index_snapshot({
                    'index_name': index_name,
                    'index_version': index_version,
                    'status': 'failed',
                    'profile_type': profile_type,
                    'vector_method': str((profiles[0] if profiles else {}).get('vector_method') or 'price_volume'),
                    'metric': str((profiles[0] if profiles else {}).get('metric') or 'cosine'),
                    'backend': self.backend_name(db),
                    'profile_count': int(layout.get('profile_count') or len(items)),
                    'bucket_count': int(layout.get('bucket_count') or 0),
                    'vector_dim': int(layout.get('vector_dim') or 0),
                    'centroids': layout.get('centroids') or [],
                    'metadata': {
                        **dict(layout.get('metadata') or {}),
                        'index_name': index_name,
                        'index_version': index_version,
                        'source': source,
                        'task_run_id': task_run_id,
                        'error': str(exc),
                    },
                    'task_run_id': task_run_id,
                    'source': source,
                    'built_at': now,
                    'activated_at': None,
                })
            raise
        unified_snapshot = None
        unified_collection_name = None
        if hasattr(db, 'save_vector_index_snapshot') and hasattr(db, 'list_vector_profiles'):
            try:
                from .unified_vector_governance import build_vector_collection_snapshot

                primary_collection, _ = await self._select_primary_unified_collection(
                    db,
                    index_name=index_name,
                    profile_type=profile_type,
                    version=index_version,
                )
                unified_collection_name = str((primary_collection or {}).get('collection_name') or '').strip() or None
                if unified_collection_name:
                    unified_snapshot = await build_vector_collection_snapshot(
                        db,
                        collection_name=unified_collection_name,
                        version=index_version,
                        index_version=index_version,
                        profile_type=profile_type,
                        activate=True,
                        source=source,
                    )
            except Exception as exc:
                logger.warning('StrategyVectorPlatform.build_persisted_ann_index unified snapshot build failed: %s', exc)
        return {
            'snapshot': snapshot,
            'items_count': len(items),
            'bucket_count': int(layout.get('bucket_count') or 0),
            'profile_count': int(layout.get('profile_count') or len(items)),
            'unified_snapshot': unified_snapshot,
            'unified_collection_name': unified_collection_name,
        }

    async def _get_latest_snapshot(self, db, index_name: str, index_version: Optional[str] = None) -> Optional[dict]:
        if not hasattr(db, 'list_strategy_vector_index_snapshots'):
            return None
        if index_version:
            rows = await db.list_strategy_vector_index_snapshots(index_name=index_name, index_version=index_version, limit=1)
            return rows[0] if rows else None
        if hasattr(db, 'get_latest_strategy_vector_index_snapshot'):
            return await db.get_latest_strategy_vector_index_snapshot(index_name=index_name)
        rows = await db.list_strategy_vector_index_snapshots(index_name=index_name, limit=1)
        return rows[0] if rows else None

    @staticmethod
    def _snapshot_bucket_map(snapshot: Optional[dict]) -> dict[str, dict]:
        centroids = list((snapshot or {}).get('centroids') or [])
        return {str(item.get('bucket_id')): dict(item) for item in centroids if item.get('bucket_id')}

    def _resolve_query_bucket(self, snapshot: dict, query_embedding: np.ndarray) -> tuple[Optional[str], List[str]]:
        bucket_map = self._snapshot_bucket_map(snapshot)
        if not bucket_map:
            return None, []
        scored = []
        for bucket_id, item in bucket_map.items():
            centroid = self._normalize_embedding(item.get('centroid'))
            if len(centroid) != len(query_embedding) or len(centroid) == 0:
                continue
            scored.append((bucket_id, float(self.engine.calculate_similarity(query_embedding, centroid, 'cosine'))))
        if not scored:
            return None, []
        scored.sort(key=lambda item: item[1], reverse=True)
        primary = scored[0][0]
        bucket_rows = [primary]
        neighbors = bucket_map.get(primary, {}).get('neighbors') or []
        for item in neighbors[:2]:
            if item not in bucket_rows:
                bucket_rows.append(item)
        return primary, bucket_rows

    async def archive_profile(
        self,
        db,
        strategy: dict,
        profile_type: str = 'behavior',
        vector_method: Optional[str] = None,
        metric: str = 'cosine',
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
    ) -> Optional[dict]:
        return await self.build_strategy_profile(
            db,
            strategy,
            profile_type=profile_type,
            vector_method=vector_method,
            metric=metric,
            index_name=index_name,
            index_version=index_version,
        )

    async def get_active_index(self, db, index_name: str = 'strategy_behavior', index_version: Optional[str] = None) -> Optional[dict]:
        collections = await self._list_unified_strategy_collections(db, index_name=index_name)
        if collections and hasattr(db, 'list_vector_index_snapshots'):
            resolved_index_version = str(index_version or '').strip() or None
            for collection in collections:
                if resolved_index_version:
                    snapshots = await db.list_vector_index_snapshots(
                        collection_name=collection.get('collection_name'),
                        index_version=resolved_index_version,
                        latest_only=True,
                        limit=1,
                    )
                else:
                    active_version = str(collection.get('active_version') or '').strip() or None
                    snapshots = await db.list_vector_index_snapshots(
                        collection_name=collection.get('collection_name'),
                        index_version=active_version,
                        latest_only=True,
                        limit=1,
                    ) if active_version else []
                    if not snapshots:
                        snapshots = await db.list_vector_index_snapshots(
                            collection_name=collection.get('collection_name'),
                            latest_only=True,
                            limit=1,
                        )
                if snapshots:
                    snapshot = dict(snapshots[0] or {})
                    mapped = self._map_unified_snapshot_row(snapshot, dict(collection), index_name=index_name)
                    return {
                        'index_name': mapped.get('index_name') or str(index_name or 'strategy_behavior'),
                        'index_version': mapped.get('index_version') or str(index_version or ''),
                        'backend': mapped.get('backend') or self.backend_name(db),
                        'status': mapped.get('status') or 'active',
                        'source': mapped.get('source') or 'unified_snapshot',
                        'collection_name': mapped.get('collection_name'),
                        'model_id': mapped.get('model_id'),
                        'vector_dim': mapped.get('vector_dim'),
                    }
        snapshot = await self._get_latest_snapshot(db, index_name, index_version=index_version)
        if snapshot:
            return {
                'index_name': str(snapshot.get('index_name') or index_name),
                'index_version': str(snapshot.get('index_version') or index_version or ''),
                'backend': str(snapshot.get('backend') or self.backend_name(db)),
                'status': str(snapshot.get('status') or 'active'),
                'source': 'snapshot',
            }
        if hasattr(db, 'list_vector_index_registry'):
            rows = await db.list_vector_index_registry(index_name=index_name, status='active', limit=20)
            if index_version:
                rows = [row for row in rows if str(row.get('index_version') or '') == str(index_version)]
            if rows:
                row = rows[0]
                return {
                    'index_name': str(row.get('index_name') or index_name),
                    'index_version': str(row.get('index_version') or index_version or ''),
                    'backend': str(row.get('backend') or self.backend_name(db)),
                    'status': str(row.get('status') or 'active'),
                    'source': 'registry',
                }
        return None

    async def _build_unified_health(
        self,
        db,
        *,
        index_name: str,
        limit_versions: int,
        include_hnsw_indexes: bool,
    ) -> Optional[dict]:
        del include_hnsw_indexes
        collections = await self._list_unified_strategy_collections(db, index_name=index_name)
        if not collections or not hasattr(db, 'list_vector_index_snapshots'):
            return None
        counts = {
            'profiles': 0,
            'profile_store': 0,
            'index_snapshots': 0,
            'index_items': 0,
            'index_item_store': 0,
        }
        versions: List[dict] = []
        latest_snapshot: Optional[dict] = None
        for collection in collections:
            collection_name = collection.get('collection_name')
            try:
                profiles = await db.list_vector_profiles(
                    collection_name=collection_name,
                    entity_type='strategy',
                    limit=5000,
                ) if hasattr(db, 'list_vector_profiles') else []
            except Exception:
                profiles = []
            counts['profiles'] += len(profiles)
            if getattr(db, 'supports_pgvector', lambda: False)():
                counts['profile_store'] += len(profiles)
            snapshots = await db.list_vector_index_snapshots(
                collection_name=collection_name,
                latest_only=False,
                limit=max(20, min(int(limit_versions or 20) * 4, 500)),
            )
            counts['index_snapshots'] += len(snapshots)
            for snapshot in snapshots:
                mapped = self._map_unified_snapshot_row(dict(snapshot or {}), dict(collection), index_name=index_name)
                try:
                    items = await db.list_vector_index_items(
                        collection_name=collection_name,
                        index_version=mapped.get('index_version'),
                        profile_type=mapped.get('profile_type'),
                        limit=5000,
                    ) if hasattr(db, 'list_vector_index_items') else []
                except Exception:
                    items = []
                item_count = len(items)
                counts['index_items'] += item_count
                if getattr(db, 'supports_pgvector', lambda: False)():
                    counts['index_item_store'] += item_count
                versions.append({
                    'collection_name': mapped.get('collection_name'),
                    'index_version': mapped.get('index_version'),
                    'registry_status': mapped.get('status'),
                    'registry_backend': mapped.get('backend'),
                    'snapshot_status': mapped.get('status'),
                    'snapshot_backend': mapped.get('backend'),
                    'profile_count': mapped.get('profile_count'),
                    'bucket_count': mapped.get('bucket_count'),
                    'vector_dim': mapped.get('vector_dim'),
                    'model_id': mapped.get('model_id'),
                    'profile_rows': sum(
                        1
                        for row in profiles
                        if str((row or {}).get('version') or '') == str(mapped.get('index_version') or '')
                    ),
                    'profile_store_rows': sum(
                        1
                        for row in profiles
                        if str((row or {}).get('version') or '') == str(mapped.get('index_version') or '')
                    ) if getattr(db, 'supports_pgvector', lambda: False)() else 0,
                    'index_item_rows': item_count,
                    'index_item_store_rows': item_count if getattr(db, 'supports_pgvector', lambda: False)() else 0,
                    'last_seen': str(mapped.get('activated_at') or mapped.get('built_at') or ''),
                })
                candidate_latest_key = str(mapped.get('activated_at') or mapped.get('built_at') or '')
                current_latest_key = str((latest_snapshot or {}).get('activated_at') or (latest_snapshot or {}).get('built_at') or '')
                if candidate_latest_key >= current_latest_key:
                    latest_snapshot = dict(mapped)
        versions.sort(
            key=lambda row: (
                str(row.get('last_seen') or ''),
                str(row.get('collection_name') or ''),
                str(row.get('index_version') or ''),
            ),
            reverse=True,
        )
        return {
            'index_name': index_name,
            'backend': self._pgvector_backend_family(getattr(db, 'get_vector_backend', lambda: 'pgvector')()),
            'pgvector_enabled': getattr(db, 'supports_pgvector', lambda: False)(),
            'tables': {
                'vector_collections': True,
                'vector_profiles': True,
                'vector_profile_store': getattr(db, 'supports_pgvector', lambda: False)(),
                'vector_index_snapshots': True,
                'vector_index_items': True,
                'vector_index_item_store': getattr(db, 'supports_pgvector', lambda: False)(),
            },
            'counts': counts,
            'latest_snapshot': latest_snapshot,
            'versions': versions[: max(1, min(int(limit_versions or 20), 200))],
            'hnsw_indexes': [],
            'hnsw_index_count': 0,
            'recommended_cleanup_versions': [row.get('index_version') for row in versions[1:] if row.get('index_version')],
            'health_mode': 'unified',
        }

    async def search_similar(
        self,
        db,
        strategy_id: str,
        profile_type: str = 'behavior',
        limit: int = 5,
        candidate_limit: int = 80,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
    ) -> dict:
        started_at = time.perf_counter()
        requested_backend = self.requested_backend_name(db)
        resolved_index_name = str(index_name or 'strategy_behavior')
        active_index = await self.get_active_index(db, resolved_index_name, index_version=index_version)
        rows = await self.ann_search_profiles(
            db,
            strategy_id,
            profile_type=profile_type,
            limit=limit,
            candidate_limit=candidate_limit,
            index_name=index_name,
            index_version=index_version,
        )
        first = rows[0] if rows else {}
        fallback_used = False
        fallback_reason = None
        if rows:
            fallback_used = bool(first.get('search_fallback_used'))
            fallback_reason = first.get('search_fallback_reason')
        if not rows and self.allow_fallback:
            rows = await self.find_similar_profiles(
                db,
                strategy_id,
                profile_type=profile_type,
                limit=limit,
                index_name=index_name,
                index_version=index_version,
            )
            if rows:
                fallback_used = True
                fallback_reason = 'ann_empty_result'
        first = rows[0] if rows else {}
        resolved_index_name = str(
            first.get('index_name')
            or (active_index or {}).get('index_name')
            or index_name
            or 'strategy_behavior'
        )
        resolved_index_version = str(
            first.get('index_version')
            or (active_index or {}).get('index_version')
            or index_version
            or ''
        )
        backend_used = str(
            first.get('backend')
            or (active_index or {}).get('backend')
            or requested_backend
        )
        return {
            'items': rows,
            'count': len(rows),
            'index_name': resolved_index_name,
            'index_version': resolved_index_version,
            'active_index': active_index,
            **self._merge_backend_audit(
                backend_requested=requested_backend,
                backend_used=backend_used,
                fallback_reason=fallback_reason,
                fallback_used=fallback_used,
                started_at=started_at,
            ),
        }

    async def health_check(
        self,
        db,
        index_name: str = 'strategy_behavior',
        limit_versions: int = 20,
        include_hnsw_indexes: bool = False,
    ) -> dict:
        started_at = time.perf_counter()
        unified_result = await self._build_unified_health(
            db,
            index_name=index_name,
            limit_versions=limit_versions,
            include_hnsw_indexes=include_hnsw_indexes,
        )
        if unified_result:
            active_index = await self.get_active_index(db, index_name=index_name)
            backend_requested = self.requested_backend_name(db)
            backend_used = str((active_index or {}).get('backend') or unified_result.get('backend') or backend_requested)
            audit = self._merge_backend_audit(
                backend_requested=backend_requested,
                backend_used=backend_used,
                started_at=started_at,
            )
            return {
                **unified_result,
                'active_index': active_index,
                **audit,
            }
        if not hasattr(db, 'get_strategy_vector_health'):
            audit = self._merge_backend_audit(
                backend_requested=self.requested_backend_name(db),
                backend_used=self.backend_name(db),
                fallback_reason='health_unsupported',
                fallback_used=False,
                started_at=started_at,
            )
            return {
                'index_name': index_name,
                'active_index': None,
                **audit,
            }
        result = await db.get_strategy_vector_health(
            index_name=index_name,
            limit_versions=limit_versions,
            include_hnsw_indexes=include_hnsw_indexes,
        )
        active_index = await self.get_active_index(db, index_name=index_name)
        backend_requested = self.requested_backend_name(db)
        backend_used = str((active_index or {}).get('backend') or result.get('backend') or backend_requested)
        audit = self._merge_backend_audit(
            backend_requested=backend_requested,
            backend_used=backend_used,
            started_at=started_at,
        )
        return {
            **result,
            'active_index': active_index,
            **audit,
        }

    async def _search_unified_profiles(
        self,
        db,
        strategy_id: str,
        *,
        profile_type: str = 'behavior',
        limit: int = 5,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
    ) -> List[dict]:
        if not hasattr(db, 'search_vector_collection'):
            return []
        query_profile = await self._load_unified_query_profile(
            db,
            strategy_id,
            profile_type=profile_type,
            preferred_version=index_version,
            index_name=index_name,
        )
        if not query_profile:
            return []
        collection = dict(query_profile.get('_collection') or {})
        query_embedding = self._normalize_embedding(query_profile.get('embedding'))
        if len(query_embedding) == 0:
            return []
        resolved_index_name = str(
            index_name
            or dict(query_profile.get('metadata') or {}).get('index_name')
            or collection.get('index_name')
            or 'strategy_behavior'
        )
        search_result = await db.search_vector_collection(
            collection_name=str(query_profile.get('collection_name') or collection.get('collection_name') or ''),
            query_embedding=query_embedding.tolist(),
            index_version=index_version or collection.get('active_version') or query_profile.get('version'),
            version=index_version or query_profile.get('version'),
            profile_type=profile_type,
            exclude_entity_id=strategy_id,
            limit=max(1, min(int(limit or 5), 20)),
            metric=str(query_profile.get('metric') or collection.get('metric') or 'cosine'),
        )
        items = list((search_result or {}).get('items') or [])
        if not items:
            return []
        backend_used = str((search_result or {}).get('backend_used') or collection.get('backend') or 'pgvector')
        backend_family = self._pgvector_backend_family(backend_used)
        fallback_reason = str((search_result or {}).get('fallback_reason') or '').strip() or None
        fallback_used = bool((search_result or {}).get('fallback_used') or fallback_reason)
        query_bucket_id = (search_result or {}).get('query_bucket_id')
        candidate_bucket_ids = list((search_result or {}).get('candidate_bucket_ids') or [])
        results: List[dict] = []
        for item in items:
            metadata = dict((item or {}).get('metadata') or {})
            resolved_strategy_id = str(item.get('entity_id') or '').strip()
            if not resolved_strategy_id:
                continue
            results.append({
                'profile_id': item.get('profile_id') or item.get('id') or metadata.get('legacy_profile_id'),
                'strategy_id': resolved_strategy_id,
                'profile_type': item.get('profile_type') or profile_type,
                'vector_method': metadata.get('effective_vector_method') or metadata.get('vector_method'),
                'metric': item.get('metric') or query_profile.get('metric') or collection.get('metric') or 'cosine',
                'vector_dim': item.get('vector_dim') or query_profile.get('vector_dim') or collection.get('vector_dim'),
                'bucket_id': item.get('bucket_id'),
                'query_bucket_id': query_bucket_id,
                'candidate_bucket_ids': candidate_bucket_ids,
                'coarse_score': item.get('coarse_score'),
                'similarity': round(float(item.get('similarity') or 0.0), 6),
                'backend': backend_family,
                'index_name': resolved_index_name,
                'index_version': str((search_result or {}).get('index_version') or query_profile.get('version') or index_version or ''),
                'signature': item.get('signature') or metadata.get('signature'),
                'candidate_count': len(items),
                'retrieval_mode': self._unified_retrieval_mode(backend_used),
                'collection_name': query_profile.get('collection_name') or collection.get('collection_name'),
                'model_id': item.get('model_id') or query_profile.get('model_id') or collection.get('model_id'),
                'metadata': metadata,
                'search_fallback_used': fallback_used,
                'search_fallback_reason': fallback_reason,
            })
        results.sort(key=lambda row: (row.get('similarity', 0), row.get('coarse_score', 0)), reverse=True)
        return results[: max(1, min(int(limit or 5), 20))]


    async def ann_search_profiles(
        self,
        db,
        strategy_id: str,
        profile_type: str = 'behavior',
        limit: int = 5,
        candidate_limit: int = 80,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
    ) -> List[dict]:
        unified_rows = await self._search_unified_profiles(
            db,
            strategy_id,
            profile_type=profile_type,
            limit=limit,
            index_name=index_name,
            index_version=index_version,
        )
        if unified_rows:
            return unified_rows
        query_profile = await self._load_query_profile(db, strategy_id, profile_type=profile_type, preferred_version=index_version)
        if not query_profile:
            return []
        requested_backend = self.requested_backend_name(db)
        resolved_index_name = self._resolved_index_name(index_name, query_profile)
        snapshot = await self._get_latest_snapshot(db, resolved_index_name, index_version=index_version)
        if snapshot and snapshot.get('index_version') and query_profile.get('index_version') != snapshot.get('index_version'):
            preferred = await self._load_query_profile(db, strategy_id, profile_type=profile_type, preferred_version=str(snapshot.get('index_version')))
            if preferred:
                query_profile = preferred
        query_embedding = self._normalize_embedding(query_profile.get('embedding'))
        if len(query_embedding) == 0:
            return []
        if not snapshot or not hasattr(db, 'list_strategy_vector_index_items'):
            return []
        pgvector_available = getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'search_strategy_vector_index_items_by_embedding')
        if requested_backend == 'pgvector' and pgvector_available:
            pg_rows = await db.search_strategy_vector_index_items_by_embedding(
                query_embedding=query_embedding.tolist(),
                index_name=resolved_index_name,
                index_version=str(snapshot.get('index_version') or ''),
                profile_type=profile_type,
                exclude_strategy_id=strategy_id,
                limit=max(1, min(int(candidate_limit or 80), 500)),
                metric=str(query_profile.get('metric') or 'cosine'),
            )
            if pg_rows:
                results = []
                candidate_count = 0
                for item in pg_rows:
                    if item.get('strategy_id') == strategy_id:
                        continue
                    candidate_count += 1
                    results.append({
                        'profile_id': item.get('profile_id'),
                        'strategy_id': item.get('strategy_id'),
                        'profile_type': item.get('profile_type'),
                        'vector_method': item.get('vector_method'),
                        'metric': item.get('metric') or str(query_profile.get('metric') or 'cosine'),
                        'vector_dim': item.get('vector_dim'),
                        'bucket_id': item.get('bucket_id'),
                        'query_bucket_id': None,
                        'coarse_score': item.get('coarse_score'),
                        'similarity': round(float(item.get('similarity') or 0.0), 6),
                        'backend': 'pgvector',
                        'index_name': resolved_index_name,
                        'index_version': snapshot.get('index_version'),
                        'signature': dict(item.get('metadata') or {}).get('signature'),
                        'candidate_count': max(candidate_count, len(pg_rows)),
                        'retrieval_mode': 'pgvector_ann',
                        'metadata': item.get('metadata') or {},
                    })
                results.sort(key=lambda row: (row.get('similarity', 0), row.get('coarse_score', 0)), reverse=True)
                return results[: max(1, min(int(limit or 5), 20))]
            if not self.allow_fallback:
                return []
        elif requested_backend == 'pgvector' and not self.allow_fallback:
            return []
        primary_bucket, candidate_buckets = self._resolve_query_bucket(snapshot, query_embedding)
        if not candidate_buckets:
            return []
        items = await db.list_strategy_vector_index_items(
            index_name=resolved_index_name,
            index_version=str(snapshot.get('index_version') or ''),
            bucket_ids=candidate_buckets,
            limit=max(1, min(int(candidate_limit or 80), 500)),
        )
        if not items:
            return []
        metric = str(query_profile.get('metric') or 'cosine')
        results = []
        candidate_count = 0
        for item in items:
            embedding = self._normalize_embedding(item.get('embedding'))
            if len(embedding) != len(query_embedding) or len(embedding) == 0:
                continue
            if item.get('strategy_id') == strategy_id:
                continue
            candidate_count += 1
            similarity = self.engine.calculate_similarity(query_embedding, embedding, metric)
            results.append({
                'profile_id': item.get('profile_id'),
                'strategy_id': item.get('strategy_id'),
                'profile_type': item.get('profile_type'),
                'vector_method': item.get('vector_method'),
                'metric': item.get('metric') or metric,
                'vector_dim': item.get('vector_dim'),
                'bucket_id': item.get('bucket_id'),
                'query_bucket_id': primary_bucket,
                'coarse_score': item.get('coarse_score'),
                'similarity': round(float(similarity), 6),
                'backend': snapshot.get('backend') or self.engine.backend,
                'index_name': resolved_index_name,
                'index_version': snapshot.get('index_version'),
                'signature': dict(item.get('metadata') or {}).get('signature'),
                'candidate_count': max(candidate_count, len(items) - 1),
                'retrieval_mode': 'persisted_ann',
                'metadata': item.get('metadata') or {},
            })
        results.sort(key=lambda row: (row.get('similarity', 0), row.get('coarse_score', 0)), reverse=True)
        return results[: max(1, min(int(limit or 5), 20))]

    async def find_similar_profiles(
        self,
        db,
        strategy_id: str,
        profile_type: str = 'behavior',
        limit: int = 5,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
    ) -> List[dict]:
        ann_rows = await self.ann_search_profiles(
            db,
            strategy_id,
            profile_type=profile_type,
            limit=limit,
            index_name=index_name,
            index_version=index_version,
        )
        if ann_rows:
            return ann_rows
        query_profile = await self._load_query_profile(db, strategy_id, profile_type=profile_type, preferred_version=index_version)
        if not query_profile:
            return []
        requested_backend = self.requested_backend_name(db)
        query_embedding = self._normalize_embedding(query_profile.get('embedding'))
        if len(query_embedding) == 0:
            return []
        resolved_index_name = self._resolved_index_name(index_name, query_profile)
        pgvector_available = getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'search_strategy_vector_profiles_by_embedding')
        if requested_backend == 'pgvector' and pgvector_available:
            pg_rows = await db.search_strategy_vector_profiles_by_embedding(
                query_embedding=query_embedding.tolist(),
                profile_type=profile_type,
                index_name=resolved_index_name,
                index_version=index_version or query_profile.get('index_version'),
                exclude_strategy_id=strategy_id,
                limit=max(1, min(int(limit or 5), 50)),
                metric=str(query_profile.get('metric') or 'cosine'),
            )
            if pg_rows:
                results = []
                candidate_count = 0
                for item in pg_rows:
                    if item.get('strategy_id') == strategy_id:
                        continue
                    candidate_count += 1
                    results.append({
                        **item,
                        'similarity': round(float(item.get('similarity') or 0.0), 6),
                        'retrieval_mode': 'pgvector_exact',
                        'candidate_count': max(candidate_count, len(pg_rows)),
                        'index_name': self._resolved_index_name(index_name, item),
                        'query_bucket_id': None,
                        'bucket_id': None,
                        'backend': 'pgvector',
                    })
                results.sort(key=lambda row: row.get('similarity', 0), reverse=True)
                return results[: max(1, min(int(limit or 5), 20))]
            if not self.allow_fallback:
                return []
        elif requested_backend == 'pgvector' and not self.allow_fallback:
            return []
        profiles = await db.list_strategy_vector_profiles(
            profile_type=profile_type,
            index_name=resolved_index_name,
            index_version=index_version or query_profile.get('index_version'),
            limit=2000,
        )
        results = []
        candidate_count = 0
        for item in profiles:
            if item.get('strategy_id') == strategy_id:
                continue
            candidate = self._normalize_embedding(item.get('embedding'))
            if len(candidate) != len(query_embedding) or len(candidate) == 0:
                continue
            candidate_count += 1
            similarity = self.engine.calculate_similarity(query_embedding, candidate, query_profile.get('metric') or 'cosine')
            results.append({
                **item,
                'similarity': round(float(similarity), 6),
                'retrieval_mode': 'full_scan',
                'candidate_count': candidate_count,
                'index_name': self._resolved_index_name(index_name, item),
                'query_bucket_id': None,
                'bucket_id': None,
            })
        results.sort(key=lambda row: row.get('similarity', 0), reverse=True)
        return results[: max(1, min(int(limit or 5), 20))]


_vector_platform: Optional[StrategyVectorPlatform] = None


def get_strategy_vector_platform() -> StrategyVectorPlatform:
    global _vector_platform
    if _vector_platform is None:
        _vector_platform = StrategyVectorPlatform()
    return _vector_platform

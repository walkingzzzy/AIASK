"""策略向量平台：统一画像、索引注册和相似度检索元数据。"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np

from .vector_search import VectorSearchEngine

logger = logging.getLogger(__name__)


class StrategyVectorPlatform:
    def __init__(self):
        self.engine = VectorSearchEngine(backend='index', allow_fallback=True)

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

    async def build_strategy_profile(
        self,
        db,
        strategy: dict,
        profile_type: str = 'behavior',
        vector_method: str = 'price_volume',
        metric: str = 'cosine',
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
    ) -> Optional[dict]:
        try:
            from .strategy_factory import _build_strategy_panels

            panels = await _build_strategy_panels(
                strategy.get('strategy_type') or '',
                strategy.get('params') or {},
                db,
                sample_size=4,
            )
            series = panels.get('strategy_returns')
            if series is None or len(series) < 30:
                return None

            klines = self._returns_to_pseudo_klines(np.asarray(series, dtype=np.float64))
            embedding = self.engine.kline_to_vector(klines, vector_method)
            if embedding is None or len(embedding) == 0:
                return None

            profile = await db.save_strategy_vector_profile({
                'strategy_id': strategy.get('id'),
                'profile_type': profile_type,
                'vector_method': vector_method,
                'metric': metric,
                'vector_dim': int(len(embedding)),
                'embedding': embedding.tolist(),
                'signature': self._signature(strategy, profile_type, vector_method),
                'backend': self.engine.backend,
                'index_version': index_version,
                'metadata': {
                    'strategy_type': strategy.get('strategy_type'),
                    'sample_length': int(len(klines)),
                    'pattern_length': int(len(klines)),
                    'index_name': index_name,
                    'index_version': index_version,
                    'profile_type': profile_type,
                },
            })
            await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': self.engine.backend,
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': vector_method,
                'metric': metric,
                'sample_count': 1,
                'index_version': index_version,
                'metadata': {
                    'last_strategy_id': strategy.get('id'),
                },
            })
            return profile
        except Exception as exc:
            logger.warning('StrategyVectorPlatform.build_strategy_profile failed for %s: %s', strategy.get('id'), exc)
            return None

    async def build_profiles_for_strategies(
        self,
        db,
        strategies: List[dict],
        profile_type: str = 'behavior',
        vector_method: str = 'price_volume',
        index_name: str = 'strategy_behavior',
        index_version: str = 'v1',
    ) -> dict:
        items = []
        for strategy in strategies:
            profile = await self.build_strategy_profile(
                db,
                strategy,
                profile_type=profile_type,
                vector_method=vector_method,
                index_name=index_name,
                index_version=index_version,
            )
            if profile:
                items.append(profile)
        if items:
            await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': self.engine.backend,
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': vector_method,
                'metric': 'cosine',
                'sample_count': len(items),
                'index_version': index_version,
                'metadata': {
                    'profile_ids': [item.get('id') for item in items if item.get('id') is not None],
                },
            })
        return {'count': len(items), 'items': items}

    async def find_similar_profiles(
        self,
        db,
        strategy_id: str,
        profile_type: str = 'behavior',
        limit: int = 5,
    ) -> List[dict]:
        profiles = await db.list_strategy_vector_profiles(profile_type=profile_type, limit=500)
        query_profile = next((item for item in profiles if item.get('strategy_id') == strategy_id), None)
        if not query_profile:
            return []
        query_embedding = np.asarray(query_profile.get('embedding') or [], dtype=np.float64)
        if len(query_embedding) == 0:
            return []
        results = []
        for item in profiles:
            if item.get('strategy_id') == strategy_id:
                continue
            candidate = np.asarray(item.get('embedding') or [], dtype=np.float64)
            if len(candidate) != len(query_embedding) or len(candidate) == 0:
                continue
            similarity = self.engine.calculate_similarity(query_embedding, candidate, query_profile.get('metric') or 'cosine')
            results.append({
                **item,
                'similarity': round(float(similarity), 6),
            })
        results.sort(key=lambda row: row.get('similarity', 0), reverse=True)
        return results[: max(1, min(int(limit or 5), 20))]


_vector_platform: Optional[StrategyVectorPlatform] = None


def get_strategy_vector_platform() -> StrategyVectorPlatform:
    global _vector_platform
    if _vector_platform is None:
        _vector_platform = StrategyVectorPlatform()
    return _vector_platform

"""策略向量平台：统一画像、持久化索引和 ANN-like 相似检索。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from .text_embedding import get_strategy_text_embedding_service
from .vector_search import VectorSearchEngine

logger = logging.getLogger(__name__)


class StrategyVectorPlatform:
    SUPPORTED_NUMERIC_METHODS = {'price_volume', 'ohlc', 'returns', 'technical'}
    TEXT_EMBEDDING_ALIASES = {'text', 'text_embedding', 'text_embed', 'semantic', 'semantic_text'}

    def __init__(self):
        self.engine = VectorSearchEngine(backend='index', allow_fallback=True)
        self.text_embedding_service = get_strategy_text_embedding_service()

    def backend_name(self, db) -> str:
        if hasattr(db, 'get_vector_backend'):
            try:
                return str(db.get_vector_backend() or 'index')
            except Exception:
                return 'index'
        return 'pgvector' if getattr(db, 'supports_pgvector', lambda: False)() else self.engine.backend

    def default_vector_method(self) -> str:
        return 'text_embedding' if self.text_embedding_service.is_enabled() else 'price_volume'

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

    @staticmethod
    def _normalize_embedding(values: Any) -> np.ndarray:
        vector = np.asarray(values or [], dtype=np.float64)
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
        series = np.asarray(panels.get('strategy_returns') or [], dtype=np.float64)
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
        factor_panel = np.asarray(panels.get('factor_panel') or [], dtype=np.float64)
        return_panel = np.asarray(panels.get('return_panel') or [], dtype=np.float64)
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
    ) -> tuple[np.ndarray, dict]:
        series = panels.get('strategy_returns')
        if series is None or len(series) < 30:
            return np.asarray([], dtype=np.float64), {}
        if vector_method == 'text_embedding':
            document = self._build_text_embedding_document(
                strategy,
                panels,
                profile_type=profile_type,
                index_name=index_name,
                index_version=index_version,
            )
            embedding = np.asarray(await self.text_embedding_service.embed_text(document), dtype=np.float64)
            return embedding, {
                'embedding_source': 'strategy_text_profile',
                'embedding_provider': getattr(getattr(self.text_embedding_service, 'config', None), 'provider', 'openai_compatible'),
                'embedding_model': getattr(getattr(self.text_embedding_service, 'config', None), 'model', None),
                'embedding_text_preview': document[:240],
                'embedding_text_hash': hashlib.sha1(document.encode('utf-8')).hexdigest(),
                'sample_length': int(len(series)),
                'pattern_length': int(min(len(series), 60)),
            }
        klines = self._returns_to_pseudo_klines(np.asarray(series, dtype=np.float64))
        embedding = self.engine.kline_to_vector(klines, vector_method)
        return np.asarray(embedding if embedding is not None else [], dtype=np.float64), {
            'sample_length': int(len(klines)),
            'pattern_length': int(len(klines)),
        }

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
            from .strategy_factory import _build_strategy_panels

            resolved_vector_method = self.ensure_vector_method_available(vector_method)
            panels = await _build_strategy_panels(
                strategy.get('strategy_type') or '',
                strategy.get('params') or {},
                db,
                sample_size=4,
            )
            series = panels.get('strategy_returns')
            if series is None or len(series) < 30:
                return None

            embedding, embedding_meta = await self._build_embedding(
                strategy=strategy,
                panels=panels,
                vector_method=resolved_vector_method,
                profile_type=profile_type,
                index_name=index_name,
                index_version=index_version,
            )
            if embedding is None or len(embedding) == 0:
                return None

            profile = await db.save_strategy_vector_profile({
                'strategy_id': strategy.get('id'),
                'profile_type': profile_type,
                'vector_method': resolved_vector_method,
                'metric': metric,
                'vector_dim': int(len(embedding)),
                'embedding': embedding.tolist(),
                'signature': self._signature(strategy, profile_type, resolved_vector_method),
                'backend': self.backend_name(db),
                'index_name': index_name,
                'index_version': index_version,
                'metadata': {
                    'strategy_type': strategy.get('strategy_type'),
                    'index_name': index_name,
                    'index_version': index_version,
                    'profile_type': profile_type,
                    **embedding_meta,
                },
            })
            await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': self.backend_name(db),
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': resolved_vector_method,
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
            for _ in range(4):
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
                centroids = updated

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
            return {'snapshot': None, 'items_count': 0, 'bucket_count': 0}
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
                'activated_at': now,
            })
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
        return {
            'snapshot': snapshot,
            'items_count': len(items),
            'bucket_count': int(layout.get('bucket_count') or 0),
            'profile_count': int(layout.get('profile_count') or len(items)),
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
        query_profile = await self._load_query_profile(db, strategy_id, profile_type=profile_type, preferred_version=index_version)
        if not query_profile:
            return []
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
        if getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'search_strategy_vector_index_items_by_embedding'):
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
        query_embedding = self._normalize_embedding(query_profile.get('embedding'))
        if len(query_embedding) == 0:
            return []
        resolved_index_name = self._resolved_index_name(index_name, query_profile)
        if getattr(db, 'supports_pgvector', lambda: False)() and hasattr(db, 'search_strategy_vector_profiles_by_embedding'):
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

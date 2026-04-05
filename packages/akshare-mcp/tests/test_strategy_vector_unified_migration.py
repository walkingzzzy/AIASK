from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import numpy as np
import pytest

from akshare_mcp.services.vector_platform import StrategyVectorPlatform
from akshare_mcp.tools.managers import strategy_manager as sm_mod


class _DualWriteDb:
    def __init__(self):
        self.saved_strategy_profiles: list[dict[str, Any]] = []
        self.saved_collections: list[dict[str, Any]] = []
        self.saved_unified_profiles: list[dict[str, Any]] = []
        self.saved_registries: list[dict[str, Any]] = []

    def supports_pgvector(self):
        return False

    async def save_strategy_vector_profile(self, payload):
        item = {'id': len(self.saved_strategy_profiles) + 1, **dict(payload)}
        self.saved_strategy_profiles.append(item)
        return dict(item)

    async def save_vector_collection(self, payload):
        item = dict(payload)
        self.saved_collections.append(item)
        return dict(item)

    async def save_vector_profile(self, payload):
        item = {'id': len(self.saved_unified_profiles) + 1, **dict(payload)}
        self.saved_unified_profiles.append(item)
        return dict(item)

    async def save_vector_index_registry(self, payload):
        item = dict(payload)
        self.saved_registries.append(item)
        return dict(item)


class _UnifiedStrategyDb:
    def __init__(self):
        self.collections = [
            {
                'collection_name': 'strategy_behavior_embeddings',
                'entity_family': 'strategy_behavior',
                'backend': 'pgvector',
                'metric': 'cosine',
                'model_id': 'strategy-behavior-v1',
                'vector_dim': 120,
                'normalization': 'unit',
                'status': 'active',
                'active_version': 'u_v1',
                'metadata': {
                    'index_name': 'strategy_behavior',
                    'vector_method': 'price_volume',
                },
            }
        ]
        self.profiles = [
            {
                'id': 1,
                'collection_name': 'strategy_behavior_embeddings',
                'entity_type': 'strategy',
                'entity_id': 'sid_query',
                'profile_type': 'behavior',
                'model_id': 'strategy-behavior-v1',
                'vector_dim': 120,
                'metric': 'cosine',
                'version': 'u_v1',
                'signature': 'sig_query',
                'embedding': [1.0, 0.0, 0.0],
                'metadata': {
                    'index_name': 'strategy_behavior',
                    'index_version': 'u_v1',
                    'effective_vector_method': 'price_volume',
                },
            },
            {
                'id': 2,
                'collection_name': 'strategy_behavior_embeddings',
                'entity_type': 'strategy',
                'entity_id': 'sid_peer',
                'profile_type': 'behavior',
                'model_id': 'strategy-behavior-v1',
                'vector_dim': 120,
                'metric': 'cosine',
                'version': 'u_v1',
                'signature': 'sig_peer',
                'embedding': [0.98, 0.02, 0.0],
                'metadata': {
                    'index_name': 'strategy_behavior',
                    'index_version': 'u_v1',
                    'effective_vector_method': 'price_volume',
                },
            },
        ]
        self.snapshots = [
            {
                'id': 9,
                'collection_name': 'strategy_behavior_embeddings',
                'index_version': 'u_v1',
                'status': 'active',
                'model_id': 'strategy-behavior-v1',
                'profile_type': 'behavior',
                'metric': 'cosine',
                'vector_dim': 120,
                'sample_count': 2,
                'bucket_count': 1,
                'metadata': {
                    'profile_version': 'u_v1',
                    'vector_method': 'price_volume',
                },
                'built_at': '2026-03-25T00:00:00+00:00',
                'activated_at': '2026-03-25T00:00:01+00:00',
            }
        ]
        self.index_items = [
            {
                'id': 101,
                'collection_name': 'strategy_behavior_embeddings',
                'index_version': 'u_v1',
                'profile_id': 2,
                'entity_type': 'strategy',
                'entity_id': 'sid_peer',
                'profile_type': 'behavior',
                'model_id': 'strategy-behavior-v1',
                'metric': 'cosine',
                'vector_dim': 120,
                'bucket_id': 'b_0000',
                'coarse_score': 0.97,
                'embedding': [0.98, 0.02, 0.0],
                'metadata': {
                    'index_name': 'strategy_behavior',
                    'index_version': 'u_v1',
                    'effective_vector_method': 'price_volume',
                    'signature': 'sig_peer',
                },
            }
        ]

    def supports_pgvector(self):
        return True

    def get_vector_backend(self):
        return 'pgvector'

    async def list_vector_collections(self, **_kwargs):
        return [dict(item) for item in self.collections]

    async def list_vector_profiles(self, **kwargs):
        rows = list(self.profiles)
        for field in ('collection_name', 'entity_type', 'entity_id', 'profile_type', 'version'):
            value = kwargs.get(field)
            if value:
                rows = [row for row in rows if row.get(field) == value]
        return [dict(item) for item in rows[: int(kwargs.get('limit') or len(rows))]]

    async def list_vector_index_snapshots(self, **kwargs):
        rows = list(self.snapshots)
        if kwargs.get('collection_name'):
            rows = [row for row in rows if row.get('collection_name') == kwargs.get('collection_name')]
        if kwargs.get('index_version'):
            rows = [row for row in rows if row.get('index_version') == kwargs.get('index_version')]
        if kwargs.get('status'):
            rows = [row for row in rows if row.get('status') == kwargs.get('status')]
        return [dict(item) for item in rows[: int(kwargs.get('limit') or len(rows))]]

    async def list_vector_index_items(self, **kwargs):
        rows = list(self.index_items)
        if kwargs.get('collection_name'):
            rows = [row for row in rows if row.get('collection_name') == kwargs.get('collection_name')]
        if kwargs.get('index_version'):
            rows = [row for row in rows if row.get('index_version') == kwargs.get('index_version')]
        if kwargs.get('profile_type'):
            rows = [row for row in rows if row.get('profile_type') == kwargs.get('profile_type')]
        return [dict(item) for item in rows[: int(kwargs.get('limit') or len(rows))]]

    async def search_vector_collection(self, **kwargs):
        assert kwargs['collection_name'] == 'strategy_behavior_embeddings'
        assert kwargs['exclude_entity_id'] == 'sid_query'
        return {
            'items': [dict(self.index_items[0], similarity=0.9523)],
            'backend_used': 'pgvector_index_item',
            'fallback_used': False,
            'fallback_reason': None,
            'index_version': 'u_v1',
            'profile_version': 'u_v1',
            'query_bucket_id': 'b_0000',
            'candidate_bucket_ids': ['b_0000'],
        }


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


@pytest.mark.asyncio
async def test_build_strategy_profile_dual_writes_unified_vector_profile(monkeypatch):
    import strategy_factory

    async def _fake_build_strategy_panels(*_args, **_kwargs):
        return {
            'strategy_returns': np.linspace(0.001, 0.04, 40, dtype=np.float64),
            'holdings': [{'code': '600519', 'weight': 0.4}],
            'factor_panel': np.ones((40, 3), dtype=np.float64),
            'return_panel': np.full((40, 3), 0.01, dtype=np.float64),
        }

    monkeypatch.setattr(strategy_factory, 'build_strategy_panels', _fake_build_strategy_panels)

    platform = StrategyVectorPlatform()
    monkeypatch.setattr(platform.engine, 'kline_to_vector', lambda _klines, _method: np.asarray([0.2, 0.4, 0.6]))
    db = _DualWriteDb()

    result = await platform.build_strategy_profile(
        db,
        {'id': 'sid_dual', 'name': 'Dual Write', 'strategy_type': 'momentum', 'params': {'lookback': 20}},
        vector_method='price_volume',
        index_name='strategy_behavior',
        index_version='u_v1',
    )
    assert result is not None
    expected_collection_name = platform._strategy_collection_name(
        index_name='strategy_behavior',
        model_id=result['model_id'],
        vector_dim=db.saved_strategy_profiles[0]['vector_dim'],
        metric=db.saved_strategy_profiles[0]['metric'],
    )

    assert db.saved_strategy_profiles[0]['strategy_id'] == 'sid_dual'
    assert db.saved_collections[0]['collection_name'] == expected_collection_name
    assert db.saved_collections[0]['entity_family'] == 'strategy_behavior'
    assert db.saved_unified_profiles[0]['collection_name'] == expected_collection_name
    assert db.saved_unified_profiles[0]['entity_type'] == 'strategy'
    assert db.saved_unified_profiles[0]['entity_id'] == 'sid_dual'
    assert db.saved_unified_profiles[0]['version'] == 'u_v1'
    assert db.saved_unified_profiles[0]['metadata']['legacy_profile_id'] == 1
    assert db.saved_registries[-1]['metadata']['unified_collection_name'] == expected_collection_name


@pytest.mark.asyncio
async def test_search_similar_prefers_unified_vector_collection():
    platform = StrategyVectorPlatform()
    db = _UnifiedStrategyDb()

    result = await platform.search_similar(
        db,
        'sid_query',
        profile_type='behavior',
        limit=5,
        index_name='strategy_behavior',
        index_version='u_v1',
    )

    assert result['count'] == 1
    assert result['backend_requested'] == 'pgvector'
    assert result['backend_used'] == 'pgvector'
    assert result['fallback_used'] is False
    assert result['active_index']['source'] == 'unified_snapshot'
    assert result['active_index']['collection_name'] == 'strategy_behavior_embeddings'
    assert result['items'][0]['strategy_id'] == 'sid_peer'
    assert result['items'][0]['retrieval_mode'] == 'unified_pgvector_ann'
    assert result['items'][0]['collection_name'] == 'strategy_behavior_embeddings'


@pytest.mark.asyncio
async def test_strategy_manager_vector_actions_support_unified_only_db(monkeypatch):
    mcp = _DummyMCP()
    sm_mod.register_strategy_manager(mcp)
    monkeypatch.setattr(sm_mod, 'get_db', lambda: _UnifiedStrategyDb())

    profiles = await mcp.strategy_manager(action='vector_profiles', kwargs='{"strategy_id":"sid_query"}')
    snapshots = await mcp.strategy_manager(action='vector_index_snapshots', kwargs='{"index_name":"strategy_behavior"}')

    assert profiles['success'] is True
    assert profiles['data']['count'] == 1
    assert profiles['data']['items'][0]['strategy_id'] == 'sid_query'
    assert profiles['data']['items'][0]['collection_name'] == 'strategy_behavior_embeddings'

    assert snapshots['success'] is True
    assert snapshots['data']['count'] == 1
    assert snapshots['data']['latest']['source'] == 'unified_snapshot'
    assert snapshots['data']['latest']['collection_name'] == 'strategy_behavior_embeddings'


@pytest.mark.asyncio
async def test_unified_health_check_reports_counts_without_legacy_tables():
    platform = StrategyVectorPlatform()
    db = _UnifiedStrategyDb()

    result = await platform.health_check(db, index_name='strategy_behavior', limit_versions=10)

    assert result['health_mode'] == 'unified'
    assert result['backend_requested'] == 'pgvector'
    assert result['backend_used'] == 'pgvector'
    assert result['counts']['profiles'] == 2
    assert result['counts']['index_items'] == 1
    assert result['active_index']['collection_name'] == 'strategy_behavior_embeddings'

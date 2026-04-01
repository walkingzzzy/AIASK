from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class TestVectorAnnSearchActions:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_vector_ann_search_and_snapshot_actions(self, setup):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        mcp, db = setup
        await db.save_strategy({'id': 'sid_ann_1', 'name': 'ANN1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_ann_2', 'name': 'ANN2', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 22}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_ann_3', 'name': 'ANN3', 'strategy_type': 'mean_reversion', 'status': 'listed', 'params': {'lookback': 5}, 'factor_weights': {}})
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'ann_sig_1', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.98, 0.05, 0.0], 'signature': 'ann_sig_2', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_ann_3', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [-1.0, 0.0, 0.0], 'signature': 'ann_sig_3', 'backend': 'index',
            'index_version': 'ann_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'ann_v1'},
        })

        platform = StrategyVectorPlatform()
        persisted = await platform.build_persisted_ann_index(db, index_name='strategy_behavior', index_version='ann_v1', profile_type='behavior', task_run_id=11, source='test_case')

        snapshots = await mcp.strategy_manager(action='vector_index_snapshots', kwargs=json.dumps({'index_name': 'strategy_behavior', 'limit': 10}))
        search = await mcp.strategy_manager(action='vector_ann_search', kwargs=json.dumps({'strategy_id': 'sid_ann_1', 'index_version': 'ann_v1', 'limit': 5}))

        assert persisted['items_count'] == 3
        assert snapshots['success'] is True
        assert snapshots['data']['count'] >= 1
        assert snapshots['data']['latest']['index_version'] == 'ann_v1'
        assert search['success'] is True
        assert search['data']['count'] >= 1
        assert search['data']['backend_requested'] == 'pgvector'
        assert search['data']['backend_used'] == 'index'
        assert search['data']['fallback_used'] is True
        assert search['data']['fallback_reason'] == 'preferred_backend_unavailable'
        assert search['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert search['data']['fallback_allowed'] is True
        assert search['data']['index_name'] == 'strategy_behavior'
        assert search['data']['index_version'] == 'ann_v1'
        assert search['data']['active_index']['index_version'] == 'ann_v1'
        assert search['data']['active_index']['backend'] == 'index'
        assert search['data']['items'][0]['strategy_id'] == 'sid_ann_2'
        assert search['data']['items'][0]['retrieval_mode'] == 'persisted_ann'
        assert search['data']['items'][0]['candidate_count'] >= 1

    @pytest.mark.asyncio
    async def test_vector_index_snapshots_preserve_history_per_version(self, setup):
        _, db = setup

        await db.save_strategy_vector_index_snapshot({
            'index_name': 'strategy_behavior',
            'index_version': 'v9',
            'status': 'building',
        })
        await db.save_strategy_vector_index_snapshot({
            'index_name': 'strategy_behavior',
            'index_version': 'v9',
            'status': 'active',
        })

        rows = await db.list_strategy_vector_index_snapshots(
            index_name='strategy_behavior',
            index_version='v9',
            limit=10,
        )
        latest_only = await db.list_strategy_vector_index_snapshots(
            index_name='strategy_behavior',
            limit=10,
            latest_only=True,
        )

        assert [item.get('status') for item in rows[:2]] == ['active', 'building']
        assert any(
            item.get('index_version') == 'v9' and item.get('status') == 'active'
            for item in latest_only
        )
        assert not any(
            item.get('index_version') == 'v9' and item.get('status') == 'building'
            for item in latest_only
        )

    @pytest.mark.asyncio
    async def test_vector_ann_search_uses_pgvector_backend_when_available(self, setup):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        mcp, db = setup
        db._pgvector_enabled = True
        await db.save_strategy({'id': 'sid_pg_1', 'name': 'PG1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_pg_2', 'name': 'PG2', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 21}, 'factor_weights': {}})
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_pg_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'pg_sig_1', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'pg_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'pg_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_pg_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.99, 0.01, 0.0], 'signature': 'pg_sig_2', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'pg_v1', 'metadata': {'index_name': 'strategy_behavior', 'index_version': 'pg_v1'},
        })

        platform = StrategyVectorPlatform()
        await platform.build_persisted_ann_index(db, index_name='strategy_behavior', index_version='pg_v1', profile_type='behavior', task_run_id=21, source='test_case')

        search = await mcp.strategy_manager(action='vector_ann_search', kwargs=json.dumps({'strategy_id': 'sid_pg_1', 'index_version': 'pg_v1', 'limit': 5}))

        assert search['success'] is True
        assert search['data']['count'] >= 1
        assert search['data']['backend_requested'] == 'pgvector'
        assert search['data']['backend_used'] == 'pgvector'
        assert search['data']['fallback_used'] is False
        assert search['data']['fallback_reason'] is None
        assert search['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert search['data']['fallback_allowed'] is True
        assert search['data']['index_name'] == 'strategy_behavior'
        assert search['data']['index_version'] == 'pg_v1'
        assert search['data']['active_index']['index_version'] == 'pg_v1'
        assert search['data']['active_index']['backend'] == 'pgvector'
        assert search['data']['items'][0]['strategy_id'] == 'sid_pg_2'
        assert search['data']['items'][0]['retrieval_mode'] == 'pgvector_ann'
        assert search['data']['items'][0]['backend'] == 'pgvector'

    @pytest.mark.asyncio
    async def test_vector_health_action_reports_counts_and_hnsw_indexes(self, setup):
        mcp, db = setup
        db._pgvector_enabled = True
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_vh_1', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': 'vh_sig_1', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'created_at': '2026-03-08T00:00:00+00:00',
            'metadata': {'index_name': 'strategy_behavior', 'index_version': 'vh_v1'},
        })
        await db.save_strategy_vector_profile({
            'strategy_id': 'sid_vh_2', 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
            'vector_dim': 3, 'embedding': [0.9, 0.1, 0.0], 'signature': 'vh_sig_2', 'backend': 'pgvector',
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'created_at': '2026-03-08T00:01:00+00:00',
            'metadata': {'index_name': 'strategy_behavior', 'index_version': 'vh_v1'},
        })
        await db.save_vector_index_registry({
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'status': 'active', 'backend': 'pgvector',
            'sample_count': 2, 'created_at': '2026-03-08T00:02:00+00:00',
        })
        await db.save_strategy_vector_index_snapshot({
            'index_name': 'strategy_behavior', 'index_version': 'vh_v1', 'status': 'active', 'backend': 'pgvector',
            'profile_count': 2, 'bucket_count': 1, 'vector_dim': 3,
            'built_at': '2026-03-08T00:03:00+00:00', 'activated_at': '2026-03-08T00:03:00+00:00',
        })
        await db.replace_strategy_vector_index_items('strategy_behavior', 'vh_v1', [
            {
                'profile_id': 1, 'strategy_id': 'sid_vh_1', 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 1.0,
                'embedding': [1.0, 0.0, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': '2026-03-08T00:04:00+00:00',
            },
            {
                'profile_id': 2, 'strategy_id': 'sid_vh_2', 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 0.9,
                'embedding': [0.9, 0.1, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': '2026-03-08T00:04:30+00:00',
            },
        ])
        await db.ensure_strategy_vector_profile_pgvector_index('strategy_behavior', 'vh_v1', 3, profile_type='behavior')
        await db.ensure_strategy_vector_index_item_pgvector_index('strategy_behavior', 'vh_v1', 3)

        health = await mcp.strategy_manager(action='vector_health', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'limit_versions': 5,
            'include_hnsw_indexes': True,
        }))

        assert health['success'] is True
        assert health['data']['backend'] == 'pgvector'
        assert health['data']['backend_requested'] == 'pgvector'
        assert health['data']['backend_used'] == 'pgvector'
        assert health['data']['fallback_used'] is False
        assert health['data']['fallback_reason'] is None
        assert health['data']['production_backend_standard'] == 'pgvector_with_observable_fallback'
        assert health['data']['fallback_allowed'] is True
        assert health['data']['active_index']['index_name'] == 'strategy_behavior'
        assert health['data']['active_index']['index_version'] == 'vh_v1'
        assert health['data']['active_index']['backend'] == 'pgvector'
        assert health['data']['active_index']['source'] == 'snapshot'
        assert health['data']['counts']['profiles'] == 2
        assert health['data']['counts']['profile_store'] == 2
        assert health['data']['counts']['index_items'] == 2
        assert health['data']['counts']['index_item_store'] == 2
        assert health['data']['hnsw_index_count'] == 2
        assert health['data']['versions'][0]['index_version'] == 'vh_v1'
        assert health['data']['versions'][0]['profile_store_rows'] == 2
        assert health['data']['versions'][0]['index_item_store_rows'] == 2

    @pytest.mark.asyncio
    async def test_build_profiles_for_strategies_builds_profiles_concurrently(self, monkeypatch):
        from akshare_mcp.services.vector_platform import StrategyVectorPlatform

        platform = StrategyVectorPlatform()
        db = MagicMock()
        db.save_vector_index_registry = AsyncMock()
        db.supports_pgvector = lambda: False

        active = 0
        max_active = 0

        async def _build_profile(_db, strategy, profile_type='behavior', vector_method='price_volume', index_name='strategy_behavior', index_version='v1'):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                'id': f"profile_{strategy['id']}",
                'strategy_id': strategy['id'],
                'profile_type': profile_type,
                'vector_method': vector_method,
                'metric': 'cosine',
                'vector_dim': 3,
                'embedding': [1.0, 0.0, 0.0],
            }

        monkeypatch.setattr(platform, 'build_strategy_profile', _build_profile)

        result = await platform.build_profiles_for_strategies(
            db,
            strategies=[{'id': f's{i}'} for i in range(6)],
            profile_type='behavior',
            vector_method='price_volume',
            index_name='strategy_behavior',
            index_version='pytest_v1',
        )

        assert result['count'] == 6
        assert max_active > 1
        db.save_vector_index_registry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vector_cleanup_action_prunes_old_versions_and_hnsw_indexes(self, setup):
        mcp, db = setup
        db._pgvector_enabled = True

        async def seed(version: str, ts: str, strategy_id: str):
            await db.save_strategy_vector_profile({
                'strategy_id': strategy_id, 'profile_type': 'behavior', 'vector_method': 'price_volume', 'metric': 'cosine',
                'vector_dim': 3, 'embedding': [1.0, 0.0, 0.0], 'signature': f'{version}_sig', 'backend': 'pgvector',
                'index_name': 'strategy_behavior', 'index_version': version, 'created_at': ts,
                'metadata': {'index_name': 'strategy_behavior', 'index_version': version},
            })
            await db.save_vector_index_registry({
                'index_name': 'strategy_behavior', 'index_version': version, 'status': 'active', 'backend': 'pgvector',
                'sample_count': 1, 'created_at': ts,
            })
            await db.save_strategy_vector_index_snapshot({
                'index_name': 'strategy_behavior', 'index_version': version, 'status': 'active', 'backend': 'pgvector',
                'profile_count': 1, 'bucket_count': 1, 'vector_dim': 3, 'built_at': ts, 'activated_at': ts,
            })
            await db.replace_strategy_vector_index_items('strategy_behavior', version, [{
                'profile_id': len(db._vector_profiles), 'strategy_id': strategy_id, 'profile_type': 'behavior', 'vector_method': 'price_volume',
                'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_0', 'coarse_score': 1.0,
                'embedding': [1.0, 0.0, 0.0], 'metadata': {'backend': 'pgvector'}, 'created_at': ts,
            }])
            await db.ensure_strategy_vector_profile_pgvector_index('strategy_behavior', version, 3, profile_type='behavior')
            await db.ensure_strategy_vector_index_item_pgvector_index('strategy_behavior', version, 3)

        await seed('cleanup_v1', '2026-03-07T00:00:00+00:00', 'sid_cleanup_1')
        await seed('cleanup_v2', '2026-03-08T00:00:00+00:00', 'sid_cleanup_2')
        await seed('cleanup_v3', '2026-03-09T00:00:00+00:00', 'sid_cleanup_3')

        preview = await mcp.strategy_manager(action='vector_cleanup', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'keep_versions': 1,
            'dry_run': True,
            'cleanup_hnsw': True,
        }))
        cleaned = await mcp.strategy_manager(action='vector_cleanup', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'keep_versions': 1,
            'dry_run': False,
            'cleanup_hnsw': True,
        }))
        health = await mcp.strategy_manager(action='vector_health', kwargs=json.dumps({
            'index_name': 'strategy_behavior',
            'limit_versions': 10,
            'include_hnsw_indexes': True,
        }))

        assert preview['success'] is True
        assert set(preview['data']['target_versions']) == {'cleanup_v1', 'cleanup_v2'}
        assert cleaned['success'] is True
        assert cleaned['data']['deleted']['vector_index_registry'] == 2
        assert cleaned['data']['deleted']['vector_index_snapshots'] == 2
        assert cleaned['data']['deleted']['vector_profiles'] == 2
        assert cleaned['data']['deleted']['vector_profile_store'] == 2
        assert cleaned['data']['deleted']['vector_index_items'] == 2
        assert cleaned['data']['deleted']['vector_index_item_store'] == 2
        assert cleaned['data']['deleted']['hnsw_indexes'] == 4
        assert health['success'] is True
        assert [item['index_version'] for item in health['data']['versions']] == ['cleanup_v3']
        assert health['data']['hnsw_index_count'] == 2


class TestIncubationPipelineActions:
    @pytest.fixture
    def setup(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, "get_db", lambda: db)
        return mcp, db

    @pytest.mark.asyncio
    async def test_incubation_pipeline_auto_promotes_strategy(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action='create', kwargs=json.dumps({
            'name': '孵化晋级策略', 'strategy_type': 'momentum', 'params': {'lookback': 20},
        }))
        sid = created['data']['strategy_id']
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': 1.3, 'max_drawdown': -0.08})
        db._signal_stats[sid] = {
            'total_signals': 24,
            'hit_rate': {1: 0.54, 5: 0.62, 10: 0.58, 20: 0.57},
            'forward_ic': {1: 0.01, 5: 0.03, 10: 0.02, 20: 0.01},
            'forward_sharpe': {1: 0.10, 5: 0.9, 10: 0.7, 20: 0.5},
        }
        await db.save_strategy_incubation_account(sid, 'acct_pipe', stage='candidate', status='active')
        metric_dates = [f'2026-02-{day:02d}' for day in range(17, 29)] + [f'2026-03-{day:02d}' for day in range(1, 9)]
        for offset, metric_date in enumerate(metric_dates):
            await db.save_strategy_incubation_metric(sid, metric_date, {
                'account_id': 'acct_pipe',
                'stage': 'candidate',
                'decision': 'promote',
                'nav': 1.05 + offset * 0.002,
                'sharpe_ratio': 1.2,
                'max_drawdown': 0.08,
                'hit_rate_5d': 0.62,
                'forward_sharpe_5d': 0.85,
                'total_signals': 24,
                'total_orders': 6,
                'total_trades': 4,
            })

        run = await mcp.strategy_manager(action='incubation_pipeline_run', kwargs=json.dumps({'strategy_id': sid, 'auto_apply_review': True}))
        snapshots = await mcp.strategy_manager(action='incubation_pipeline', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': sid}))
        capabilities = await mcp.strategy_manager(action='capabilities')

        assert run['success'] is True
        assert run['data']['snapshot']['pipeline_stage'] in {'graduation_ready', 'promoted'}
        assert run['data']['auto_promoted'] is True
        assert snapshots['data']['count'] >= 1
        assert detail['data']['latest_incubation_pipeline_snapshot']['pipeline_stage'] == 'promoted'
        assert detail['data']['strategy']['status'] == 'listed'
        assert capabilities['data']['incubation_pipeline'] is True

    @pytest.mark.asyncio
    async def test_incubation_pipeline_batch_records_failed_stage(self, setup):
        mcp, db = setup
        created = await mcp.strategy_manager(action='create', kwargs=json.dumps({
            'name': '孵化阻塞策略', 'strategy_type': 'mean_reversion', 'params': {'lookback': 5},
        }))
        sid = created['data']['strategy_id']
        await db.update_strategy_status(sid, 'submitted')
        await db.update_strategy_status(sid, 'incubating')
        await db.save_strategy_metrics(sid, 'all', {'sharpe_ratio': -0.2, 'max_drawdown': -0.35})
        db._signal_stats[sid] = {
            'total_signals': 12,
            'hit_rate': {1: 0.42, 5: 0.28, 10: 0.25, 20: 0.24},
            'forward_ic': {1: 0.0, 5: -0.01, 10: -0.03, 20: -0.02},
            'forward_sharpe': {1: -0.1, 5: -0.4, 10: -0.5, 20: -0.6},
        }
        await db.save_strategy_incubation_account(sid, 'acct_fail', stage='observe', status='active')
        await db.save_strategy_incubation_metric(sid, '2026-03-08', {
            'account_id': 'acct_fail', 'stage': 'observe', 'decision': 'halt', 'nav': 0.91, 'sharpe_ratio': -0.3,
            'max_drawdown': 0.35, 'hit_rate_5d': 0.28, 'forward_sharpe_5d': -0.4, 'total_signals': 12, 'total_orders': 2, 'total_trades': 1,
        })
        await db.save_strategy_incubation_metric(sid, '2026-03-07', {
            'account_id': 'acct_fail', 'stage': 'observe', 'decision': 'halt', 'nav': 0.92, 'sharpe_ratio': -0.25,
            'max_drawdown': 0.32, 'hit_rate_5d': 0.29, 'forward_sharpe_5d': -0.3, 'total_signals': 12, 'total_orders': 1, 'total_trades': 1,
        })

        batch = await mcp.strategy_manager(action='incubation_pipeline_run', kwargs=json.dumps({'statuses': ['incubating'], 'auto_apply_review': False}))
        snapshots = await mcp.strategy_manager(action='incubation_pipeline', kwargs=json.dumps({'strategy_id': sid, 'limit': 10}))

        assert batch['success'] is True
        assert batch['data']['count'] >= 1
        assert batch['data']['stage_counts'].get('failed', 0) >= 1
        assert snapshots['data']['latest']['pipeline_stage'] == 'failed'
        assert snapshots['data']['latest']['pipeline_status'] == 'blocked'


class TestBacktestFilterReport:
    def test_report_entry_preserves_generation_metadata(self):
        entry = BacktestFilter._build_report_entry({
            'strategy_type': 'momentum',
            'generator_type': 'local_rule_v1',
            'params': {'lookback': 8, 'threshold': 0.01},
            'spawn_reason': 'test',
            'generation_reason': {'source': 'event_driven_local_fallback'},
            'target_symbols': ['601398'],
            'stock_pool': {'selection_mode': 'explicit', 'symbols': ['601398']},
            'selection_logic': ['follow trend'],
            'research_task': {'task_id': 'task_evt'},
            'event_context': {'event_id': 'evt_1'},
            'tags': ['ai_generated', 'llm_proxy_fallback'],
            'backtest_result': {'passed': True},
            'backtest_metrics': {'sharpe_ratio': 0.8},
        })

        assert entry['generator_type'] == 'local_rule_v1'
        assert entry['generation_reason']['source'] == 'event_driven_local_fallback'
        assert entry['research_task']['task_id'] == 'task_evt'
        assert entry['event_context']['event_id'] == 'evt_1'
        assert 'llm_proxy_fallback' in entry['tags']



__all__ = [name for name in globals() if name.startswith("Test")]

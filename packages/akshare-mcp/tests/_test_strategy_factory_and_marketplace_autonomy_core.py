from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestAutonomyEnhancementsCoreMixin:
    @pytest.mark.asyncio
    async def test_run_cycle_records_committee_reviews(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 20, 'threshold': 0.02}, name='ok', tags=['rule']),
            StrategySpec(strategy_type='unknown_type', params={'lookback': 1}, name='reject', tags=['rule']),
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        result = await service.run_cycle(db, snapshot={'date': '2026-03-07', 'fear_greed_index': 68}, limit=3, source='test')

        assert result['generated_count'] == 1
        assert result['generation']['count'] == result['generated_count']
        assert result['review']['reviewed_count'] == result['reviewed_count']
        assert result['review']['rejected_count'] == result['rejected_count']
        assert result['task_run']['id'] == result['task_run_id']
        assert result['experiments']['count'] == 1
        assert result['experiments']['items'] == result['experiment_records']
        assert result['artifacts']['experiments'] == result['experiment_records']
        assert result['submission']['result'] is None
        assert result['reviewed_count'] == 1
        assert result['rejected_count'] == 1
        assert any(item['decision'] in {'accept', 'reject', 'revise'} for item in result['committee_reviews'])
        experiments = await db.list_strategy_generation_experiments(limit=10)
        assert experiments[0]['evaluation']['committee_review']['decision'] in {'accept', 'revise'}
        assert result['champion']['experiment_id'] == experiments[0]['experiment_id']


    @pytest.mark.asyncio
    async def test_run_cycle_exposes_factor_research_across_result_and_event_payload(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='value_factor', params={'lookback': 30}, name='factor-aware', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        factor_research = {
            'active_factors': ['value', 'quality'],
            'summary': {'top_factor_names': ['value', 'quality']},
            'preferred_strategy_types': ['value_factor', 'quality_factor'],
            'degraded': False,
        }
        research_task = {
            'task_id': 'task_factor_ctx',
            'theme': 'factor_rotation_value',
            'strategy_preferences': ['value_factor'],
        }

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 63, 'factor_research': factor_research},
            limit=3,
            source='test',
            research_task=research_task,
        )

        assert result['factor_research'] == factor_research
        assert result['generation_stats']['factor_research'] == factor_research
        assert result['research_task']['metadata']['factor_research'] == factor_research

        task_runs = await db.list_strategy_task_runs(limit=10)
        assert task_runs[0]['result']['factor_research'] == factor_research
        assert task_runs[0]['result']['research_task']['metadata']['factor_research'] == factor_research

        domain_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.completed', limit=10)
        assert domain_events[0]['payload']['factor_research'] == factor_research
        assert domain_events[0]['payload']['research_task']['metadata']['factor_research'] == factor_research

    @pytest.mark.asyncio
    async def test_run_cycle_exposes_lifecycle_across_result_task_run_and_event(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 15}, name='lifecycle-ok', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test',
        )

        lifecycle = result['lifecycle']
        phases = {item['name']: item for item in lifecycle['phases']}

        assert lifecycle['state'] == 'completed'
        assert lifecycle['current_phase'] == 'completed'
        assert lifecycle['terminal_phase'] == 'completed'
        assert lifecycle['phase_order'] == ['prepared', 'generating', 'reviewing', 'recording', 'submitting', 'completed']
        assert phases['prepared']['status'] == 'completed'
        assert phases['generating']['status'] == 'completed'
        assert phases['reviewing']['status'] == 'completed'
        assert phases['recording']['status'] == 'completed'
        assert phases['submitting']['status'] == 'skipped'
        assert phases['submitting']['reason'] == 'auto_submit_disabled'
        assert phases['completed']['status'] == 'completed'
        assert result['task_run']['lifecycle']['state'] == 'completed'

        task_runs = await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=10)
        assert task_runs[0]['result']['lifecycle']['state'] == 'completed'
        assert task_runs[0]['result']['lifecycle']['phase_status_counts']['completed'] >= 4

        domain_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.completed', limit=10)
        assert domain_events[0]['payload']['lifecycle']['state'] == 'completed'
        assert domain_events[0]['payload']['lifecycle']['phase_status_counts']['skipped'] == 1


    @pytest.mark.asyncio
    async def test_run_cycle_auto_submit_preserves_parent_lineage(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_parent_cycle',
            'name': 'ParentCycle',
            'strategy_type': 'momentum',
            'params': {'lookback': 20, 'threshold': 0.02},
            'author_id': 'u1',
            'status': 'listed',
        })

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 18, 'threshold': 0.018}, name='child-from-parent', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        async def _fake_submit(self, candidates, snapshot, db_):
            return {
                'items': [{
                    'experiment_id': candidates[0]['experiment_id'],
                    'strategy_id': 'sid_generated_child',
                    'passed': True,
                    'duplicate': False,
                }]
            }

        monkeypatch.setattr('akshare_mcp.services.strategy_factory.StrategySubmitter.submit', _fake_submit)

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 72},
            limit=1,
            source='test',
            parent_strategy_id='sid_parent_cycle',
            auto_submit=True,
        )

        experiments = await db.list_strategy_generation_experiments(parent_strategy_id='sid_parent_cycle', limit=10)
        child_lookup = await db.list_strategy_generation_experiments(strategy_id='sid_generated_child', limit=10)
        task_run = (await db.list_strategy_task_runs(strategy_id='sid_parent_cycle', task_name='strategy_ai_cycle', limit=5))[0]

        assert result['generated_count'] == 1
        assert result['generation']['count'] == 1
        assert result['submission']['auto_submit'] is True
        assert result['submission']['submitted_count'] == 1
        assert result['submission']['passed_count'] == 1
        assert result['submission']['result'] == result['submitted']
        assert result['champion']['generated_strategy_id'] == 'sid_generated_child'
        assert result['experiments']['status_counts']['accepted'] == 1
        assert len(experiments) == 1
        assert experiments[0]['strategy_id'] == 'sid_parent_cycle'
        assert experiments[0]['parent_strategy_id'] == 'sid_parent_cycle'
        assert experiments[0]['generated_strategy_id'] == 'sid_generated_child'
        assert experiments[0]['task_run_id'] == result['task_run_id']
        assert experiments[0]['status'] == 'accepted'
        assert experiments[0]['evaluation']['committee_review']['is_champion'] is True
        assert child_lookup[0]['generated_strategy_id'] == 'sid_generated_child'
        assert task_run['result']['champion']['experiment_id'] == experiments[0]['experiment_id']

    @pytest.mark.asyncio
    async def test_run_cycle_submission_failure_keeps_experiments_and_task_run_sections(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 16, 'threshold': 0.015}, name='reject-at-submit', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])

        async def _fake_submit(self, candidates, snapshot, db_):
            return {
                'submitted': len(candidates),
                'gate_3_passed': 0,
                'gate_3_failed': len(candidates),
                'gate_3_failure_reason_topn': [{'reason_code': 'risk_guard', 'count': len(candidates)}],
                'items': [{
                    'experiment_id': candidates[0]['experiment_id'],
                    'passed': False,
                    'duplicate': False,
                    'reason_code': 'risk_guard',
                }],
            }

        monkeypatch.setattr('akshare_mcp.services.strategy_factory.StrategySubmitter.submit', _fake_submit)

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-09', 'fear_greed_index': 49},
            limit=1,
            source='test',
            auto_submit=True,
        )

        experiments = await db.list_strategy_generation_experiments(limit=10)
        task_run = (await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=5))[0]

        assert result['submission']['auto_submit'] is True
        assert result['submission']['attempted'] is True
        assert result['submission']['submitted_count'] == 1
        assert result['submission']['failed_count'] == 1
        assert result['submission']['failure_reason_topn'][0]['reason_code'] == 'risk_guard'
        assert result['submission']['result'] == result['submitted']
        assert result['experiments']['count'] == 1
        assert result['experiments']['items'] == result['experiment_records']
        assert result['experiments']['status_counts']['rejected'] == 1
        assert experiments[0]['status'] == 'rejected'
        assert task_run['result']['submission']['failed_count'] == 1
        assert task_run['result']['experiments']['status_counts']['rejected'] == 1

    @pytest.mark.asyncio
    async def test_run_cycle_failure_persists_failed_lifecycle_and_domain_event(self):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec

        service = StrategyAutonomyService()
        db = _StrategyDB()

        service.rule_generator.generate = lambda *_args, **_kwargs: [
            StrategySpec(strategy_type='momentum', params={'lookback': 18}, name='broken-recording', tags=['rule'])
        ]
        service.llm_generator.generate = AsyncMock(return_value=[])
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.experiment_recorder.record_candidates = AsyncMock(side_effect=RuntimeError('recorder down'))

        with pytest.raises(RuntimeError, match='recorder down'):
            await service.run_cycle(
                db,
                snapshot={'date': '2026-03-09', 'fear_greed_index': 47},
                limit=1,
                source='test',
            )

        task_run = (await db.list_strategy_task_runs(task_name='strategy_ai_cycle', limit=5))[0]
        lifecycle = task_run['result']['lifecycle']

        assert task_run['status'] == 'failed'
        assert lifecycle['state'] == 'failed'
        assert lifecycle['failed_phase'] == 'recording'
        assert lifecycle['terminal_phase'] == 'failed'
        assert lifecycle['phase_status_counts']['failed'] == 1

        failed_events = await db.list_strategy_domain_events(event_type='strategy_ai_cycle.failed', limit=10)
        assert failed_events[0]['payload']['error'] == 'recorder down'
        assert failed_events[0]['payload']['lifecycle']['state'] == 'failed'
        assert failed_events[0]['payload']['lifecycle']['failed_phase'] == 'recording'


    @pytest.mark.asyncio
    async def test_bandit_optimizer_uses_experiment_feedback(self):
        from akshare_mcp.services.strategy_autonomy import BanditParameterOptimizer

        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_parent',
            'name': 'Parent',
            'strategy_type': 'momentum',
            'params': {'lookback': 20, 'threshold': 0.02},
            'author_id': 'u1',
            'status': 'listed',
        })
        await db.save_strategy_metrics('sid_parent', 'all', {'sharpe_ratio': 1.1, 'max_drawdown': -0.12})
        db._signal_stats['sid_parent'] = {'total_signals': 48, 'hit_rate': {5: 0.61}}
        await db.save_strategy_generation_experiment({
            'experiment_id': 'exp_good',
            'strategy_id': None,
            'parent_strategy_id': 'sid_parent',
            'generated_strategy_id': 'sid_child_good',
            'source': 'manual',
            'generator_type': 'rl_bandit',
            'optimizer_type': 'epsilon_greedy_feedback',
            'status': 'accepted',
            'evaluation': {'generation_reason': {'scale': 1.1}, 'committee_review': {'final_score': 0.82}},
            'result': {'passed': True},
        })
        await db.save_strategy_generation_experiment({
            'experiment_id': 'exp_bad',
            'strategy_id': None,
            'parent_strategy_id': 'sid_parent',
            'generated_strategy_id': 'sid_child_bad',
            'source': 'manual',
            'generator_type': 'rl_bandit',
            'optimizer_type': 'epsilon_greedy_feedback',
            'status': 'rejected',
            'evaluation': {'generation_reason': {'scale': 0.8}, 'committee_review': {'final_score': 0.31}},
            'result': {'passed': False},
        })

        optimizer = BanditParameterOptimizer()
        parent = await db.get_strategy('sid_parent')
        specs = await optimizer.evolve(db, parent, limit=2)

        assert len(specs) == 2
        feedback = specs[0].metadata['generation_reason']['bandit_feedback']
        assert specs[0].metadata['generation_reason']['scale'] == 1.1
        assert feedback['historical_reward_avg'] > 0
        assert '1.10' in feedback['known_scales']

    def test_dsl_rule_strategy_can_run_backtest(self):
        from akshare_mcp.services.backtest.engine import BacktestEngine
        prices = [10 - i * 0.04 for i in range(30)] + [8.8 + i * 0.08 for i in range(45)] + [12.4 - i * 0.07 for i in range(45)]
        klines = [
            {
                'date': f'2026-02-{(idx % 28) + 1:02d}',
                'open': round(price * 0.998, 4),
                'high': round(price * 1.01, 4),
                'low': round(price * 0.99, 4),
                'close': round(price, 4),
                'volume': 1000 + idx * 10,
            }
            for idx, price in enumerate(prices)
        ]
        dsl = {
            'version': '1.0',
            'timeframe': 'daily',
            'entry': {
                'all': [
                    {
                        'op': 'cross_above',
                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                    },
                    {
                        'op': 'gt',
                        'left': {'indicator': 'roc', 'field': 'close', 'window': 10},
                        'right': {'value': 0.01},
                    },
                ],
            },
            'exit': {
                'any': [
                    {
                        'op': 'cross_below',
                        'left': {'indicator': 'sma', 'field': 'close', 'window': 5},
                        'right': {'indicator': 'sma', 'field': 'close', 'window': 20},
                    },
                    {
                        'op': 'lt',
                        'left': {'indicator': 'roc', 'field': 'close', 'window': 5},
                        'right': {'value': -0.02},
                    },
                ],
            },
        }

        result = BacktestEngine.run_backtest('000001', klines, 'dsl_rule', {'dsl': dsl})

        assert result['success'] is True
        assert result['data']['strategy'] == 'dsl_rule'
        assert 'total_return' in result['data']

    def test_strategy_llm_config_can_load_from_mcp_env_file(self, tmp_path, monkeypatch):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        env_file = tmp_path / '.env'
        env_file.write_text(
            '\n'.join([
                'STRATEGY_LLM_ENABLED=1',
                'STRATEGY_LLM_PROVIDER=openai_compatible',
                'STRATEGY_LLM_BASE_URL=https://example.com/v1',
                'STRATEGY_LLM_API_KEY=test-key',
                'STRATEGY_LLM_MODEL=test-model',
                'STRATEGY_LLM_INITIAL_COMPACT_LEVEL=1',
                'STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK=2',
                'STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC=123',
                'STRATEGY_LLM_STRICT_MODE=1',
            ]),
            encoding='utf-8',
        )
        for key in [
            'STRATEGY_LLM_ENABLED', 'STRATEGY_LLM_PROVIDER', 'STRATEGY_LLM_BASE_URL',
            'STRATEGY_LLM_API_KEY', 'STRATEGY_LLM_MODEL', 'STRATEGY_LLM_INITIAL_COMPACT_LEVEL',
            'STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK', 'STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC',
            'STRATEGY_LLM_STRICT_MODE',
        ]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv('AKSHARE_MCP_ENV', str(env_file))

        config = StrategyLLMConfig.from_env()

        assert config.enabled is True
        assert config.base_url == 'https://example.com/v1'
        assert config.api_key == 'test-key'
        assert config.model == 'test-model'
        assert config.initial_compact_level == 1
        assert config.recent_timeout_minimal_streak == 2
        assert config.recent_timeout_cooldown_sec == 123.0
        assert config.strict is True

    @pytest.mark.asyncio
    async def test_register_experiment_uses_storage_get_db_injection(self, monkeypatch):
        import akshare_mcp.storage as storage_mod
        from akshare_mcp.services import artifact_registry as artifact_mod

        class _ArtifactDB:
            def __init__(self):
                self.saved = []

            async def save_artifact(self, artifact):
                self.saved.append(dict(artifact))
                return dict(artifact)

        db = _ArtifactDB()
        monkeypatch.setattr(storage_mod, 'get_db', lambda: db)

        artifact_mod.register_experiment({
            'experiment_id': 'exp_injected',
            'hypothesis': 'verify injected db getter',
            'method': 'unit_test',
            'parameters': {'alpha': 1},
            'status': 'running',
        })
        await asyncio.sleep(0)

        assert db.saved
        assert db.saved[0]['artifact_id'] == 'exp_injected'
        assert db.saved[0]['artifact_type'] == 'experiment'

    def test_compile_strategy_blueprint_can_tune_sparse_dsl(self):
        import pandas as pd
        from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

        prices = [10 + math.sin(idx / 4) * 0.8 + idx * 0.015 for idx in range(160)]
        volumes = [1000 + (idx % 12) * 120 for idx in range(160)]
        frame = pd.DataFrame({
            'open': prices,
            'high': [price * 1.01 for price in prices],
            'low': [price * 0.99 for price in prices],
            'close': prices,
            'volume': volumes,
        })
        blueprint = {
            'name': '稀疏 DSL',
            'dsl': {
                'version': '1.0',
                'timeframe': 'daily',
                'entry': {
                    'all': [
                        {
                            'op': 'cross_above',
                            'left': {'indicator': 'sma', 'field': 'close', 'window': 30},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 80},
                        },
                        {
                            'op': 'gt',
                            'left': {'indicator': 'volume_ratio', 'window': 20},
                            'right': {'value': 1.18},
                        },
                    ],
                },
                'exit': {
                    'any': [
                        {
                            'op': 'cross_below',
                            'left': {'indicator': 'sma', 'field': 'close', 'window': 30},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 80},
                        },
                    ],
                },
            },
        }

        compiled = compile_strategy_blueprint(blueprint, market_frame=frame, tune_for_factory=True)
        tuning = compiled['metadata']['dsl_tuning']
        activity = compiled['metadata']['dsl_activity']

        assert tuning['variants_evaluated'] > 1
        assert activity['score'] >= tuning['before']['score']
        assert activity['entry_count'] >= tuning['before']['entry_count']

    def test_compile_strategy_blueprint_supports_shorthand_llm_dsl(self):
        import pandas as pd
        from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

        prices = [10 + math.sin(i / 4) * 0.8 + i * 0.015 for i in range(160)]
        frame = pd.DataFrame({
            'open': prices,
            'high': [price * 1.01 for price in prices],
            'low': [price * 0.99 for price in prices],
            'close': prices,
            'volume': [1000 + (i % 12) * 120 for i in range(160)],
        })
        blueprint = {
            'name': '简写 DSL',
            'dsl': {
                'version': '1.0',
                'timeframe': 'daily',
                'entry': {
                    'all': [
                        {'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 20}}]},
                        {'gte': [{'volume_ratio': {'field': 'volume', 'window': 10}}, 0.98]},
                    ]
                },
                'exit': {
                    'any': [
                        {'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 10}}]},
                        {'lt': [{'rsi': {'field': 'close', 'window': 6}}, 45]},
                    ]
                },
            },
        }

        compiled = compile_strategy_blueprint(blueprint, market_frame=frame, tune_for_factory=True)
        dsl = compiled['params']['dsl']
        activity = compiled['metadata']['dsl_activity']

        entry_branch = dsl['entry'].get('all') or dsl['entry'].get('any') or []
        exit_branch = dsl['exit'].get('all') or dsl['exit'].get('any') or []

        assert entry_branch
        assert exit_branch
        assert activity['entry_count'] > 0
        assert activity['exit_count'] > 0
        assert activity['score'] > 0

    def test_backtest_filter_relaxes_thresholds_for_external_llm_prototype(self):
        flt = BacktestFilter()

        thresholds = flt._get_thresholds('dsl_rule', {'generator_type': 'external_llm', 'tags': ['external_llm']})
        fallback_thresholds = flt._get_thresholds('momentum', {'generator_type': 'local_rule_v1', 'tags': ['llm_proxy_fallback']})
        bandit_thresholds = flt._get_thresholds('momentum', {'generator_type': 'rl_bandit', 'parent_strategy_id': 'sid_parent'})

        assert thresholds['sharpe_min'] == 0.10
        assert thresholds['mdd_max'] == 0.45
        assert thresholds['trades_min'] == 1
        assert fallback_thresholds['sharpe_min'] == 0.10
        assert fallback_thresholds['mdd_max'] == 0.45
        assert fallback_thresholds['trades_min'] == 1
        assert bandit_thresholds['sharpe_min'] == 0.10
        assert bandit_thresholds['mdd_max'] == 0.45
        assert bandit_thresholds['trades_min'] == 1

    def test_strategy_llm_prompt_profiles_shrink_context_and_contract(self):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

        normal_system, normal_user = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-08', 'fear_greed_index': 61},
            market_summary={'rows': 120},
            research_context={
                'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61, 'hot_sectors': ['AI', '芯片']},
                'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                'symbol_insights': [
                    {'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'close': 88.1, 'return_5d': 0.02, 'return_20d': 0.12, 'volatility_20d': 0.03, 'trend_state': 'uptrend', 'price_vs_sma20': 'above', 'volume_ratio_20': 1.2},
                    {'code': '002371', 'name': '北方华创', 'industry': '芯片', 'close': 120.5, 'return_5d': 0.01, 'return_20d': 0.08, 'volatility_20d': 0.02, 'trend_state': 'uptrend', 'price_vs_sma20': 'above', 'volume_ratio_20': 1.1},
                ],
                'candidate_universe': [
                    {'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'market_cap': 100, 'pe_ratio': 20, 'pb_ratio': 3, 'return_20d': 0.12, 'trend_state': 'uptrend', 'volume_ratio_20': 1.2, 'screen_score': 0.9, 'factor_snapshot': {'momentum': 0.9, 'quality': 0.6}, 'financial_snapshot': {'revenue_growth': 0.2, 'profit_growth': 0.3, 'roe': 0.1}},
                    {'code': '002371', 'name': '北方华创', 'industry': '芯片', 'market_cap': 90, 'pe_ratio': 18, 'pb_ratio': 2.8, 'return_20d': 0.08, 'trend_state': 'uptrend', 'volume_ratio_20': 1.1, 'screen_score': 0.8, 'factor_snapshot': {'momentum': 0.7, 'quality': 0.5}, 'financial_snapshot': {'revenue_growth': 0.18, 'profit_growth': 0.24, 'roe': 0.11}},
                    {'code': '300750', 'name': '宁德时代', 'industry': '电池', 'market_cap': 80, 'pe_ratio': 16, 'pb_ratio': 2.1, 'return_20d': 0.03, 'trend_state': 'sideways', 'volume_ratio_20': 0.9, 'screen_score': 0.6, 'factor_snapshot': {'momentum': 0.4}, 'financial_snapshot': {'revenue_growth': 0.1, 'profit_growth': 0.09, 'roe': 0.08}},
                ],
                'population_state': {'listed_count': 12, 'incubating_count': 3, 'top_categories': {'momentum': 5}},
            },
            parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
            history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
            limit=2,
            research_task={'theme': 'chip_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']},
            compact_level=0,
        )
        minimal_system, minimal_user = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-08', 'fear_greed_index': 61},
            market_summary={'rows': 120},
            research_context={
                'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61, 'hot_sectors': ['AI', '芯片']},
                'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                'symbol_insights': [{'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'close': 88.1, 'return_20d': 0.12, 'trend_state': 'uptrend'}],
                'candidate_universe': [{'code': '688981', 'name': '中芯国际', 'industry': '芯片', 'return_20d': 0.12, 'trend_state': 'uptrend', 'volume_ratio_20': 1.2, 'screen_score': 0.9}],
            },
            parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
            history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
            limit=1,
            research_task={'theme': 'chip_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']},
            compact_level=2,
        )

        normal_payload = json.loads(normal_user)
        minimal_payload = json.loads(minimal_user)

        assert len(minimal_system) + len(minimal_user) < len(normal_system) + len(normal_user)
        assert len(minimal_system) < len(normal_system)
        assert minimal_payload['output_contract']['target_symbol_rule'] == 'prefer_intersection_with_research_task'
        assert minimal_payload['output_contract']['prefer_single_high_confidence_candidate'] is True
        assert minimal_payload['output_contract']['required'] == ['candidates']
        assert minimal_payload['output_contract']['analysis_fields'] == []
        assert len(minimal_payload['output_contract']['candidate_fields']) < len(normal_payload['output_contract']['candidate_fields'])
        assert set(minimal_payload['research_task'].keys()) <= {'task_id', 'opportunity_type', 'target_symbols'}
        assert 'output_example' in minimal_payload
        assert minimal_payload['output_example']['candidates'][0]['dsl']['metadata']['target_symbols']

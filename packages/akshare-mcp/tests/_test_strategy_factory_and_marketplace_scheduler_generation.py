from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestStrategyFactorySchedulerGenerationMixin:
    async def test_market_frame_prefers_research_task_targets(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        calls = []

        async def _get_klines(code, limit=180):
            calls.append(code)
            if code == '688981':
                return _make_klines(150)
            return []

        db = MagicMock()
        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.list_stock_universe = AsyncMock(return_value=[{'code': '601398'}])

        frame = await generator._build_market_frame(db, research_task={'target_symbols': ['688981', '002371']})

        assert frame is not None
        assert calls[0] == '688981'

    @pytest.mark.asyncio
    async def test_market_frame_normalizes_descending_db_klines(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        ascending = _make_klines(150, base=10.0, trend=0.01, noise=0.0)
        descending = list(reversed([
            {**row, 'date': row.get('time')}
            for row in ascending
        ]))

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=descending)

        frame = await generator._frame_from_codes(db, ['688981'], limit=180)

        assert frame is not None
        assert float(frame['close'].iloc[0]) < float(frame['close'].iloc[-1])

    @pytest.mark.asyncio
    async def test_generate_uses_research_context_frame_cache_when_primary_frame_missing(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _no_frame(_db, research_task=None):
            return None

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        async def _frame_cache(_db, research_context=None, research_task=None):
            return {'688981': sample_frame}

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{
                        'name': 'cache_frame_candidate',
                        'description': 'uses cached frame',
                        'rationale': 'test',
                        'target_symbols': ['688981'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                        'selection_logic': ['test'],
                        'dsl': {
                            'version': '1.0',
                            'timeframe': 'daily',
                            'entry': {'all': [{'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 12}}]}]},
                            'exit': {'any': [{'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 8}}]}]},
                            'metadata': {'target_symbols': ['688981']},
                        },
                        'tags': ['external_llm'],
                    }],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _no_frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        generator._build_symbol_frame_cache = _frame_cache

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981']})
        report = generator.get_last_report()

        assert len(specs) == 1
        assert report['market_frame_source'] == 'research_context_frame_cache'
        assert report['market_frame_ready'] is True
        assert report['external_provider']['status'] in {'succeeded', 'fallback_only'}

    @pytest.mark.asyncio
    async def test_generate_local_fallback_preserves_research_task_targets(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMRequestError

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError('timeout', metrics={'last_error_type': 'ReadTimeout', 'last_error': 'ReadTimeout'})

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981'], 'task_id': 'task_chip'})
        report = generator.get_last_report()
        candidate = specs[0].to_candidate('strategy_factory', 'exp_local_fallback')

        assert len(specs) == 1
        assert specs[0].metadata['generator_type'] == 'local_rule_v1'
        assert 'llm_proxy_fallback' in specs[0].tags
        assert specs[0].metadata['target_symbols'] == ['688981']
        assert specs[0].metadata['stock_pool']['symbols'] == ['688981']
        assert report['external_provider']['status'] == 'failed'
        assert candidate['target_symbols'] == ['688981']
        assert candidate['stock_pool']['symbols'] == ['688981']
        assert candidate['generator_type'] == 'local_rule_v1'

    @pytest.mark.asyncio
    async def test_generate_targeted_research_avoids_mixing_local_specs_when_external_fallback_exists(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{
                        'name': 'event_fallback_candidate',
                        'description': '消息驱动后的延续性。',
                        'rationale': 'test',
                        'target_symbols': ['688981'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                        'selection_logic': ['test'],
                        'dsl': {
                            'version': '1.0',
                            'timeframe': 'daily',
                            'entry': {'all': [{'gt': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 12}}]}]},
                            'exit': {'any': [{'cross_below': [{'field': 'close'}, {'ema': {'field': 'close', 'window': 8}}]}]},
                            'metadata': {'target_symbols': ['688981']},
                        },
                        'tags': ['external_llm'],
                    }],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(MagicMock(), limit=2, snapshot={'date': '2026-03-08'}, research_task={'task_id': 'task_evt', 'target_symbols': ['688981']})

        assert len(specs) == 1
        assert specs[0].metadata['generator_type'] == 'external_llm'

    @pytest.mark.asyncio
    async def test_generate_fans_out_external_requests_and_dedupes_aggregated_specs(self, monkeypatch):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig
        from akshare_mcp.services.strategy_spec import StrategySpec
        from akshare_mcp.services.strategy_factory.constants import LLM_FAN_OUT_COUNT

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

        spec_a = StrategySpec(
            strategy_type='momentum',
            params={'lookback': 20, 'threshold': 0.02},
            name='fanout_a',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )
        spec_a_dup = StrategySpec(
            strategy_type='momentum',
            params={'lookback': 20, 'threshold': 0.02},
            name='fanout_a_dup',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )
        spec_b = StrategySpec(
            strategy_type='rsi',
            params={'rsi_period': 14, 'oversold': 30, 'overbought': 70},
            name='fanout_b',
            metadata={'generator_type': 'external_llm', 'target_symbols': ['688981'], 'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']}},
        )

        async def _fanout_request(**kwargs):
            request_index = int(kwargs.get('request_index') or 0)
            specs = [spec_a] if request_index == 1 else [spec_a_dup, spec_b]
            return {
                'status': 'succeeded',
                'request_index': request_index,
                'analysis': {'request_index': request_index},
                'request_report': {
                    'request_index': request_index,
                    'request_limit': kwargs.get('request_limit'),
                    'status': 'succeeded',
                    'viable_candidate_count': len(specs),
                },
                'successful_without_specs': False,
                'all_specs': list(specs),
                'viable_specs': list(specs),
                'exception': None,
            }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        monkeypatch.setattr(generator, '_run_external_provider_request', AsyncMock(side_effect=_fanout_request))

        specs = await generator.generate(
            MagicMock(),
            limit=2,
            snapshot={'date': '2026-03-08'},
            research_task={'task_id': 'task_evt', 'target_symbols': ['688981']},
        )
        report = generator.get_last_report()
        expected_requests = max(1, min(int(LLM_FAN_OUT_COUNT or 1), 4))

        assert len(specs) == 2
        assert {spec.strategy_type for spec in specs} == {'momentum', 'rsi'}
        assert generator._run_external_provider_request.await_count == expected_requests
        assert len(report['external_provider']['requests']) == expected_requests
        assert report['external_provider']['viable_selected_count'] == 2
        assert report['external_provider']['status'] == 'succeeded'

    @pytest.mark.asyncio
    async def test_build_research_context_includes_factor_research_artifact(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        db = MagicMock()
        db.list_stock_universe = AsyncMock(return_value=[])
        db.count_stock_universe = AsyncMock(return_value=0)
        db.get_klines = AsyncMock(return_value=[])

        context = await generator._build_research_context(
            db,
            {
                'date': '2026-03-08',
                'fg_level': 'greed',
                'fear_greed_index': 63,
                'factor_research': {
                    'active_factors': ['value', 'quality'],
                    'summary': {'top_factor_names': ['value', 'quality']},
                    'preferred_strategy_types': ['value_factor', 'quality_factor'],
                    'degraded': False,
                },
            },
            research_task={'task_id': 'task_factor_ctx'},
        )

        assert context['market_regime']['factor_research']['active_factors'] == ['value', 'quality']
        assert context['selection_framework']['factor_names'] == ['value', 'quality']

    @pytest.mark.asyncio
    async def test_build_research_context_reuses_shared_cache_when_available(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        generator = LLMProxyStrategyGenerator()
        generator._load_universe_rows = AsyncMock(side_effect=AssertionError("shared cache should avoid reloading universe"))
        db = MagicMock()

        context = await generator._build_research_context(
            db,
            {
                'date': '2026-03-08',
                'fg_level': 'greed',
                'fear_greed_index': 63,
                'factor_research': {
                    'active_factors': ['value', 'quality'],
                    'summary': {'top_factor_names': ['value', 'quality']},
                    'preferred_strategy_types': ['value_factor', 'quality_factor'],
                    'degraded': False,
                },
                '_shared_generation_context': {
                    'research_context': {
                        'symbol_insights': [
                            {'code': '600519', 'trend_state': 'uptrend', 'return_20d': 0.12, 'return_5d': 0.03, 'volatility_20d': 0.02, 'industry': '白酒', 'market': 'SH'},
                        ],
                        'candidate_universe': [
                            {'code': '600519', 'trend_state': 'uptrend', 'return_20d': 0.12, 'return_5d': 0.03, 'volatility_20d': 0.02, 'industry': '白酒', 'market': 'SH'},
                        ],
                        'universe_scan': {'total_stock_count': 1, 'scanned_stock_count': 1, 'data_ready_count': 1, 'coverage_ratio': 1.0},
                        'analysis_scope': {'scan_limit': 1},
                    },
                },
            },
            research_task={'task_id': 'task_cache_ctx'},
        )

        assert context['universe_scan']['cache_reused'] is True
        assert context['symbol_insights'][0]['code'] == '600519'

    @pytest.mark.asyncio
    async def test_generate_event_task_local_fallback_prioritizes_breakout_categories(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMRequestError

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '601398'}],
                'symbol_insights': [{'code': '601398'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError('timeout', metrics={'last_error_type': 'ReadTimeout', 'last_error': 'ReadTimeout'})

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context

        specs = await generator.generate(
            MagicMock(),
            limit=2,
            snapshot={'date': '2026-03-08'},
            research_task={
                'task_id': 'task_evt',
                'task_source': 'event_driven',
                'opportunity_type': 'sector_breakout',
                'target_symbols': ['601398', '601288'],
                'event_id': 'evt_bank',
                'theme_code': 'high_dividend_banks',
                'strategy_preferences': ['quality_factor', 'value_factor', 'ma_cross'],
            },
        )

        assert len(specs) == 1
        assert specs[0].strategy_type in {'momentum', 'ma_cross'}
        assert all(spec.strategy_type != 'quality_factor' for spec in specs)
        candidate = specs[0].to_candidate('strategy_factory:sector_breakout', 'exp_evt_local_fallback')
        assert candidate['generation_reason']['source'] == 'event_driven_local_fallback'
        assert candidate['research_task']['task_id'] == 'task_evt'
        assert candidate['event_context']['event_id'] == 'evt_bank'

    def test_local_fallback_varies_params_by_research_task(self):
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator

        candidate = {
            'name': 'Momentum_20_60_Spread',
            'description': '中期与短期动量差，捕捉趋势加速。',
            'formula': '(close.pct_change(60) - close.pct_change(20))',
            'category': 'momentum',
            'rationale': '趋势行情中更稳健地识别加速段。',
            'engine': 'local_rule_v1',
        }

        spec_a = LLMProxyStrategyGenerator._local_candidate_to_spec(candidate, research_task={'task_id': 'task_breakout', 'opportunity_type': 'sector_breakout', 'target_symbols': ['688981', '002371']})
        spec_b = LLMProxyStrategyGenerator._local_candidate_to_spec(candidate, research_task={'task_id': 'task_rotation', 'opportunity_type': 'rotation_balanced', 'target_symbols': ['600519', '000858']})

        assert spec_a is not None
        assert spec_b is not None
        assert spec_a.params != spec_b.params
        assert spec_a.metadata['fallback_profile']['task_opportunity_type'] == 'sector_breakout'
        assert spec_b.metadata['fallback_profile']['task_opportunity_type'] == 'rotation_balanced'

    @pytest.mark.asyncio
    async def test_generate_marks_non_executable_when_external_candidates_do_not_compile(self):
        import pandas as pd
        from akshare_mcp.services.strategy_autonomy import LLMProxyStrategyGenerator
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig

        generator = LLMProxyStrategyGenerator()
        sample_frame = pd.DataFrame({
            'open': [10 + i * 0.03 for i in range(140)],
            'high': [10.1 + i * 0.03 for i in range(140)],
            'low': [9.9 + i * 0.03 for i in range(140)],
            'close': [10 + i * 0.03 for i in range(140)],
            'volume': [1000 + (i % 8) * 90 for i in range(140)],
        })

        async def _frame(_db, research_task=None):
            return sample_frame

        async def _recent(_db, parent_strategies=None):
            return []

        async def _context(_db, _snapshot, parent_strategies=None, history_summary=None, research_task=None):
            return {
                'candidate_universe': [{'code': '688981'}],
                'symbol_insights': [{'code': '688981'}],
                'analysis_scope': {'scan_mode': 'test'},
                'population_state': {'listed_count': 1, 'incubating_count': 0, 'top_categories': {}},
            }

        class _Provider:
            def __init__(self):
                self.config = StrategyLLMConfig(enabled=True, provider='openai_compatible', base_url='https://example.com/v1', api_key='k', model='m')

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                return {
                    'provider': 'openai_compatible',
                    'model': 'm',
                    'analysis': {'selection_notes': ['test']},
                    'research_context': _kwargs.get('research_context') or {},
                    'research_task': _kwargs.get('research_task') or {},
                    'request_metrics': {'status': 'succeeded', 'elapsed_seconds': 0.1},
                    'candidates': [{'name': 'bad_blueprint', 'dsl': {'entry': {'all': []}, 'exit': {'any': []}}}],
                }

        generator.external_provider = _Provider()
        generator._build_market_frame = _frame
        generator._recent_experiments = _recent
        generator._build_research_context = _context
        generator._build_external_candidate_spec = lambda *args, **kwargs: None

        specs = await generator.generate(MagicMock(), limit=1, snapshot={'date': '2026-03-08'}, research_task={'target_symbols': ['688981'], 'task_id': 'task_non_exec'})
        report = generator.get_last_report()

        assert len(specs) == 1
        assert report['external_provider']['status'] == 'non_executable'
        assert report['external_provider']['last_error_type'] == 'NoExecutableCandidates'
        assert report['external_provider']['requests'][0]['status'] == 'succeeded'
        assert report['external_provider']['requests'][0]['compiled_candidate_count'] == 0
        assert report['external_provider']['requests'][0]['non_executable_candidate_count'] == 1

    @pytest.mark.asyncio
    async def test_bandit_optimizer_accepts_stringified_parent_params(self):
        from akshare_mcp.services.strategy_autonomy import BanditParameterOptimizer

        optimizer = BanditParameterOptimizer()
        db = MagicMock()
        db.get_strategy_metrics = AsyncMock(return_value=[])
        db.get_signal_stats = AsyncMock(return_value={'total_signals': 12, 'hit_rate': {'5': 0.56}})
        db.list_strategy_generation_experiments = AsyncMock(return_value=[])

        specs = await optimizer.evolve(db, {
            'id': 'parent_1',
            'name': 'parent',
            'strategy_type': 'momentum',
            'params': '{"lookback": 20, "threshold": 0.02}',
        }, limit=1)

        assert len(specs) == 1
        assert specs[0].strategy_type == 'momentum'
        assert isinstance(specs[0].params, dict)
        assert 'lookback' in specs[0].params

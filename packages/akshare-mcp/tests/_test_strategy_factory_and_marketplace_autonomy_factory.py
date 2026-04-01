from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestAutonomyEnhancementsFactoryMixin:
    async def test_run_cycle_uses_external_llm_dsl_blueprint(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService

        captured = {}

        class _FakeProvider:
            class config:
                strict = True
                provider = 'openai_compatible'
                model = 'test-model'

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                captured['research_context'] = _kwargs.get('research_context')
                return {
                    'provider': 'openai_compatible',
                    'model': 'test-model',
                    'prompt': {'system': 's', 'user': 'u'},
                    'analysis': {
                        'market_regime': 'neutral_to_up',
                        'style_bias': 'trend',
                        'hypothesis': '顺势回踩后放量确认',
                        'evidence': ['trend_up_count>0'],
                        'risk_focus': ['avoid_chasing'],
                        'selection_notes': ['prefer_pullback_entry'],
                        'universe_view': 'candidate_universe 中消费与新能源趋势较强',
                        'selection_plan': ['优先 trend_state=uptrend', '再筛 volume_ratio_20>1.0'],
                        'trade_plan': ['回踩确认买入', '跌破中期均线退出'],
                    },
                    'research_context': _kwargs.get('research_context') or {},
                    'content': '{"analysis": {...}, "candidates": [...] }',
                    'candidates': [{
                        'name': '外部 AI 趋势策略',
                        'description': '外部模型生成的 DSL 规则。',
                        'rationale': '使用短中期均线趋势与量能确认。',
                        'tags': ['swing'],
                        'target_symbols': ['600519', '000858', '300750'],
                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['600519', '000858', '300750']},
                        'selection_logic': ['消费龙头与新能源龙头共振', '保留量能确认的强趋势股'],
                        'dsl': {
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
                                        'left': {'indicator': 'volume_ratio', 'window': 10},
                                        'right': {'value': 1.05},
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
                                ],
                            },
                            'risk_rules': {'stop_loss': 0.06, 'take_profit': 0.15},
                            'metadata': {'target_symbols': ['600519', '000858', '300750']},
                        },
                    }],
                }

        service = StrategyAutonomyService()
        db = _StrategyDB()
        service.rule_generator.generate = lambda *_args, **_kwargs: []
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.llm_generator.external_provider = _FakeProvider()
        monkeypatch.setattr('akshare_mcp.services.strategy_generators.PIPELINE_MODE', 'monolithic')

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test_external',
        )
        experiments = await db.list_strategy_generation_experiments(limit=10)

        assert result['generated_count'] == 1
        assert captured['research_context']['symbol_insights']
        assert captured['research_context']['candidate_universe']
        assert result['llm_generation']['research_context_summary']['symbol_count'] >= 1
        assert result['llm_generation']['research_context_summary']['candidate_universe_count'] >= 1
        assert result['llm_generation']['external_provider']['analysis']['style_bias'] == 'trend'
        assert result['candidates'][0]['strategy_type'] == 'dsl_rule'
        assert result['candidates'][0]['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['generator_type'] == 'external_llm'
        assert experiments[0]['strategy_spec']['params']['dsl']['entry']
        assert experiments[0]['strategy_spec']['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['evaluation']['llm_analysis']['style_bias'] == 'trend'
        assert experiments[0]['evaluation']['target_symbols'] == ['600519', '000858', '300750']
        assert experiments[0]['evaluation']['llm_response']['provider'] == 'openai_compatible'
        assert result['llm_generation']['external_provider']['status'] in {'succeeded', 'fallback_only'}

    @pytest.mark.asyncio
    async def test_run_cycle_records_external_llm_failure_metrics(self, monkeypatch):
        from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMRequestError

        class _FailProvider:
            class config:
                strict = False
                provider = 'openai_compatible'
                model = 'test-model'

            def is_enabled(self):
                return True

            async def generate_candidates(self, **_kwargs):
                raise StrategyLLMRequestError(
                    'external llm timeout',
                    metrics={
                        'status': 'failed',
                        'attempt_count': 2,
                        'elapsed_seconds': 18.5,
                        'last_error_type': 'ReadTimeout',
                        'last_error': 'timeout',
                        'attempts': [
                            {'attempt': 1, 'status': 'failed', 'error_type': 'ReadTimeout'},
                            {'attempt': 2, 'status': 'failed', 'error_type': 'ReadTimeout'},
                        ],
                    },
                )

        service = StrategyAutonomyService()
        db = _StrategyDB()
        service.rule_generator.generate = lambda *_args, **_kwargs: []
        service.optimizer.evolve = AsyncMock(return_value=[])
        service.llm_generator.external_provider = _FailProvider()
        monkeypatch.setattr('akshare_mcp.services.strategy_generators.PIPELINE_MODE', 'monolithic')

        result = await service.run_cycle(
            db,
            snapshot={'date': '2026-03-08', 'fear_greed_index': 58},
            limit=1,
            source='test_external_failure',
        )

        assert result['generated_count'] >= 1
        assert result['llm_generation']['external_provider']['status'] == 'failed'
        assert result['llm_generation']['external_provider']['last_error_type'] == 'ReadTimeout'
        assert result['llm_generation']['external_provider']['requests'][0]['request_metrics']['attempt_count'] == 2

    @pytest.mark.asyncio
    async def test_task_runs_can_filter_by_strategy_id(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)
        await db.save_strategy_task_run({'strategy_id': 'sid_keep', 'task_name': 'strategy_ai_cycle', 'task_scope': 'manual', 'status': 'completed'})
        await db.save_strategy_task_run({'strategy_id': 'sid_other', 'task_name': 'strategy_ai_cycle', 'task_scope': 'manual', 'status': 'completed'})

        result = await mcp.strategy_manager(action='task_runs', kwargs=json.dumps({'strategy_id': 'sid_keep'}))

        assert result['success'] is True
        assert result['data']['count'] == 1
        assert result['data']['items'][0]['strategy_id'] == 'sid_keep'

from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class _TestAutonomyEnhancementsLlmMixin:
    async def test_strategy_llm_provider_accepts_candidate_only_minimal_response(self):
        import pandas as pd
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'candidates': [
                                    {
                                        'name': 'candidate_ok',
                                        'target_symbols': ['688981'],
                                        'stock_pool': {'selection_mode': 'explicit', 'symbols': ['688981']},
                                        'dsl': {
                                            'version': '1.0',
                                            'timeframe': 'daily',
                                            'entry': {'any': [{'op': 'cross_above', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                            'exit': {'any': [{'op': 'cross_below', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        },
                                        'tags': ['external_llm'],
                                    },
                                    {
                                        'name': 'candidate_bad',
                                        'target_symbols': ['688981'],
                                        'dsl': 'not_a_dict',
                                    },
                                ],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                assert user_payload.get('prompt_profile') == 'minimal'
                assert user_payload.get('output_contract', {}).get('required') == ['candidates']
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
                initial_compact_level=2,
            ))
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}, 'candidate_universe': [{'code': '688981'}]},
                research_task={'task_id': 't1', 'target_symbols': ['688981']},
                limit=2,
            )

        assert result['analysis'] == {}
        assert len(result['candidates']) == 1
        assert result['candidates'][0]['target_symbols'] == ['688981']
        assert result['candidates'][0]['dsl']['metadata']['target_symbols'] == ['688981']
        assert result['request_metrics']['raw_candidate_count'] == 2
        assert result['request_metrics']['returned_candidate_count'] == 1
        assert result['request_metrics']['analysis_present'] is False

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_retries_after_timeout(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        calls = {'count': 0, 'prompt_chars': [], 'timeout_reads': [], 'max_tokens': []}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {
                                    'market_regime': 'trend_up',
                                    'style_bias': 'momentum',
                                    'hypothesis': '顺势回踩',
                                    'evidence': ['close_above_sma20'],
                                    'risk_focus': ['watch_drawdown'],
                                    'selection_notes': ['prefer_medium_frequency'],
                                },
                                'candidates': [{
                                    'name': 'retry_candidate',
                                    'dsl': {
                                        'version': '1.0',
                                        'timeframe': 'daily',
                                        'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                    },
                                }],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                calls['count'] += 1
                calls['prompt_chars'].append(len(kwargs['json']['messages'][1]['content']))
                calls['timeout_reads'].append(float(kwargs['timeout'].read))
                calls['max_tokens'].append(int(kwargs['json'].get('max_tokens') or 0))
                if calls['count'] == 1:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
            ))
            result = await provider.generate_candidates(
                snapshot={
                    'date': '2026-03-08',
                    'fear_greed_index': 61,
                    'hot_sectors': ['AI', '芯片', '机器人', '算力'],
                    'cold_sectors': ['银行', '煤炭', '地产'],
                    'category_counts': {'momentum': 5, 'value': 3, 'quality': 2},
                    'completeness': {'completion_ratio': 0.86, 'missing_sources': ['north_fund', 'margin']},
                    'failure_reasons': [{'source': 'north_fund', 'reason': 'timeout'}],
                },
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={
                    'market_regime': {'fg_level': 'greed', 'fear_greed_index': 61},
                    'market_breadth': {'symbol_count': 4, 'trend_up_count': 3, 'trend_down_count': 1},
                    'symbol_insights': [{'code': '000300', 'return_20d': 0.05, 'trend_state': 'uptrend'}],
                    'population_state': {'listed_count': 12, 'incubating_count': 3, 'top_categories': {'momentum': 5}},
                },
                parent_strategies=[{'id': 'p1', 'name': 'parent', 'strategy_type': 'momentum', 'status': 'listed', 'tags': ['trend', 'swing']}],
                history_summary=[{'parent_strategy_id': 'p1', 'generator_type': 'external_llm', 'status': 'rejected', 'decision': 'retry', 'final_score': 0.42}],
                limit=3,
            )

        assert calls['count'] == 2
        assert calls['prompt_chars'][1] <= calls['prompt_chars'][0]
        assert calls['timeout_reads'][0] <= calls['timeout_reads'][1]
        assert calls['max_tokens'][1] <= calls['max_tokens'][0]
        assert result['analysis']['market_regime'] == 'trend_up'
        assert result['research_context']['market_regime']['fg_level'] is not None
        assert result['candidates'][0]['name'] == 'retry_candidate'
        assert result['request_metrics']['attempt_count'] == 2
        assert result['request_metrics']['analysis_present'] is True
        assert result['request_metrics']['attempts'][0]['error_type'] == 'ReadTimeout'
        assert result['request_metrics']['attempts'][1]['prompt_profile'] == 'minimal'

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_starts_minimal_after_recent_timeout_failure(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider, StrategyLLMRequestError

        calls = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {'market_regime': 'trend_up'},
                                'candidates': [{
                                    'name': 'minimal_candidate',
                                    'dsl': {
                                        'version': '1.0',
                                        'timeframe': 'daily',
                                        'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                        'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]},
                                    },
                                }],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                calls.append({
                    'prompt_profile': user_payload.get('prompt_profile'),
                    'max_tokens': int(kwargs['json'].get('max_tokens') or 0),
                    'timeout_read': float(kwargs['timeout'].read),
                })
                if len(calls) == 1:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=0,
                retry_backoff_sec=0,
                recent_timeout_minimal_streak=1,
                recent_timeout_cooldown_sec=600,
            ))
            with pytest.raises(StrategyLLMRequestError):
                await provider.generate_candidates(
                    snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                    market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                    research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                    limit=2,
                )
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                limit=2,
            )

        assert calls[0]['prompt_profile'] == 'normal'
        assert calls[1]['prompt_profile'] == 'minimal'
        assert calls[1]['max_tokens'] <= calls[0]['max_tokens']
        assert calls[1]['timeout_read'] >= calls[0]['timeout_read']
        assert result['request_metrics']['prompt_profile'] == 'minimal'
        assert result['request_metrics']['initial_prompt_profile'] == 'minimal'
        assert result['request_metrics']['degrade_reason'] == 'recent_timeout'

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_recent_timeout_uses_single_minimal_attempt(self):
        import pandas as pd
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider, StrategyLLMRequestError

        calls = []

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'analysis': {'market_regime': 'trend_up'},
                                'candidates': [{'name': 'minimal_candidate', 'dsl': {'version': '1.0', 'timeframe': 'daily', 'entry': {'any': [{'op': 'gt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]}, 'exit': {'any': [{'op': 'lt', 'left': {'field': 'close'}, 'right': {'indicator': 'sma', 'field': 'close', 'window': 10}}]}}}],
                            })
                        }
                    }]
                }

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                user_payload = json.loads(kwargs['json']['messages'][1]['content'])
                calls.append(user_payload.get('prompt_profile'))
                if len(calls) <= 2:
                    raise httpx.ReadTimeout('timeout')
                return _Resp()

        with patch('akshare_mcp.services.strategy_llm_provider.httpx.AsyncClient', _Client):
            provider = StrategyLLMProvider(StrategyLLMConfig(
                enabled=True,
                provider='openai_compatible',
                base_url='https://example.com/v1',
                api_key='k',
                model='m',
                retry_count=1,
                retry_backoff_sec=0,
                recent_timeout_minimal_streak=1,
                recent_timeout_cooldown_sec=600,
            ))
            with pytest.raises(StrategyLLMRequestError):
                await provider.generate_candidates(
                    snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                    market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                    research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                    limit=2,
                )
            result = await provider.generate_candidates(
                snapshot={'date': '2026-03-09', 'fear_greed_index': 50},
                market_frame=pd.DataFrame({'close': [1, 1.1, 1.2], 'volume': [100, 120, 110]}),
                research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 50}},
                limit=2,
            )

        assert calls == ['normal', 'minimal', 'minimal']
        assert result['request_metrics']['attempt_count'] == 1
        assert len(result['request_metrics']['attempts']) == 1
        assert result['request_metrics']['initial_prompt_profile'] == 'minimal'

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_call_stage_retries_after_502(self):
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider

        request = httpx.Request('POST', 'https://example.com/v1/chat/completions')
        first_response = httpx.Response(502, request=request, headers={'Retry-After': '0'})
        calls = {'count': 0}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [{
                        'message': {
                            'content': json.dumps({
                                'events': [{'event_type': 'policy_shift', 'description': '政策边际转暖'}]
                            })
                        }
                    }]
                }

        async def _post(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                raise httpx.HTTPStatusError('bad gateway', request=request, response=first_response)
            return _Resp()

        provider = StrategyLLMProvider(StrategyLLMConfig(
            enabled=True,
            provider='openai_compatible',
            base_url='https://example.com/v1',
            api_key='k',
            model='m',
            stage_retry_count=1,
            stage_retry_backoff_sec=0,
        ))
        provider._client.post = AsyncMock(side_effect=_post)

        with patch('akshare_mcp.services._strategy_llm_provider_runtime.asyncio.sleep', new=AsyncMock()) as sleep_mock:
            result = await provider.call_stage(
                stage_id='event_recognition',
                input_data={'market_snapshot': {'date': '2026-03-09'}},
                system_prompt='Return JSON only.',
                timeout_sec=5,
            )

        assert calls['count'] == 2
        assert result['events'][0]['event_type'] == 'policy_shift'
        sleep_mock.assert_awaited()
        await provider.close()

    @pytest.mark.asyncio
    async def test_strategy_llm_provider_call_stage_enters_overload_cooldown_after_429(self):
        import time
        import httpx
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider, StrategyLLMRequestError

        request = httpx.Request('POST', 'https://example.com/v1/chat/completions')
        response = httpx.Response(429, request=request, headers={'Retry-After': '0'})
        provider = StrategyLLMProvider(StrategyLLMConfig(
            enabled=True,
            provider='openai_compatible',
            base_url='https://example.com/v1',
            api_key='k',
            model='m',
            stage_retry_count=0,
            recent_overload_minimal_streak=1,
            recent_overload_cooldown_sec=30,
        ))
        provider._client.post = AsyncMock(side_effect=httpx.HTTPStatusError('rate limited', request=request, response=response))

        with pytest.raises(StrategyLLMRequestError) as excinfo:
            await provider.call_stage(
                stage_id='event_recognition',
                input_data={'market_snapshot': {'date': '2026-03-09'}},
                system_prompt='Return JSON only.',
                timeout_sec=5,
            )

        assert excinfo.value.metrics['last_error_type'] == 'HTTP429'
        assert provider._recent_overload_streak == 1
        assert provider._recent_overload_cooldown_until > time.monotonic()

        provider._client.post = AsyncMock(side_effect=AssertionError('cooldown should skip network request'))
        with pytest.raises(StrategyLLMRequestError) as cooldown_exc:
            await provider.call_stage(
                stage_id='event_recognition',
                input_data={'market_snapshot': {'date': '2026-03-09'}},
                system_prompt='Return JSON only.',
                timeout_sec=5,
            )

        assert cooldown_exc.value.metrics['status'] == 'cooldown_skip'
        assert cooldown_exc.value.metrics['last_error_type'] == 'RecentOverloadCooldown'
        assert cooldown_exc.value.metrics['cooldown_reason'] == 'recent_overload'
        provider._client.post.assert_not_awaited()
        await provider.close()

    def test_strategy_llm_provider_build_prompt_includes_event_driven_research_task(self):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider

        _system_prompt, user_prompt = StrategyLLMProvider._build_prompt(
            snapshot={'date': '2026-03-09', 'fear_greed_index': 57, 'fg_level': 'neutral'},
            market_summary={'rows': 10, 'close': {'latest': 101.2}},
            research_context={'market_regime': {'fg_level': 'neutral', 'fear_greed_index': 57}},
            parent_strategies=[],
            history_summary=[],
            limit=2,
            research_task={
                'task_id': 'task_evt_oil',
                'task_source': 'event_driven',
                'event_id': 'evt_oil_1',
                'event_type': 'geopolitics',
                'theme': 'event_theme_upstream_oil_gas',
                'theme_code': 'upstream_oil_gas',
                'direction': 'positive',
                'horizon': 'swing_5_20d',
                'opportunity_type': 'sector_breakout',
                'target_symbols': ['601857', '600938'],
                'evidence_bundle': {
                    'event_summary': '中东战事升级抬升原油供给风险。',
                    'theme_name': '上游油气',
                    'direction': 'positive',
                    'signal_count': 2,
                    'score_summary': {'avg_final_score': 0.87, 'top_symbols': ['601857', '600938']},
                    'supporting_reasons': ['油价中枢抬升', '供给扰动强化'],
                },
            },
            compact_level=0,
        )

        user_payload = json.loads(user_prompt)
        compact_task = user_payload['research_task']

        assert compact_task['event_id'] == 'evt_oil_1'
        assert compact_task['theme_code'] == 'upstream_oil_gas'
        assert compact_task['direction'] == 'positive'
        assert compact_task['task_source'] == 'event_driven'
        assert compact_task['evidence_summary']['event_summary'].startswith('中东战事升级')
        assert compact_task['evidence_summary']['top_symbols'] == ['601857', '600938']


        @classmethod
        def _reuse_shared_research_context(
            cls,
            shared_context: dict[str, Any],
            *,
            snapshot: dict[str, Any],
            parent_strategies: Optional[list[dict]] = None,
            history_summary: Optional[list[dict]] = None,
            research_task: Optional[dict[str, Any]] = None,
        ) -> Optional[dict[str, Any]]:
            if not shared_context:
                return None
            research_task = _normalize_research_task_contract(research_task or {})
            task_target_symbols = cls._normalize_code_list(research_task.get('target_symbols'))
            task_focus_industries = [str(item).strip() for item in list(research_task.get('focus_industries') or []) if str(item).strip()]
            task_focus_markets = [str(item).strip() for item in list(research_task.get('focus_markets') or []) if str(item).strip()]
            target_symbol_set = set(task_target_symbols)
            task_focus_market_set = set(task_focus_markets)
            symbol_insights = [dict(item or {}) for item in list(shared_context.get('symbol_insights') or [])]
            candidate_universe = [dict(item or {}) for item in list(shared_context.get('candidate_universe') or [])]
            market_background_context = cls._build_market_background_context(
                symbol_insights=symbol_insights,
                candidate_universe=candidate_universe,
                universe_scan=shared_context.get('universe_scan'),
                cache_reused=True,
            )

            def _matches(item: dict[str, Any]) -> bool:
                if not item:
                    return False
                code = str(item.get('code') or '').strip()
                industry_text = str(item.get('industry') or item.get('sector') or '')
                market = str(item.get('market') or '').strip()
                if target_symbol_set and code not in target_symbol_set:
                    return False
                if task_focus_industries and not any(keyword in industry_text for keyword in task_focus_industries):
                    return False
                if task_focus_market_set and market not in task_focus_market_set:
                    return False
                return True

            has_filters = bool(task_target_symbols or task_focus_industries or task_focus_markets)
            if has_filters:
                filtered_symbols = [item for item in symbol_insights if _matches(item)]
                filtered_candidates = [item for item in candidate_universe if _matches(item)]
                if task_target_symbols and not filtered_symbols and not filtered_candidates:
                    return cls._build_blocked_research_context(
                        snapshot=snapshot,
                        research_task=research_task,
                        parent_strategies=parent_strategies,
                        history_summary=history_summary,
                        universe_total_count=int((shared_context.get('universe_scan') or {}).get('total_stock_count') or 0),
                        top_industries=dict((shared_context.get('universe_scan') or {}).get('top_industries') or {}),
                        market_background_context=market_background_context,
                        cache_reused=True,
                    )
                if task_focus_industries and not filtered_symbols and not filtered_candidates:
                    return None
                if task_target_symbols:
                    symbol_insights = filtered_symbols
                    candidate_universe = filtered_candidates
                else:
                    symbol_insights = filtered_symbols or symbol_insights[: max(1, min(len(symbol_insights), RESEARCH_SYMBOL_DETAIL_LIMIT))]
                    candidate_universe = filtered_candidates or candidate_universe[: max(1, min(len(candidate_universe), RESEARCH_CANDIDATE_POOL_LIMIT))]

            symbol_insights = [dict(item) for item in symbol_insights[:RESEARCH_SYMBOL_DETAIL_LIMIT]]
            candidate_universe = [dict(item) for item in candidate_universe[:RESEARCH_CANDIDATE_POOL_LIMIT]]
            trend_up_count = len([item for item in symbol_insights if item.get('trend_state') == 'uptrend'])
            trend_down_count = len([item for item in symbol_insights if item.get('trend_state') == 'downtrend'])
            avg_return_20d = round(sum(cls._safe_float(item.get('return_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
            avg_volatility_20d = round(sum(cls._safe_float(item.get('volatility_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
            market_regime = {
                'fg_level': snapshot.get('fg_level'),
                'fear_greed_index': snapshot.get('fear_greed_index'),
                'hot_sectors': list(snapshot.get('hot_sectors') or [])[:4],
                'cold_sectors': list(snapshot.get('cold_sectors') or [])[:3],
                'factor_ic': dict(snapshot.get('factor_ic') or {}),
                'factor_ic_trend': dict(snapshot.get('factor_ic_trend') or {}),
                'factor_research': dict(snapshot.get('factor_research') or {}),
            }
            universe_scan = dict(shared_context.get('universe_scan') or {})
            universe_scan.update({
                'detail_symbol_count': len(symbol_insights),
                'candidate_universe_count': len(candidate_universe),
                'cache_reused': True,
            })
            target_context_status = (
                'targeted_active'
                if task_target_symbols
                else ('filtered_market_context' if has_filters else 'broad_market_context')
            )
            task_target_context = cls._build_task_target_context(
                research_task=research_task,
                symbol_insights=symbol_insights,
                candidate_universe=candidate_universe,
                status=target_context_status,
            )
            analysis_scope = dict(shared_context.get('analysis_scope') or {})
            if has_filters:
                analysis_scope['scan_mode'] = target_context_status
            return {
                **dict(shared_context or {}),
                'research_task': {
                    'task_id': research_task.get('task_id'),
                    'theme': research_task.get('theme'),
                    'opportunity_type': research_task.get('opportunity_type'),
                    'focus_industries': task_focus_industries,
                    'focus_markets': task_focus_markets,
                    'target_symbols': task_target_symbols,
                    'priority': research_task.get('priority'),
                    'strategy_preferences': list(research_task.get('strategy_preferences') or []),
                    'generation_limit': research_task.get('generation_limit'),
                    'rationale': research_task.get('rationale'),
                    'task_source': research_task.get('task_source'),
                },
                'market_regime': market_regime,
                'market_breadth': {
                    'symbol_count': len(symbol_insights),
                    'trend_up_count': trend_up_count,
                    'trend_down_count': trend_down_count,
                    'avg_return_20d': avg_return_20d,
                    'avg_volatility_20d': avg_volatility_20d,
                },
                'symbol_insights': symbol_insights,
                'candidate_universe': candidate_universe,
                'symbol_insight_codes': list(task_target_context.get('symbol_insight_codes') or []),
                'candidate_universe_symbols': list(task_target_context.get('candidate_universe_symbols') or []),
                'target_context_status': target_context_status,
                'blocked_by_target_universe': False,
                'task_target_context': task_target_context,
                'market_background_context': market_background_context,
                'universe_scan': universe_scan,
                'analysis_scope': analysis_scope,
                'selection_framework': {
                    'technical': ['trend_state', 'return_20d', 'return_5d', 'volume_ratio_20', 'price_vs_sma20'],
                    'fundamental': ['market_cap', 'pe_ratio', 'pb_ratio', 'revenue_growth', 'profit_growth'],
                    'factor_names': [
                        str(key)
                        for key in list(
                            ((snapshot.get('factor_research') or {}).get('summary') or {}).get('top_factor_names')
                            or (snapshot.get('factor_research') or {}).get('active_factors')
                            or list((snapshot.get('factor_ic_trend') or {}).keys())[:3]
                        )[:3]
                    ],
                },
                'parent_context': [
                    {
                        'id': item.get('id'),
                        'name': item.get('name'),
                        'strategy_type': item.get('strategy_type'),
                        'status': item.get('status'),
                    }
                    for item in list(parent_strategies or [])[:3]
                ],
                'experiment_feedback': [
                    {
                        'generator_type': item.get('generator_type'),
                        'status': item.get('status'),
                        'decision': item.get('decision'),
                        'final_score': item.get('final_score'),
                    }
                    for item in list(history_summary or [])[:4]
                ],
            }
